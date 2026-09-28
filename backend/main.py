"""ABB Robot Web Services (RWS) Dashboard — FastAPI Application Entrypoint.

Provides REST APIs for monitoring, RAPID program and module management, Program Pointer
navigation, execution control, I/O monitoring, and serves the dashboard frontend.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import config
from backend.rws_client import rws_client
from backend.services.event_service import event_service
from backend.services.robot_state_service import robot_state_service
from backend.routers import controller, rapid, modules, io, system, events, robot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    # Test connection to controller on startup
    connected, msg = rws_client.test_connection()
    event_service.log_event(
        "INFO",
        f"Server started. Controller mode: {'Simulation' if rws_client.is_simulation() else 'Live'} ({msg})",
        source="System",
    )
    # Start digital twin low-latency polling loop
    await robot_state_service.start()
    yield
    # Stop digital twin polling loop on shutdown
    await robot_state_service.stop()
    event_service.log_event("INFO", "Server shutting down", source="System")


app = FastAPI(
    title="ABB Robot Web Services (RWS) Dashboard",
    description="Web-based monitoring and control dashboard for ABB Robot Controllers via RWS",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(controller.router)
app.include_router(rapid.router)
app.include_router(modules.router)
app.include_router(io.router)
app.include_router(system.router)
app.include_router(events.router)
app.include_router(robot.router)

# Mount frontend directory for static assets
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        """Serve dashboard single-page web app."""
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        return FileResponse(index_file)
