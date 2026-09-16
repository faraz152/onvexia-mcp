<div align="center">

<img src="assets/logo.svg" alt="Onvexia crypto MCP server" width="120" height="120">

# Onvexia — Crypto Research & Market Intelligence, for AI

### Is the hype real? Who is accumulating? Was that influencer ever right?

**Crypto sentiment, whale tracking and on-chain analytics for traders, investors and AI agents**
66 read-only tools · 2,300+ coins · works in Claude, ChatGPT and Cursor · no install, no API key

[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-com.onvexia%2Fonvexia-22D3EE)](https://registry.modelcontextprotocol.io/v0/servers?search=onvexia)
[![Smithery](https://img.shields.io/badge/Smithery-onvexia-22D3EE)](https://smithery.ai/server/farazgr8007/onvexia)
[![x402](https://img.shields.io/badge/x402-pay%20per%20call%20in%20USDC-22D3EE)](https://onvexia.com/.well-known/x402)
[![License: MIT](https://img.shields.io/badge/license-MIT-22D3EE)](LICENSE)

</div>

---

## Connect it in one line

```bash
claude mcp add --transport http onvexia https://onvexia.com/mcp
```

That is the whole setup. The server is hosted — nothing to clone, nothing to
run, no key to request.

<details>
<summary><b>ChatGPT, Cursor, Windsurf, Cline, and any other MCP client</b></summary>

Any client that speaks **Streamable HTTP**:

```json
{
  "mcpServers": {
    "onvexia": {
      "type": "http",
      "url": "https://onvexia.com/mcp"
    }
  }
}
```

Or install across clients with [Smithery](https://smithery.ai/server/farazgr8007/onvexia):

```bash
npx -y @smithery/cli install farazgr8007/onvexia
```

</details>

## The problem this solves

**If you trade or invest:** by the time a coin is trending on your timeline, you
cannot tell whether 40,000 mentions came from 40,000 people or 400 bots, whether
the wallets buying are accumulating or are exchange hot wallets about to sell,
or whether the account that called it has ever been right before. That
information exists on-chain and in public posts. It is just not in one place at
the moment you need it.

**If you build with AI:** an LLM asked about a token answers from training data
months old, and — worse — cannot tell you when it *does not know*. A quiet market
and a hole in its knowledge look identical in the answer you get back.

Onvexia gives both live measurements, and makes the answer say which is which.

## What you can ask it

Once connected, these are ordinary questions in plain English:

**Trading and research**
- *"Is the hype around $TOKEN real, or is it bots?"*
- *"Which wallets moved the most ETH onto exchanges this week?"*
- *"Find coins under $100M market cap with rising social volume and a flat price."*
- *"What narratives is money rotating into right now?"*
- *"Show me new DEX pairs above $250k liquidity from the last 48 hours."*

**Due diligence**
- *"What unlocks are coming for $TOKEN, and how concentrated are the holders?"*
- *"Does this AI-sector project actually ship code, against how much attention it gets?"*
- *"Are there SEC filings or court dockets naming this issuer?"*

**Accountability**
- *"Did this influencer call the move before it happened, or after?"*
- *"Rank the top crypto influencers by measured accuracy, not follower count."*

**Sanity checks**
- *"What data do you actually have on this token?"*

## What it does

Onvexia is a crypto research and market intelligence platform for traders, investors, analysts and AI agents. Find out whether a token's hype is real or manufactured, which wallets are quietly accumulating or dumping, which altcoins have social momentum building before the price moves, and whether the influencer calling it has ever actually been right.

Use it through any AI assistant — Claude, ChatGPT, Cursor — by connecting one URL. No install, no API key, no signup.

Use Onvexia to:

▪ Check if crypto hype is real or bot-driven before you buy ▪ Spot pump-and-dump and coordinated shill campaigns while they are forming ▪ Track whale wallets, smart money and exchange inflows/outflows across 80,000+ labelled addresses ▪ Find trending altcoins early with social volume and sentiment from X/Twitter, Reddit, Farcaster and Bluesky ▪ Rank 2,300+ coins by Galaxy Score and AltRank, with the components behind every score ▪ Check an influencer's real track record — did they predict the move, or react to it ▪ Do token due diligence: unlock schedules, treasury, TVL, revenue, holder concentration ▪ Screen 2,300+ cryptocurrencies on social, on-chain and fundamental filters ▪ Find emerging DEX pairs and new exchange listings before they trend ▪ Query the entire dataset directly with read-only SQL

The MCP is public, read-only, and requires no API key.

Every response separates what was measured from what is not held. Sections carry a `state`, coverage counts ship alongside the results, and a null label means no label is held — never that a wallet or an influencer is safe. An empty list is never by itself evidence that nothing happened.

Galaxy Score and AltRank measure attention and social-market health. They are not valuation, price targets, or investment advice. Nothing here is a recommendation to buy or sell.

**MCP endpoint:** https://onvexia.com/mcp
**API documentation:** https://onvexia.com/openapi.json
**Agent contract:** https://onvexia.com/llms.txt
**Pricing manifest:** https://onvexia.com/.well-known/x402

## Try it right now, without installing anything

```console
$ curl -s -X POST https://onvexia.com/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
         "params":{"name":"get_data_coverage","arguments":{}}}'

{
  "assets": 2308,
  "assets_priced": 2308,
  "labelled_addresses": 80062,
  "whale_transactions": 118214,
  "social_posts": 663639,
  "chains_with_onchain_flows": 7
}
```

A real response from the live endpoint. The numbers move — the corpus grew by
1,376 posts between two runs an hour apart.

**`get_data_coverage` is the tool to call first.** It reports what is actually
held right now, so an agent can tell a quiet market from a hole in the data
before it reasons about either. There is also a pure-stdlib example in
[`examples/quickstart.py`](examples/quickstart.py).

## All 66 tools

| Group | Tools |
|---|---|
| **Assets** | `get_asset` · `search_assets` · `get_asset_platforms` · `get_asset_revisions` · `resolve_ticker` · `get_entities` |
| **Coverage** | `get_data_coverage` · `get_chain_coverage` · `get_social_coverage` · `get_address_coverage` |
| **Scores** | `get_asset_scores` · `get_top_galaxy_scores` · `get_top_altranks` · `get_creator_rankings` |
| **Social** | `get_social_dominance` · `get_topic_rank` · `get_influencers` · `get_trending_assets` · `get_social_posts` · `get_similar_posts` · `get_asset_social_signal` |
| **Sentiment** | `analyze_sentiment` · `get_aspect_sentiment` · `get_sentiment_trends` |
| **Signal integrity** | `get_signal_integrity` · `get_bot_detections` · `get_coordinated_campaigns` · `get_ai_substance` |
| **Influencer ledger** | `get_influencer_ledger` · `get_influencer_leaderboard` |
| **Fundamentals** | `get_asset_fundamentals` · `get_asset_technicals` · `get_disclosures` |
| **On-chain** | `get_whale_transactions` · `get_exchange_flows` · `get_exchange_netflow` · `get_entity_flows` · `lookup_address` · `list_labelled_addresses` · `get_address_events` · `get_hodl_waves` · `get_constellation` |
| **Market** | `get_ohlcv` · `get_emerging_dex_pairs` · `get_exchange_listings` · `get_wrapper_basis` |
| **Analytics** | `get_correlation` · `get_leading_indicators` |
| **Metrics** | `list_metrics` · `get_metric_metadata` · `get_metric_timeseries` · `get_metric_timeseries_multi` · `get_metrics_batch` · `get_metric_revisions` |
| **Screener** | `screen_assets` · `screener_fields` · `list_nl_screens` |
| **Narrative** | `get_trending_stories` · `get_story_posts` · `get_narrative_clusters` · `get_narrative_rotation` |
| **Research** | `list_research_reports` · `get_research_report` |
| **SQL** | `run_sql` · `get_sql_schema` |
| **Agents** | `get_agent_findings` |

Every tool carries a title and `readOnlyHint`, and no description is shorter
than 80 characters. That is enforced, not maintained: the server refuses to
build if a tool is missing from `TOOL_TITLES`, and
[`tests/test_tool_metadata.py`](tests/test_tool_metadata.py) asserts the rest by
reading the surface back through `list_tools()` — the same call your client
makes. **Nothing here writes, and no tool can move funds.**

## Free, and pay-per-call for agents with no account

Most of the surface is free and unauthenticated. Metered endpoints can be paid
per call with [x402](https://x402.org) — USDC on Base, via Coinbase's CDP
facilitator — so an autonomous agent can use paid data **without a human ever
creating an account**:

```bash
export X402_CLIENT_PRIVATE_KEY=0x...   # a BURNER wallet, never a treasury key
```

$0.001–$0.01 per call, published per endpoint in
[`/.well-known/x402`](https://onvexia.com/.well-known/x402) and as
`x-payment-info` on every priced operation in `/openapi.json`.

Three properties worth knowing before pointing it at mainnet:

- **It pays at most once per request.** A retry loop around a payment endpoint
  is a wallet-drainer; a second 402 is raised, not paid again.
- **It refuses to overpay.** The challenge is written by the *server*, so
  `max_payment_atomic` caps what one call can sign away.
- **You are never charged for a failure.** A response that is not 2xx is never
  settled — the signed authorisation simply expires.

## Honest data, enforced

This is the part most data APIs get wrong, and it matters more for an agent than
for a human — a human notices an empty chart, an LLM confidently summarises it.

- Sections carry a `state`: `measured`, `not_held`, or `failed`.
- Coverage counts ship **with** the results, not on a status page.
- A null label means *we hold no label*. It never means the wallet is clean.
- "We never looked" and "we looked and found nothing" are different values.
- Endpoints that cannot return data say so in the response — and are deliberately
  excluded from the paid catalogue rather than sold.

## Run it yourself

You do not need to; the hosted endpoint is the supported path. This repository
is the same server that runs it.

```bash
pip install -r requirements.txt

# stdio, for a local client
CRYPTO_INTEL_API_URL=https://onvexia.com python3 server.py

# Streamable HTTP, the way the hosted endpoint runs
CRYPTO_INTEL_API_URL=https://onvexia.com MCP_HTTP_PORT=8091 python3 http_server.py
```

`http_server.py` **refuses to start** if `CRYPTO_INTEL_API_KEY` or
`X402_CLIENT_PRIVATE_KEY` is set — one hosted instance serves every caller, so a
shared key would meter everyone against one account and a shared wallet would
pay strangers' payment challenges. Credentials are per request. See
[SECURITY.md](SECURITY.md).

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q          # 50 tests, no network
```

## Keywords

**For traders and investors:** crypto research tool · altcoin research · crypto
market analysis · trending altcoins · crypto whale alerts · whale wallet
tracker · smart money tracking · exchange inflow outflow · pump and dump
detection · is this crypto a scam · crypto due diligence · token unlock
schedule · holder concentration · crypto screener · social volume · crypto
sentiment analysis · Galaxy Score · AltRank · crypto influencer accuracy ·
find early crypto gems · DEX pair scanner · new exchange listings

**For developers and AI agents:** crypto MCP server · Model Context Protocol
crypto · crypto API · on-chain analytics API · crypto market intelligence API ·
bot detection crypto Twitter · Claude MCP crypto · ChatGPT crypto data · Cursor
MCP · AI agent crypto tools · x402 · pay per call API · USDC on Base · free
crypto API no API key

## License

MIT — see [LICENSE](LICENSE).
