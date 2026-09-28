"""I/O service for ABB RWS Dashboard.

Monitors digital inputs, digital outputs, analog signals, supports search/filter,
and provides safe output toggling.
"""

from typing import Any, Dict, List, Optional
from backend.rws_client import rws_client
from backend.services.event_service import event_service


class IOService:
    """Provides methods for querying and controlling robot I/O signals."""

    def get_signals(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch robot signals with optional category filter (di, do, ai, ao, all)."""
        data = rws_client.get_data("/rw/iosystem/signals")
        signals = data.get("signals", [])

        if not signals:
            data = rws_client.get_data("/rw/iosys/signals")
            signals = data.get("signals", [])

        if not category or category.lower() == "all":
            return signals

        cat_clean = category.lower()
        filtered = []
        for sig in signals:
            sig_type = str(sig.get("type", "")).lower()
            sig_cat = str(sig.get("category", "")).lower()
            if cat_clean in (sig_type, sig_cat) or (cat_clean == "di" and "di" in sig_type) or (cat_clean == "do" and "do" in sig_type):
                filtered.append(sig)
        return filtered

    def get_digital_inputs(self) -> List[Dict[str, Any]]:
        """Fetch all digital input signals."""
        return self.get_signals(category="di")

    def get_digital_outputs(self) -> List[Dict[str, Any]]:
        """Fetch all digital output signals."""
        return self.get_signals(category="do")

    def set_signal_value(self, signal_name: str, value: Any) -> Dict[str, Any]:
        """Set digital or analog output signal value."""
        payload = {"lvalue": str(value)}

        with rws_client.mastership():
            # Try /rw/iosystem/signals first, then fallback
            endpoint = f"/rw/iosystem/signals/{signal_name}"
            response = rws_client.post(endpoint, data=payload, params={"action": "set"})
            if hasattr(response, "status_code") and response.status_code == 404:
                endpoint = f"/rw/iosys/signals/{signal_name}"
                response = rws_client.post(endpoint, data=payload, params={"action": "set"})

            data = response if isinstance(response, dict) else {}

        status = data.get("status", "success")
        if status != "error":
            event_service.log_event(
                "INFO",
                f"Signal '{signal_name}' set to value {value}",
                source="Operator",
            )
            return {"success": True, "signal": signal_name, "value": value, "result": data}
        else:
            event_service.log_event(
                "ERROR",
                f"Failed to set signal '{signal_name}' to {value}: {data.get('message')}",
                source="Operator",
            )
            return {"success": False, "message": data.get("message", "Error setting signal"), "result": data}


io_service = IOService()
