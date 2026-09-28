"""Event and error logging service for ABB RWS Dashboard.

Maintains in-memory ring buffer of events, operator actions, controller notifications,
and communication alerts, synchronizing directly with controller elog when connected.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from collections import deque


class EventService:
    """Manages events, error logs, and operator audit trail."""

    def __init__(self, max_events: int = 500):
        self._events = deque(maxlen=max_events)
        self._counter = 0
        self._synced_elog_ids: Set[str] = set()
        self.log_event("INFO", "ABB RWS Dashboard initialized", source="System")

    def log_event(self, level: str, message: str, source: str = "System", details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record an event in the ring buffer."""
        self._counter += 1
        event = {
            "id": self._counter,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "level": level.upper(),  # INFO, WARNING, ERROR, SUCCESS
            "source": source,
            "message": message,
            "details": details or {},
        }
        self._events.appendleft(event)
        return event

    def sync_controller_events(self, elogs: List[Dict[str, str]]) -> None:
        """Sync live controller elog entries from RWS."""
        type_map = {"1": "INFO", "2": "WARNING", "3": "ERROR"}
        for ev in reversed(elogs):
            code = ev.get("code", "")
            tstamp = ev.get("tstamp", "")
            src = ev.get("src-name", "Controller")
            desc = ev.get("desc", "")
            unique_key = f"{tstamp}_{code}_{src}"

            if unique_key not in self._synced_elog_ids:
                self._synced_elog_ids.add(unique_key)
                level = type_map.get(str(ev.get("msgtype", "1")), "INFO")
                time_str = tstamp.split("T")[-1].strip() if "T" in tstamp else tstamp
                msg = f"Controller Alarm {code} [{src}]" + (f": {desc}" if desc else "")
                self._counter += 1
                self._events.appendleft({
                    "id": self._counter,
                    "timestamp": time_str or datetime.now().strftime("%H:%M:%S"),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "level": level,
                    "source": "Controller",
                    "message": msg,
                    "details": ev,
                })

    def get_events(self, limit: int = 100, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent events, optionally filtered by level."""
        events = list(self._events)
        if level and level.upper() != "ALL":
            events = [e for e in events if e["level"] == level.upper()]
        return events[:limit]

    def clear(self) -> None:
        """Clear the event buffer."""
        self._events.clear()
        self.log_event("INFO", "Event log cleared by user", source="Operator")


event_service = EventService()
