import httpx
import pytest

from liza.llm.client import LLMClient, LLMError


def _resp(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_complete_json_returns_parsed():
    transport = httpx.MockTransport(lambda req: _resp('{"score": 80, "verdict": "apply"}'))
    async with LLMClient(api_key="x", transport=transport) as c:
        out = await c.complete_json(system="s", user="u")
    assert out == {"score": 80, "verdict": "apply"}


async def test_complete_json_strips_code_fences():
    transport = httpx.MockTransport(lambda req: _resp('```json\n{"a": 1}\n```'))
    async with LLMClient(api_key="x", transport=transport) as c:
        assert await c.complete_json(system="s", user="u") == {"a": 1}


async def test_missing_key_raises():
    with pytest.raises(LLMError):
        async with LLMClient(api_key="") as c:
            await c.complete_json(system="s", user="u")
