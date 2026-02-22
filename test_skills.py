"""Local test for each skill executor. Bypasses SSL for macOS cert issue."""
import asyncio, os, ssl
os.environ["SSL_CERT_FILE"] = ""  # clear

# Monkey-patch httpx to skip SSL locally (macOS cert issue only)
import httpx
_orig_async = httpx.AsyncClient.__init__
def _patched_init(self, *a, **kw):
    kw.setdefault("verify", False)
    _orig_async(self, *a, **kw)
httpx.AsyncClient.__init__ = _patched_init

from dotenv import load_dotenv
load_dotenv()

from executors import run_weather, run_summarize, run_llava, run_nano_pdf

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

async def main():
    await test_weather()
    await test_summarize_url()
    await test_summarize_youtube()
    await test_llava()
    await test_openrouter()
    print("ALL TESTS PASSED")

asyncio.run(main())
