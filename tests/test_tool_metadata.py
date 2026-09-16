"""
The published quality of the MCP tool surface.

WHY THIS FILE EXISTS. Aggregators (Glama, Smithery, the Official MCP Registry)
score a server on its WEAKEST tool, not its average, and the score is what
decides whether an agent-builder ever installs it. Audited 2026-09-16, before
any of this was enforced: 69 tools, **0 titles, 0 annotations, 23 descriptions
under 80 characters**, and 3 tools wired to endpoints that cannot return data.

Every one of those was something somebody forgot on the day they added a tool.
A convention does not survive 69 opportunities to forget it, so the title is
enforced by construction (`_titled_tool` raises KeyError) and the rest is
enforced here.

These assertions run against the REAL server built by `build_server()` and read
back through `list_tools()` — the same call an aggregator's scanner makes. They
do not read the source, because what ships is what the SDK emits, not what the
decorator looked like.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import server  # noqa: E402

# The floor a description has to clear. Not arbitrary: a description that fits
# in one short line names the endpoint and stops, which is exactly the kind an
# agent cannot choose between. The shortest survivor of the 2026-09-16 rewrite
# is 82 characters.
MIN_DESCRIPTION = 80


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(server.build_server().list_tools())


def _desc(t):
    return " ".join((t.description or "").split())


def test_every_tool_has_a_title(tools):
    missing = [t.name for t in tools if not (t.title or "").strip()]
    assert not missing, f"tools with no title: {missing}"


def test_titles_are_grouped(tools):
    """Titles carry a "Group · Name" prefix.

    MCP has no namespace primitive and 66 flat tools is past the point where
    most clients stay usable, so the title is the only grouping surface there
    is. A title without the separator silently drops out of that grouping.
    """
    ungrouped = [t.title for t in tools if " · " not in (t.title or "")]
    assert not ungrouped, f"titles missing a 'Group · Name' prefix: {ungrouped}"


def test_every_tool_is_annotated_read_only(tools):
    """The whole surface is read-only, and says so in the annotations.

    Anthropic's connector policy forbids a tool that transfers money or crypto.
    Every tool here is a GET against /v1; the x402 wallet in api_client.py pays
    for OUR OWN outbound request and is not reachable as a tool. An agent host
    that trusts readOnlyHint to skip a confirmation prompt must not be lied to,
    so this asserts the hint rather than assuming the decorator set it.
    """
    for t in tools:
        assert t.annotations is not None, f"{t.name}: no annotations"
        assert t.annotations.read_only_hint is True, f"{t.name}: not read-only"
        assert t.annotations.destructive_hint is False, f"{t.name}: destructive"


def test_no_description_is_thin(tools):
    thin = [(t.name, len(_desc(t))) for t in tools if len(_desc(t)) < MIN_DESCRIPTION]
    assert not thin, (
        f"{len(thin)} tool(s) below {MIN_DESCRIPTION} chars — aggregators score "
        f"the weakest description, not the average: {thin}"
    )


def test_descriptions_say_more_than_the_tool_name(tools):
    """A description that is the name with spaces in it is not a description."""
    for t in tools:
        d = _desc(t).lower()
        assert d.replace(" ", "").replace(".", "") != t.name.replace("_", ""), t.name


@pytest.mark.parametrize(
    "name,why",
    [
        ("get_bq_spend",
         "/v1/chain/bq-spend is PlanEnterprise-gated and free_access.go clamps the "
         "grant so Enterprise is unreachable — it 403s for every possible caller, "
         "and it publishes OUR OWN BigQuery unit economics"),
        ("get_prediction",
         "/v1/predictions/assets/{symbol} returns 503: NO MODEL IS DEPLOYED"),
        ("get_top_opportunities",
         "/v1/predictions/* returns an empty collection: NO MODEL IS DEPLOYED"),
    ],
)
def test_tools_that_cannot_work_are_not_published(tools, name, why):
    """A tool that can only fail is not a tool.

    These were published for months. Removing them is not hiding the gap — the
    endpoints still exist and still say plainly why they are empty. It is
    declining to ADVERTISE a capability to an audience that will immediately
    call it, on the channel where a 503 gets us marked "broken" by scanners.

    Re-add each one in the same change that makes it work, not before.
    """
    assert name not in {t.name for t in tools}, f"{name} is published, but: {why}"


def test_bot_detections_warns_before_it_is_called(tools):
    """The one empty-by-design tool we DO publish must warn up front.

    /v1/social/bot-detection returns an honest `note` and a real coverage count
    saying no scorer runs — but an agent reads the description BEFORE it calls,
    and a description that omits this sends it to fetch an empty list and draw
    the wrong conclusion from it. Empty here means "nobody scored", never "the
    corpus is clean".
    """
    t = next(t for t in tools if t.name == "get_bot_detections")
    d = _desc(t).lower()
    assert "no scorer" in d, "description must state that no scorer is running"
    assert "empty" in d, "description must say the list comes back empty"


def test_titles_are_unique(tools):
    seen = {}
    for t in tools:
        assert t.title not in seen, f"duplicate title {t.title!r}: {seen.get(t.title)} and {t.name}"
        seen[t.title] = t.name


def test_title_table_has_no_dead_entries():
    """Every entry in TOOL_TITLES belongs to a tool that still exists.

    The table outlives the tools it names. A stale entry is harmless at runtime
    and is exactly how a table stops describing reality.
    """
    live = {t.name for t in asyncio.run(server.build_server().list_tools())}
    dead = sorted(set(server.TOOL_TITLES) - live)
    assert not dead, f"TOOL_TITLES names tools that no longer exist: {dead}"
