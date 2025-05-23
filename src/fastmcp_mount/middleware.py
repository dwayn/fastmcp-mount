import logging
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class MountFastMCP:
    """
    ASGI Middleware to prefix the path in MCP 'event: endpoint' SSE messages
    with the application's actual root_path from the ASGI scope.

    This corrects the issue where the MCP server (like fastmcp) generates
    endpoint URLs (e.g., '/messages/') relative to its own root, without
    knowledge of the path it's mounted under (e.g., '/mcp/server1').
    This middleware ensures the client receives the correctly prefixed path
    (e.g., '/mcp/server1/messages/').

    Args:
        app: The ASGI application to wrap (typically the result of
             `FastMCP().sse_app()`).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Regex to find the endpoint event and capture relevant parts
        # Group 1: 'event: endpoint\r\ndata: '
        # Group 2: The relative path (e.g., /messages/ or just /) - Must start with /
        # Group 3: The remainder including optional query string and CRLFs
        #          (e.g., ?session_id=value\r\n\r\n or just \r\n\r\n)
        self._endpoint_event_regex = re.compile(
            # Match 'event: endpoint\r\ndata: ' literally
            rb"^(event: endpoint\r\ndata: )"
            # Match the path: must start with '/',
            # followed by zero or more non-'?' chars
            rb"(/[^?]*)"
            # Match the rest: optional query string starting with '?'
            # up to the end CRLFs
            rb"(\?.*?\r\n\r\n.*)$",
            re.DOTALL,  # Allow '.' to match newline characters if needed within group 3
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Pass through non-HTTP scopes directly (e.g., 'lifespan', 'websocket')
            await self.app(scope, receive, send)
            return

        # Store the root_path from the scope this middleware instance receives.
        # This represents the path *up to* where this middleware (and the app it wraps)
        # is mounted.
        # Ensure it doesn't end with a slash IF it's not the root '/' itself.
        raw_root_path = scope.get("root_path", "")
        if raw_root_path != "/" and raw_root_path.endswith("/"):
            root_path = raw_root_path.rstrip("/")
        else:
            root_path = raw_root_path

        root_path_bytes = root_path.encode("utf-8")

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                # Optimization: Only attempt regex match if the prefix is present
                if body.startswith(b"event: endpoint\r\ndata: "):
                    # logger.debug(
                    #     f"[MountFastMCP] Found potential endpoint event: "
                    #     f"{body[:150]}..."
                    # )
                    match = self._endpoint_event_regex.match(body)
                    if match:
                        prefix, relative_path, remainder = match.groups()

                        # Construct full path, avoid double slashes if root_path is '/'
                        # and relative_path starts with '/' (which it should).
                        if root_path_bytes == b"/":
                            # If mounted at root, the relative path is already correct
                            full_path = relative_path
                        else:
                            # Otherwise, prepend the root path
                            full_path = root_path_bytes + relative_path

                        # Reconstruct the message body
                        new_body = prefix + full_path + remainder
                        message["body"] = new_body  # Modify the message in place
                        logger.info(
                            f"[MountFastMCP] Rewrote endpoint path. "
                            f"Original relative: {relative_path.decode()}, "
                            f"New full: {full_path.decode()}"
                        )
                        # logger.debug(
                        #     f"[MountFastMCP] Rewritten body: {new_body[:150]}..."
                        # )
                    # else:
                    # Log if the prefix matched but the full regex
                    # didn't (might indicate unexpected format)
                    # logger.warning(
                    #     f"[MountFastMCP] Endpoint event prefix found but "
                    #     f"regex failed detailed match. Body: {body[:150]}..."
                    # )

            # Send the original or modified message
            await send(message)

        # Call the wrapped application with the original scope/receive,
        # but using our wrapped_send function.
        await self.app(scope, receive, wrapped_send)
