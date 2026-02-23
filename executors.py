import subprocess, json, logging, httpx as _httpx
from lark_client import lark_api

log = logging.getLogger("executors")

# ── Weather ────────────────────────────────────────────────────────────

async def run_weather(args: dict) -> str:
    loc = args["location"].replace(" ", "+")
    mode = args.get("mode", "current")
    fmt = {"current": "?format=3", "forecast": "?0", "week": "?format=v2"}[mode]
    async with _httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://wttr.in/{loc}{fmt}", headers={"User-Agent": "curl"})
        return r.text.strip() or "Could not fetch weather data."


# ── Summarize ──────────────────────────────────────────────────────────

async def run_summarize(args: dict) -> str:
    import os, re, httpx
    target = args["target"]
    length = args.get("length", "medium")

    # YouTube: use youtube-transcript-api with language fallback
    yt_match = re.search(r"(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})", target)
    if yt_match:
        vid = yt_match.group(1)
        content = None
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            ytt = YouTubeTranscriptApi()
            transcript = ytt.fetch(vid)
            content = " ".join(s.text for s in transcript.snippets)[:15000]
        except Exception as e:
            log.warning("youtube-transcript-api failed for %s: %s", vid, e)
        if not content:
            # fallback: fetch page and ask LLM to work with whatever we get
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                    r = await c.get(f"https://www.youtube.com/watch?v={vid}")
                    content = f"[YouTube page HTML excerpt for video {vid}]:\n{r.text[:8000]}"
            except Exception as e2:
                content = f"[Could not access YouTube video {vid}. Transcript unavailable: {e2}]"
    else:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(target)
            content = r.text[:15000]

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
        # get document block ID (root block), then delete children and re-create
        doc_info = await lark_api("get", f"/docx/v1/documents/{token}")
        doc_block_id = doc_info.get("data", {}).get("document", {}).get("document_id", token)
        # list existing blocks to delete
        blocks = await lark_api("get", f"/docx/v1/documents/{token}/blocks/{doc_block_id}/children")
        child_ids = [b["block_id"] for b in blocks.get("data", {}).get("items", []) if b.get("block_id")]
        if child_ids:
            await lark_api("delete", f"/docx/v1/documents/{token}/blocks/{doc_block_id}/children/batch_delete",
                           json={"start_index": 0, "end_index": len(child_ids)})
        # create new text block with content
        content_text = args.get("content", "")
        await lark_api("post", f"/docx/v1/documents/{token}/blocks/{doc_block_id}/children",
                       json={"children": [{"block_type": 2, "text": {"elements": [{"text_run": {"content": content_text}}]}}],
                             "index": 0})
        return f"Document {token} updated."

    if action == "append":
        doc_info = await lark_api("get", f"/docx/v1/documents/{token}")
        doc_block_id = doc_info.get("data", {}).get("document", {}).get("document_id", token)
        content_text = args.get("content", "")
        await lark_api("post", f"/docx/v1/documents/{token}/blocks/{doc_block_id}/children",
                       json={"children": [{"block_type": 2, "text": {"elements": [{"text_run": {"content": content_text}}]}}],
                             "index": -1})
        return f"Content appended to doc {token}."

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
    """Use the chat model's vision capability via OpenRouter."""
    import os, httpx
    question = args.get("question", "Describe this image in detail.")
    image_url = args["image_url"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={
                "model": "google/gemini-3-flash-preview",
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": question},
                ]}],
            },
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
        log.info("executing tool %s with args %s", name, {k: str(v)[:100] for k, v in args.items()})
        result = await fn(args)
        log.info("tool %s returned %d chars", name, len(result))
        return result
    except Exception as e:
        log.exception("tool %s failed", name)
        return f"Error running {name}: {e}"
