"""Local test for each skill executor. Bypasses SSL for macOS cert issue."""
import asyncio, os, ssl, json, logging
os.environ["SSL_CERT_FILE"] = ""  # clear

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# Monkey-patch httpx to skip SSL locally (macOS cert issue only)
import httpx, ssl as _ssl
_ctx = _ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = _ssl.CERT_NONE
_orig_async = httpx.AsyncClient.__init__
def _patched_init(self, *a, **kw):
    kw.setdefault("verify", _ctx)
    _orig_async(self, *a, **kw)
httpx.AsyncClient.__init__ = _patched_init

from dotenv import load_dotenv
load_dotenv()

from executors import run_weather, run_summarize, run_llava
from lark_bot import _extract_event_info

async def test_weather():
    print("=== WEATHER ===")
    r = await run_weather({"location": "Tokyo", "mode": "current"})
    print(r)
    assert len(r) > 5, "Weather returned empty"
    print("PASS\n")

async def test_summarize_url():
    print("=== SUMMARIZE URL ===")
    r = await run_summarize({"target": "https://example.com", "length": "short"})
    print(r[:300])
    assert len(r) > 20, "Summarize returned empty"
    print("PASS\n")

async def test_summarize_youtube():
    print("=== SUMMARIZE YOUTUBE ===")
    r = await run_summarize({"target": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "length": "short"})
    print(r[:300])
    assert len(r) > 20, "YouTube summarize returned empty"
    print("PASS\n")

async def test_llava():
    print("=== LLAVA (image analysis) ===")
    # Use a public test image
    r = await run_llava({
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
        "question": "What do you see in this image?"
    })
    print(r[:300])
    assert len(r) > 10, "LLaVA returned empty"
    print("PASS\n")

async def test_openrouter():
    print("=== OPENROUTER CHAT ===")
    from agent import chat_completion
    resp = await chat_completion([
        {"role": "system", "content": "You are Mini Wang."},
        {"role": "user", "content": "Say hi in one sentence."}
    ])
    msg = resp["choices"][0]["message"]["content"]
    print(msg)
    assert len(msg) > 2, "Chat returned empty"
    print("PASS\n")

async def test_extract_image_event():
    print("=== EXTRACT IMAGE EVENT ===")
    payload = {
        "header": {"event_id": "test1", "event_type": "im.message.receive_v1"},
        "event": {"message": {
            "chat_id": "oc_test", "message_id": "om_test",
            "message_type": "image",
            "content": json.dumps({"image_key": "img_v3_test_key"})
        }}
    }
    info = _extract_event_info(payload)
    assert info["image_key"] == "img_v3_test_key", f"Expected image_key, got {info}"
    assert info["chat_id"] == "oc_test"
    print(f"Extracted: {info}")
    print("PASS\n")

async def test_extract_file_event():
    print("=== EXTRACT FILE EVENT ===")
    payload = {
        "header": {"event_id": "test2", "event_type": "im.message.receive_v1"},
        "event": {"message": {
            "chat_id": "oc_test", "message_id": "om_test",
            "message_type": "file",
            "content": json.dumps({"file_key": "file_v3_test", "file_name": "report.pdf"})
        }}
    }
    info = _extract_event_info(payload)
    assert info["file_key"] == "file_v3_test", f"Expected file_key, got {info}"
    assert info["file_name"] == "report.pdf"
    print(f"Extracted: {info}")
    print("PASS\n")

async def test_youtube_no_transcript():
    print("=== YOUTUBE NO TRANSCRIPT (fallback) ===")
    # Use a video that likely has no captions
    r = await run_summarize({"target": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "length": "short"})
    print(r[:300])
    assert len(r) > 20, "YouTube summarize returned empty"
    print("PASS\n")

async def test_agent_image_multimodal():
    print("=== AGENT IMAGE MULTIMODAL ===")
    from agent import _make_user_content
    # Simulate what _handle produces for an image
    text = "[image:data:image/png;base64,iVBORw0KGgo=] What's in this image?"
    content = _make_user_content(text)
    assert isinstance(content, list), f"Expected list, got {type(content)}"
    assert content[0]["type"] == "image_url"
    assert content[1]["type"] == "text"
    print(f"Multimodal content types: {[c['type'] for c in content]}")
    print("PASS\n")

async def test_agent_pdf_multimodal():
    print("=== AGENT PDF MULTIMODAL ===")
    from agent import _make_user_content
    text = "[file:data:application/pdf;base64,JVBERi0=] Please analyze this PDF."
    content = _make_user_content(text)
    assert isinstance(content, list), f"Expected list, got {type(content)}"
    assert content[0]["type"] == "file"
    assert content[1]["type"] == "text"
    print(f"Multimodal content types: {[c['type'] for c in content]}")
    print("PASS\n")

async def main():
    # Unit tests (no API calls)
    await test_extract_image_event()
    await test_extract_file_event()
    await test_agent_image_multimodal()
    await test_agent_pdf_multimodal()
    # API tests
    await test_weather()
    await test_summarize_url()
    await test_youtube_no_transcript()
    await test_llava()
    await test_openrouter()
    print("ALL TESTS PASSED")

asyncio.run(main())
