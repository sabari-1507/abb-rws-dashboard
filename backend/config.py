"""Configuration module for ABB RWS Dashboard.

Stores controller connection parameters, credentials, timeouts, and simulation settings.
"""

import os
from typing import Dict, Any


class Config:
    """Robot controller and dashboard configuration."""

    ROBOT_IP: str = os.getenv("ROBOT_IP", "192.168.125.1")
    ROBOT_PORT: int = int(os.getenv("ROBOT_PORT", "80"))
    USERNAME: str = os.getenv("ROBOT_USERNAME", "Default User")
    PASSWORD: str = os.getenv("ROBOT_PASSWORD", "robotics")
    TASK_NAME: str = os.getenv("ROBOT_TASK", "T_ROB1")
    TIMEOUT: float = float(os.getenv("ROBOT_TIMEOUT", "3.0"))
    
    # Simulation mode flag. If True, simulates RWS responses.
    # If False, attempts live communication with fallback if unreachable.
    SIMULATION_MODE: bool = os.getenv("SIMULATION_MODE", "false").lower() in ("true", "1", "yes")

    # Polling intervals in milliseconds
    REFRESH_CRITICAL_MS: int = 1000
    REFRESH_NORMAL_MS: int = 4000
    ROBOT_POLL_INTERVAL_MS: int = int(os.getenv("ROBOT_POLL_INTERVAL_MS", "100"))
    MECH_UNIT: str = os.getenv("ROBOT_MECH_UNIT", "ROB_1")

    @classmethod
    def get_public_config(cls) -> Dict[str, Any]:
        """Return configuration safe for frontend consumption (omits password)."""
        return {
            "robot_ip": cls.ROBOT_IP,
            "robot_port": cls.ROBOT_PORT,
            "username": cls.USERNAME,
            "task_name": cls.TASK_NAME,
            "mech_unit": cls.MECH_UNIT,
            "timeout": cls.TIMEOUT,
            "simulation_mode": cls.SIMULATION_MODE,
            "refresh_critical_ms": cls.REFRESH_CRITICAL_MS,
            "refresh_normal_ms": cls.REFRESH_NORMAL_MS,
            "robot_poll_interval_ms": cls.ROBOT_POLL_INTERVAL_MS,
        }

    @classmethod
    def update_config(cls, data: Dict[str, Any]) -> None:
        """Update configuration parameters at runtime."""
        if "robot_ip" in data and data["robot_ip"]:
            cls.ROBOT_IP = str(data["robot_ip"]).strip()
        if "robot_port" in data and data["robot_port"]:
            cls.ROBOT_PORT = int(data["robot_port"])
        if "username" in data and data["username"]:
            cls.USERNAME = str(data["username"]).strip()
        if "password" in data and data["password"]:
            cls.PASSWORD = str(data["password"])
        if "task_name" in data and data["task_name"]:
            cls.TASK_NAME = str(data["task_name"]).strip()
        if "timeout" in data and data["timeout"]:
            cls.TIMEOUT = float(data["timeout"])
        if "simulation_mode" in data:
            cls.SIMULATION_MODE = bool(data["simulation_mode"])


config = Config()
