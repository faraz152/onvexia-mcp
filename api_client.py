"""
Crypto Intel API client — Phase 04 (Distribution).

A thin, typed wrapper over the Go `/v1` API. The MCP server (server.py) exposes
these methods as agent tools. Kept separate from the MCP runtime so it is
unit-testable via httpx.MockTransport with no network and no `mcp` dependency.

Base URL from CRYPTO_INTEL_API_URL (default http://localhost:8080).
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional
from urllib.parse import quote

import httpx


# ---------------------------------------------------------------------------
# Per-caller credentials (the hosted / remote MCP server)
# ---------------------------------------------------------------------------
#
# Over stdio there is one caller: the human who put their own key in their own
# client config, and a process-wide `X-API-Key` on the shared httpx client is
# exactly right.
#
# OVER HTTP THAT IS A MULTI-TENANT BILLING BUG. https://onvexia.com/mcp serves
# every agent on the internet from ONE process. A key set on the shared client
# would meter every one of those callers against whoever owned it, and a wallet
# key in that process would PAY FOR STRANGERS' CALLS out of our own USDC — an
# unbounded drain that looks like traffic until the wallet is empty.
#
# So the HTTP transport carries the caller's own credential per request, in a
# ContextVar rather than an argument, because it has to cross 66 tool functions
# and `_request` without any of them knowing about it. http_server.py sets it
# from the inbound headers; everything below merges it at send time.
#
# THERE IS NO FALLBACK TO A SERVER CREDENTIAL, deliberately. A caller who sends
# nothing IS anonymous and gets the 401/402 the gateway would give them — which
# is an answer they can act on (sign up, or pay per call). Quietly lending them
# our identity would be worse than the error.
_CALLER_HEADERS: ContextVar[Dict[str, str]] = ContextVar("onvexia_caller_headers", default={})

# The inbound headers an agent may use to identify or pay for itself. Nothing
# else is forwarded: an allowlist, so a future header cannot be relayed to our
# own API by accident.
FORWARDABLE_HEADERS = ("x-api-key", "authorization", "x-payment")


@contextmanager
def caller_credentials(headers: Optional[Dict[str, str]]) -> Iterator[None]:
    """Bind one HTTP caller's credentials for the duration of their request."""
    token = _CALLER_HEADERS.set(dict(headers or {}))
    try:
        yield
    finally:
        _CALLER_HEADERS.reset(token)


def current_caller_headers() -> Dict[str, str]:
    return dict(_CALLER_HEADERS.get())


class PaymentRequired(RuntimeError):
    """HTTP 402 with the x402 challenge parsed into something actionable.

    The gateway answers an unauthenticated call with a well-formed x402
    challenge — scheme, network, asset, payTo, amount. That is the protocol
    working, not a failure, but only if the caller can read it. httpx's default
    `raise_for_status()` collapses all of it to the string "402 Payment
    Required".

    This carries the terms AND both ways out, because an agent hitting this has
    no way to know either exists.
    """

    def __init__(self, path: str, resp: "httpx.Response"):
        self.path = path
        self.status_code = 402
        self.challenge: Dict[str, Any] = {}
        try:
            body = resp.json()
            if isinstance(body, dict):
                self.challenge = body
        except Exception:
            pass

        accepts = (self.challenge.get("accepts") or [{}])[0]
        self.network = accepts.get("network")
        self.asset = accepts.get("asset")
        self.pay_to = accepts.get("payTo")
        self.amount_atomic = accepts.get("maxAmountRequired")
        self.asset_name = (accepts.get("extra") or {}).get("name")

        terms = "unknown terms (the response carried no x402 challenge)"
        if self.amount_atomic and self.asset_name:
            terms = (f"{self.amount_atomic} atomic units of {self.asset_name} "
                     f"on {self.network} to {self.pay_to}")
        super().__init__(
            f"{path} requires payment: {terms}. Two ways through: (1) set "
            f"CRYPTO_INTEL_API_KEY to an Onvexia key and every call is "
            f"authenticated and metered against that account, or (2) present an "
            f"X-PAYMENT header satisfying the x402 challenge in `.challenge` — "
            f"this API accepts agents with no account, which is the point. "
            f"The challenge is preserved verbatim on this exception."
        )


# Chain IDs for the EIP-712 domain. USDC's TransferWithAuthorization is signed
# over a domain that includes chainId, so a signature made for one network is
# invalid on another — which is the property that stops a testnet signature
# being replayed against mainnet.
_CHAIN_IDS = {"base": 8453, "base-sepolia": 84532}

# Refuse to pay more than this per call unless the caller raises it. The
# challenge is written by the SERVER, so an agent that signs whatever it is
# handed will sign a demand for the whole wallet. 10,000 atomic units = $0.01,
# a hundred times the current price of 100 units, so a legitimate price rise
# does not break the client while a malicious one does.
_DEFAULT_MAX_ATOMIC = 10_000


def _sign_x402_payment(challenge: Dict[str, Any], private_key: str,
                       max_atomic: int) -> str:
    """Sign an x402 `exact` payment and return the base64 X-PAYMENT header.

    The scheme is USDC's EIP-3009 `transferWithAuthorization`: we sign an
    EIP-712 message authorising a transfer, and the FACILITATOR submits it
    on-chain. That is why this needs no gas and no RPC — the client only signs.

    eth_account is imported HERE, not at module scope, so the 47 tools that use
    an API key keep working on an install without it. A payment path that makes
    the whole client unimportable is worse than one that is absent.
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "x402 payment needs `eth-account` (in requirements.txt). Install it, "
            "or set CRYPTO_INTEL_API_KEY to use the key path instead."
        ) from exc

    accepts = (challenge.get("accepts") or [{}])[0]
    scheme = accepts.get("scheme", "exact")
    if scheme != "exact":
        raise RuntimeError(f"unsupported x402 scheme {scheme!r}; only `exact` is implemented")

    network = accepts.get("network", "")
    chain_id = _CHAIN_IDS.get(network)
    if chain_id is None:
        raise RuntimeError(f"unknown x402 network {network!r}; known: {sorted(_CHAIN_IDS)}")

    value = int(accepts.get("maxAmountRequired", "0"))
    if value > max_atomic:
        raise RuntimeError(
            f"refusing to pay {value} atomic units — above the {max_atomic} cap. "
            f"Raise max_payment_atomic deliberately if this price is expected."
        )

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    acct = Account.from_key(private_key)

    extra = accepts.get("extra") or {}
    now = int(time.time())
    auth = {
        "from": acct.address,
        "to": accepts["payTo"],
        "value": str(value),
        # 60s of clock skew tolerance either side; validBefore is what stops a
        # captured signature being replayed indefinitely.
        "validAfter": str(now - 60),
        "validBefore": str(now + int(accepts.get("maxTimeoutSeconds", 60)) + 60),
        "nonce": "0x" + secrets.token_bytes(32).hex(),
    }

    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            # name/version come from the CHALLENGE, not from a constant: USDC is
            # "USDC" v2 today, and a token whose EIP-712 name differs would
            # produce a signature the contract rejects.
            "name": extra.get("name", "USDC"),
            "version": extra.get("version", "2"),
            "chainId": chain_id,
            "verifyingContract": accepts["asset"],
        },
        "message": {
            "from": auth["from"],
            "to": auth["to"],
            "value": int(auth["value"]),
            "validAfter": int(auth["validAfter"]),
            "validBefore": int(auth["validBefore"]),
            "nonce": bytes.fromhex(auth["nonce"][2:]),
        },
    }
    signed = Account.sign_message(encode_typed_data(full_message=typed), private_key)

    # 0x-PREFIX THE SIGNATURE. eth-account 0.13's HexBytes.hex() returns BARE
    # hex ("c659…"), where older versions returned "0xc659…". The facilitator
    # expects the prefixed form and rejects the bare one, which surfaced as a
    # second 402 with no explanation from our side. Normalised rather than
    # assumed, so a future eth-account that restores the prefix cannot
    # double-prefix it.
    sig = signed.signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    payload = {
        "x402Version": challenge.get("x402Version", 1),
        "scheme": scheme,
        "network": network,
        "payload": {"signature": sig, "authorization": auth},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _actionable_error(path: str, resp: httpx.Response) -> RuntimeError:
    """Turn a 4xx/5xx into something an AGENT can act on.

    THE SAME DEFECT AS THE 402 ONE ABOVE, LEFT HALF-FIXED. `raise_for_status()`
    renders every failure as `Client error '401 Unauthorized' for url ...` plus
    a link to MDN — and throws away a body that already says exactly what to do.
    Measured against production 2026-09-16, an unauthenticated whale-transaction
    call returns:

        {"error":"unauthenticated","free_access":true,
         "message":"Free access is on — a free account reaches every paid
                    endpoint, including this one, at no cost. Sign in or present
                    an API key.",
         "need_tier":"starter","reason":"free_access_needs_account",
         "signup_url":"/signup"}

    An LLM handed the MDN version retries or gives up. Handed this one, it tells
    its user to sign up. 402 was fixed on 2026-08-21 and 401 was not, which
    mattered little then and matters now: the free-access waiver turned 401 into
    the response every anonymous agent gets.

    Fixed HERE, in the client, so the stdio server and the hosted HTTP server
    both benefit — not in the one tool where it was noticed.
    """
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            parts = [str(body[k]) for k in ("message", "error", "reason") if body.get(k)]
            # Deduplicate: `error` is often a slug of `message`.
            seen, uniq = set(), []
            for s in parts:
                if s.lower() not in seen:
                    seen.add(s.lower()); uniq.append(s)
            detail = " — ".join(uniq)
            if body.get("signup_url"):
                detail += f" (sign up: {body['signup_url']})"
            if body.get("need_tier"):
                detail += f" [requires tier: {body['need_tier']}]"
    except Exception:
        detail = (resp.text or "").strip()[:300]
    if not detail:
        detail = f"HTTP {resp.status_code} with no explanation in the body"
    return RuntimeError(f"{path} refused ({resp.status_code}): {detail}")


class OnvexiaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 20.0,
        http_client: Optional[httpx.Client] = None,
        api_key: Optional[str] = None,
        wallet_private_key: Optional[str] = None,
        max_payment_atomic: int = _DEFAULT_MAX_ATOMIC,
    ):
        self.base_url = (base_url or os.getenv("CRYPTO_INTEL_API_URL", "http://localhost:8080")).rstrip("/")
        self._client = http_client or httpx.Client(timeout=timeout)
        # Apply auth to whichever client we use (injected clients included).
        # X-API-Key is the canonical header (the Authorization slot is reserved
        # for Supabase session JWTs, which the gateway parses differently).
        key = api_key or os.getenv("CRYPTO_INTEL_API_KEY")
        if key:
            self._client.headers["X-API-Key"] = key

        # x402 self-onboarding. With a wallet key, a 402 is answered by signing
        # the challenge rather than raising — which is what server.py has always
        # claimed ("an agent can self-onboard via x402") and what nothing
        # implemented until 2026-08-21.
        self._wallet_key = wallet_private_key or os.getenv("X402_CLIENT_PRIVATE_KEY", "")
        self.max_payment_atomic = max_payment_atomic

    # --- internal --------------------------------------------------------
    def _handle(self, resp: httpx.Response, path: str) -> Any:
        """Turn a response into JSON, or into an error an AGENT can act on.

        A 402 IS NOT A BUG HERE — it is the x402 payment challenge, and this
        API is deliberately open to agents with no account. But
        `raise_for_status()` turned it into `Client error '402 Payment
        Required'`, which tells an LLM nothing about what to do next: not the
        price, not the asset, not that an API key would also work. Measured
        2026-08-21: every one of the 48 MCP tools failed that way when
        CRYPTO_INTEL_API_KEY was unset, which is the default.

        server.py claims "an agent can self-onboard via x402". Self-onboarding
        starts with the agent being told, in the failure itself, what onboarding
        requires.
        """
        if resp.status_code == 402:
            raise PaymentRequired(path, resp)
        if resp.status_code >= 400:
            raise _actionable_error(path, resp)
        return resp.json()

    def _request(self, method: str, path: str, *, params=None, json_body=None) -> Any:
        """Send, and on 402 pay once and resend.

        EXACTLY ONCE. A retry loop around a payment endpoint is a wallet-drainer:
        a server that answers 402 to everything — misconfigured, or hostile —
        would be paid on every attempt. One signed attempt, and a second 402 is
        surfaced as an error the caller has to look at.
        """
        # An explicit def, not a conditional lambda: written as a ternary between
        # two lambdas, Python binds it as `lambda hdrs: (... if ... else lambda …)`
        # and the POST branch returns a FUNCTION instead of a response. The tests
        # caught it as "'function' object has no attribute 'status_code'".
        def send(hdrs):
            url = f"{self.base_url}{path}"
            # The caller's own credential wins over anything configured on this
            # process. Merged HERE rather than on the client because the client
            # is shared by every concurrent HTTP request and mutating its
            # headers would leak one agent's key into another's call.
            merged = {**current_caller_headers(), **(hdrs or {})}
            merged = merged or None
            if method == "GET":
                return self._client.get(url, params=params, headers=merged)
            return self._client.post(url, json=json_body, headers=merged)

        resp = send(None)
        if resp.status_code != 402 or not self._wallet_key:
            return self._handle(resp, path)

        challenge = {}
        try:
            challenge = resp.json()
        except Exception:
            pass
        header = _sign_x402_payment(challenge, self._wallet_key, self.max_payment_atomic)
        paid = send({"X-PAYMENT": header})
        if paid.status_code == 402:
            # Signed and still refused: the facilitator rejected it. Raising the
            # SECOND response keeps its reason, which is the diagnostic.
            raise PaymentRequired(path, paid)
        # The settlement receipt proves the payment was actually taken, not just
        # accepted — worth keeping for reconciliation.
        self.last_payment_response = paid.headers.get("X-PAYMENT-RESPONSE")
        paid.raise_for_status()
        return paid.json()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: Dict[str, Any]) -> Any:
        return self._request("POST", path, json_body=body)

    @staticmethod
    def _seg(value: str) -> str:
        return quote(str(value), safe="")

    # --- assets & scores -------------------------------------------------
    def get_asset(self, symbol: str) -> Any:
        return self._get(f"/v1/assets/{self._seg(symbol)}")

    def get_asset_scores(self, symbol: str) -> Any:
        """Galaxy Score, AltRank and components for an asset."""
        return self._get(f"/v1/assets/{self._seg(symbol)}/scores")

    def get_asset_fundamentals(self, symbol: str) -> Any:
        """The composed fundamental brief: market, supply, revenue, treasury,
        governance, unlocks, positioning and a graded scorecard.

        Each section reports one of four states — `measured`, `not_held`,
        `failed`, or (in a separate `not_applicable` list) a section this asset
        class cannot have. An agent must read the state, not just the values: a
        section that is absent from `sections` is one the asset cannot have, and
        `failed` means the read broke rather than the market being empty.
        """
        return self._get(f"/v1/assets/{self._seg(symbol)}/fundamentals")

    def get_asset_technicals(self, symbol: str, limit: int = 8) -> Any:
        """Indicators per timeframe, support/resistance merged across
        1w/1d/4h/1h, and derived spot/long/short setups.

        `measured_against` names the venue and pair every distance and
        support/resistance classification was computed from, and
        `price_age_minutes` says how old that price is. Setups are geometry
        over the levels, never a forecast.
        """
        return self._get(f"/v1/assets/{self._seg(symbol)}/technicals",
                         params={"limit": limit})

    def get_top_galaxy_scores(self, limit: int = 10) -> Any:
        return self._get("/v1/scores/galaxy/top", params={"limit": limit})

    def get_top_altranks(self, limit: int = 10) -> Any:
        return self._get("/v1/scores/altrank/top", params={"limit": limit})

    def get_narrative_rotation(self, days: int = 7, include_legacy: bool = False) -> Any:
        params: Dict[str, Any] = {"days": days}
        if include_legacy:
            params["include_legacy"] = "true"
        return self._get("/v1/narratives/rotation", params=params)

    def get_ai_substance(self, limit: int = 40) -> Any:
        return self._get("/v1/ai/substance", params={"limit": limit})

    def get_wrapper_basis(self, limit: int = 40) -> Any:
        return self._get("/v1/tokenized/basis", params={"limit": limit})

    def get_disclosures(self, symbol: str = "", limit: int = 50) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._get("/v1/disclosures", params=params)

    def get_category_rankings(self, category: str) -> Any:
        return self._get(f"/v1/categories/{self._seg(category)}/rankings")

    # --- analytics -------------------------------------------------------
    def get_correlation(self, symbol: str) -> Any:
        return self._get(f"/v1/analytics/correlation/{self._seg(symbol)}")

    def get_leading_indicators(self, symbol: str) -> Any:
        return self._get(f"/v1/analytics/leading-indicators/{self._seg(symbol)}")

    def get_trading_signals(self, symbol: Optional[str] = None) -> Any:
        if symbol:
            return self._get(f"/v1/analytics/signals/{self._seg(symbol)}")
        return self._get("/v1/analytics/signals")

    # --- predictions -----------------------------------------------------
    def get_prediction(self, symbol: str) -> Any:
        return self._get(f"/v1/predictions/assets/{self._seg(symbol)}")

    def get_top_opportunities(self) -> Any:
        return self._get("/v1/predictions/top-opportunities")

    # --- whales / on-chain ----------------------------------------------
    def get_social_dominance(self, hours: int = 168) -> Any:
        """Each asset's share of social attention over the window."""
        return self._get("/v1/social/dominance", {"hours": hours})

    def get_topic_rank(self, hours: int = 168, limit: int = 10) -> Any:
        """TopicRank leaderboard over the window."""
        return self._get("/v1/topics/rank", {"hours": hours, "limit": limit})

    def get_whale_transactions(self, limit: int = 25, symbol: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._get("/v1/whales/transactions", params=params)

    def get_exchange_flows(self, symbol: Optional[str] = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return self._get("/v1/whales/exchange-flows", params=params)

    def get_wallet_profile(self, address: str) -> Any:
        return self._get(f"/v1/whales/wallets/{self._seg(address)}")

    def get_entity_flows(self, hours: int = 168, limit: int = 20) -> Any:
        """Whale flow per labelled entity (exchange accumulation vs distribution)."""
        return self._get("/v1/whales/entities", {"hours": hours, "limit": limit})

    # --- metric registry (Phase 08 / C1) --------------------------------
    def list_metrics(self, category: str = "", available_only: bool = False) -> Any:
        """The metric registry, including what we CANNOT serve."""
        params: Dict[str, Any] = {}
        if category:
            params["category"] = category
        if available_only:
            params["available"] = "true"
        return self._get("/v1/metrics", params or None)

    def get_metric_metadata(self, slug: str) -> Any:
        """One metric's parity, category and caveat."""
        return self._get(f"/v1/metrics/{self._seg(slug)}")

    def get_metric_timeseries(self, slug: str, asset: str, from_: str = "utc_now-30d",
                              to: str = "utc_now", interval: str = "1d",
                              aggregation: str = "LAST") -> Any:
        """Timeseries for a metric and asset."""
        return self._get(f"/v1/metrics/{self._seg(slug)}/timeseries", {
            "slug": asset, "from": from_, "to": to,
            "interval": interval, "aggregation": aggregation,
        })

    # --- universe / coverage / labels (Stage F) --------------------------
    def get_chains(self) -> Any:
        """Per-chain coverage: tokens mapped, labels held, whales seen/attributed."""
        return self._get("/v1/chains")

    def get_coverage(self) -> Any:
        """Platform-wide data inventory and freshness timestamps."""
        return self._get("/v1/coverage")

    def search_universe(self, q: str, limit: int = 20) -> Any:
        """Search the whole asset universe by symbol or name."""
        return self._get("/v1/universe/search", {"q": q, "limit": limit})

    def get_asset_platforms(self, symbol: str) -> Any:
        """An asset's contract address on each chain it is deployed to."""
        return self._get(f"/v1/assets/{self._seg(symbol)}/platforms")

    def lookup_address(self, address: str) -> Any:
        """Attribution for one address across chains (entity, category, provenance)."""
        return self._get(f"/v1/labels/{self._seg(address)}")

    def list_labels(self, chain: str = "", entity: str = "",
                    category: str = "", limit: int = 50) -> Any:
        """Browse the labelled-address corpus."""
        params: Dict[str, Any] = {"limit": limit}
        for k, v in (("chain", chain), ("entity", entity), ("category", category)):
            if v:
                params[k] = v
        return self._get("/v1/labels", params)

    # --- NLP / sentiment -------------------------------------------------
    def get_aspect_sentiment(self, asset: str) -> Any:
        return self._get(f"/v1/nlp/aspects/{self._seg(asset)}")

    def analyze_sentiment(self, text: str) -> Any:
        return self._post("/v1/nlp/analyze", {"text": text})

    # --- flagship features ----------------------------------------------
    def get_signal_integrity(self, symbol: str) -> Any:
        """Signal Integrity (Real-vs-Fake Score) for an asset."""
        return self._get(f"/v1/assets/{self._seg(symbol)}/signal-integrity")

    def get_influencer_ledger(self, influencer_id: str) -> Any:
        """An influencer's accountability record (Predictor/Reactor, hit rate)."""
        return self._get(f"/v1/influencers/{self._seg(influencer_id)}/ledger")

    def get_influencer_leaderboard(self) -> Any:
        """The influencer accountability leaderboard (ranked by track record)."""
        return self._get("/v1/influencers/leaderboard")

    # --- social ----------------------------------------------------------
    def get_influencers(self, asset: str) -> Any:
        return self._get(f"/v1/social/influencers/{self._seg(asset)}")

    def get_coordinated_campaigns(self) -> Any:
        return self._get("/v1/social/campaigns")

    # --- screener (C5) ---------------------------------------------------
    # The endpoint Santiment charges for. Exposing it to agents is the point of
    # the whole MCP surface: an agent that can filter 1,924 assets server-side
    # does not have to pull them all and reason over the pile.
    def screen(self, filter_: str = "", sort: str = "", limit: int = 50) -> Any:
        params: Dict[str, Any] = {"limit": limit}
        if filter_:
            params["filter"] = filter_
        if sort:
            params["sort"] = sort
        return self._get("/v1/screener", params)

    def screener_fields(self) -> Any:
        return self._get("/v1/screener/fields")

    # --- market data -----------------------------------------------------
    def get_ohlcv(self, symbol: str = "", limit: int = 100) -> Any:
        if symbol:
            return self._get(f"/v1/ohlcv/{self._seg(symbol)}", {"limit": limit})
        return self._get("/v1/ohlcv", {"limit": limit})

    def get_trending(self) -> Any:
        return self._get("/v1/trending")

    # --- metrics, plural -------------------------------------------------
    # One call for many assets. The single-asset tool loops in the agent's head
    # and costs a round trip each time; this is the reason /multi exists.
    def get_metric_timeseries_multi(self, slug: str, assets: str,
                                    from_: str = "utc_now-30d",
                                    to_: str = "utc_now",
                                    interval: str = "1d") -> Any:
        return self._get(f"/v1/metrics/{self._seg(slug)}/timeseries/multi", {
            "assets": assets, "from": from_, "to": to_, "interval": interval})

    def get_metrics_batch(
        self,
        metrics: Any,
        assets: Any,
        from_: str = "",
        to_: str = "",
        interval: str = "1d",
    ) -> Any:
        """Several metrics for several assets in one call.

        THIS USED `_get` AGAINST A POST-ONLY ROUTE, so the tool returned 404
        every time it was called — `api.POST("/metrics/batch", …)` in
        batch_metric_handler.go. It also sent `asset` (singular, a string) where
        the handler binds `assets` (plural, a list) and would have 400'd on the
        shape even had the method been right.

        Two mismatches in one call, and nothing caught them because no test and
        no caller ever exercised this tool against a running API.
        """
        body: Dict[str, Any] = {
            "metrics": [metrics] if isinstance(metrics, str) else list(metrics),
            "assets": [assets] if isinstance(assets, str) else list(assets),
            "interval": interval,
        }
        if from_:
            body["from"] = from_
        if to_:
            body["to"] = to_
        return self._post("/v1/metrics/batch", body)

    # --- revisions (C9) --------------------------------------------------
    # A metric that changed after publication is a fact about our data, and an
    # agent quoting yesterday's number needs to be able to find out.
    def get_asset_revisions(self, symbol: str) -> Any:
        return self._get(f"/v1/assets/{self._seg(symbol)}/revisions")

    # --- nlp -------------------------------------------------------------
    def get_entities(self, asset: str) -> Any:
        return self._get(f"/v1/nlp/entities/{self._seg(asset)}")

    def get_sentiment_trends(self, asset: str) -> Any:
        return self._get(f"/v1/nlp/trends/{self._seg(asset)}")

    def get_bot_detections(self) -> Any:
        return self._get("/v1/social/bot-detection")

    # --- analytics -------------------------------------------------------
    def get_creator_rankings(self, limit: int = 25) -> Any:
        return self._get("/v1/analytics/creators/rank", {"limit": limit})

    # --- the C8 LLM product layer ----------------------------------------
    # All of this was computed by the pipeline and had no endpoint until now,
    # which meant no agent could reach any of it.
    def get_stories(self, limit: int = 20) -> Any:
        return self._get("/v1/stories", {"limit": limit})

    def get_narratives(self, limit: int = 25) -> Any:
        return self._get("/v1/narratives", {"limit": limit})

    def list_reports(self) -> Any:
        return self._get("/v1/reports")

    def get_report(self, symbol: str) -> Any:
        return self._get(f"/v1/reports/{self._seg(symbol)}")

    def resolve_ticker(self, ticker: str) -> Any:
        return self._get(f"/v1/tickers/{self._seg(ticker)}/resolve")

    def get_social_coverage(self, band: int = 300) -> Any:
        return self._get("/v1/coverage/social", {"band": band})

    def list_nl_screens(self, limit: int = 25) -> Any:
        return self._get("/v1/screen/nl", {"limit": limit})

    def get_agent_findings(self, limit: int = 50) -> Any:
        return self._get("/v1/agents/findings", {"limit": limit})

    def close(self) -> None:
        self._client.close()

    # --- on-chain, SQL and the surfaces added 2026-08-21/22 ------------------
    #
    # These were served by /v1 and NOT reachable from any MCP tool. The gap
    # mattered most for /v1/sql: llms.txt tells agents it is the escape hatch
    # for questions the REST surface cannot express, and the MCP server — the
    # thing an agent actually calls — had no tool for it. The product advertised
    # a capability to agents and then withheld it.

    def run_sql(self, query: str) -> Any:
        """Read-only SELECT. 15s timeout, 10k row cap, truncation reported."""
        return self._post("/v1/sql", {"query": query})

    def get_sql_schema(self) -> Any:
        """Relations and columns queryable via run_sql, plus the rules."""
        return self._get("/v1/sql/schema")

    def get_hodl_waves(self, limit: int = 260) -> Any:
        """Bitcoin supply by coin age over time (utxo_cohorts, 9,033,064 rows)."""
        return self._get("/v1/chain/hodl-waves", params={"limit": limit})

    def get_exchange_netflow(self, limit: int = 40) -> Any:
        """Per-token flow onto and off exchanges, with net_usd where priceable."""
        return self._get("/v1/chain/exchange-netflow", params={"limit": limit})

    def get_constellation(self, limit: int = 150) -> Any:
        """Asset co-mention graph: nodes, edges and what was filtered."""
        return self._get("/v1/graph/constellation", params={"limit": limit})

    def get_social_posts(self, platform: str | None = None, limit: int = 50) -> Any:
        """Collected social posts, optionally filtered by platform."""
        params: dict = {"limit": limit}
        if platform:
            params["platform"] = platform
        return self._get("/v1/social/posts", params=params)

    def get_similar_posts(self, post_id: int) -> Any:
        """Embedding-nearest posts. Read the BAND, never the raw cosine."""
        return self._get(f"/v1/social/posts/{post_id}/similar")

    def get_asset_social_signal(self, symbol: str, days: int = 30) -> Any:
        """Per-asset social signal series; `available` states whether we hold it."""
        return self._get(f"/v1/assets/{symbol}/social-signal", params={"days": days})

    def get_metric_revisions(self, limit: int = 50) -> Any:
        """Corpus-wide restatements — when a published number changed, and why."""
        return self._get("/v1/revisions", params={"limit": limit})

    def get_emerging_dex_pairs(self, min_liquidity_usd: int = 50000) -> Any:
        """New DEX pairs above a liquidity floor."""
        return self._get("/v1/dex/emerging",
                         params={"min_liquidity_usd": min_liquidity_usd})

    def get_exchange_listings(self, limit: int = 40) -> Any:
        """Recent exchange listing announcements."""
        return self._get("/v1/listings", params={"limit": limit})

    def get_address_watches(self) -> Any:
        """Watched addresses and the per-chain coverage behind them."""
        return self._get("/v1/watchlists/addresses")

    def get_address_coverage(self) -> Any:
        """What we see, what we miss, and what an empty event feed means."""
        return self._get("/v1/watchlists/addresses/coverage")

    def get_address_events(self, limit: int = 50) -> Any:
        """Events on watched addresses. Read coverage before concluding silence."""
        return self._get("/v1/watchlists/addresses/events", params={"limit": limit})

    def get_bq_spend(self) -> Any:
        """What the on-chain backfills cost in BigQuery, against the cap."""
        return self._get("/v1/chain/bq-spend")

    def get_story_posts(self, story_id: int) -> Any:
        """The posts a story was summarised from — its receipts."""
        return self._get(f"/v1/stories/{story_id}/posts")
