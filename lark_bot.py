import asyncio, json, os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from lark_client import send_lark_message, download_lark_image
from agent import run_agent
from storage import save_message

app = FastAPI()

# simple dedup: track processed event IDs
_seen: set[str] = set()


def _extract_event_info(data: dict) -> dict:
    """Extract text, chat_id, image_key, message_id from Lark event."""
    event = data.get("event", {})
    msg = event.get("message", {})
    chat_id = msg.get("chat_id")
    message_id = msg.get("message_id")
    msg_type = msg.get("message_type", "text")
    content = msg.get("content", "{}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}
    text = parsed.get("text", "").strip()
    image_key = parsed.get("image_key") if msg_type == "image" else None
    return {"text": text, "chat_id": chat_id, "image_key": image_key, "message_id": message_id}


@app.post("/lark/webhook")
async def webhook(request: Request):
    data = await request.json()

    # challenge verification
    if "challenge" in data:
        return {"challenge": data["challenge"]}

    # schema v2 event
    header = data.get("header", {})
    event_id = header.get("event_id", "")
    if event_id in _seen:
        return {"ok": True}
    _seen.add(event_id)
    # cap dedup set
    if len(_seen) > 500:
        _seen.clear()

    event_type = header.get("event_type", "")
    if event_type != "im.message.receive_v1":
        return {"ok": True}

    info = _extract_event_info(data)
    chat_id = info["chat_id"]
    text = info["text"]
    image_key = info["image_key"]
    message_id = info["message_id"]

    if not chat_id:
        return {"ok": True}

    # image-only messages have no text — give them a default prompt
    if image_key and not text:
        text = "What's in this image?"
    if not text:
        return {"ok": True}

    # run agent in background so we return 200 fast
    asyncio.create_task(_handle(chat_id, text, image_key, message_id))
    return {"ok": True}


async def _handle(chat_id: str, text: str, image_key: str | None = None, message_id: str | None = None):
    # if user sent an image, download it and convert to base64 data URI
    if image_key and message_id:
        import base64
        img_bytes = await download_lark_image(message_id, image_key)
        b64 = base64.b64encode(img_bytes).decode()
        text = f"[image:data:image/png;base64,{b64}] {text}"

    save_message(chat_id, "user", text)
    try:
        replies = await run_agent(chat_id, text)
    except Exception as e:
        replies = [f"Oops, something went wrong 😥: {e}"]

    # send replies as separate messages for natural feel
    for i, part in enumerate(replies):
        await send_lark_message(chat_id, part)
        if i < len(replies) - 1:
            await asyncio.sleep(0.5)

    # store assistant reply
    save_message(chat_id, "assistant", "\n\n".join(replies))
