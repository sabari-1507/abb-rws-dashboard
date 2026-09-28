"""Controller API router for ABB RWS Dashboard."""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import config
from backend.services.controller_service import controller_service

router = APIRouter(prefix="/api/controller", tags=["Controller"])


class ConfigUpdateRequest(BaseModel):
    robot_ip: str = Field(default="192.168.125.1")
    robot_port: int = Field(default=80)
    username: str = Field(default="Default User")
    password: str = Field(default="robotics")
    task_name: str = Field(default="T_ROB1")
    timeout: float = Field(default=3.0)
    simulation_mode: bool = Field(default=False)


@router.get("/status")
def get_controller_status() -> Dict[str, Any]:
    """Get live controller operational state and connection health."""
    try:
        return controller_service.get_status()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/info")
def get_controller_info() -> Dict[str, Any]:
    """Get controller hardware and software identification."""
    try:
        return controller_service.get_info()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/config")
def get_config() -> Dict[str, Any]:
    """Get current safe configuration (without sensitive secrets)."""
    return config.get_public_config()


@router.post("/config")
def update_config(req: ConfigUpdateRequest) -> Dict[str, Any]:
    """Update controller connection parameters and verify status."""
    try:
        return controller_service.update_connection_settings(req.model_dump())
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
