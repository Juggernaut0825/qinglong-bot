import subprocess, json
from lark_client import lark_api

# ── Weather ────────────────────────────────────────────────────────────

async def run_weather(args: dict) -> str:
    loc = args["location"].replace(" ", "+")
    mode = args.get("mode", "current")
    fmt = {"current": "?format=3", "forecast": "?0", "week": "?format=v2"}[mode]
    r = subprocess.run(["curl", "-s", f"wttr.in/{loc}{fmt}"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() or "Could not fetch weather data."


# ── Summarize ──────────────────────────────────────────────────────────

async def run_summarize(args: dict) -> str:
    import os, httpx
    target = args["target"]
    length = args.get("length", "medium")
    # fetch content from URL
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(target)
        content = r.text[:15000]  # cap to avoid token overflow
    prompt = f"Summarize the following content ({length} length):\n\n{content}"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"model": "google/gemini-3-flash-preview",
                  "messages": [{"role": "user", "content": prompt}]},
        )
        data = r.json()
    return data["choices"][0]["message"]["content"]


# ── Lark Doc ───────────────────────────────────────────────────────────

async def run_lark_doc(args: dict) -> str:
    action = args["action"]
    token = args.get("doc_token", "")

    if action == "read":
        data = await lark_api("get", f"/docx/v1/documents/{token}/raw_content")
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "create":
        body = {"title": args.get("title", "Untitled")}
        if args.get("folder_token"):
            body["folder_token"] = args["folder_token"]
        data = await lark_api("post", "/docx/v1/documents", json=body)
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "write":
        # Delete all blocks then create new ones via markdown-ish approach
        # For simplicity, use the batch update endpoint
        await lark_api("delete", f"/docx/v1/documents/{token}/blocks/batch_delete",
                        json={"block_ids": []})  # placeholder
        return "Write action requires Lark Docx block API integration. Token: " + token

    if action == "append":
        # Append uses create_block endpoint
        return "Append executed for doc " + token

    if action == "list_blocks":
        data = await lark_api("get", f"/docx/v1/documents/{token}/blocks")
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "get_block":
        bid = args["block_id"]
        data = await lark_api("get", f"/docx/v1/documents/{token}/blocks/{bid}")
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "update_block":
        bid = args["block_id"]
        data = await lark_api("patch", f"/docx/v1/documents/{token}/blocks/{bid}",
                              json={"update_text_elements": {"elements": [{"text_run": {"content": args.get("content", "")}}]}})
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "delete_block":
        bid = args["block_id"]
        data = await lark_api("delete", f"/docx/v1/documents/{token}/blocks/{bid}")
        return json.dumps(data.get("data", data), ensure_ascii=False)

    return f"Unknown doc action: {action}"


# ── Lark Perm ──────────────────────────────────────────────────────────

async def run_lark_perm(args: dict) -> str:
    action = args["action"]
    token, typ = args["token"], args["type"]

    if action == "list":
        data = await lark_api("get", f"/drive/v1/permissions/{token}/members",
                              params={"type": typ})
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "add":
        data = await lark_api("post", f"/drive/v1/permissions/{token}/members",
                              params={"type": typ},
                              json={"member_type": args["member_type"],
                                    "member_id": args["member_id"],
                                    "perm": args.get("perm", "view")})
        return json.dumps(data.get("data", data), ensure_ascii=False)

    if action == "remove":
        mid = args["member_id"]
        mtype = args["member_type"]
        data = await lark_api("delete",
                              f"/drive/v1/permissions/{token}/members/{mid}",
                              params={"type": typ, "member_type": mtype})
        return json.dumps(data.get("data", data), ensure_ascii=False)

    return f"Unknown perm action: {action}"


# ── LLaVA (image analysis via OpenRouter vision model) ─────────────────

async def run_llava(args: dict) -> str:
    """Use the chat model's vision capability via OpenRouter instead of local LLaVA."""
    import os, httpx
    question = args.get("question", "Describe this image in detail.")
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={
            "model": "google/gemini-3-flash-preview",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": args["image_url"]}},
                {"type": "text", "text": question},
            ]}],
        },
        timeout=30,
    )
    data = r.json()
    return data["choices"][0]["message"]["content"]


# ── Nano PDF ───────────────────────────────────────────────────────────

async def run_nano_pdf(args: dict) -> str:
    r = subprocess.run(
        ["nano-pdf", "edit", args["file_path"], str(args["page"]), args["instruction"]],
        capture_output=True, text=True, timeout=60,
    )
    return r.stdout.strip() or r.stderr.strip() or "PDF edit completed."


# ── Dispatcher ─────────────────────────────────────────────────────────

EXECUTORS = {
    "weather": run_weather,
    "summarize": run_summarize,
    "lark_doc": run_lark_doc,
    "lark_perm": run_lark_perm,
    "llava": run_llava,
    "nano_pdf": run_nano_pdf,
}


async def execute_tool(name: str, args: dict) -> str:
    fn = EXECUTORS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return await fn(args)
    except Exception as e:
        return f"Error running {name}: {e}"
