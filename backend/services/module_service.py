"""RAPID module management service for ABB RWS Dashboard.

Handles listing loaded RAPID modules, uploading .mod and .sys files to $HOME,
loading modules with replace options, and safely unloading modules.
"""

from typing import Any, Dict, List, Optional
from backend.config import config
from backend.rws_client import rws_client
from backend.services.event_service import event_service


class ModuleService:
    """Provides methods for managing RAPID modules on the controller."""

    def get_modules(self, task: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch list of loaded modules for the specified task."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/modules?task={target_task}"
        data = rws_client.get_data(endpoint)
        modules = data.get("modules", [])
        return modules

    def upload_module(self, filename: str, content: bytes) -> Dict[str, Any]:
        """Upload a RAPID module (.mod, .sys) to $HOME/ directory on the controller."""
        clean_filename = filename.replace("\\", "/").split("/")[-1]
        success = rws_client.put_file(clean_filename, content)

        if success:
            event_service.log_event(
                "INFO",
                f"Module file uploaded to $HOME/{clean_filename} ({len(content)} bytes)",
                source="Operator",
            )
            return {
                "success": True,
                "message": f"Successfully uploaded {clean_filename} to $HOME/",
                "filename": clean_filename,
                "path": f"$HOME/{clean_filename}",
                "size_bytes": len(content),
            }
        else:
            event_service.log_event("ERROR", f"Failed to upload module file {clean_filename}", source="System")
            return {"success": False, "message": f"Failed to upload {clean_filename} to controller"}

    def load_module(self, modulepath: str, replace: bool = True, task: Optional[str] = None) -> Dict[str, Any]:
        """Load a RAPID module from controller storage into active task."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/tasks/{target_task}"
        payload = {
            "modulepath": modulepath,
            "replace": "true" if replace else "false",
        }

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "loadmod"})
            data = response if isinstance(response, dict) else {}

        status = data.get("status", "success")
        if status != "error":
            event_service.log_event(
                "INFO",
                f"Loaded module '{modulepath}' into task '{target_task}' (Replace: {replace})",
                source="Operator",
            )
            return {"success": True, "message": f"Module {modulepath} loaded successfully", "result": data}
        else:
            event_service.log_event(
                "WARNING",
                f"Module load warning/error for '{modulepath}': {data.get('message')}",
                source="Operator",
            )
            return {"success": False, "message": data.get("message", "Error loading module"), "result": data}

    def unload_module(self, module_name: str, task: Optional[str] = None) -> Dict[str, Any]:
        """Unload a RAPID module from the specified task."""
        target_task = task or config.TASK_NAME
        endpoint = f"/rw/rapid/tasks/{target_task}"
        payload = {"module": module_name}

        with rws_client.mastership():
            response = rws_client.post(endpoint, data=payload, params={"action": "unloadmod"})
            data = response if isinstance(response, dict) else {}

        status = data.get("status", "success")
        if status != "error":
            event_service.log_event(
                "WARNING",
                f"Unloaded module '{module_name}' from task '{target_task}'",
                source="Operator",
            )
            return {"success": True, "message": f"Module {module_name} unloaded successfully", "result": data}
        else:
            event_service.log_event(
                "ERROR",
                f"Failed to unload module '{module_name}': {data.get('message')}",
                source="Operator",
            )
            return {"success": False, "message": data.get("message", "Error unloading module"), "result": data}


module_service = ModuleService()
