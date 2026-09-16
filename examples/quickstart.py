#!/usr/bin/env python3
"""
Talk to the hosted Onvexia MCP server with nothing but the standard library.

    python3 examples/quickstart.py

No install, no API key. This is the whole protocol exchange an agent makes.
"""
import json
import urllib.request

ENDPOINT = "https://onvexia.com/mcp"

# IDENTIFY YOUR CLIENT. Left to itself, urllib sends `Python-urllib/3.x`, which
# some edges (including ours, at the time of writing) treat as a bot signature
# and refuse before the request reaches the server. Any real product name works.
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "User-Agent": "onvexia-quickstart/1",
}


def call(method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        for line in resp.read().decode().splitlines():
            line = line[len("data: "):] if line.startswith("data: ") else line
            if line.startswith("{"):
                return json.loads(line)
    raise RuntimeError("no JSON-RPC message in the response")


def main():
    info = call("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "quickstart", "version": "1"},
    })["result"]["serverInfo"]
    print(f"connected to {info['name']} v{info.get('version', '?')}")

    tools = call("tools/list", request_id=2)["result"]["tools"]
    print(f"{len(tools)} tools available, e.g.:")
    for t in tools[:5]:
        print(f"  {t['title']:<44} {t['name']}")

    # ALWAYS START HERE. It reports what is actually held right now, so you can
    # tell a quiet market from a gap in coverage before reasoning about either.
    out = call("tools/call", {"name": "get_data_coverage", "arguments": {}}, request_id=3)
    coverage = json.loads(out["result"]["content"][0]["text"])
    print("\ncoverage:")
    for key in ("assets", "social_posts", "labelled_addresses", "whale_transactions"):
        print(f"  {key:<20} {coverage.get(key):,}")


if __name__ == "__main__":
    main()
