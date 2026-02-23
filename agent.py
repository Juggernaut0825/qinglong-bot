import os, json, re, yaml, httpx, logging
from pathlib import Path
from skills import TOOLS
from executors import execute_tool
from storage import get_recent_messages, get_summary, save_summary, count_messages, get_old_messages

log = logging.getLogger("agent")

_cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
SYSTEM_PROMPT = _cfg["system_prompt"]
SPLIT_MAX = _cfg["split_reply"]["max_chars_per_message"]
MODEL = "google/gemini-3-flash-preview"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
RECENT_WINDOW = 20  # keep last N messages as-is
SUMMARIZE_THRESHOLD = 30  # trigger summarization when total exceeds this


async def chat_completion(messages: list) -> dict:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            API_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"model": MODEL, "messages": messages, "tools": TOOLS},
        )
        data = r.json()
        if "error" in data:
            log.error("OpenRouter error: %s", data["error"])
        return data


def split_reply(text: str) -> list[str]:
    """Split a long reply into multiple short messages for natural chat feel."""
    if len(text) <= SPLIT_MAX:
        return [text]
    parts, buf = [], ""
    for para in text.split("\n\n"):
        if buf and len(buf) + len(para) + 2 > SPLIT_MAX:
            parts.append(buf.strip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text]


async def _summarize_old(chat_id: str):
    """Compress older messages into a summary stored in DB."""
    old = get_old_messages(chat_id, before_last_n=RECENT_WINDOW)
    if not old:
        return
    existing = get_summary(chat_id) or ""
    text = "\n".join(f"{m['role']}: {m['content']}" for m in old)
    prompt = "Compress this conversation history into a concise summary, preserving key facts, user preferences, and decisions:\n\n"
    if existing:
        prompt += f"Previous summary:\n{existing}\n\nNew messages:\n"
    prompt += text

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            API_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]},
        )
        summary = r.json()["choices"][0]["message"]["content"]
    save_summary(chat_id, summary, old[-1]["id"])


def _make_user_content(text: str):
    """Convert text with [image:data:...] or [file:data:...] prefix into multimodal content."""
    # Image
    m = re.match(r"\[image:(data:[^\]]+)\]\s*(.*)", text, re.DOTALL)
    if m:
        return [
            {"type": "image_url", "image_url": {"url": m.group(1)}},
            {"type": "text", "text": m.group(2) or "What's in this image?"},
        ]
    # PDF file — extract base64, send as inline_data for Gemini via OpenRouter
    m = re.match(r"\[file:(data:application/pdf;base64,[^\]]+)\]\s*(.*)", text, re.DOTALL)
    if m:
        return [
            {"type": "file", "file": {"url": m.group(1)}},
            {"type": "text", "text": m.group(2) or "Please analyze this PDF."},
        ]
    return text


def _build_messages(chat_id: str, user_text: str) -> list:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    summary = get_summary(chat_id)
    if summary:
        msgs.append({"role": "system", "content": f"Summary of earlier conversation:\n{summary}"})
    msgs += get_recent_messages(chat_id, RECENT_WINDOW)
    msgs.append({"role": "user", "content": _make_user_content(user_text)})
    return msgs


async def run_agent(chat_id: str, user_text: str) -> list[str]:
    """Run one agent turn with SQLite-backed context window."""
    # auto-summarize if history is getting long
    if count_messages(chat_id) > SUMMARIZE_THRESHOLD:
        await _summarize_old(chat_id)

    messages = _build_messages(chat_id, user_text)

    # tool-call loop (max 5 rounds to avoid infinite loops)
    for _ in range(5):
        resp = await chat_completion(messages)
        choice = resp["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        if not msg.get("tool_calls"):
            return split_reply(msg.get("content", ""))

        # execute each tool call and feed results back
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            result = await execute_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return ["Hmm, I got stuck in a loop 😅 Could you try rephrasing?"]
