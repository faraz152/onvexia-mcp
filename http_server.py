#!/usr/bin/env python3
"""
Onvexia MCP server over Streamable HTTP — the REMOTE, hosted transport.

WHY THIS FILE EXISTS.

`server.py` runs over stdio: the agent's host process spawns a local Python
process that the user installed and configured with their own API key. That is
the right shape for a developer on their laptop and the wrong shape for
distribution. Every registry that matters — the Official MCP Registry, Smithery,
Glama — lists a REMOTE server as a URL an agent connects to with no install, and
`https://onvexia.com/mcp` answered **404** when this was written (measured
2026-09-16). The catalogue was ready and there was nothing to point it at.

So this module takes the SAME server object, with the same 66 tools defined in
exactly one place, and serves it over HTTP. There is no second tool definition
here, deliberately: a hosted surface that drifts from the stdio one is two
products with one name, and this repo has paid for reader/writer pairs that
stopped naming the same thing more than once.

WHAT THIS PROCESS MUST NOT HAVE, AND WHY IT IS ENFORCED AT STARTUP.

This is a MULTI-TENANT process. One instance serves every agent on the internet.
Two environment variables that are correct for stdio are dangerous here:

  CRYPTO_INTEL_API_KEY     every caller would be metered against whoever owns
                           that key, and would inherit its plan
  X402_CLIENT_PRIVATE_KEY  every anonymous caller's 402 would be paid FROM OUR
                           OWN WALLET — an unbounded USDC drain that looks
                           exactly like healthy traffic right up until the
                           wallet is empty

Neither is a hypothetical: both are already set in the repo `.env` because the
stdio server and the payment tests need them, so the failure mode is inheriting
a shell, not writing new config. `_refuse_shared_credentials()` exits non-zero
rather than starting, because a service that starts and quietly bills the wrong
account is worse than one that does not start.

Callers authenticate per request instead — see `caller_credentials` in
api_client.py. An agent sends its own `X-API-Key`, session `Authorization`, or
`X-PAYMENT`, and we forward exactly those three to /v1. An agent that sends
nothing is anonymous and gets the gateway's own 401/402, which names what to do.

UNAUTHENTICATED DISCOVERY IS REQUIRED, NOT AN OVERSIGHT.
`initialize` and `tools/list` answer without any credential. Aggregator scanners
probe exactly those two, and a server that demands auth to describe itself is
recorded as "broken" and stops being listed. Authorisation happens where the
data is: /v1 gates `tools/call`, because /v1 is the layer that owns it.
"""

from __future__ import annotations

import os
import sys

from api_client import caller_credentials, FORWARDABLE_HEADERS
from server import build_server


def _refuse_shared_credentials() -> None:
    """Refuse to start holding a credential that would be spent on behalf of
    strangers. See the module docstring."""
    banned = {
        "CRYPTO_INTEL_API_KEY": "every caller would be metered against this key's account",
        "X402_CLIENT_PRIVATE_KEY": "anonymous callers' payments would come out of this wallet",
    }
    found = [f"  {k} is set — {why}" for k, why in banned.items() if os.getenv(k)]
    if found:
        sys.stderr.write(
            "REFUSING TO START: the hosted MCP server must hold no caller credentials.\n"
            + "\n".join(found)
            + "\n\nThis process serves every agent on the internet from one instance;\n"
              "credentials are per-request (see api_client.caller_credentials).\n"
              "Unset them in the unit's EnvironmentFile, or run server.py for stdio.\n"
        )
        raise SystemExit(2)


class CallerCredentialMiddleware:
    """Bind the inbound request's credentials for the life of the request.

    Pure ASGI rather than a Starlette `BaseHTTPMiddleware`: that class runs the
    downstream app in a SEPARATE anyio task, and a ContextVar set in the parent
    after the child was spawned is not visible to it. The bug that produces is
    the worst kind — every tool call silently anonymous, which looks like a
    permissions problem rather than a plumbing one. Here the downstream app is
    awaited directly, in this task, inside the `with`.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower()
            if name in FORWARDABLE_HEADERS:
                # Canonical casing on the way out: the gateway reads X-API-Key
                # and X-PAYMENT, and httpx does not normalise for us.
                headers[{"x-api-key": "X-API-Key",
                         "authorization": "Authorization",
                         "x-payment": "X-PAYMENT"}[name]] = raw_value.decode("latin-1")
        with caller_credentials(headers):
            await self.app(scope, receive, send)


def build_app():
    """Build the ASGI app serving the MCP endpoint at `/mcp`."""
    _refuse_shared_credentials()
    mcp = build_server()

    # STATELESS. Each request is self-contained, so the service can be restarted
    # under a deploy, or run more than once, without an agent's session
    # evaporating mid-conversation. A session-bound transport behind a proxy is
    # a sticky-routing problem we have no reason to take on.
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=_env_bool("MCP_JSON_RESPONSE", False),
        transport_security=_transport_security(),
    )

    # Liveness for systemd and the deploy verifier. Deliberately NOT on /mcp:
    # a GET to the MCP path is part of the protocol, and using it as a health
    # check would make "the protocol answered an error" look like "the process
    # is up".
    async def health(request):  # noqa: ANN001
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "ok", "tools": len(await mcp.list_tools())})

    from starlette.routing import Route
    app.router.routes.append(Route("/health", health, methods=["GET"]))

    return CallerCredentialMiddleware(app)


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _transport_security():
    """DNS-rebinding protection, configured for running behind the gateway.

    The SDK defaults this ON and then has no allowed host to compare against,
    which behind a reverse proxy rejects every request by Host header. The hosts
    we are actually served under are known, so they are named rather than the
    protection being switched off.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = [h.strip() for h in os.getenv(
        "MCP_ALLOWED_HOSTS", "onvexia.com,www.onvexia.com,127.0.0.1,localhost"
    ).split(",") if h.strip()]
    origins = [o.strip() for o in os.getenv(
        "MCP_ALLOWED_ORIGINS", "https://onvexia.com,https://www.onvexia.com"
    ).split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=_env_bool("MCP_DNS_REBINDING_PROTECTION", True),
        allowed_hosts=hosts + [f"{h}:*" for h in hosts],
        allowed_origins=origins,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        build_app(),
        # Loopback only. cloudflared fronts the gateway and the gateway proxies
        # /mcp to here; nothing about this process should be directly reachable.
        host=os.getenv("MCP_HTTP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_HTTP_PORT", "8091")),
        log_level=os.getenv("MCP_LOG_LEVEL", "info"),
        access_log=False,
    )


if __name__ == "__main__":
    main()
