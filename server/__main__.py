import uvicorn

from server.analytics import http_app
from server.app import mcp


def main() -> None:
    uvicorn.run(http_app(mcp), host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    main()
