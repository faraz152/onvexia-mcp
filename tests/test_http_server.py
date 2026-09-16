"""
The hosted (Streamable HTTP) MCP transport.

This process is MULTI-TENANT — one instance at https://onvexia.com/mcp serves
every agent on the internet — and that is the whole reason this file exists.
Over stdio a credential belongs to the one human who configured it; over HTTP
the same code holding the same credential bills strangers to somebody else's
account and pays strangers' x402 challenges out of our own USDC wallet.

Neither is hypothetical: both variables are set in the repo `.env` for the stdio
server and the payment tests, so the way this breaks is inheriting a shell, not
writing new config.
"""

import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api_client  # noqa: E402
import http_server  # noqa: E402
from api_client import OnvexiaClient, caller_credentials  # noqa: E402

BASE = "http://testhost:8080"


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch):
    monkeypatch.delenv("CRYPTO_INTEL_API_KEY", raising=False)
    monkeypatch.delenv("X402_CLIENT_PRIVATE_KEY", raising=False)


# --- the startup guard ------------------------------------------------------

@pytest.mark.parametrize("var", ["CRYPTO_INTEL_API_KEY", "X402_CLIENT_PRIVATE_KEY"])
def test_refuses_to_start_holding_a_shared_credential(monkeypatch, var):
    monkeypatch.setenv(var, "something")
    with pytest.raises(SystemExit) as e:
        http_server.build_app()
    assert e.value.code == 2, "must exit non-zero, not start and quietly misbill"


def test_starts_clean_when_no_credential_is_present():
    assert http_server.build_app() is not None


# --- header forwarding ------------------------------------------------------

def _capture():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return httpx.Response(200, json={"ok": True})

    c = OnvexiaClient(base_url=BASE,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return c, seen


def test_caller_credential_is_forwarded():
    c, seen = _capture()
    with caller_credentials({"X-API-Key": "onvex_sk_caller"}):
        c.get_coverage()
    assert seen["headers"]["x-api-key"] == "onvex_sk_caller"


def test_no_credential_means_anonymous_not_borrowed():
    """The property that makes this safe: we never substitute our own identity.

    An anonymous caller must reach /v1 anonymously and receive the gateway's own
    401/402 — an answer they can act on. Lending them a server credential would
    meter their calls against someone else.
    """
    c, seen = _capture()
    c.get_coverage()
    assert "x-api-key" not in seen["headers"]
    assert "authorization" not in seen["headers"]


def test_an_explicit_per_call_header_beats_the_caller_credential():
    """The x402 retry's X-PAYMENT must win over anything in the caller context.

    `_request` answers a 402 by signing and re-sending with a per-call
    X-PAYMENT. If the merge preferred the ContextVar, a caller who sent their
    own (stale) X-PAYMENT would have the fresh signature silently dropped and
    the retry would 402 again — indistinguishable from the facilitator refusing
    the payment. Asserted by driving the real `_request`, not by re-implementing
    the merge in the test.
    """
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-payment"))
        if len(seen) == 1:
            return httpx.Response(402, json={"x402Version": 1, "accepts": [{
                "scheme": "exact", "network": "base-sepolia", "maxAmountRequired": "1000",
                "payTo": "0x" + "1" * 40, "maxTimeoutSeconds": 60,
                "asset": "0x" + "2" * 40, "extra": {"name": "USDC", "version": "2"}}]})
        return httpx.Response(200, json={"ok": True})

    c = OnvexiaClient(
        base_url=BASE,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        # a throwaway key; this never touches a network or a real wallet
        wallet_private_key="0x" + "11" * 32,
    )
    with caller_credentials({"X-API-Key": "caller", "X-PAYMENT": "stale"}):
        c.get_coverage()

    assert seen[0] == "stale", "first send carries whatever the caller sent"
    assert seen[1] is not None and seen[1] != "stale", (
        f"the signed retry must replace the caller's X-PAYMENT, got {seen[1]!r}")


def test_middleware_filters_to_the_allowlist():
    """The ASGI middleware, not the client, is the filter — assert it directly."""
    captured = {}

    async def app(scope, receive, send):
        captured.update(api_client.current_caller_headers())

    mw = http_server.CallerCredentialMiddleware(app)
    scope = {"type": "http", "headers": [
        (b"x-api-key", b"onvex_sk_1"),
        (b"authorization", b"Bearer jwt"),
        (b"x-payment", b"base64payload"),
        (b"cookie", b"session=secret"),          # must NOT be relayed
        (b"x-forwarded-for", b"1.2.3.4"),        # must NOT be relayed
        (b"user-agent", b"scanner/1.0"),         # must NOT be relayed
    ]}
    asyncio.run(mw(scope, None, None))
    assert captured == {"X-API-Key": "onvex_sk_1",
                        "Authorization": "Bearer jwt",
                        "X-PAYMENT": "base64payload"}, captured


def test_credentials_do_not_leak_between_concurrent_callers():
    """Two agents in flight at once must not see each other's key.

    The reason the credential is a ContextVar and is merged at SEND time rather
    than set on the shared httpx.Client: one client object serves every request,
    and mutating its headers is a race whose symptom is one customer's calls
    being billed to another.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        who = request.headers.get("x-api-key")
        seen.setdefault(who, 0)
        seen[who] += 1
        return httpx.Response(200, json={"ok": True})

    c = OnvexiaClient(base_url=BASE,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    async def call(key):
        with caller_credentials({"X-API-Key": key}):
            await asyncio.sleep(0)          # force interleaving
            c.get_coverage()

    async def both():
        await asyncio.gather(*[call(f"key_{i}") for i in range(8)])

    asyncio.run(both())
    assert seen == {f"key_{i}": 1 for i in range(8)}, seen


# --- error surfacing --------------------------------------------------------

def test_4xx_surfaces_the_gateways_own_explanation():
    """Measured against production 2026-09-16: the body says what to do, and
    raise_for_status() replaced it with a link to MDN."""
    def handler(request):
        return httpx.Response(401, json={
            "error": "unauthenticated", "free_access": True,
            "message": "Free access is on — a free account reaches every paid endpoint.",
            "reason": "free_access_needs_account", "signup_url": "/signup",
            "need_tier": "starter"})

    c = OnvexiaClient(base_url=BASE,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError) as e:
        c.get_whale_transactions()
    msg = str(e.value)
    assert "Free access is on" in msg
    assert "/signup" in msg
    assert "starter" in msg
    assert "mozilla.org" not in msg, "the MDN link is what this replaced"


def test_4xx_without_a_json_body_still_says_something():
    def handler(request):
        return httpx.Response(500, text="upstream exploded")

    c = OnvexiaClient(base_url=BASE,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError, match="upstream exploded"):
        c.get_coverage()
