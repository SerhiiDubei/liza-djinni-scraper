import httpx
import pytest

from liza.scraper.client import BlockedError, DjinniClient


async def test_get_returns_body_text():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<html>ok</html>"))
    async with DjinniClient(delay=0, transport=transport) as c:
        assert "ok" in await c.get("/jobs/", params={"page": 1})


async def test_get_raises_blocked_on_429():
    transport = httpx.MockTransport(lambda req: httpx.Response(429, text="nope"))
    async with DjinniClient(delay=0, max_retries=2, transport=transport) as c:
        with pytest.raises(BlockedError):
            await c.get("/jobs/")


async def test_get_sends_user_agent_and_cookie():
    seen = {}

    def handler(req):
        seen["ua"] = req.headers.get("user-agent")
        seen["cookie"] = req.headers.get("cookie")
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    async with DjinniClient(delay=0, user_agent="UA/1", cookie="sessionid=abc",
                            transport=transport) as c:
        await c.get("/jobs/")
    assert seen["ua"] == "UA/1"
    assert seen["cookie"] == "sessionid=abc"
