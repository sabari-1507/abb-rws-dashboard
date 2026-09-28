"""RAPID module management router for ABB RWS Dashboard."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.module_service import module_service

router = APIRouter(prefix="/api/rapid", tags=["Modules"])


class LoadModuleRequest(BaseModel):
    modulepath: str = Field(..., description="Full path on controller, e.g. $HOME/TestModule.mod")
    replace: bool = Field(default=True, description="Replace if module with same name exists")
    task: Optional[str] = Field(default=None, description="Target task name")


class UnloadModuleRequest(BaseModel):
    module_name: str = Field(..., description="Name of module to unload, e.g. TestModule")
    task: Optional[str] = Field(default=None, description="Target task name")


@router.get("/modules")
def get_modules(task: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all loaded RAPID modules for the specified task."""
    try:
        return module_service.get_modules(task=task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/upload-module")
async def upload_module(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload a RAPID module (.mod or .sys) to $HOME/ directory on the controller."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file provided")
        return module_service.upload_module(filename=file.filename or "module.mod", content=content)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/load-module")
def load_module(req: LoadModuleRequest) -> Dict[str, Any]:
    """Load a RAPID module into the robot task."""
    try:
        return module_service.load_module(modulepath=req.modulepath, replace=req.replace, task=req.task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/unload-module")
def unload_module(req: UnloadModuleRequest) -> Dict[str, Any]:
    """Unload a RAPID module from the robot task."""
    try:
        return module_service.unload_module(module_name=req.module_name, task=req.task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
