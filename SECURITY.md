# Security

## Reporting a vulnerability

Email **security@onvexia.com**. Please do not open a public issue for a
vulnerability. We will acknowledge within 72 hours.

## The tool surface is read-only, and that is enforced

Every one of the 66 tools is a `GET` against the public `/v1` API. Nothing here
writes, and **no tool can move funds**. `tests/test_tool_metadata.py` asserts
`readOnlyHint` and `destructiveHint: false` on all of them, read back through
`list_tools()` — the same call an MCP client makes — rather than trusted from
the decorator.

The x402 wallet in `api_client.py` pays for **the client's own outbound
request**. It is not reachable as a tool.

## The hosted server holds no credentials, and refuses to start if it does

`https://onvexia.com/mcp` is one process serving every caller on the internet.
Two environment variables that are correct for a local stdio server are
dangerous there:

| variable | what it would do |
|---|---|
| `CRYPTO_INTEL_API_KEY` | meter every caller against one account, and grant them its plan |
| `X402_CLIENT_PRIVATE_KEY` | **pay every anonymous caller's payment challenge out of that wallet** — an unbounded drain that looks like ordinary traffic until the wallet is empty |

`http_server.py` exits non-zero rather than starting with either set. This is
not theoretical: both are legitimately present in the deployment environment for
other components, so the failure mode is inheriting a shell, not writing new
config. The guard has already turned one bad deploy into a rollback instead of a
silent leak.

Callers authenticate **per request**. `X-API-Key`, `Authorization` and
`X-PAYMENT` are forwarded to the API — an allowlist; nothing else is relayed.
They are carried in a `ContextVar` and merged at send time rather than set on
the shared `httpx.Client`, because one concurrent request mutating shared
headers would leak one caller's credential into another's call. That property
is asserted with eight interleaved callers in `tests/test_http_server.py`.

A caller who sends no credential **is anonymous**. We never substitute a server
identity for them; they receive the API's own `401`/`402`, which names what to
do next.

## Unauthenticated discovery is deliberate

`initialize` and `tools/list` answer without any credential. Registry scanners
probe exactly those two, and a server that demands a credential to describe
itself is catalogued as broken. Authorisation happens one hop later, at `/v1`,
which is the layer that owns it.
