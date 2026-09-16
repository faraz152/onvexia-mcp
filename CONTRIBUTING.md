# Contributing

## Adding a tool

You cannot add one without a title — the server will refuse to build:

```python
KeyError: MCP tool 'get_something' has no entry in TOOL_TITLES.
```

That is deliberate. Aggregators score an MCP server on its **weakest** tool
description, not its average, so one tool added in a hurry lowers the rating of
all the others. Before this was enforced, an audit of the surface found 69 tools
with **0 titles, 0 annotations and 23 descriptions under 80 characters**.

So, in order:

1. Add the client method in `api_client.py`.
2. Add a `"Group · Name"` entry to `TOOL_TITLES` in `server.py`.
3. Add the `@tool`-decorated function. Not `@mcp.tool()` — the wrapper is what
   applies the title and the read-only annotations from one place.
4. Write a description that would let an agent choose this tool over a
   neighbouring one. Say what it returns, in what units, and what it must not be
   read as. The floor is 80 characters and the median here is 257.
5. `pytest -q`.

## Do not publish a tool that cannot work

Three tools were removed for this reason: one was gated behind a tier no caller
can hold, and two were backed by a model that is not deployed. A tool that can
only return `503` gets the whole server marked broken by the first scanner that
tries it.

`tests/test_tool_metadata.py` pins them. Re-add a tool in the same change that
makes it work, not before.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

No test may reach the network. `httpx.MockTransport` is the seam.

**And check what your test would catch.** A test that asserts a header on
`httptest`-style recorder can pass while the real behaviour is broken — that
exact mistake hid a missing payment receipt here for its whole lifetime. Break
the code deliberately and watch your test fail before you keep it.
