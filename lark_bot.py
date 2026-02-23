import asyncio, json, os, logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("lark_bot")

from fastapi import FastAPI, Request
from lark_client import send_lark_message, download_lark_image, download_lark_file
from agent import run_agent
from storage import save_message

app = FastAPI()

# simple dedup: track processed event IDs
_seen: set[str] = set()


def _extract_event_info(data: dict) -> dict:
    """Extract text, chat_id, image_key, file_key, message_id from Lark event."""
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
    file_key = parsed.get("file_key") if msg_type == "file" else None
    file_name = parsed.get("file_name", "") if msg_type == "file" else ""
    log.info("event: type=%s chat=%s text=%r image_key=%s file_key=%s file_name=%s",
             msg_type, chat_id, text[:100] if text else "", image_key, file_key, file_name)
    return {"text": text, "chat_id": chat_id, "image_key": image_key,
            "file_key": file_key, "file_name": file_name, "message_id": message_id}


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
    file_key = info["file_key"]
    file_name = info["file_name"]
    message_id = info["message_id"]

    if not chat_id:
        return {"ok": True}

    # image-only messages have no text — give them a default prompt
    if image_key and not text:
        text = "What's in this image?"
    # file-only messages have no text — give them a default prompt
    if file_key and not text:
        text = f"User uploaded a file: {file_name}. Please analyze it."
    if not text:
        return {"ok": True}

    # run agent in background so we return 200 fast
    asyncio.create_task(_handle(chat_id, text, image_key, file_key, file_name, message_id))
    return {"ok": True}


async def _handle(chat_id, text, image_key=None, file_key=None, file_name="", message_id=None):
    import base64

    # image: download and embed as base64
    if image_key and message_id:
        img_bytes = await download_lark_image(message_id, image_key)
        if img_bytes:
            b64 = base64.b64encode(img_bytes).decode()
            text = f"[image:data:image/png;base64,{b64}] {text}"
        else:
            log.error("Failed to download image, proceeding with text only")

    # file: download and embed as base64 (for PDFs, etc.)
    if file_key and message_id:
        file_bytes, fname = await download_lark_file(message_id, file_key)
        if file_bytes:
            b64 = base64.b64encode(file_bytes).decode()
            ext = (fname or file_name).rsplit(".", 1)[-1].lower() if (fname or file_name) else ""
            if ext == "pdf":
                text = f"[file:data:application/pdf;base64,{b64}] {text}"
            elif ext in ("png", "jpg", "jpeg", "gif", "webp"):
                text = f"[image:data:image/{ext};base64,{b64}] {text}"
            else:
                # for non-image/non-pdf files, decode as text if possible
                try:
                    file_text = file_bytes.decode("utf-8")[:10000]
                    text = f"[file content of {fname or file_name}:\n{file_text}]\n{text}"
                except UnicodeDecodeError:
                    text = f"[Binary file: {fname or file_name}, {len(file_bytes)} bytes] {text}"
        else:
            log.error("Failed to download file %s", file_name)

    save_message(chat_id, "user", text)
    try:
        replies = await run_agent(chat_id, text)
    except Exception as e:
        log.exception("run_agent failed")
        replies = [f"Oops, something went wrong 😥: {e}"]

    for i, part in enumerate(replies):
        await send_lark_message(chat_id, part)
        if i < len(replies) - 1:
            await asyncio.sleep(0.5)

    save_message(chat_id, "assistant", "\n\n".join(replies))
