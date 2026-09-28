"""RAPID monitoring and execution router for ABB RWS Dashboard."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.rapid_service import rapid_service

router = APIRouter(prefix="/api/rapid", tags=["RAPID"])


class SetPPRoutineRequest(BaseModel):
    module: str = Field(..., description="Module name, e.g. MainModule or TestModule")
    routine: str = Field(..., description="Routine name, e.g. main or myRoutine")
    userlevel: int = Field(default=1, description="User level for routine pointer")
    task: Optional[str] = Field(default=None, description="RAPID task name, defaults to active task")


class SetPPCursorRequest(BaseModel):
    module: str = Field(..., description="Module name")
    routine: str = Field(..., description="Routine name")
    line: int = Field(..., description="Line number")
    col: int = Field(default=1, description="Column number")
    task: Optional[str] = Field(default=None, description="RAPID task name")


class StepInstructionRequest(BaseModel):
    direction: str = Field(default="next", description="'next' or 'prev'")
    task: Optional[str] = Field(default=None)


class ExecutionControlRequest(BaseModel):
    cycle: Optional[str] = Field(default="once", description="'once' or 'continuous'")


class SpeedRatioRequest(BaseModel):
    speedratio: int = Field(..., ge=1, le=100, description="Speed override percentage (1-100)")


@router.get("/execution")
def get_execution_state() -> Dict[str, Any]:
    """Get current RAPID execution state and cycle mode."""
    try:
        return rapid_service.get_execution_state()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/program-pointer")
def get_program_pointer(task: Optional[str] = None) -> Dict[str, Any]:
    """Get current Program Pointer (PCP) coordinates for task."""
    try:
        return rapid_service.get_program_pointer(task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/set-pointer-routine")
def set_pointer_routine(req: SetPPRoutineRequest) -> Dict[str, Any]:
    """Set Program Pointer to a specific routine entry."""
    try:
        return rapid_service.set_pointer_routine(
            module=req.module, routine=req.routine, userlevel=req.userlevel, task=req.task
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/set-pointer-cursor")
def set_pointer_cursor(req: SetPPCursorRequest) -> Dict[str, Any]:
    """Set Program Pointer to specific line and column."""
    try:
        return rapid_service.set_pointer_cursor(
            module=req.module, routine=req.routine, line=req.line, col=req.col, task=req.task
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/previous-instruction")
def previous_instruction(task: Optional[str] = None) -> Dict[str, Any]:
    """Step Program Pointer back one instruction."""
    try:
        return rapid_service.step_instruction(direction="prev", task=task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/next-instruction")
def next_instruction(task: Optional[str] = None) -> Dict[str, Any]:
    """Advance Program Pointer by one instruction."""
    try:
        return rapid_service.step_instruction(direction="next", task=task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/execution/start")
def start_execution(req: ExecutionControlRequest) -> Dict[str, Any]:
    """Start RAPID program execution."""
    try:
        return rapid_service.start_execution(cycle=req.cycle or "once")
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/execution/stop")
def stop_execution() -> Dict[str, Any]:
    """Stop RAPID program execution."""
    try:
        return rapid_service.stop_execution()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/execution/reset")
def reset_execution(task: Optional[str] = None) -> Dict[str, Any]:
    """Reset Program Pointer to main routine."""
    try:
        return rapid_service.reset_execution_pointer(task=task)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/execution/abort")
def abort_execution() -> Dict[str, Any]:
    """Abort RAPID program execution."""
    try:
        return rapid_service.abort_execution()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/module-source/{module_name}")
def get_module_source(module_name: str) -> Dict[str, Any]:
    """Fetch RAPID source code for specified module."""
    try:
        return rapid_service.get_module_source(module_name)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/speed-ratio")
def set_speed_ratio(req: SpeedRatioRequest) -> Dict[str, Any]:
    """Set RAPID execution speed override ratio (1-100%)."""
    try:
        return rapid_service.set_speed_ratio(req.speedratio)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

