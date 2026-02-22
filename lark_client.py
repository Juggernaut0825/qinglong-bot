import os, time, json, httpx

LARK_HOST = "https://open.larksuite.com"
_token_cache = {"token": "", "expires": 0}


async def _get_tenant_token() -> str:
    if _token_cache["expires"] > time.time():
        return _token_cache["token"]
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{LARK_HOST}/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": os.environ["LARK_APP_ID"],
                "app_secret": os.environ["LARK_APP_SECRET"],
            },
        )
        data = r.json()
        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expires"] = time.time() + data.get("expire", 7200) - 60
        return _token_cache["token"]


async def lark_api(method: str, path: str, **kwargs) -> dict:
    token = await _get_tenant_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as c:
        r = await getattr(c, method)(
            f"{LARK_HOST}/open-apis{path}", headers=headers, **kwargs
        )
        return r.json()


async def download_lark_image(message_id: str, image_key: str) -> bytes:
    """Download image from Lark and return raw bytes."""
    token = await _get_tenant_token()
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{LARK_HOST}/open-apis/im/v1/messages/{message_id}/resources/{image_key}",
            headers={"Authorization": f"Bearer {token}"},
            params={"type": "image"},
        )
        return r.content


async def send_lark_message(chat_id: str, text: str):
    await lark_api(
        "post",
        "/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
    )
