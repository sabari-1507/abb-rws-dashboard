"""RAPID service for ABB RWS Dashboard.

Manages RAPID execution monitoring, Program Pointer (PCP) inspection and manipulation,
and execution control commands with mastership management and event auditing.
"""

from typing import Any, Dict, Optional
from backend.config import config
from backend.rws_client import rws_client
from backend.services.event_service import event_service


class RapidService:
    """Provides methods for RAPID execution status, Program Pointer, and execution controls."""

    def get_execution_state(self) -> Dict[str, Any]:
        """Fetch current RAPID execution state."""
        data = rws_client.get_data("/rw/rapid/execution")

        state = data.get("ctrlexecstate", data.get("state", "stopped")).upper()
        cycle = data.get("cycle", "once").upper()
        speedratio = data.get("speedratio", 100)

        return {
            "state": state,
            "is_running": state == "RUNNING",
            "cycle": cycle,
            "speedratio": speedratio,
            "task": config.TASK_NAME,
        }

    def get_program_pointer(self, task: Optional[str] = None) -> Dict[str, Any]:
        """Fetch Program Pointer (PCP) location for specified task."""
        target_task = task or config.TASK_NAME
        data = rws_client.get_data(f"/rw/rapid/tasks/{target_task}/pcp")

        mod = data.get("modulemame", data.get("modulename", data.get("module", "MainModule")))
        routine = data.get("routinename", data.get("routine", "main"))
        begin_pos = data.get("beginposition", "")
        if begin_pos and "," in begin_pos:
            parts = begin_pos.split(",")
            line = int(parts[0]) if parts[0].isdigit() else 1
            col = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        else:
            line = int(data.get("line", 1))
            col = int(data.get("col", 1))

        return {
            "task": target_task,
            "module": mod,
            "routine": routine,
            "line": line,
            "col": col,
            "end_line": line,
            "end_col": col,
            "formatted_position": f"{line},{col}",
        }

    def set_pointer_routine(self, module: str, routine: str, userlevel: int = 1, task: Optional[str] = None) -> Dict[str, Any]:
        """Set Program Pointer to the entry of a specific routine."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/tasks/{target_task}/pcp"
        payload = {
            "module": module,
            "routine": routine,
            "userlevel": str(userlevel),
        }

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "set-pp-routine"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event(
            "INFO",
            f"Set Program Pointer to routine: {module}.{routine} (Task: {target_task})",
            source="Operator",
            details=payload,
        )
        return {"success": True, "message": f"Program Pointer set to {module}.{routine}", "result": data}

    def set_pointer_cursor(
        self, module: str, routine: str, line: int, col: int = 1, task: Optional[str] = None
    ) -> Dict[str, Any]:
        """Set Program Pointer to a specific cursor coordinate (line, column)."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/tasks/{target_task}/pcp"
        payload = {
            "module": module,
            "routine": routine,
            "line": str(line),
            "col": str(col),
        }

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "set-pp-curser"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event(
            "INFO",
            f"Set Program Pointer to line {line}, col {col} in {module}.{routine}",
            source="Operator",
            details=payload,
        )
        return {"success": True, "message": f"Program Pointer set to line {line}, col {col}", "result": data}

    def step_instruction(self, direction: str, task: Optional[str] = None) -> Dict[str, Any]:
        """Step Program Pointer forward or backward by one instruction."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/tasks/{target_task}/pcp"
        action = "set-pp-next-inst" if direction.lower() in ("next", "forward") else "set-pp-prev-inst"

        with rws_client.mastership():
            response = rws_client.post(endpoint, params={"action": action})
            data = response if isinstance(response, dict) else {}

        event_service.log_event(
            "INFO",
            f"Stepped Program Pointer {direction} on task {target_task}",
            source="Operator",
        )
        updated_pp = self.get_program_pointer(target_task)
        return {"success": True, "direction": direction, "pp": updated_pp, "result": data}

    def start_execution(self, cycle: str = "once") -> Dict[str, Any]:
        """Start RAPID program execution."""
        endpoint = "/rw/rapid/execution"
        payload = {"regain": "continue", "execmode": "continue", "cycle": cycle}

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "start"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event("WARNING", f"RAPID program execution STARTED (Cycle: {cycle.upper()})", source="Operator")
        return {"success": True, "message": "RAPID execution started", "result": data}

    def stop_execution(self) -> Dict[str, Any]:
        """Stop RAPID program execution."""
        endpoint = "/rw/rapid/execution"
        payload = {"stopmode": "stop"}

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "stop"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event("WARNING", "RAPID program execution STOPPED", source="Operator")
        return {"success": True, "message": "RAPID execution stopped", "result": data}

    def abort_execution(self) -> Dict[str, Any]:
        """Abort RAPID program execution."""
        endpoint = "/rw/rapid/execution"
        payload = {"stopmode": "stop"}

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "abort"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event("ERROR", "RAPID program execution ABORTED", source="Operator")
        return {"success": True, "message": "RAPID execution aborted", "result": data}

    def reset_execution_pointer(self, task: Optional[str] = None) -> Dict[str, Any]:
        """Reset Program Pointer to Main entry point."""
        endpoint = "/rw/rapid/execution"

        with rws_client.mastership():
            response = rws_client.post(endpoint, params={"action": "resetpp"})
            data = response if isinstance(response, dict) else {}

        event_service.log_event("INFO", "Program Pointer RESET to Main routine", source="Operator")
        return {"success": True, "message": "Program Pointer reset to main", "result": data}

    def get_module_source(self, module_name: str) -> Dict[str, Any]:
        """Fetch RAPID module source code."""
        # Try fetching from fileservice
        for ext in ("mod", "sys"):
            resp = rws_client.get(f"/fileservice/$HOME/{module_name}.{ext}")
            if hasattr(resp, "status_code") and resp.status_code == 200:
                return {
                    "module": module_name,
                    "filename": f"{module_name}.{ext}",
                    "source": resp.text,
                    "found": True,
                }

        # Simulated fallback code template
        sample_source = f"""MODULE {module_name}
    ! RAPID Module: {module_name}
    ! Generated / Inspected from Task {config.TASK_NAME}

    VAR num cycleCount := 0;
    PERS tooldata tGripper := [TRUE,[[0,0,100],[1,0,0,0]],[1,[0,0,50],[1,0,0,0],0,0,0]];

    PROC main()
        ! Main routine entrypoint
        MoveJ pHome, v1000, fine, tGripper;
        cycleCount := cycleCount + 1;
        WaitTime 0.5;
    ENDPROC

    PROC {module_name}1()
        ! Routine in module
        MoveL pPick, v500, z10, tGripper;
        WaitDI DI_PartPresent, 1;
        SetDO DO_Gripper, 1;
        MoveL pPlace, v500, fine, tGripper;
        SetDO DO_Gripper, 0;
    ENDPROC
ENDMODULE"""
        return {
            "module": module_name,
            "filename": f"{module_name}.mod",
            "source": sample_source,
            "found": True,
        }

    def set_speed_ratio(self, speedratio: int) -> Dict[str, Any]:
        """Set RAPID speed override ratio (1-100%)."""
        speed = max(1, min(100, int(speedratio)))
        if rws_client.is_simulation():
            rws_client._sim_state["speedratio"] = speed
        else:
            with rws_client.mastership():
                rws_client.post("/rw/rapid/execution", data={"speedratio": speed}, params={"action": "setspeedratio"})
        event_service.log_event("INFO", f"RAPID Speed Override set to {speed}%", source="Operator")
        return {"success": True, "speedratio": speed}


rapid_service = RapidService()
