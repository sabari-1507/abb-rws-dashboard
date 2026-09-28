"""Robot State Service for ABB RWS Dashboard.

Implements a single, tight, low-latency polling loop against the controller's
motion system resource (/rw/motionsystem/mechunits/{MECH_UNIT}/jointtarget)
and fans out minimal joint state updates to all connected WebSocket clients.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket

from backend.config import config
from backend.rws_client import rws_client

logger = logging.getLogger("robot_state_service")


class RobotStateService:
    """Manages robot motion system polling and WebSocket broadcast."""

    def __init__(self):
        self._active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._latest_joints: List[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self._latest_timestamp: int = int(time.time() * 1000)
        self._is_stale: bool = False
        self._consecutive_failures: int = 0

    @property
    def client_count(self) -> int:
        """Number of currently connected WebSocket clients."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new client WebSocket and send immediate current pose."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info("Digital twin client connected. Total clients: %d", len(self._active_connections))
        
        # Send current state immediately on connect
        init_payload = {
            "j": self._latest_joints,
            "t": self._latest_timestamp,
            "status": "stale" if self._is_stale else "live",
            "sim": rws_client.is_simulation(),
        }
        try:
            await websocket.send_json(init_payload)
        except Exception:
            pass

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a client WebSocket."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info("Digital twin client disconnected. Remaining clients: %d", len(self._active_connections))

    async def start(self) -> None:
        """Start the background motion system polling loop."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Robot state service started (cadence: %d ms, unit: %s)",
            config.ROBOT_POLL_INTERVAL_MS,
            config.MECH_UNIT,
        )

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("Robot state service stopped")

    def _fetch_jointtarget(self) -> Optional[List[float]]:
        """Synchronously fetch and parse jointtarget from controller."""
        endpoint = f"/rw/motionsystem/mechunits/{config.MECH_UNIT}/jointtarget"
        try:
            data = rws_client.get_data(endpoint)
            return self._extract_joints(data)
        except Exception as ex:
            logger.debug("Failed to query jointtarget: %s", ex)
            return None

    def _extract_joints(self, data: Dict[str, Any]) -> Optional[List[float]]:
        """Extract 6 joint floats (rax_1 to rax_6) from parsed RWS response."""
        if not data or not isinstance(data, dict):
            return None

        # Format 1: Direct keys in dict
        j = []
        has_direct = True
        for i in range(1, 7):
            val = data.get(f"rax_{i}")
            if val is None:
                val = data.get(f"rax{i}")
            if val is not None:
                try:
                    j.append(float(val))
                except (ValueError, TypeError):
                    has_direct = False
                    break
            else:
                has_direct = False
                break
        if has_direct and len(j) == 6:
            return j

        # Format 2: RWS JSON structure: _embedded._state[0].rax_i
        embedded = data.get("_embedded", {})
        if isinstance(embedded, dict):
            state_list = embedded.get("_state", [])
            if state_list and isinstance(state_list, list):
                state = state_list[0]
                j = []
                for i in range(1, 7):
                    val = state.get(f"rax_{i}")
                    if val is None:
                        val = state.get(f"rax{i}")
                    if val is not None:
                        try:
                            j.append(float(val))
                        except (ValueError, TypeError):
                            return None
                    else:
                        return None
                if len(j) == 6:
                    return j

        # Format 3: XHTML spans
        spans = data.get("spans", {})
        if isinstance(spans, dict) and spans:
            j = []
            for i in range(1, 7):
                val = spans.get(f"rax_{i}")
                if val is None:
                    val = spans.get(f"rax{i}")
                if val is not None:
                    try:
                        j.append(float(val))
                    except (ValueError, TypeError):
                        return None
                else:
                    return None
            if len(j) == 6:
                return j

        return None

    async def _poll_loop(self) -> None:
        """Continuous polling loop running at specified poll interval."""
        interval_sec = max(0.05, config.ROBOT_POLL_INTERVAL_MS / 1000.0)

        while self._running:
            start_time = time.monotonic()
            now_ms = int(time.time() * 1000)

            # Fetch via thread pool to avoid blocking the asyncio event loop
            joints = await asyncio.to_thread(self._fetch_jointtarget)

            if joints is not None:
                self._latest_joints = joints
                self._latest_timestamp = now_ms
                self._is_stale = False
                self._consecutive_failures = 0

                # Minimal compact payload for minimum delay
                payload = {
                    "j": joints,
                    "t": now_ms,
                }
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    self._is_stale = True

                payload = {
                    "j": self._latest_joints,
                    "t": now_ms,
                    "status": "stale",
                }

            # Fan out to all connected WebSocket clients
            if self._active_connections:
                await self._broadcast(payload)

            # Sleep remaining interval to maintain target cadence
            elapsed = time.monotonic() - start_time
            sleep_duration = max(0.005, interval_sec - elapsed)
            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        """Broadcast payload to all active clients; remove stale/closed sockets."""
        async with self._lock:
            clients = list(self._active_connections)

        if not clients:
            return

        # Parallel transmission to all connected tabs
        dead_clients = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_clients.append(ws)

        if dead_clients:
            async with self._lock:
                for ws in dead_clients:
                    self._active_connections.discard(ws)

    def get_latest_joint_state(self) -> Dict[str, Any]:
        """Return latest joint state for REST one-shot endpoints."""
        return {
            "joints": self._latest_joints,
            "timestamp": self._latest_timestamp,
            "status": "stale" if self._is_stale else "live",
            "simulation": rws_client.is_simulation(),
            "connected_clients": len(self._active_connections),
            "mech_unit": config.MECH_UNIT,
        }

    def get_tcp_pose(self) -> Dict[str, Any]:
        """Fetch TCP pose (x, y, z, q1..q4) from /robtarget."""
        endpoint = f"/rw/motionsystem/mechunits/{config.MECH_UNIT}/robtarget"
        data = rws_client.get_data(endpoint)
        return {
            "x": float(data.get("x", 0.0)),
            "y": float(data.get("y", 0.0)),
            "z": float(data.get("z", 0.0)),
            "q1": float(data.get("q1", 1.0)),
            "q2": float(data.get("q2", 0.0)),
            "q3": float(data.get("q3", 0.0)),
            "q4": float(data.get("q4", 0.0)),
            "timestamp": int(time.time() * 1000),
        }


# Singleton service instance
robot_state_service = RobotStateService()
