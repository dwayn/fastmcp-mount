# FastMCP Mount

[![CI](https://github.com/dwayn/fastmcp-mount/actions/workflows/ci.yml/badge.svg)](https://github.com/dwayn/fastmcp-mount/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

ASGI Middleware to fix [FastMCP](https://github.com/modelcontextprotocol/python-sdk?tab=readme-ov-file#mounting-to-an-existing-asgi-server) endpoint paths when mounted under a sub-path in frameworks like FastAPI or Starlette.

## The Problem

When using the official MCP SDK, the `FastMCP` server generates an SSE `event: endpoint` message containing the path for the client to post messages back (e.g., `/messages/`). However, if you mount the `FastMCP().sse_app()` ASGI application under a sub-path in your main framework (like FastAPI), for example at `/mcp/my-server`, the endpoint path sent to the client remains `/messages/` instead of the correct, fully qualified path `/mcp/my-server/messages/`. This causes client post requests to fail with a 404 Not Found error.

## The Solution

This library provides a simple ASGI middleware, `MountFastMCP`, that intercepts the SSE response stream. It specifically looks for the `event: endpoint` message and automatically prepends the correct `root_path` (the path where the app is mounted) to the endpoint before sending it to the client.

## Installation

```bash
pip install fastmcp-mount
```
Or using UV:
```bash
uv pip install fastmcp-mount
```

You will also need the official [MCP python SDK](https://github.com/modelcontextprotocol/python-sdk) and a compatible ASGI framework like `fastapi` or `starlette`.

```bash
pip install mcp[cli] fastapi uvicorn[standard]
# or
uv pip install mcp[cli] fastapi uvicorn[standard]
```

## Usage

Simply wrap the `FastMCP().sse_app()` with `MountFastMCP` before mounting it in your main application.

```python
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from fastmcp_mount import MountFastMCP # Import the middleware
import uvicorn

# 1. Create your FastMCP instance and define tools (as usual)
mcp_server = FastMCP(title="My Mounted Server")

@mcp_server.tool()
def my_tool(param: str) -> str:
    return f"Processed: {param}"

# 2. Get the raw SSE ASGI app
sse_app = mcp_server.sse_app()

# 3. Create your main FastAPI/Starlette app
app = FastAPI(title="Main API")

# 4. Mount the *wrapped* app at your desired sub-path
app.mount("/mcp/my-server", app=MountFastMCP(app=sse_app), name="my_mcp_server")

@app.get("/")
def read_root():
    return {"message": "Main API running"}

# Run with: uvicorn your_module:app --reload
# Connect your MCP client to: http://localhost:8000/mcp/my-server/sse
```

Now, when an MCP client connects to `/mcp/my-server/sse`, the endpoint it receives from the server will be correctly prefixed with `/mcp/my-server/...`, allowing the client to post back successfully.

## Compatibility

*   **Python:** 3.8+
*   **Frameworks:** Starlette, FastAPI (and likely other Starlette-based ASGI frameworks)
*   **Dependencies:** `starlette`

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request on the [GitHub repository](https://github.com/dwayn/fastmcp-mount).

1.  Fork the repository.
2.  Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3.  Install development dependencies: `pip install -e ".[dev,test]"`
4.  Make your changes and add tests.
5.  Run tests: `pytest`
6.  Format, lint, and type check: `ruff format . && ruff check . && mypy .`
7.  Commit and push your changes.
8.  Open a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
