"""ABB Robot Web Services (RWS) Client.

Provides session management, HTTP Digest Authentication, mastership control,
XHTML and JSON response parsing, file upload to $HOME, and transparent simulation fallback.
"""

import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
from requests.auth import HTTPDigestAuth

from backend.config import config

logger = logging.getLogger("rws_client")


def parse_rws_xhtml(text: str) -> Dict[str, Any]:
    """Parse ABB RWS XHTML response into structured dictionary."""
    if not text or not ("<html" in text or "<?xml" in text):
        return {}

    try:
        root = ET.fromstring(text)
        ns = "http://www.w3.org/1999/xhtml"
        result: Dict[str, Any] = {}

        # Collect all spans
        spans: Dict[str, str] = {}
        for s in root.iter(f"{{{ns}}}span"):
            cls = s.attrib.get("class")
            if cls:
                spans[cls] = (s.text or "").strip()
        result["spans"] = spans

        # Check for modules list: li.rap-module-info-li
        modules = []
        for li in root.iter(f"{{{ns}}}li"):
            cls = li.attrib.get("class", "")
            if "rap-module-info" in cls:
                name, mtype = "", ""
                for s in li.iter(f"{{{ns}}}span"):
                    s_cls = s.attrib.get("class", "")
                    if s_cls == "name":
                        name = (s.text or "").strip()
                    elif s_cls == "type":
                        mtype = (s.text or "").strip()
                if name:
                    modules.append({"name": name, "type": mtype})
        if modules:
            result["modules"] = modules

        # Check for signals list: li.ios-signal-li
        signals = []
        for li in root.iter(f"{{{ns}}}li"):
            cls = li.attrib.get("class", "")
            if "ios-signal" in cls:
                name, stype, val, cat = "", "", "0", ""
                for s in li.iter(f"{{{ns}}}span"):
                    s_cls = s.attrib.get("class", "")
                    if s_cls == "name":
                        name = (s.text or "").strip()
                    elif s_cls == "type":
                        stype = (s.text or "").strip()
                    elif s_cls == "lvalue":
                        val = (s.text or "0").strip()
                    elif s_cls == "category":
                        cat = (s.text or "").strip()
                if name:
                    signals.append({"name": name, "type": stype, "value": val, "category": cat or stype})
        if signals:
            result["signals"] = signals

        # Check for options list: li.sys-option-li
        options = []
        for s in root.iter(f"{{{ns}}}span"):
            if s.attrib.get("class") == "option":
                options.append((s.text or "").strip())
        if options:
            result["options"] = options

        # Check for elog events: li.elog-message-li
        elogs = []
        for li in root.iter(f"{{{ns}}}li"):
            cls = li.attrib.get("class", "")
            if "elog-message" in cls:
                ev = {}
                for s in li.iter(f"{{{ns}}}span"):
                    s_cls = s.attrib.get("class", "")
                    if s_cls:
                        ev[s_cls] = (s.text or "").strip()
                if ev:
                    elogs.append(ev)
        if elogs:
            result["elogs"] = elogs

        # Promote all spans to top-level dict keys
        for k, v in spans.items():
            result[k] = v

        return result
    except Exception as ex:
        logger.debug("Failed parsing XHTML with ElementTree: %s", ex)
        return {}


class RWSClient:
    """Central client for communicating with ABB Robot Web Services (RWS)."""

    def __init__(self):
        self.session = requests.Session()
        self._last_connected = False
        self._is_simulated = False
        self._init_simulation_state()

    def _init_simulation_state(self):
        """Initialize internal state for simulation mode."""
        self._sim_state = {
            "ctrlstate": "motoron",
            "opmode": "AUTO",
            "execution": "stopped",
            "cycle": "once",
            "speedratio": 100,
            "tasks": ["T_ROB1"],
            "active_task": "T_ROB1",
            "pp": {
                "task": "T_ROB1",
                "module": "MainModule",
                "routine": "main",
                "line": 3,
                "col": 3,
                "end_line": 3,
                "end_col": 25,
            },
            "modules": [
                {"name": "BASE", "type": "SysMod"},
                {"name": "MainModule", "type": "ProgMod"},
                {"name": "pw1", "type": "ProgMod"},
                {"name": "TestModule", "type": "ProgMod"},
            ],
            "signals": {
                "DI_Start": {"type": "DI", "value": 1, "category": "digital_in"},
                "DI_Stop": {"type": "DI", "value": 0, "category": "digital_in"},
                "DI_Sensor": {"type": "DI", "value": 1, "category": "digital_in"},
                "DI_SafetyGate": {"type": "DI", "value": 1, "category": "digital_in"},
                "DI_PartPresent": {"type": "DI", "value": 0, "category": "digital_in"},
                "DO_Run": {"type": "DO", "value": 0, "category": "digital_out"},
                "DO_Light": {"type": "DO", "value": 1, "category": "digital_out"},
                "DO_Gripper": {"type": "DO", "value": 0, "category": "digital_out"},
                "DO_CycleActive": {"type": "DO", "value": 0, "category": "digital_out"},
                "DO_Alarm": {"type": "DO", "value": 0, "category": "digital_out"},
                "AI_Pressure": {"type": "AI", "value": 4.8, "category": "analog_in"},
                "AI_WeldCurrent": {"type": "AI", "value": 120.5, "category": "analog_in"},
                "AO_MotorSpeed": {"type": "AO", "value": 1500.0, "category": "analog_out"},
            },
            "system_info": {
                "system_name": "Robot_Cell_01",
                "controller_name": "IRC5 Controller",
                "robotware_version": "6.06.03.00",
                "system_type": "Robotics Controller",
                "robot_type": "IRB 1660ID-6/1.55",
                "serial_number": "1600-510330",
                "axis_count": 6,
                "options": ["RobotWare Base", "PC Interface", "Multitasking"],
            },
            "has_mastership": False,
        }

    @property
    def base_url(self) -> str:
        """Controller base URL."""
        return f"http://{config.ROBOT_IP}:{config.ROBOT_PORT}"

    def _get_auth(self) -> HTTPDigestAuth:
        return HTTPDigestAuth(config.USERNAME, config.PASSWORD)

    def is_connected(self) -> bool:
        """Check if controller is currently connected or operating in simulation."""
        return self._last_connected or config.SIMULATION_MODE or self._is_simulated

    def is_simulation(self) -> bool:
        """Return True if active in simulation mode."""
        return config.SIMULATION_MODE or self._is_simulated

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to the physical controller or fallback."""
        if config.SIMULATION_MODE:
            self._is_simulated = True
            self._last_connected = True
            return True, "Simulation mode active"

        try:
            url = f"{self.base_url}/rw/system"
            resp = self.session.get(
                url,
                auth=self._get_auth(),
                timeout=config.TIMEOUT,
                headers={"Accept": "application/json,application/xhtml+xml"},
            )
            if resp.status_code in (200, 401):
                self._last_connected = True
                self._is_simulated = False
                return True, "Connected to physical controller"
            else:
                self._is_simulated = True
                self._last_connected = False
                return False, f"Unexpected response status: {resp.status_code}"
        except Exception as ex:
            logger.info("Physical controller unreachable (%s). Using simulation.", ex)
            self._is_simulated = True
            self._last_connected = False
            return False, f"Physical controller unreachable: {str(ex)}"

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Union[Dict[str, Any], requests.Response]:
        """Send GET request to RWS or simulate response."""
        if not config.SIMULATION_MODE and not self._is_simulated:
            try:
                url = f"{self.base_url}{endpoint}"
                resp = self.session.get(
                    url,
                    auth=self._get_auth(),
                    params=params,
                    timeout=config.TIMEOUT,
                    headers={"Accept": "application/json,application/xhtml+xml"},
                )
                self._last_connected = True
                return resp
            except Exception as ex:
                logger.warning("GET %s failed (%s). Falling back to simulation.", endpoint, ex)
                self._is_simulated = True
                self._last_connected = False

        return self._simulate_get(endpoint, params)

    def get_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send GET request and return parsed dictionary (handles JSON, XHTML, or simulated)."""
        resp = self.get(endpoint, params=params)
        if isinstance(resp, dict):
            return resp
        if hasattr(resp, "text"):
            content_type = resp.headers.get("Content-Type", "").lower()
            if "json" in content_type:
                try:
                    return resp.json()
                except Exception:
                    pass
            parsed = parse_rws_xhtml(resp.text)
            if parsed:
                return parsed
            try:
                return resp.json()
            except Exception:
                return {"raw_text": resp.text, "status_code": getattr(resp, "status_code", 200)}
        return {}

    def post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], requests.Response]:
        """Send POST request to RWS or simulate response."""
        if not config.SIMULATION_MODE and not self._is_simulated:
            try:
                url = f"{self.base_url}{endpoint}"
                resp = self.session.post(
                    url,
                    auth=self._get_auth(),
                    data=data,
                    params=params,
                    timeout=config.TIMEOUT,
                    headers={"Accept": "application/json,application/xhtml+xml"},
                )
                self._last_connected = True
                return resp
            except Exception as ex:
                logger.warning("POST %s failed (%s). Falling back to simulation.", endpoint, ex)
                self._is_simulated = True
                self._last_connected = False

        return self._simulate_post(endpoint, data, params)

    def put_file(self, filename: str, content: bytes) -> bool:
        """Upload file to $HOME/ on controller via /fileservice/$HOME/{filename}."""
        if not config.SIMULATION_MODE and not self._is_simulated:
            try:
                url = f"{self.base_url}/fileservice/$HOME/{filename}"
                resp = self.session.put(
                    url,
                    auth=self._get_auth(),
                    data=content,
                    timeout=config.TIMEOUT * 3,
                    headers={"Content-Type": "application/octet-stream"},
                )
                return resp.status_code in (200, 201, 204)
            except Exception as ex:
                logger.warning("File upload failed (%s). Simulating file upload.", ex)
                self._is_simulated = True
                self._last_connected = False

        return True

    @contextmanager
    def mastership(self):
        """Context manager to acquire and release mastership."""
        acquired = self.request_mastership()
        try:
            yield acquired
        finally:
            if acquired:
                self.release_mastership()

    def request_mastership(self) -> bool:
        """Request mastership (/rw/mastership?action=request)."""
        if not config.SIMULATION_MODE and not self._is_simulated:
            try:
                url = f"{self.base_url}/rw/mastership?action=request"
                resp = self.session.post(url, auth=self._get_auth(), timeout=config.TIMEOUT)
                return resp.status_code in (200, 204)
            except Exception:
                pass
        self._sim_state["has_mastership"] = True
        return True

    def release_mastership(self) -> bool:
        """Release mastership (/rw/mastership?action=release)."""
        if not config.SIMULATION_MODE and not self._is_simulated:
            try:
                url = f"{self.base_url}/rw/mastership?action=release"
                resp = self.session.post(url, auth=self._get_auth(), timeout=config.TIMEOUT)
                return resp.status_code in (200, 204)
            except Exception:
                pass
        self._sim_state["has_mastership"] = False
        return True

    # -------------------------------------------------------------------------
    # Simulation Implementation
    # -------------------------------------------------------------------------

    def _simulate_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate realistic responses for RWS GET queries."""
        endpoint = endpoint.split("?")[0].rstrip("/")

        if endpoint in ("/rw/panel/ctrlstate", "/rw/system"):
            return {
                "ctrlstate": self._sim_state["ctrlstate"],
                "opmode": self._sim_state["opmode"],
                "name": self._sim_state["system_info"]["controller_name"],
                "system_name": self._sim_state["system_info"]["system_name"],
                "rwversionname": self._sim_state["system_info"]["robotware_version"],
                "robot_type": self._sim_state["system_info"]["robot_type"],
                "sysid": self._sim_state["system_info"]["serial_number"],
                "axis_count": self._sim_state["system_info"]["axis_count"],
                "options": self._sim_state["system_info"]["options"],
            }

        if endpoint == "/rw/panel/opmode":
            return {"opmode": self._sim_state["opmode"]}

        if endpoint == "/rw/rapid/execution":
            return {
                "ctrlexecstate": self._sim_state["execution"],
                "state": self._sim_state["execution"],
                "cycle": self._sim_state["cycle"],
                "speedratio": self._sim_state["speedratio"],
            }

        if "/pcp" in endpoint:
            return {
                "task": self._sim_state["pp"]["task"],
                "modulemame": self._sim_state["pp"]["module"],
                "modulename": self._sim_state["pp"]["module"],
                "module": self._sim_state["pp"]["module"],
                "routinename": self._sim_state["pp"]["routine"],
                "routine": self._sim_state["pp"]["routine"],
                "beginposition": f"{self._sim_state['pp']['line']},{self._sim_state['pp']['col']}",
                "line": self._sim_state["pp"]["line"],
                "col": self._sim_state["pp"]["col"],
                "end_line": self._sim_state["pp"]["end_line"],
                "end_col": self._sim_state["pp"]["end_col"],
            }

        if endpoint == "/rw/rapid/modules":
            return {"modules": self._sim_state["modules"]}

        if endpoint == "/rw/rapid/tasks":
            return {"tasks": self._sim_state["tasks"]}

        if endpoint in ("/rw/iosystem/signals", "/rw/iosys/signals"):
            sig_list = []
            for name, details in self._sim_state["signals"].items():
                sig_list.append({
                    "name": name,
                    "type": details["type"],
                    "value": details["value"],
                    "category": details["category"],
                })
            return {"signals": sig_list}

        if "/rw/elog" in endpoint:
            return {
                "elogs": [
                    {"msgtype": "1", "code": "10012", "src-name": "MC0", "tstamp": "2026-09-18 T 15:04:23", "desc": "Controller state changed to guardstop"},
                    {"msgtype": "1", "code": "10011", "src-name": "MC0", "tstamp": "2026-09-18 T 15:04:19", "desc": "Execution cycle completed"},
                    {"msgtype": "2", "code": "20032", "src-name": "SYS", "tstamp": "2026-09-18 T 14:55:00", "desc": "Speed override set to 100%"},
                ]
            }

        if "/jointtarget" in endpoint:
            # Generate continuous smooth kinematics for IRB 1660ID
            now = time.time()
            is_running = self._sim_state.get("execution") == "running"
            speed = 1.0 if is_running else 0.25
            
            # Smooth arc welding profile or idle breathing motion
            j1 = round(30.0 * math.sin(now * 0.7 * speed), 2)
            j2 = round(-10.0 + 20.0 * math.sin(now * 0.5 * speed), 2)
            j3 = round(15.0 + 22.0 * math.cos(now * 0.6 * speed), 2)
            j4 = round(20.0 * math.sin(now * 0.9 * speed), 2)
            j5 = round(40.0 + 15.0 * math.sin(now * 0.8 * speed), 2)
            j6 = round(50.0 * math.cos(now * 1.1 * speed), 2)

            return {
                "rax_1": j1,
                "rax_2": j2,
                "rax_3": j3,
                "rax_4": j4,
                "rax_5": j5,
                "rax_6": j6,
                "_embedded": {
                    "_state": [{
                        "_type": "ms-jointtarget-state",
                        "rax_1": j1,
                        "rax_2": j2,
                        "rax_3": j3,
                        "rax_4": j4,
                        "rax_5": j5,
                        "rax_6": j6,
                    }]
                }
            }

        if "/robtarget" in endpoint:
            now = time.time()
            is_running = self._sim_state.get("execution") == "running"
            speed = 1.0 if is_running else 0.25
            return {
                "x": round(680.0 + 150.0 * math.cos(now * 0.7 * speed), 2),
                "y": round(100.0 * math.sin(now * 0.7 * speed), 2),
                "z": round(450.0 + 60.0 * math.sin(now * 1.2 * speed), 2),
                "q1": round(math.cos(now * 0.3 * speed), 4),
                "q2": 0.0,
                "q3": round(math.sin(now * 0.3 * speed), 4),
                "q4": 0.0,
            }

        if "/rw/motionsystem" in endpoint:
            return {
                "mechunits": [
                    {"name": "ROB_1", "type": "TCP_ROBOT", "axes": 6, "mode": "synchronized"}
                ]
            }

        return {"status": "ok", "simulated": True, "endpoint": endpoint}

    def _simulate_post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle simulated POST actions."""
        data = data or {}
        params = params or {}
        action = params.get("action", "")

        if "/rw/rapid/execution" in endpoint:
            if action == "start":
                self._sim_state["execution"] = "running"
                return {"status": "success", "message": "RAPID execution started"}
            elif action in ("stop", "abort"):
                self._sim_state["execution"] = "stopped"
                return {"status": "success", "message": f"RAPID execution {action}ed"}
            elif action == "resetpp":
                self._sim_state["pp"]["line"] = 1
                self._sim_state["pp"]["col"] = 1
                self._sim_state["pp"]["routine"] = "main"
                return {"status": "success", "message": "Program pointer reset to main"}

        if "/pcp" in endpoint:
            if action == "set-pp-routine":
                self._sim_state["pp"]["module"] = data.get("module", self._sim_state["pp"]["module"])
                self._sim_state["pp"]["routine"] = data.get("routine", "main")
                self._sim_state["pp"]["line"] = 1
                self._sim_state["pp"]["col"] = 1
                return {"status": "success", "message": f"PP set to routine {self._sim_state['pp']['routine']}"}
            elif action in ("set-pp-curser", "set-pp-cursor"):
                self._sim_state["pp"]["module"] = data.get("module", self._sim_state["pp"]["module"])
                self._sim_state["pp"]["routine"] = data.get("routine", self._sim_state["pp"]["routine"])
                self._sim_state["pp"]["line"] = int(data.get("line", 1))
                self._sim_state["pp"]["col"] = int(data.get("col", 1))
                return {"status": "success", "message": f"PP set to line {self._sim_state['pp']['line']}"}
            elif action == "set-pp-next-inst":
                self._sim_state["pp"]["line"] += 1
                return {"status": "success", "message": f"PP advanced to line {self._sim_state['pp']['line']}"}
            elif action == "set-pp-prev-inst":
                self._sim_state["pp"]["line"] = max(1, self._sim_state["pp"]["line"] - 1)
                return {"status": "success", "message": f"PP stepped back to line {self._sim_state['pp']['line']}"}

        if "/rw/rapid/tasks" in endpoint and action == "loadmod":
            modulepath = data.get("modulepath", "")
            filename = modulepath.split("/")[-1]
            mod_name = filename.rsplit(".", 1)[0]
            ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
            mod_type = "SysMod" if ext == "sys" else "ProgMod"

            existing = [m for m in self._sim_state["modules"] if m["name"] == mod_name]
            if existing and not str(data.get("replace", "false")).lower() in ("true", "1", "yes"):
                return {"status": "error", "message": f"Module {mod_name} already exists. Set replace=true."}

            self._sim_state["modules"] = [m for m in self._sim_state["modules"] if m["name"] != mod_name]
            self._sim_state["modules"].append({"name": mod_name, "type": mod_type})
            return {"status": "success", "message": f"Module {mod_name} loaded successfully"}

        if "/rw/rapid/tasks" in endpoint and action == "unloadmod":
            mod_name = data.get("module", "")
            if not any(m["name"] == mod_name for m in self._sim_state["modules"]):
                return {"status": "error", "message": f"Module {mod_name} not found"}
            self._sim_state["modules"] = [m for m in self._sim_state["modules"] if m["name"] != mod_name]
            return {"status": "success", "message": f"Module {mod_name} unloaded successfully"}

        if ("/rw/iosystem/signals" in endpoint or "/rw/iosys/signals" in endpoint) and action == "set":
            sig_name = endpoint.split("/")[-1]
            lvalue = data.get("lvalue", 0)
            if sig_name in self._sim_state["signals"]:
                self._sim_state["signals"][sig_name]["value"] = float(lvalue) if "." in str(lvalue) else int(lvalue)
                return {"status": "success", "message": f"Signal {sig_name} set to {lvalue}"}
            return {"status": "error", "message": f"Signal {sig_name} not found"}

        return {"status": "success", "message": "Action completed"}


# Global singleton client instance
rws_client = RWSClient()
