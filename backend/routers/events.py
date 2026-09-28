"""Events and audit log router for ABB RWS Dashboard."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from backend.rws_client import rws_client
from backend.services.event_service import event_service

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("")
def get_events(
    limit: int = Query(default=100, ge=1, le=500),
    level: Optional[str] = Query(default=None, description="INFO, WARNING, ERROR, SUCCESS, ALL"),
) -> List[Dict[str, Any]]:
    """Retrieve system, controller, and operator events."""
    try:
        data = rws_client.get_data("/rw/elog/0?order=lifo&limit=15")
        elogs = data.get("elogs", [])
        if elogs:
            event_service.sync_controller_events(elogs)
    except Exception:
        pass
    return event_service.get_events(limit=limit, level=level)


@router.post("/clear")
def clear_events() -> Dict[str, Any]:
    """Clear in-memory event buffer."""
    event_service.clear()
    return {"success": True, "message": "Event log cleared"}
