#!/usr/bin/env python3
"""
Crypto Intel MCP Server — Phase 04 (Distribution, master plan §16 Stage 3a).

Exposes the platform's `/v1` API as MCP tools so AI agents (Claude, ChatGPT,
Gemini) can discover and call crypto social + on-chain intelligence in one click.
This is the platform's PRIMARY agent-distribution channel.

Thin translation layer: every tool delegates to OnvexiaClient (api_client.py),
which calls the Go API. Run over stdio:

    CRYPTO_INTEL_API_URL=https://api.example.com python3 server.py

The `mcp` package is imported lazily so api_client.py stays testable without it.
"""

from __future__ import annotations

import os
from typing import Optional

from api_client import OnvexiaClient


def _server_class():
    """Resolve the decorator-style server class across MCP SDK versions.

    SDK 1.x exposes `mcp.server.fastmcp.FastMCP`; SDK 2.x renamed it to
    `mcp.server.MCPServer`. Both support the `@server.tool()` decorator, so we
    accept either rather than pinning users to one SDK generation.
    """
    try:                                            # SDK 2.x
        from mcp.server import MCPServer            # type: ignore
        return MCPServer
    except ImportError:
        pass
    try:                                            # SDK 1.x
        from mcp.server.fastmcp import FastMCP      # type: ignore
        return FastMCP
    except ImportError as e:                        # neither available
        raise ImportError(
            "No MCP server class found. Install the SDK: pip install 'mcp>=1.2.0'"
        ) from e


# ---------------------------------------------------------------------------
# Tool presentation metadata
# ---------------------------------------------------------------------------
#
# WHY THIS IS A TABLE AND A WRAPPER RATHER THAN 68 HAND-EDITED DECORATORS.
#
# Aggregators (Glama, Smithery, the Official Registry) score an MCP server on
# its WEAKEST tool, not its average — one tool with no title drags the badge for
# all of them. Audited 2026-09-16, before this existed: 69 tools, 0 titles,
# 0 annotations, 23 descriptions under 80 characters. Every one of those is a
# thing somebody forgot on the day they added a tool, which is exactly the
# failure a per-decorator convention produces.
#
# So the title is REQUIRED BY CONSTRUCTION: `_titled_tool` raises KeyError at
# import time for a tool that is not in TOOL_TITLES. A new tool cannot be added
# without one — the server refuses to build. That is the difference between a
# constraint and a reminder (CLAUDE.md), and it is why this is not just a
# `title=` kwarg sprinkled 68 times.
#
# THE READ-ONLY HINT IS A PROPERTY OF THE WHOLE SURFACE, not a per-tool choice.
# Anthropic's connector policy forbids a tool that moves money or crypto, and
# every tool here is a GET against /v1 — the x402 wallet in api_client.py pays
# for OUR OWN request and is never reachable as a tool. Declaring it once, in
# one place, means there is no decorator where somebody can quietly declare
# otherwise. `test_tool_metadata.py` asserts it holds for all of them.

_TOOL_GROUPS_NOTE = """Titles are "Group · Name" so a client that sorts or
groups by title gets a usable menu out of 68 tools. MCP has no namespace
primitive; the title is the surface a human actually reads."""

TOOL_TITLES = {
    # Assets, entities and coverage ----------------------------------------
    "get_asset":                   "Assets · Profile",
    "search_assets":               "Assets · Search",
    "get_asset_platforms":         "Assets · Contract addresses",
    "get_asset_revisions":         "Assets · Revision history",
    "resolve_ticker":              "Assets · Resolve ambiguous ticker",
    "get_entities":                "Assets · Entities",
    "get_data_coverage":           "Coverage · Data",
    "get_chain_coverage":          "Coverage · Chains",
    "get_social_coverage":         "Coverage · Social",
    "get_address_coverage":        "Coverage · Addresses",
    # Scores ----------------------------------------------------------------
    "get_asset_scores":            "Scores · Asset breakdown",
    "get_top_galaxy_scores":       "Scores · Top by Galaxy Score",
    "get_top_altranks":            "Scores · Top by AltRank",
    "get_creator_rankings":        "Scores · Creator rankings",
    # Social ----------------------------------------------------------------
    "get_social_dominance":        "Social · Share of conversation",
    "get_topic_rank":              "Social · Topic rank",
    "get_influencers":             "Social · Influencers by asset",
    "get_trending_assets":         "Social · Trending assets",
    "get_social_posts":            "Social · Posts",
    "get_similar_posts":           "Social · Similar posts",
    "get_asset_social_signal":     "Social · Asset signal",
    # Sentiment -------------------------------------------------------------
    "analyze_sentiment":           "Sentiment · Score arbitrary text",
    "get_aspect_sentiment":        "Sentiment · By aspect",
    "get_sentiment_trends":        "Sentiment · Trends",
    # Signal integrity (flagship) -------------------------------------------
    "get_signal_integrity":        "Signal integrity · Real-vs-fake score",
    "get_bot_detections":          "Signal integrity · Bot detections",
    "get_coordinated_campaigns":   "Signal integrity · Coordinated campaigns",
    "get_ai_substance":            "Signal integrity · AI substance",
    # Influencer accountability (flagship) ----------------------------------
    "get_influencer_ledger":       "Influencer ledger · Track record",
    "get_influencer_leaderboard":  "Influencer ledger · Leaderboard",
    # Fundamentals ----------------------------------------------------------
    "get_asset_fundamentals":      "Fundamentals · Full brief",
    "get_asset_technicals":        "Fundamentals · Technical levels",
    "get_disclosures":             "Fundamentals · Public disclosures",
    # On-chain --------------------------------------------------------------
    "get_whale_transactions":      "On-chain · Whale transactions",
    "get_exchange_flows":          "On-chain · Exchange flows",
    "get_exchange_netflow":        "On-chain · Exchange netflow",
    "get_entity_flows":            "On-chain · Entity flows",
    "lookup_address":              "On-chain · Address lookup",
    "list_labelled_addresses":     "On-chain · Labelled addresses",
    "get_address_events":          "On-chain · Address events",
    "get_hodl_waves":              "On-chain · HODL waves",
    "get_constellation":           "On-chain · Entity graph",
    # Market ----------------------------------------------------------------
    "get_ohlcv":                   "Market · OHLCV",
    "get_emerging_dex_pairs":      "Market · Emerging DEX pairs",
    "get_exchange_listings":       "Market · Exchange listings",
    "get_wrapper_basis":           "Market · Wrapper basis",
    # Analytics -------------------------------------------------------------
    "get_correlation":             "Analytics · Social-price correlation",
    "get_leading_indicators":      "Analytics · Leading indicators",
    # get_prediction / get_top_opportunities are DELIBERATELY ABSENT. No model
    # is deployed, so /v1/predictions/assets/{symbol} answers 503 and the list
    # routes answer an empty collection — /v1/public/plans already omits
    # predictions for the same reason. Re-add both here, and their tools, in
    # the same change that deploys a model. See test_tool_metadata.py.
    # Santiment-parity metrics ----------------------------------------------
    "list_metrics":                "Metrics · Catalogue",
    "get_metric_metadata":         "Metrics · Metadata",
    "get_metric_timeseries":       "Metrics · Timeseries",
    "get_metric_timeseries_multi": "Metrics · Timeseries (multi-asset)",
    "get_metrics_batch":           "Metrics · Batch",
    "get_metric_revisions":        "Metrics · Revisions",
    # Screener --------------------------------------------------------------
    "screen_assets":               "Screener · Run screen",
    "screener_fields":             "Screener · Available fields",
    "list_nl_screens":             "Screener · Saved natural-language screens",
    # Narrative and research -------------------------------------------------
    "get_trending_stories":        "Narrative · Trending stories",
    "get_story_posts":             "Narrative · Story sources",
    "get_narrative_clusters":      "Narrative · Clusters",
    "get_narrative_rotation":      "Narrative · Rotation",
    "list_research_reports":       "Research · Available reports",
    "get_research_report":         "Research · Report",
    # Read-only SQL ----------------------------------------------------------
    "run_sql":                     "SQL · Run read-only query",
    "get_sql_schema":              "SQL · Schema",
    # Agentic ops ------------------------------------------------------------
    "get_agent_findings":          "Agents · Findings",
}


SERVER_VERSION = "1.0.0"

SERVER_INSTRUCTIONS = """Onvexia is crypto social + on-chain intelligence: 2,300+ assets,
660,000+ social posts, 118,000+ whale transfers and 80,000+ labelled addresses.

HOW TO USE THIS SERVER WELL:

- Start from a symbol. get_asset confirms which asset a ticker means; tickers
  collide across chains and resolve_ticker will say so rather than guess.
- Read the states, not just the values. Sections and fields carry `state`,
  `coverage` and `note` fields that distinguish "we measured this" from "we have
  not looked". An empty list is never by itself evidence that nothing happened.
- A null label is not a safe label. Whale counterparties, disclosure severities
  and bot scores all return null when WE HOLD NOTHING, which is a fact about our
  coverage and not about the subject.
- Scores are attention and health, not valuation. Galaxy Score and AltRank say
  who is being talked about and how healthily, not what anything is worth.

Every tool is read-only."""


def _server_metadata(ServerClass) -> dict:
    """Identity fields, passed only if this SDK generation accepts them.

    Registries and aggregators read serverInfo.version, and an empty string
    there is what a server that has never been released looks like — ours
    reported exactly that until 2026-09-16. `website_url` and `title` are newer
    than `version`, so each is filtered against the real constructor signature
    rather than assumed: server.py deliberately runs on SDK 1.x and 2.x, and a
    TypeError here would break the stdio server to improve a registry listing.
    """
    import inspect

    wanted = {
        "version": SERVER_VERSION,
        "title": "Onvexia — Crypto Social & On-chain Intelligence",
        "website_url": "https://onvexia.com",
        "instructions": SERVER_INSTRUCTIONS,
    }
    try:
        accepted = set(inspect.signature(ServerClass.__init__).parameters)
    except (TypeError, ValueError):       # C-implemented or unintrospectable
        return {"version": SERVER_VERSION}
    return {k: v for k, v in wanted.items() if k in accepted}


def _titled_tool(mcp):
    """Return a decorator that registers a tool with its title and annotations.

    Replaces a bare `@tool`. The title lookup is deliberately NOT
    `.get(name, "")` — a missing entry must break the build, not ship a tool
    with a blank title that nobody notices until an aggregator grades it.
    """
    from mcp.types import ToolAnnotations  # lazy, same reason as _server_class

    def decorator(fn):
        name = fn.__name__
        if name not in TOOL_TITLES:
            raise KeyError(
                f"MCP tool {name!r} has no entry in TOOL_TITLES. Add one — a tool "
                f"without a title lowers the score of every other tool on the "
                f"aggregators that rank this server."
            )
        return mcp.tool(
            title=TOOL_TITLES[name],
            annotations=ToolAnnotations(
                title=TOOL_TITLES[name],
                # Every tool is a GET against /v1. Nothing here writes, and
                # nothing here can move funds — see the note above.
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                # The data is live market/social state fetched from our API,
                # not a closed local set.
                open_world_hint=True,
            ),
        )(fn)

    return decorator


def build_server():
    """Construct the MCP server with all tools wired to the API client."""
    ServerClass = _server_class()  # lazy: only needed to run the server

    mcp = ServerClass("onvexia", **_server_metadata(ServerClass))
    client = OnvexiaClient()

    # Every tool below registers through `tool`, not `mcp.tool()`, so a title and
    # the read-only annotations are applied from one place and cannot be omitted.
    tool = _titled_tool(mcp)

    @tool
    def get_asset(symbol: str) -> dict:
        """An asset's core profile by symbol: name, category and cross-system
        identifiers (CoinGecko id, contract addresses, chains).

        Start here when you have a ticker and need to be sure which asset it
        refers to. Tickers collide across chains — if the symbol is ambiguous,
        resolve_ticker is the tool that says so instead of guessing."""
        return client.get_asset(symbol)

    @tool
    def get_asset_scores(symbol: str) -> dict:
        """An asset's Galaxy Score and AltRank, with the components behind each.

        Galaxy Score is a composite of social and market health on a 0-100
        scale; AltRank is relative standing against the rest of the universe,
        where 1 is best. READ THE COMPONENT BREAKDOWN — a score moved by
        sentiment and one moved by volume mean different things, and the
        composite alone cannot tell you which happened."""
        return client.get_asset_scores(symbol)

    @tool
    def get_asset_fundamentals(symbol: str) -> dict:
        """Get the full fundamental brief for an asset: market snapshot, supply
        and valuation, project, TVL, revenue, treasury, security, governance,
        unlock schedule, derivatives positioning, competitive rank, valuation
        ratios and a graded scorecard — in one call.

        READ THE SECTION STATES, NOT ONLY THE VALUES. Each section is
        `measured`, `not_held` or `failed`, and sections the asset class cannot
        have are returned separately in `not_applicable`. "This chain has no
        DAO treasury" and "we could not read it" are different facts and this
        response keeps them apart.

        Revenue is split: `S06` is the entity's own fees, `S06b` is the total
        earned by protocols deployed on a chain. The two can differ by two
        orders of magnitude and only the first accrues to the token.
        """
        return client.get_asset_fundamentals(symbol)

    @tool
    def get_asset_technicals(symbol: str, limit: int = 8) -> dict:
        """Get support and resistance merged across 1w/1d/4h/1h, per-timeframe
        indicators, and derived spot/long/short setups for an asset.

        Each level carries the timeframes that confirmed it and the method on
        each — a level agreed by four charts is a different claim from one seen
        on the hourly. `measured_against` names the exchange and pair every
        distance was computed from, and `price_age_minutes` says how old that
        price is.

        Setups are GEOMETRY, not forecasts: an entry is a level cluster, a stop
        is that level offset by a measured multiple of daily range, and
        `rr_ratio` is computed from those prices. `status` is derived per
        request — pending, in_zone or passed.
        """
        return client.get_asset_technicals(symbol, limit)

    @tool
    def get_top_galaxy_scores(limit: int = 10) -> dict:
        """The assets with the strongest Galaxy Score right now.

        Galaxy Score is 0-100 and composite: social volume, engagement,
        sentiment and market health folded together. A high score is a
        statement about ATTENTION AND HEALTH, not about valuation — it does not
        mean an asset is cheap. Call get_asset_scores for the breakdown."""
        return client.get_top_galaxy_scores(limit)

    @tool
    def get_top_altranks(limit: int = 10) -> dict:
        """The assets ranked best by AltRank right now — relative standing, not absolute.

        AltRank is a RANK: 1 is the strongest in the universe. A rising AltRank
        in a falling market means outperforming the fall, not going up. Pair
        with get_asset_scores when the distinction matters."""
        return client.get_top_altranks(limit)

    @tool
    def get_correlation(symbol: str) -> dict:
        """How closely an asset's social activity tracks its price, with the lead/lag.

        Correlation is not causation and this endpoint does not claim it is. A
        high coefficient says the two series moved together over the window —
        it does not say which one moved first. Use get_leading_indicators for
        that question."""
        return client.get_correlation(symbol)

    @tool
    def get_leading_indicators(symbol: str) -> dict:
        """Which social and on-chain signals have historically MOVED FIRST for an asset.

        This is the lead/lag question that get_correlation deliberately does not
        answer. A lead measured over a past window is not a forecast and the
        response does not present it as one — it is the observed ordering of two
        series, and it can break."""
        return client.get_leading_indicators(symbol)

    @tool
    def get_social_dominance(hours: int = 168) -> dict:
        """Each asset's SHARE of total social attention over a window, with the posts,
        distinct authors, engagement and sentiment behind the share.

        Share is relative and sums across the universe, so an asset's dominance
        can fall while its absolute volume rises — that is the market getting
        louder, not the asset getting quieter. Distinct authors is the column
        that separates a real conversation from one account posting 400 times."""
        return {"data": client.get_social_dominance(hours)}

    @tool
    def get_topic_rank(hours: int = 168, limit: int = 10) -> dict:
        """Rank what the market is TALKING ABOUT — themes and narratives, not assets.

        Ranked by mentions weighted by engagement over the window, so a topic
        posted about loudly by few accounts does not outrank one discussed
        widely. Use get_trending_assets for tickers; this is the layer above,
        where "restaking" and "AI agents" live."""
        return {"data": client.get_topic_rank(hours, limit)}

    @tool
    def get_whale_transactions(limit: int = 25, symbol: Optional[str] = None) -> dict:
        """Recent large on-chain transfers, optionally filtered to one asset.

        "Whale" is a SIZE threshold, not an identity. A large transfer is very
        often an exchange moving its own funds between wallets, which is not a
        market action at all — counterparty labels are included where we hold
        them, and a null label means WE HAVE NO LABEL, never that the
        counterparty is unknown or safe."""
        return client.get_whale_transactions(limit=limit, symbol=symbol)

    @tool
    def get_exchange_flows(symbol: Optional[str] = None) -> dict:
        """Net movement of an asset into and out of exchange wallets.

        Inflows are supply arriving somewhere it can be sold; outflows are
        supply leaving to self-custody. The conventional reading is
        distribution vs accumulation, but a single large transfer can be an
        exchange rebalancing its own wallets — check get_entity_flows before
        attributing intent."""
        return client.get_exchange_flows(symbol)

    @tool
    def get_aspect_sentiment(asset: str) -> dict:
        """Split an asset's sentiment by what people are actually talking about:
        technology, price, team and community.

        The aggregate can be flat while the parts disagree sharply — bullish on
        technology, bearish on team is a different situation from uniformly
        neutral, and only this tool can tell them apart."""
        return client.get_aspect_sentiment(asset)

    @tool
    def analyze_sentiment(text: str) -> dict:
        """Score any text for crypto sentiment, tuned for crypto slang and tickers.

        Takes arbitrary text you supply — it does not look anything up. General
        sentiment models read "this is going to zero" and "wagmi" badly; this
        one is fitted to the register. Returns polarity plus the terms that
        drove it, so a score can be checked rather than trusted."""
        return client.analyze_sentiment(text)

    @tool
    def get_influencers(asset: str) -> dict:
        """The accounts driving conversation about one asset, by reach and engagement.

        Ranked by measured activity in our corpus, NOT by follower count, and
        NOT by whether they were right — see get_influencer_ledger for track
        record. A large account posting noise ranks here; that is the point of
        keeping the two tools separate."""
        return client.get_influencers(asset)

    @tool
    def get_signal_integrity(symbol: str) -> dict:
        """Get the Signal Integrity score (0-100) — is the move real or exit liquidity?
        Fuses social authenticity + on-chain reality + fundamental backing, with an
        Exit Liquidity Radar flag."""
        return client.get_signal_integrity(symbol)

    @tool
    def get_influencer_ledger(influencer_id: str) -> dict:
        """Get an influencer's accountability record: did their calls precede the move
        (Predictor) or react to it (Reactor)? Includes hit rate and track record."""
        return client.get_influencer_ledger(influencer_id)

    @tool
    def get_influencer_leaderboard() -> dict:
        """The influencer accountability leaderboard, ranked by what people actually
        got RIGHT rather than by how loud they are.

        Each entry is scored Predictor vs Reactor: did the call come before the
        move, or after it. This is the flagship differentiator — reach and
        accuracy are different axes, and most rankings only publish the first."""
        return client.get_influencer_leaderboard()

    # --- universe / coverage / attribution (Stage F) ---------------------
    # Agents benefit disproportionately from these: they let a model discover
    # what data exists before asking for it, instead of guessing symbols.

    @tool
    def search_assets(query: str, limit: int = 20) -> dict:
        """Search the whole asset universe (~1,900 assets) by symbol or name.
        Use this to resolve a user's loose reference into a real symbol before
        calling the other tools."""
        return client.search_universe(query, limit)

    @tool
    def get_data_coverage() -> dict:
        """What data this platform actually holds right now: asset count, how many
        are priced, chains covered, labelled addresses, social corpus size, and
        freshness timestamps. Call this to check whether an answer is supportable
        before asserting it."""
        return client.get_coverage()

    @tool
    def get_chain_coverage() -> dict:
        """Per-chain coverage — tokens mapped, labelled addresses, whale
        transactions seen, and how many were attributed to a named entity.
        Attribution is Etherscan-derived, so it is strong on Ethereum and sparse
        on other chains."""
        return client.get_chains()

    @tool
    def get_asset_platforms(symbol: str) -> dict:
        """Every chain an asset is deployed on, with its contract address and
        token decimals."""
        return client.get_asset_platforms(symbol)

    @tool
    def lookup_address(address: str) -> dict:
        """Identify a blockchain address — exchange, bridge, DEX, MEV bot, mining
        pool, or OFAC-sanctioned — with the source and confidence of each label.
        IMPORTANT: `known: false` means no label is held. It does NOT mean the
        address is clean or unflagged."""
        return client.lookup_address(address)

    @tool
    def list_labelled_addresses(chain: str = "", entity: str = "",
                                category: str = "", limit: int = 50) -> dict:
        """Browse labelled addresses, filtered by chain, entity (e.g. Binance) or
        category (exchange | bridge | dex | mev | staking | mining | sanctioned)."""
        return client.list_labels(chain, entity, category, limit)

    # --- metric registry (Phase 08 / C1) ---------------------------------
    # Santiment's own MCP exposes 30+ metrics across 500 assets and requires a
    # human OAuth login. These tools expose our FULL registry across 1,924 assets
    # with no account — an agent can self-onboard via x402.

    @tool
    def list_metrics(category: str = "", available_only: bool = False) -> dict:
        """List every metric Onvexia knows, with its parity and caveats.

        parity=exact means we compute it the way Santiment does; approximate means
        same concept but different coverage or method (read the caveat before
        relying on the number); unavailable means we do NOT serve it yet.
        Unavailable metrics are listed on purpose — check here before asserting
        that Onvexia can answer a question."""
        return client.list_metrics(category, available_only)

    @tool
    def get_metric_metadata(metric: str) -> dict:
        """Describe one metric before you use it: parity, category, minimum interval
        and any caveat attached to it.

        CALL THIS BEFORE get_metric_timeseries if the metric is unfamiliar. The
        minimum interval tells you the finest resolution that is real rather
        than interpolated, and the caveat is where an approximate metric admits
        what it approximates."""
        return client.get_metric_metadata(metric)

    @tool
    def get_metric_timeseries(metric: str, asset: str, from_date: str = "utc_now-30d",
                              to_date: str = "utc_now", interval: str = "1d",
                              aggregation: str = "LAST") -> dict:
        """Timeseries for any available metric on any asset.

        Accepts Santiment-style relative dates ("utc_now-7d") as well as ISO
        timestamps. If the metric is not available this returns an error naming it
        rather than an empty series — an empty result here always means "no data in
        that range", never "we do not have this metric"."""
        return client.get_metric_timeseries(metric, asset, from_date, to_date,
                                            interval, aggregation)

    @tool
    def get_entity_flows(hours: int = 168, limit: int = 20) -> dict:
        """Whale flow per labelled entity over the window. Inflow to an exchange
        is distribution pressure; outflow is accumulation."""
        return client.get_entity_flows(hours, limit)

    @tool
    def get_metric_timeseries_multi(metric: str, assets: str,
                                    from_date: str = "utc_now-30d",
                                    to_date: str = "utc_now",
                                    interval: str = "1d") -> dict:
        """Timeseries for ONE metric across MANY assets in a single call.

        `assets` is comma-separated (e.g. "BTC,ETH,SOL"). Prefer this over
        looping get_metric_timeseries — it is one round trip instead of N, and
        the values are guaranteed to come from the same read."""
        return client.get_metric_timeseries_multi(metric, assets, from_date,
                                                  to_date, interval)

    @tool
    def get_metrics_batch(metrics: str, asset: str) -> dict:
        """Latest value of MANY metrics for ONE asset in a single call.
        `metrics` is comma-separated. The mirror of get_metric_timeseries_multi."""
        return client.get_metrics_batch(metrics, asset)

    # --- screener (Phase 08 / C5) ----------------------------------------
    # Santiment charges for screening. This is free and server-side, which is
    # the difference that matters to an agent: filtering 1,924 assets here beats
    # pulling them all and reasoning over the pile.

    @tool
    def screen_assets(filter: str = "", sort: str = "", limit: int = 50) -> dict:
        """Filter the whole asset universe server-side and return the matches.

        `filter` is comma-separated `field:op:value` terms, e.g.
        "market_cap:gt:1000000000,funding_rate:lt:0" — assets over $1B whose
        funding rate is negative. Ops: gt, gte, lt, lte, eq, ne.
        Call screener_fields() first to see what fields exist and their ranges;
        guessing a field name gets the whole query rejected."""
        return client.screen(filter, sort, limit)

    @tool
    def screener_fields() -> dict:
        """Every field the screener accepts, with type and description. Call this
        before building a filter rather than guessing field names."""
        return client.screener_fields()

    # --- market data ------------------------------------------------------

    @tool
    def get_ohlcv(symbol: str = "", limit: int = 100) -> dict:
        """Daily candles (open/high/low/close/volume) for an asset, with the
        venue they came from. Coverage is bounded by which assets have a USDT
        pair on Binance or Bybit — an asset absent here has no candle source we
        collect, which is not the same as having no price."""
        return client.get_ohlcv(symbol, limit)

    @tool
    def get_trending_assets() -> dict:
        """Assets trending now by social activity, with the hype score that
        separates a real move from a burst of noise."""
        return client.get_trending()

    # --- social / nlp depth -----------------------------------------------

    @tool
    def get_entities(asset: str) -> dict:
        """Named entities extracted from social documents about an asset —
        people, organisations, products and other tickers mentioned alongside
        it. Use it to find what a narrative is actually about."""
        return client.get_entities(asset)

    @tool
    def get_sentiment_trends(asset: str) -> dict:
        """Sentiment over time for an asset, with sample size and confidence
        interval. IMPORTANT: sentiment measured on few documents is unreliable —
        our own bootstrap put the direction wrong 35.6% of the time at n=1 and
        9.5% at n=20. Read n before quoting a direction."""
        return client.get_sentiment_trends(asset)

    @tool
    def get_bot_detections() -> dict:
        """Accounts flagged as automated or coordinated, with the behavioural
        evidence. Volume from these should not be read as organic attention.

        READ `coverage` AND `note` BEFORE YOU READ THE LIST. No scorer is
        currently running, so `bot_probability` is NULL for every account and
        this list comes back EMPTY. An empty list here says nothing whatsoever
        about how clean the corpus is — it means nobody has been scored yet,
        and the response says so explicitly in `note`.

        `coverage.accounts_scored` vs `accounts_total` is the honest number:
        while the first is 0, treat this tool as reporting our coverage, not
        the market's cleanliness."""
        return client.get_bot_detections()

    @tool
    def get_coordinated_campaigns() -> dict:
        """Detected coordinated posting campaigns — the same message pushed by
        multiple accounts. Matching is exact-text, so this catches copypasta and
        misses the same campaign reworded."""
        return client.get_coordinated_campaigns()

    @tool
    def get_creator_rankings(limit: int = 25) -> dict:
        """Rank social creators across the whole corpus by measured influence.

        Corpus-wide, unlike get_influencers which is scoped to one asset.
        Influence is computed from engagement our collectors actually observed,
        so a creator we do not ingest is absent rather than ranked low — an
        absence here is a coverage fact, not a judgement."""
        return client.get_creator_rankings(limit)

    @tool
    def get_asset_revisions(symbol: str) -> dict:
        """Metrics for this asset that CHANGED after they were first published,
        with the old value, the new one and why. An agent that quoted an earlier
        number can find out here that it moved."""
        return client.get_asset_revisions(symbol)


    # --- the C8 LLM product layer (Phase 08 / C8) ------------------------
    # Computed by the pipeline for weeks and reachable only from psql. An agent
    # asking "what is happening with X and can I trust the number" needs all
    # three of these: the narrative, its author count, and the ticker verdict.

    @tool
    def get_trending_stories(limit: int = 20) -> dict:
        """Current narratives, each an LLM summary of a CLUSTER of posts rather
        than a single document.

        Read author_count before quoting one: a high post_count with a low
        author_count is one person repeating themselves, not a narrative. These
        are machine summaries, not edited articles."""
        return client.get_stories(limit)

    @tool
    def get_narrative_clusters(limit: int = 25) -> dict:
        """The raw clusters behind the stories, without the prose — for a model
        doing its own summarisation. Every cluster has >= 2 distinct authors;
        near-identical posts from one account are copypasta and excluded."""
        return client.get_narratives(limit)

    @tool
    def list_research_reports() -> dict:
        """List the assets that currently have a generated research report available.

        Returns the index, not the reports — call get_research_report with a
        symbol for the body. An asset missing from this list has not been
        written up; that is a statement about our coverage, not about the
        asset."""
        return client.list_reports()

    @tool
    def get_research_report(symbol: str) -> dict:
        """One asset's generated report. The `unavailable` field lists metrics
        the report could NOT use — read it, because a report that silently omits
        funding rate reads as a report about an asset with unremarkable funding."""
        return client.get_report(symbol)

    @tool
    def resolve_ticker(ticker: str) -> dict:
        """Does a bare ticker actually mean the crypto asset?

        verdict 'crypto' means mentions are about the asset; 'equity'/'other'
        means the bare word is dominated by something else (TIA is Spanish
        'tia'; GRT collides with 'graph'). A 404 is NOT a clean bill of health —
        it means nobody has adjudicated that ticker yet."""
        return client.resolve_ticker(ticker)

    @tool
    def get_social_coverage(band: int = 300) -> dict:
        """How many assets actually clear the document floor that makes each
        social metric computable.

        Call this BEFORE quoting sentiment for an asset. A large corpus total
        does not mean sentiment works everywhere: attention is a power law and
        the documents pile onto BTC, so most assets stay uncomputable."""
        return client.get_social_coverage(band)

    @tool
    def list_nl_screens(limit: int = 25) -> dict:
        """Previously compiled natural-language screens: the English somebody
        wrote and the filter it compiled to, INCLUDING refusals. Useful as
        worked examples of the screener's filter grammar before you write one."""
        return client.list_nl_screens(limit)

    @tool
    def get_agent_findings(limit: int = 50) -> dict:
        """What this platform's own monitoring agents are currently complaining
        about — dead collectors, stale data streams, coverage drops.

        Worth checking before relying on a number: a stream flagged stale here
        is still being served, it is just old."""
        return client.get_agent_findings(limit)


    # --- on-chain, SQL and the surfaces added 2026-08-21/22 -----------------
    #
    # 18 served /v1 routes had no MCP tool. The worst was /v1/sql: llms.txt
    # tells agents it is the escape hatch for questions REST cannot express,
    # and the server they actually call had no way to reach it.

    @tool
    def run_sql(query: str) -> dict:
        """Run a read-only SELECT against the platform's data. One statement, 15s timeout, 10,000-row cap; truncation is always reported. Call get_sql_schema first for the queryable relations."""
        return client.run_sql(query)

    @tool
    def get_sql_schema() -> dict:
        """List every relation and column queryable via run_sql, plus the rules and what is deliberately not exposed."""
        return client.get_sql_schema()

    @tool
    def get_hodl_waves(limit: int = 260) -> dict:
        """Bitcoin supply split by coin age over time — which cohorts are holding and which are moving."""
        return client.get_hodl_waves(limit)

    @tool
    def get_exchange_netflow(limit: int = 40) -> dict:
        """Per-token flow onto and off exchanges. Inflow is distribution pressure, outflow is accumulation. net_usd where the token can be priced."""
        return client.get_exchange_netflow(limit)

    @tool
    def get_constellation(limit: int = 150) -> dict:
        """Asset co-mention graph — which assets are discussed together, with what was filtered out."""
        return client.get_constellation(limit)

    @tool
    def get_social_posts(platform: str = "", limit: int = 50) -> dict:
        """Collected social posts, optionally filtered by platform (bluesky, farcaster, reddit, 4chan, bitcointalk, rss)."""
        return client.get_social_posts(platform or None, limit)

    @tool
    def get_similar_posts(post_id: int) -> dict:
        """Posts nearest a given post in embedding space. Read the returned BAND, never the raw cosine — 43% of this corpus sits at 0.80-0.90 by default."""
        return client.get_similar_posts(post_id)

    @tool
    def get_asset_social_signal(symbol: str, days: int = 30) -> dict:
        """Per-asset social signal over time. The `available` field states plainly whether we hold it."""
        return client.get_asset_social_signal(symbol, days)

    @tool
    def get_metric_revisions(limit: int = 50) -> dict:
        """Restatements of published numbers — what changed, over which period, and why. A correction is not a market move."""
        return client.get_metric_revisions(limit)

    @tool
    def get_emerging_dex_pairs(min_liquidity_usd: int = 50000) -> dict:
        """Newly created DEX pairs above a USD liquidity floor.

        THE FLOOR IS RETURNED IN THE RESPONSE, and it is load-bearing: this is
        the long tail where most pairs are rugs or noise, and the floor is the
        only thing separating a signal from a list of scams. Raising it shrinks
        the result set and raises its quality."""
        return client.get_emerging_dex_pairs(min_liquidity_usd)

    @tool
    def get_exchange_listings(limit: int = 40) -> dict:
        """Recent exchange listing announcements — an asset being added to a venue.

        A listing is an ATTENTION event, not a fundamental one: it changes who
        can buy, not what the project is worth. Use it to explain a volume or
        social spike, not as a valuation input."""
        return client.get_exchange_listings(limit)

    @tool
    def get_address_coverage() -> dict:
        """What we index per chain for watched addresses: what we see, what we miss, and what an empty feed actually means."""
        return client.get_address_coverage()

    @tool
    def get_address_events(limit: int = 50) -> dict:
        """Events on watched addresses. Check get_address_coverage before reading an empty result as silence — below the observed USD floor, movement is invisible to us."""
        return client.get_address_events(limit)

    @tool
    def get_story_posts(story_id: int) -> dict:
        """The individual posts a story was assembled from — the receipts.

        Call this whenever a story matters enough to check. A generated story is
        a summary over these posts; this is how you verify it says what the
        sources say rather than taking the summary on trust."""
        return client.get_story_posts(story_id)

    # THE TWO 2026-NARRATIVE TOOLS. Agents are this product's declared primary
    # channel (PRODUCT_STRATEGY_2026 §16), so an endpoint that exists only for a
    # browser is half-shipped. Both of these carry states an agent MUST read
    # before quoting them, and the docstrings say so, because a model will
    # otherwise report a coverage gap as a finding.

    @tool
    def get_narrative_rotation(days: int = 7, include_legacy: bool = False) -> dict:
        """Which crypto narrative is GAINING or LOSING attention share, with a
        liquidity confirmation leg.

        Compares the last `days` against the equally long window immediately
        before. Covers the 2026 narrative set — RWA, tokenized equities and
        treasuries, stablecoins, DePIN, perp DEXs, prediction markets, AI agents
        — as well as DeFi, NFT, Gaming and the L1/L2 split.

        READ `vocabulary_stale` BEFORE QUOTING ANY DELTA. When true, the corpus
        spans two keyword vocabularies and a narrative whose keywords were just
        added will appear to be rising purely because only recent posts were
        ever tested against them. That is a rotation signal manufactured by a
        deploy, not by the market.

        A narrative with `unconfirmed: true` has measured attention and NO
        liquidity confirmation — the confirmation is absent, not zero, and the
        row states why.
        """
        return client.get_narrative_rotation(days, include_legacy)

    @tool
    def get_ai_substance(limit: int = 40) -> dict:
        """Does an AI-sector project actually ship code, against how much
        attention it gets.

        Four states, and the fourth is not a verdict:
          ships           public repo with development activity in 30 days
          silent          public repo, no activity in 30 days
          no_public_repo  no repository is published for this asset
          unmapped        WE have not checked. This is a gap in OUR coverage
                          and must NEVER be reported as the project failing to
                          ship. RENDER sat in this state with 447 posts while
                          publishing code the whole time.

        `dev_events_30d` is null rather than 0 for the last two states: there is
        no repository to have produced a zero. `attention_without_substance` is
        only ever set where the state was actually measured.
        """
        return client.get_ai_substance(limit)

    @tool
    def get_wrapper_basis(limit: int = 40) -> dict:
        """Cross-wrapper spread for tokenized equities: one real company, every
        issuer that tokenizes it, and how far apart they trade.

        SpaceX trades under five wrappers and they do not agree. Spreads run
        roughly 0.1-0.9 percent between programs referencing the same share.

        This is a CROSS-WRAPPER comparison, deliberately not a comparison
        against the underlying stock — that needs a licensed equity feed and no
        free commercially-usable one exists.

        A spread is NOT free money. Each issuer carries its own credit,
        redemption terms and transfer restrictions, and the cheapest wrapper is
        often cheapest for a reason. Do not present it as an arbitrage.
        """
        return client.get_wrapper_basis(limit)

    @tool
    def get_disclosures(symbol: str = "", limit: int = 50) -> dict:
        """Public-record documents about issuers we track: SEC filings and
        federal court dockets.

        Exists because both RWA failures of 2026 were disclosed in public text
        before the price moved -- RealT's tax delinquency sat in court filings
        for a year, Goldfinch's borrower defaults were in governance forums
        before the vote.

        TWO THINGS YOU MUST NOT MISREPORT:

        A null `severity` means the document was FOUND and NOT ASSESSED. It is
        unjudged, not benign, and must never be summarised as "nothing
        concerning".

        `match_confidence: name_unverified` means the document was matched on a
        NAME and may concern a different company entirely -- searching for
        'RealT' returns 'Broadway White Realty'. Do not attribute an unverified
        filing to an issuer without checking it.

        An empty result means nothing has been found, which for a subject never
        searched is not a statement about them at all.
        """
        return client.get_disclosures(symbol, limit)

    return mcp


def main() -> None:
    server = build_server()
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
