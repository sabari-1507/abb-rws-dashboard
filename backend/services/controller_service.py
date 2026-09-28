"""Controller service for ABB RWS Dashboard.

Retrieves controller operational state, panel mode, system health, and handles
connection lifecycle.
"""

from typing import Any, Dict
from backend.config import config
from backend.rws_client import rws_client
from backend.services.event_service import event_service


class ControllerService:
    """Provides methods for reading controller status and updating settings."""

    def get_status(self) -> Dict[str, Any]:
        """Fetch real-time controller operational state."""
        connected, msg = rws_client.test_connection()
        is_sim = rws_client.is_simulation()

        pnl_ctrl = rws_client.get_data("/rw/panel/ctrlstate")
        pnl_op = rws_client.get_data("/rw/panel/opmode")

        ctrlstate = pnl_ctrl.get("ctrlstate", "motoron" if is_sim else "unknown")
        opmode = pnl_op.get("opmode", pnl_ctrl.get("opmode", "AUTO" if is_sim else "unknown"))

        return {
            "connected": connected or is_sim,
            "simulation": is_sim,
            "message": msg,
            "ip": config.ROBOT_IP,
            "port": config.ROBOT_PORT,
            "task_name": config.TASK_NAME,
            "ctrlstate": ctrlstate,
            "opmode": opmode,
            "motors_on": ctrlstate.lower() in ("motoron", "motorson"),
            "is_auto": opmode.upper() in ("AUTO", "AUTOMATIC"),
            "system_status": "NORMAL" if (connected or is_sim) else "DISCONNECTED",
        }

    def get_info(self) -> Dict[str, Any]:
        """Fetch general controller specification and hardware info."""
        data = rws_client.get_data("/rw/system")

        ctrl_name = data.get("name", data.get("controller_name", "IRC5 Controller"))
        rw_ver = data.get("rwversionname", data.get("rwversion", data.get("robotware_version", "6.06.03.00")))
        sys_name = data.get("title", data.get("system_name", "Robot_System"))
        sys_id = data.get("sysid", data.get("serial_number", "120-104928"))

        return {
            "controller_name": ctrl_name,
            "system_name": sys_name,
            "robotware_version": rw_ver,
            "robot_type": data.get("robot_type", "IRB 1660ID-6/1.55"),
            "serial_number": sys_id,
            "axis_count": data.get("axis_count", 6),
            "ip_address": config.ROBOT_IP,
            "active_task": config.TASK_NAME,
        }

    def update_connection_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update controller connection parameters and verify."""
        config.update_config(new_settings)
        connected, msg = rws_client.test_connection()
        event_service.log_event(
            "INFO",
            f"Controller configuration updated (IP: {config.ROBOT_IP}, Task: {config.TASK_NAME}, Sim: {config.SIMULATION_MODE})",
            source="Operator",
        )
        return {
            "success": True,
            "connected": connected or rws_client.is_simulation(),
            "simulation": rws_client.is_simulation(),
            "message": msg,
            "config": config.get_public_config(),
        }


controller_service = ControllerService()
