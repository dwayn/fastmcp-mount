# tests/test_middleware.py
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from fastmcp_mount import MountFastMCP

# --- Test ASGI App Definitions (Adapted to Request/Response pattern) ---


async def generate_sse_with_endpoint(request: Request) -> StreamingResponse:
    """An endpoint simulating the problematic SSE message."""
    session_id = "test-session-123"
    relative_endpoint_path = f"/messages/?session_id={session_id}"
    sse_event = f"event: endpoint\r\ndata: {relative_endpoint_path}\r\n\r\n"

    async def stream():
        yield "event: info\r\ndata: Connected\r\n\r\n"
        yield sse_event
        yield "event: done\r\ndata: Finished\r\n\r\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


async def simple_http_endpoint(request: Request) -> PlainTextResponse:
    """A basic HTTP endpoint for testing non-SSE passthrough."""
    return PlainTextResponse("Hello")


async def _lifespan_app_local(scope: Scope, receive: Receive, send: Send):
    """An ASGI app focusing only on lifespan messages."""
    lifespan_startup_called = False
    lifespan_shutdown_called = False
    message = await receive()
    if message["type"] == "lifespan.startup":
        lifespan_startup_called = True
        await send({"type": "lifespan.startup.complete"})
        message = await receive()
        assert message["type"] == "lifespan.shutdown"
        lifespan_shutdown_called = True
        await send({"type": "lifespan.shutdown.complete"})
        scope["state"] = {
            "startup": lifespan_startup_called,
            "shutdown": lifespan_shutdown_called,
        }  # Store state if needed outside


# --- Tests ---


@pytest.mark.parametrize(
    "mount_path, expected_endpoint_data",
    [
        ("", "/messages/?session_id=test-session-123"),  # Mounted at root
        ("/", "/messages/?session_id=test-session-123"),  # Mounted at root explicitly
        ("/mcp", "/mcp/messages/?session_id=test-session-123"),  # Mounted at /mcp
        (
            "/api/v1/mcp",
            "/api/v1/mcp/messages/?session_id=test-session-123",
        ),  # Deeper mount path
    ],
)
def test_endpoint_path_rewriting(mount_path, expected_endpoint_data):
    """Verify the endpoint path is correctly prefixed based on the mount path."""
    raw_sse_app = Starlette(routes=[Route("/sse", endpoint=generate_sse_with_endpoint)])
    wrapped_app = MountFastMCP(app=raw_sse_app)

    if not mount_path or mount_path == "/":
        host_app = wrapped_app
        target_url = "/sse"
    else:
        host_app = Starlette()
        # Ensure mount_path starts with / if not empty
        if not mount_path.startswith("/"):
            mount_path = "/" + mount_path
        host_app.mount(mount_path, app=wrapped_app)
        target_url = f"{mount_path}/sse"

    client = TestClient(host_app)
    response = client.get(target_url)

    assert response.status_code == 200
    # Modify assertion to check the start of the content-type header
    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )

    raw_data = response.content
    try:
        sse_events = raw_data.decode().split("\r\n\r\n")
    except UnicodeDecodeError:
        pytest.fail(f"Failed to decode SSE response: {raw_data[:200]}...")

    endpoint_event_data = None
    for event in sse_events:
        if event.startswith("event: endpoint"):
            lines = event.strip().split("\r\n")
            for line in lines:
                if line.startswith("data:"):
                    endpoint_event_data = line[len("data: ") :].strip()
                    break
            break

    assert endpoint_event_data is not None, (
        "Endpoint event not found in SSE stream. "
        f"Raw data received: {raw_data.decode()[:200]}..."
    )
    assert endpoint_event_data == expected_endpoint_data


def test_non_sse_request_passthrough():
    """Verify non-SSE requests are passed through without modification."""
    raw_http_app = Starlette(routes=[Route("/hello", endpoint=simple_http_endpoint)])
    wrapped_app = MountFastMCP(app=raw_http_app)
    host_app = Starlette()
    host_app.mount("/api", app=wrapped_app)
    client = TestClient(host_app)
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert response.text == "Hello"
    # Check content-type includes charset added by PlainTextResponse
    assert response.headers["content-type"] == "text/plain; charset=utf-8"


def test_lifespan_passthrough():
    """Verify 'lifespan' scope is passed through using TestClient."""
    wrapped_app = MountFastMCP(app=_lifespan_app_local)
    # TestClient handles lifespan automatically.
    try:
        with TestClient(wrapped_app) as _:  # Use _ for unused client variable
            pass  # Entering/exiting context manager is the test
    except Exception as e:
        pytest.fail(f"TestClient failed during lifespan execution: {e}")
    # If no exception occurred, the lifespan calls were likely
    # handled correctly by the client/transport
