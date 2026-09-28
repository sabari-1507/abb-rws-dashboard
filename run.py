"""Single-command runner script for ABB RWS Dashboard.

Launches the FastAPI backend with Uvicorn server and serves both the REST API
and the responsive web interface.
"""

import os
import sys
import uvicorn

# Ensure the rws_dashboard root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def main():
    """Start the Uvicorn ASGI server."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print("=" * 65)
    print("      ABB Robot Web Services (RWS) Dashboard")
    print("=" * 65)
    print(f"  * Web Dashboard:  http://127.0.0.1:{port}")
    print(f"  * REST API Docs:  http://127.0.0.1:{port}/docs")
    print(f"  * Host Binding:   {host}:{port}")
    print("=" * 65)
    print("Press CTRL+C to stop the server.\n")

    uvicorn.run("backend.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
