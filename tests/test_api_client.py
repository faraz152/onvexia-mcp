"""
Tests for the MCP server's API client — Phase 04.

Uses httpx.MockTransport to assert each method hits the correct /v1 endpoint and
method, with no network. This is the routing contract the MCP tools depend on.
"""

import os
import sys

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api_client import OnvexiaClient, PaymentRequired  # noqa: E402

BASE = "http://testhost:8080"


def _client_capturing(recorder):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder["method"] = request.method
        recorder["path"] = request.url.path
        # raw_path keeps percent-encoding; .path decodes it, so only raw_path can
        # tell an escaped %2F from a real path separator.
        recorder["raw_path"] = request.url.raw_path.decode().split("?")[0]
        recorder["query"] = dict(request.url.params)
        if request.method == "POST":
            import json
            recorder["body"] = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"ok": True})
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return OnvexiaClient(base_url=BASE, http_client=http)


def test_get_asset_scores_path():
    rec = {}
    c = _client_capturing(rec)
    assert c.get_asset_scores("BTC") == {"ok": True}
    assert rec["method"] == "GET"
    assert rec["path"] == "/v1/assets/BTC/scores"


def test_top_galaxy_scores_query():
    rec = {}
    c = _client_capturing(rec)
    c.get_top_galaxy_scores(limit=25)
    assert rec["path"] == "/v1/scores/galaxy/top"
    assert rec["query"] == {"limit": "25"}


def test_prediction_and_opportunities_paths():
    rec = {}
    c = _client_capturing(rec)
    c.get_prediction("eth")
    assert rec["path"] == "/v1/predictions/assets/eth"
    c.get_top_opportunities()
    assert rec["path"] == "/v1/predictions/top-opportunities"


def test_whale_transactions_with_symbol_filter():
    rec = {}
    c = _client_capturing(rec)
    c.get_whale_transactions(limit=50, symbol="BTC")
    assert rec["path"] == "/v1/whales/transactions"
    assert rec["query"] == {"limit": "50", "symbol": "BTC"}


def test_wallet_profile_path_encoding():
    rec = {}
    c = _client_capturing(rec)
    c.get_wallet_profile("0xAbC123")
    assert rec["path"] == "/v1/whales/wallets/0xAbC123"


def test_analyze_sentiment_is_post_with_body():
    rec = {}
    c = _client_capturing(rec)
    c.analyze_sentiment("bitcoin looks strong")
    assert rec["method"] == "POST"
    assert rec["path"] == "/v1/nlp/analyze"
    assert rec["body"] == {"text": "bitcoin looks strong"}


def test_trading_signals_with_and_without_symbol():
    rec = {}
    c = _client_capturing(rec)
    c.get_trading_signals()
    assert rec["path"] == "/v1/analytics/signals"
    c.get_trading_signals("SOL")
    assert rec["path"] == "/v1/analytics/signals/SOL"


def test_aspect_sentiment_and_influencers_paths():
    rec = {}
    c = _client_capturing(rec)
    c.get_aspect_sentiment("BTC")
    assert rec["path"] == "/v1/nlp/aspects/BTC"
    c.get_influencers("ETH")
    assert rec["path"] == "/v1/social/influencers/ETH"


def test_flagship_paths():
    rec = {}
    c = _client_capturing(rec)
    c.get_signal_integrity("BTC")
    assert rec["path"] == "/v1/assets/BTC/signal-integrity"
    c.get_influencer_ledger("alice")
    assert rec["path"] == "/v1/influencers/alice/ledger"
    c.get_influencer_leaderboard()
    assert rec["path"] == "/v1/influencers/leaderboard"


def test_api_key_uses_x_api_key_not_authorization():
    """The key goes in X-API-Key, and the Authorization slot must stay FREE.

    The gateway resolves `Authorization: Bearer …` as a Supabase JWT. Sending an
    API key there made the two identity mechanisms collide, so the client was
    changed to X-API-Key; this test pins that and would catch a regression back
    to the colliding header.
    """
    rec = {}

    def handler(request: httpx.Request) -> httpx.Response:
        rec["auth"] = request.headers.get("Authorization")
        rec["api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = OnvexiaClient(base_url=BASE, http_client=http, api_key="secret123")
    c.get_asset("BTC")
    assert rec["api_key"] == "secret123"
    assert rec["auth"] is None, "Authorization must stay free for the JWT"


def test_stage_f_paths():
    rec = {}
    c = _client_capturing(rec)
    c.get_chains()
    assert rec["path"] == "/v1/chains"
    c.get_coverage()
    assert rec["path"] == "/v1/coverage"
    c.search_universe("bitcoin", 5)
    assert rec["path"] == "/v1/universe/search"
    c.get_asset_platforms("USDC")
    assert rec["path"] == "/v1/assets/USDC/platforms"
    c.lookup_address("0xABC")
    assert rec["path"] == "/v1/labels/0xABC"
    c.list_labels(chain="ethereum", category="exchange")
    assert rec["path"] == "/v1/labels"
    c.get_entity_flows()
    assert rec["path"] == "/v1/whales/entities"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))


# --- routing contract for the C1 MCP expansion -------------------------------
# Every one of these is a path an agent will hit and a typo nobody would notice:
# a wrong path returns the API's 404 body, which looks like "no data" rather than
# "wrong endpoint". Asserting the route is the only thing that distinguishes them.

def test_screen_builds_filter_query():
    rec = {}
    c = _client_capturing(rec)
    c.screen(filter_="market_cap:gt:1000000000,funding_rate:lt:0",
             sort="market_cap", limit=10)
    assert rec["path"] == "/v1/screener"
    assert rec["query"]["filter"] == "market_cap:gt:1000000000,funding_rate:lt:0"
    assert rec["query"]["sort"] == "market_cap"
    assert rec["query"]["limit"] == "10"


def test_screen_omits_empty_filter():
    # An empty filter must not become `filter=`, which the handler would try to
    # parse as a term and reject.
    rec = {}
    c = _client_capturing(rec)
    c.screen()
    assert "filter" not in rec["query"]
    assert "sort" not in rec["query"]


def test_screener_fields_path():
    rec = {}
    c = _client_capturing(rec)
    c.screener_fields()
    assert rec["path"] == "/v1/screener/fields"


def test_ohlcv_with_and_without_symbol():
    rec = {}
    c = _client_capturing(rec)
    c.get_ohlcv("BTC", limit=5)
    assert rec["path"] == "/v1/ohlcv/BTC"
    c.get_ohlcv()
    assert rec["path"] == "/v1/ohlcv"


def test_trending_path():
    rec = {}
    c = _client_capturing(rec)
    c.get_trending()
    assert rec["path"] == "/v1/trending"


def test_metric_timeseries_multi_path_and_params():
    rec = {}
    c = _client_capturing(rec)
    c.get_metric_timeseries_multi("price_usd", "BTC,ETH", interval="1h")
    assert rec["path"] == "/v1/metrics/price_usd/timeseries/multi"
    assert rec["query"]["assets"] == "BTC,ETH"
    assert rec["query"]["interval"] == "1h"


def test_metrics_batch_path():
    """batch is a POST with a JSON body, and the fields are PLURAL.

    This test used to assert the opposite — a GET with `metrics` as a query
    parameter — and passed, because MockTransport answers 200 to anything. The
    real route is `api.POST("/metrics/batch")` binding `{metrics: [], assets:
    []}`, so the client 404'd on every call while the test stayed green. A mock
    that never sees the server cannot tell you the contract is wrong; it can
    only tell you the client is self-consistent.

    Asserting the METHOD and the BODY SHAPE is what makes this test able to fail
    for the reason that mattered.
    """
    rec = {}
    c = _client_capturing(rec)
    c.get_metrics_batch(["price_usd", "social_volume"], ["BTC"])
    assert rec["method"] == "POST"
    assert rec["path"] == "/v1/metrics/batch"
    assert rec["body"]["metrics"] == ["price_usd", "social_volume"]
    assert rec["body"]["assets"] == ["BTC"]


def test_metrics_batch_accepts_bare_strings():
    """A single metric/asset as a string still becomes a one-element list.

    Agents pass `"BTC"` far more often than `["BTC"]`, and the old signature
    took strings, so coercing keeps every existing caller working against the
    corrected contract.
    """
    rec = {}
    c = _client_capturing(rec)
    c.get_metrics_batch("price_usd", "BTC")
    assert rec["body"]["metrics"] == ["price_usd"]
    assert rec["body"]["assets"] == ["BTC"]


def test_payment_required_is_actionable():
    """A 402 must arrive as terms an agent can act on, not a bare HTTP error.

    The gateway answers unauthenticated calls with a well-formed x402
    challenge. httpx's raise_for_status() flattened it to "402 Payment
    Required", which tells an LLM nothing — not the price, not the asset, not
    that an API key is also an option.
    """
    challenge = {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact", "network": "base", "maxAmountRequired": "100",
            "payTo": "0xPAYTO", "asset": "0xUSDC", "extra": {"name": "USDC"},
        }],
    }

    def handler(request):
        return httpx.Response(402, json=challenge)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = OnvexiaClient(base_url=BASE, http_client=http)
    try:
        c.get_trending()
    except PaymentRequired as e:
        assert e.amount_atomic == "100"
        assert e.asset_name == "USDC"
        assert e.network == "base"
        assert e.pay_to == "0xPAYTO"
        assert e.challenge == challenge, "the raw challenge must survive"
        assert "CRYPTO_INTEL_API_KEY" in str(e), "must name the key route out"
        assert "X-PAYMENT" in str(e), "must name the x402 route out"
    else:
        raise AssertionError("402 did not raise PaymentRequired")


def test_nlp_and_social_paths():
    rec = {}
    c = _client_capturing(rec)
    c.get_entities("BTC");            assert rec["path"] == "/v1/nlp/entities/BTC"
    c.get_sentiment_trends("BTC");    assert rec["path"] == "/v1/nlp/trends/BTC"
    c.get_bot_detections();           assert rec["path"] == "/v1/social/bot-detection"
    c.get_creator_rankings();         assert rec["path"] == "/v1/analytics/creators/rank"
    c.get_asset_revisions("BTC");     assert rec["path"] == "/v1/assets/BTC/revisions"


def test_slug_with_slash_is_escaped():
    # _seg exists because a slug or symbol containing a slash would otherwise
    # silently retarget the request at a different endpoint.
    #
    # Asserted on raw_path, NOT path: httpx decodes `.path`, so a correctly
    # escaped %2F reads back as a literal "/" there and the test would fail on
    # working code. The first version of this test did exactly that.
    rec = {}
    c = _client_capturing(rec)
    c.get_metric_timeseries_multi("a/b", "BTC")
    assert rec["raw_path"] == "/v1/metrics/a%2Fb/timeseries/multi"


def test_c8_product_layer_paths():
    # The C8 outputs were computed for weeks with no endpoint. These assert the
    # routes an agent reaches them through.
    rec = {}
    c = _client_capturing(rec)
    c.get_stories(limit=5)
    assert rec["path"] == "/v1/stories" and rec["query"]["limit"] == "5"
    c.get_narratives();          assert rec["path"] == "/v1/narratives"
    c.list_reports();            assert rec["path"] == "/v1/reports"
    c.get_report("BTC");         assert rec["path"] == "/v1/reports/BTC"
    c.resolve_ticker("TIA");     assert rec["path"] == "/v1/tickers/TIA/resolve"
    c.get_social_coverage(500)
    assert rec["path"] == "/v1/coverage/social" and rec["query"]["band"] == "500"
    c.list_nl_screens();         assert rec["path"] == "/v1/screen/nl"
    c.get_agent_findings();      assert rec["path"] == "/v1/agents/findings"


# --- x402 payment ---------------------------------------------------------
# Proven end to end on Base Sepolia 2026-08-21: an agent with NO API key paid
# 100 atomic units of USDC and received 20 rows. On-chain, the client wallet
# went 20,000,000 -> 19,999,900 and payTo 0 -> 100. These tests pin the parts
# that were wrong on the way there, so they cannot regress silently.

_CHALLENGE = {
    "x402Version": 1,
    "accepts": [{
        "scheme": "exact", "network": "base-sepolia", "maxAmountRequired": "100",
        "payTo": "0x54F57D0FE2FFBa8C8111fc89D4a0E624D53Dd0e3",
        "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "maxTimeoutSeconds": 60, "extra": {"name": "USDC", "version": "2"},
    }],
}
# A throwaway key. Never funded, never used anywhere but this test.
_TEST_KEY = "0x" + "11" * 32


def _sign(challenge=None, cap=10_000):
    import api_client as ac
    return ac._sign_x402_payment(challenge or _CHALLENGE, _TEST_KEY, cap)


def test_x402_signature_is_0x_prefixed():
    """eth-account 0.13 returns BARE hex from .hex(); the facilitator needs 0x.

    This exact omission cost a real debugging round: the payment was signed
    correctly, sent, and rejected with a second 402 carrying no explanation
    from our side. The signature was `c659…` where `0xc659…` was required.
    """
    import base64, json
    payload = json.loads(base64.b64decode(_sign()))
    assert payload["payload"]["signature"].startswith("0x")
    # 65 bytes: r(32) + s(32) + v(1), hex-encoded, plus the prefix.
    assert len(payload["payload"]["signature"]) == 132


def test_x402_payload_shape_matches_the_facilitator():
    import base64, json
    p = json.loads(base64.b64decode(_sign()))
    assert p["scheme"] == "exact" and p["network"] == "base-sepolia"
    auth = p["payload"]["authorization"]
    assert auth["to"] == _CHALLENGE["accepts"][0]["payTo"]
    assert auth["value"] == "100"
    assert auth["nonce"].startswith("0x") and len(auth["nonce"]) == 66
    # validBefore bounds the replay window; without it a captured signature is
    # good forever.
    assert int(auth["validBefore"]) > int(auth["validAfter"])


def test_x402_refuses_to_overpay():
    """The SERVER writes the challenge, so an unbounded client signs whatever
    it is asked — including a demand for the whole wallet."""
    greedy = {"x402Version": 1, "accepts": [dict(_CHALLENGE["accepts"][0],
                                                 maxAmountRequired="999999999")]}
    try:
        _sign(greedy)
    except RuntimeError as e:
        assert "refusing to pay" in str(e)
    else:
        raise AssertionError("signed a payment above the cap")


def test_x402_rejects_unknown_network():
    """chainId is part of the EIP-712 domain, so signing for an unknown network
    would produce a signature valid nowhere — better to refuse than to emit it."""
    bad = {"x402Version": 1, "accepts": [dict(_CHALLENGE["accepts"][0], network="ethereum")]}
    try:
        _sign(bad)
    except RuntimeError as e:
        assert "unknown x402 network" in str(e)
    else:
        raise AssertionError("signed for an unsupported network")


def test_402_without_a_wallet_still_raises_actionable_error():
    """No wallet key configured: the client must not silently swallow the 402."""
    def handler(request):
        return httpx.Response(402, json=_CHALLENGE)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = OnvexiaClient(base_url=BASE, http_client=http, wallet_private_key="")
    try:
        c.get_trending()
    except PaymentRequired as e:
        assert e.amount_atomic == "100"
    else:
        raise AssertionError("no PaymentRequired raised")


def test_402_with_a_wallet_pays_exactly_once():
    """A retry LOOP around a payment endpoint drains the wallet. One attempt."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(402, json=_CHALLENGE)   # reject the payment too
        return httpx.Response(402, json=_CHALLENGE)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = OnvexiaClient(base_url=BASE, http_client=http, wallet_private_key=_TEST_KEY)
    try:
        c.get_trending()
    except PaymentRequired:
        pass
    assert calls["n"] == 2, f"expected 1 unpaid + 1 paid attempt, got {calls['n']}"

