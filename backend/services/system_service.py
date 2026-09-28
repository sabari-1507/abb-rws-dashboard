"""System information service for ABB RWS Dashboard.

Retrieves detailed system specifications, controller hardware info, RobotWare release,
and robot mechanical unit configuration.
"""

from typing import Any, Dict
from backend.config import config
from backend.rws_client import rws_client


class SystemService:
    """Provides methods for reading controller and robot specifications."""

    def get_system_info(self) -> Dict[str, Any]:
        """Fetch system, controller, and mechanical unit specifications."""
        data = rws_client.get_data("/rw/system")

        ctrl_name = data.get("name", data.get("controller_name", "IRC5 Controller"))
        rw_ver = data.get("rwversionname", data.get("rwversion", data.get("robotware_version", "6.06.03.00")))
        sys_name = data.get("title", data.get("system_name", "Robot_System"))
        sys_id = data.get("sysid", data.get("serial_number", "120-104928"))
        options = data.get("options", [])

        # Find robot arm model from options (e.g. IRB 1660ID-6/1.55)
        robot_model = data.get("robot_type", "IRB 1660ID-6/1.55")
        for opt in options:
            if "IRB " in opt:
                robot_model = opt
                break

        return {
            "controller": {
                "controller_name": ctrl_name,
                "system_name": sys_name,
                "robotware_version": rw_ver,
                "serial_number": sys_id,
                "ip_address": config.ROBOT_IP,
                "port": config.ROBOT_PORT,
            },
            "robot": {
                "robot_type": robot_model,
                "mechanical_unit": "ROB_1",
                "axes": data.get("axis_count", 6),
                "payload_kg": 6.0 if "1660" in robot_model else 3.0,
                "reach_m": 1.55 if "1660" in robot_model else 0.58,
            },
            "rapid": {
                "active_task": config.TASK_NAME,
                "tasks": ["T_ROB1"],
            },
            "options": options or [
                "RobotWare Base",
                "PC Interface (RWS)",
                "Multitasking",
            ],
        }


system_service = SystemService()
