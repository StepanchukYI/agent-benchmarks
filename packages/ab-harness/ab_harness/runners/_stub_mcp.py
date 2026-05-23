"""Deterministic stub MCP server for benchmark tool-use tasks.

Reads a ``tools.json`` schema file and registers all listed tools as callable
MCP tools. Each tool returns a deterministic stub response so the benchmark
agent can call them and the tool_call / tool_return pairs land in the
trajectory for tool_call_validator scoring.

Stub response logic
-------------------
* Default: ``{"status": "ok", "result": null}``
* If the tool schema has a ``_test_behavior`` field with
  ``always_returns_error``, the stub returns that string as an error detail
  (``is_error=true``). This drives the L0_306 error-recovery scenario.
* If the tool schema declares ``_stub_return``, that dict is returned verbatim.
  This lets tasks like L0_303 (multi-tool ordering) feed a return value (e.g.
  ``order_id``) from the first call back to the agent for the second call.

MCP stdio protocol (2024-11 JSON-RPC subset)
--------------------------------------------
The server reads newline-delimited JSON-RPC requests from stdin and writes
JSON-RPC responses to stdout. It implements only the three methods the claude
CLI requires to advertise tools and handle calls:

* ``initialize``             — capability handshake
* ``tools/list``             — enumerate registered tools
* ``tools/call``             — invoke a tool by name, return stub

Usage
-----
Run as a subprocess with the tools.json path as the first argument::

    python -m ab_harness.runners._stub_mcp /path/to/tools.json

The runner writes an mcp_config.json pointing at this script so claude CLI
can launch it as a stdio MCP server.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _load_tools(tools_json_path: str) -> dict[str, dict[str, Any]]:
    """Return a mapping of tool_name → tool_schema_dict from a tools.json file."""
    with open(tools_json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    tools: dict[str, dict[str, Any]] = {}
    for entry in data.get("tools") or []:
        name = entry.get("name")
        if name:
            tools[name] = entry
    return tools


def _stub_response(tool_schema: dict[str, Any], call_args: dict[str, Any]) -> tuple[Any, bool]:
    """Return (content, is_error) for a stub tool invocation.

    Priority order:
    1. ``_test_behavior.always_returns_error`` → error string.
    2. ``_stub_return`` → verbatim dict.
    3. Default → {"status": "ok", "result": null}.
    """
    behavior = tool_schema.get("_test_behavior") or {}
    if behavior.get("always_returns_error"):
        return str(behavior["always_returns_error"]), True

    stub_ret = tool_schema.get("_stub_return")
    if stub_ret is not None:
        return stub_ret, False

    return {"status": "ok", "result": None}, False


def _mcp_tools_list(tools: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the MCP tools/list result array."""
    out: list[dict[str, Any]] = []
    for name, schema in tools.items():
        entry: dict[str, Any] = {
            "name": name,
            "description": schema.get("description", ""),
        }
        if "parameters" in schema:
            entry["inputSchema"] = schema["parameters"]
        else:
            entry["inputSchema"] = {"type": "object", "properties": {}}
        out.append(entry)
    return out


def _run_server(tools_json_path: str) -> None:
    tools = _load_tools(tools_json_path)

    # Write all responses to stdout, read requests from stdin.
    # Use sys.stdout.buffer for byte-level control; decode/encode UTF-8 per line.
    stdin = sys.stdin
    stdout = sys.stdout

    for raw_line in stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            req = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        response: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ab-stub-mcp", "version": "0.1.0"},
            }

        elif method == "notifications/initialized":
            # Notification — no response expected; just continue.
            continue

        elif method == "tools/list":
            response["result"] = {"tools": _mcp_tools_list(tools)}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            call_args = params.get("arguments") or {}
            schema = tools.get(tool_name)
            if schema is None:
                response["error"] = {
                    "code": -32602,
                    "message": f"Unknown tool: {tool_name!r}",
                }
            else:
                content, is_error = _stub_response(schema, call_args)
                text = json.dumps(content) if isinstance(content, (dict, list)) else str(content)
                response["result"] = {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_error,
                }

        elif method == "ping":
            response["result"] = {}

        else:
            response["error"] = {
                "code": -32601,
                "message": f"Method not found: {method!r}",
            }

        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("usage: _stub_mcp.py <tools.json>\n")
        sys.exit(1)
    _run_server(sys.argv[1])
