"""I/O monitoring and signal control router for ABB RWS Dashboard."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.io_service import io_service

router = APIRouter(prefix="/api/io", tags=["I/O"])


class SetSignalRequest(BaseModel):
    signal_name: str = Field(..., description="Signal identifier, e.g. DO_Light")
    value: Any = Field(..., description="New signal value (e.g. 0, 1, or float)")


@router.get("/signals")
def get_signals(category: Optional[str] = Query(default=None, description="Filter: di, do, ai, ao, all")) -> List[Dict[str, Any]]:
    """Get robot I/O signals with optional category filter."""
    try:
        return io_service.get_signals(category=category)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/digital-inputs")
def get_digital_inputs() -> List[Dict[str, Any]]:
    """Get list of all digital input signals."""
    try:
        return io_service.get_digital_inputs()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/digital-outputs")
def get_digital_outputs() -> List[Dict[str, Any]]:
    """Get list of all digital output signals."""
    try:
        return io_service.get_digital_outputs()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/set-signal")
def set_signal(req: SetSignalRequest) -> Dict[str, Any]:
    """Set the state or value of an I/O signal."""
    try:
        return io_service.set_signal_value(signal_name=req.signal_name, value=req.value)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
