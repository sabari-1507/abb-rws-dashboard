"""Robot Motion and Digital Twin Router for ABB RWS Dashboard.

Provides REST and high-performance WebSocket endpoints for streaming live joint
angles and TCP poses to the 3D Digital Twin visualization.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.services.robot_state_service import robot_state_service

router = APIRouter(prefix="/api/robot", tags=["Digital Twin"])


@router.get("/joint-state")
def get_joint_state() -> Dict[str, Any]:
    """One-shot read of the latest 6-axis joint angles and connection status."""
    try:
        return robot_state_service.get_latest_joint_state()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/tcp-pose")
def get_tcp_pose() -> Dict[str, Any]:
    """One-shot read of the current Tool Center Point (TCP) cartesian coordinates."""
    try:
        return robot_state_service.get_tcp_pose()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.websocket("/ws")
async def robot_telemetry_ws(websocket: WebSocket):
    """High-frequency low-latency WebSocket push stream for 3D digital twin.
    
    Pushes minimal JSON packets: {"j": [j1, j2, j3, j4, j5, j6], "t": timestamp_ms}
    """
    await robot_state_service.connect(websocket)
    try:
        while True:
            # Keep socket open and respond to client pings if received
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await robot_state_service.disconnect(websocket)
    except Exception:
        await robot_state_service.disconnect(websocket)
