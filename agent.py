import os, json, yaml, httpx
from pathlib import Path
from skills import TOOLS
from executors import execute_tool

_cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
SYSTEM_PROMPT = _cfg["system_prompt"]
SPLIT_MAX = _cfg["split_reply"]["max_chars_per_message"]
MODEL = "google/gemini-3-flash-preview"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


async def chat_completion(messages: list) -> dict:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            API_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"model": MODEL, "messages": messages, "tools": TOOLS},
        )
        return r.json()


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


async def run_agent(user_text: str, history: list | None = None) -> list[str]:
    """Run one agent turn. Returns a list of reply strings (split for chat)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history or []
    messages.append({"role": "user", "content": user_text})

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
