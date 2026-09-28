"""System specifications router for ABB RWS Dashboard."""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException

from backend.services.system_service import system_service

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/info")
def get_system_info() -> Dict[str, Any]:
    """Get controller hardware and robot specifications."""
    try:
        return system_service.get_system_info()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
