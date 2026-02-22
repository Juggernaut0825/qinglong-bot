import asyncio, json, os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from lark_client import send_lark_message
from agent import run_agent

app = FastAPI()

# simple dedup: track processed event IDs
_seen: set[str] = set()
# per-chat conversation history (in-memory)
_history: dict[str, list] = {}
MAX_HISTORY = 20


def _extract_text_and_chat(data: dict) -> tuple[str | None, str | None, str | None]:
    """Extract user text, chat_id, and image_key from Lark event."""
    event = data.get("event", {})
    msg = event.get("message", {})
    chat_id = msg.get("chat_id")
    # text message
    content = msg.get("content", "{}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}
    text = parsed.get("text", "").strip()
    image_key = parsed.get("image_key")
    return text, chat_id, image_key


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

    text, chat_id, image_key = _extract_text_and_chat(data)
    if not chat_id or not text:
        return {"ok": True}

    # handle image: prepend image context
    if image_key:
        text = f"[User sent an image: image_key={image_key}] {text}"

    # run agent in background so we return 200 fast
    asyncio.create_task(_handle(chat_id, text))
    return {"ok": True}


async def _handle(chat_id: str, text: str):
    history = _history.setdefault(chat_id, [])
    try:
        replies = await run_agent(text, history)
    except Exception as e:
        replies = [f"Oops, something went wrong 😥: {e}"]

    # update history
    history.append({"role": "user", "content": text})

    # send replies as separate messages for natural feel
    for i, part in enumerate(replies):
        await send_lark_message(chat_id, part)
        if i < len(replies) - 1:
            await asyncio.sleep(0.5)

    # store assistant reply in history
    history.append({"role": "assistant", "content": "\n\n".join(replies)})

    # trim history
    if len(history) > MAX_HISTORY:
        _history[chat_id] = history[-MAX_HISTORY:]
