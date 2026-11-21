"""Behind the load balancer, the rate-limit key must be the real client, which
needs uvicorn's ProxyHeadersMiddleware to accept a CIDR for its trusted proxies."""
from httpx import ASGITransport, AsyncClient
from slowapi.util import get_remote_address
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

ALB_PEER = ("10.0.3.7", 5555)


async def _key(trusted: str, peer: tuple[str, int], xff: str | None) -> str:
    async def echo(request):  # the exact key function the limiter uses (ratelimit.py:12)
        return PlainTextResponse(get_remote_address(request))

    app = ProxyHeadersMiddleware(Starlette(routes=[Route("/ip", echo)]), trusted_hosts=trusted)
    headers = {"x-forwarded-for": xff} if xff else {}
    async with AsyncClient(transport=ASGITransport(app=app, client=peer), base_url="http://t") as c:
        return (await c.get("/ip", headers=headers)).text


async def test_the_real_client_is_the_rightmost_untrusted_entry():
    assert await _key("10.0.0.0/16", ALB_PEER, "198.51.100.7, 203.0.113.9") == "203.0.113.9"


async def test_a_forged_leftmost_entry_does_not_change_the_rate_limit_key():
    honest = await _key("10.0.0.0/16", ALB_PEER, "203.0.113.9")
    forged = await _key("10.0.0.0/16", ALB_PEER, "1.2.3.4, 203.0.113.9")
    assert honest == forged == "203.0.113.9"


async def test_an_untrusted_peer_cannot_choose_its_address():
    assert await _key("10.0.0.0/16", ("192.0.2.50", 1), "203.0.113.9") == "192.0.2.50"


async def test_a_wildcard_would_trust_the_forged_entry():  # why validate_serving_settings refuses "*"
    assert await _key("*", ALB_PEER, "1.2.3.4, 203.0.113.9") == "1.2.3.4"
