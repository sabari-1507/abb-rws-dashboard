"""Automated unit and integration test suite for ABB RWS Dashboard backend and APIs.

Uses Starlette/FastAPI TestClient to verify all REST endpoints and client simulation.
"""

import os
import sys
import io
import pytest
from starlette.testclient import TestClient

# Ensure root directory is in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.main import app
from backend.config import config
from backend.rws_client import rws_client


@pytest.fixture(scope="module")
def client():
    """Create test client fixture."""
    config.SIMULATION_MODE = True
    with TestClient(app) as tc:
        yield tc


def test_frontend_serving(client):
    """Verify frontend HTML and static assets are served properly."""
    res = client.get("/")
    assert res.status_code == 200
    assert "ABB ROBOT WEB SERVICES" in res.text

    css_res = client.get("/static/css/style.css")
    assert css_res.status_code == 200
    assert "Industrial Dark Theme" in css_res.text

    js_res = client.get("/static/js/dashboard.js")
    assert js_res.status_code == 200
    assert "RWSDashboardApp" in js_res.text


def test_controller_status(client):
    """Verify /api/controller/status endpoint."""
    res = client.get("/api/controller/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "ctrlstate" in data
    assert "opmode" in data
    assert data["connected"] is True


def test_controller_info(client):
    """Verify /api/controller/info endpoint."""
    res = client.get("/api/controller/info")
    assert res.status_code == 200
    data = res.json()
    assert "controller_name" in data
    assert "robotware_version" in data


def test_controller_config(client):
    """Verify getting and updating config."""
    res = client.get("/api/controller/config")
    assert res.status_code == 200
    data = res.json()
    assert data["task_name"] == "T_ROB1"

    update_res = client.post(
        "/api/controller/config",
        json={
            "robot_ip": "192.168.125.1",
            "robot_port": 80,
            "username": "Default User",
            "password": "robotics",
            "task_name": "T_ROB1",
            "timeout": 3.0,
            "simulation_mode": True,
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["success"] is True


def test_rapid_execution(client):
    """Verify RAPID execution queries and controls."""
    # Check initial execution state
    res = client.get("/api/rapid/execution")
    assert res.status_code == 200
    data = res.json()
    assert "state" in data
    assert "cycle" in data

    # Start execution
    start_res = client.post("/api/rapid/execution/start", json={"cycle": "once"})
    assert start_res.status_code == 200
    assert start_res.json()["success"] is True

    # Check updated state is RUNNING
    exec_res = client.get("/api/rapid/execution")
    assert exec_res.json()["state"] == "RUNNING"

    # Stop execution
    stop_res = client.post("/api/rapid/execution/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["success"] is True

    # Check stopped
    exec_res2 = client.get("/api/rapid/execution")
    assert exec_res2.json()["state"] == "STOPPED"

    # Reset execution
    reset_res = client.post("/api/rapid/execution/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["success"] is True

    # Abort execution
    abort_res = client.post("/api/rapid/execution/abort")
    assert abort_res.status_code == 200
    assert abort_res.json()["success"] is True

    # Test speed ratio setting
    speed_res = client.post("/api/rapid/speed-ratio", json={"speedratio": 75})
    assert speed_res.status_code == 200
    assert speed_res.json()["speedratio"] == 75

    # Test module source inspection
    source_res = client.get("/api/rapid/module-source/MainModule")
    assert source_res.status_code == 200
    assert "source" in source_res.json()
    assert "MainModule" in source_res.json()["source"]


def test_program_pointer(client):
    """Verify reading and controlling program pointer."""
    res = client.get("/api/rapid/program-pointer")
    assert res.status_code == 200
    data = res.json()
    assert "module" in data
    assert "routine" in data
    assert "line" in data

    # Set PP to routine
    set_routine_res = client.post(
        "/api/rapid/set-pointer-routine",
        json={"module": "TestModule", "routine": "Test", "userlevel": 1},
    )
    assert set_routine_res.status_code == 200
    assert set_routine_res.json()["success"] is True

    # Set PP to cursor
    set_cursor_res = client.post(
        "/api/rapid/set-pointer-cursor",
        json={"module": "MainModule", "routine": "main", "line": 10, "col": 5},
    )
    assert set_cursor_res.status_code == 200
    assert set_cursor_res.json()["success"] is True

    # Check PP updated
    pp_res = client.get("/api/rapid/program-pointer")
    assert pp_res.json()["line"] == 10

    # Step next instruction
    next_res = client.post("/api/rapid/next-instruction")
    assert next_res.status_code == 200
    assert next_res.json()["pp"]["line"] == 11

    # Step prev instruction
    prev_res = client.post("/api/rapid/previous-instruction")
    assert prev_res.status_code == 200
    assert prev_res.json()["pp"]["line"] == 10


def test_modules_management(client):
    """Verify listing, uploading, loading, and unloading modules."""
    # List modules
    res = client.get("/api/rapid/modules")
    assert res.status_code == 200
    modules = res.json()
    assert any(m["name"] == "MainModule" for m in modules)

    # Upload module
    file_content = b"MODULE SampleModule\nPROC main()\nENDPROC\nENDMODULE\n"
    upload_res = client.post(
        "/api/rapid/upload-module",
        files={"file": ("SampleModule.mod", io.BytesIO(file_content), "application/octet-stream")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["success"] is True

    # Load module
    load_res = client.post(
        "/api/rapid/load-module",
        json={"modulepath": "$HOME/SampleModule.mod", "replace": True, "task": "T_ROB1"},
    )
    assert load_res.status_code == 200
    assert load_res.json()["success"] is True

    # Verify SampleModule is now in modules list
    mod_res = client.get("/api/rapid/modules")
    assert any(m["name"] == "SampleModule" for m in mod_res.json())

    # Unload module
    unload_res = client.post(
        "/api/rapid/unload-module",
        json={"module_name": "SampleModule", "task": "T_ROB1"},
    )
    assert unload_res.status_code == 200
    assert unload_res.json()["success"] is True

    # Verify SampleModule removed
    mod_res2 = client.get("/api/rapid/modules")
    assert not any(m["name"] == "SampleModule" for m in mod_res2.json())


def test_io_monitoring(client):
    """Verify reading and controlling robot I/O signals."""
    # Get all signals
    res = client.get("/api/io/signals")
    assert res.status_code == 200
    signals = res.json()
    assert len(signals) > 0

    # Filter DI
    di_res = client.get("/api/io/digital-inputs")
    assert di_res.status_code == 200
    for s in di_res.json():
        assert s["type"] == "DI"

    # Filter DO
    do_res = client.get("/api/io/digital-outputs")
    assert do_res.status_code == 200
    for s in do_res.json():
        assert s["type"] == "DO"

    # Set DO signal
    set_res = client.post("/api/io/set-signal", json={"signal_name": "DO_Light", "value": 1})
    assert set_res.status_code == 200
    assert set_res.json()["success"] is True


def test_system_info(client):
    """Verify system and robot specs."""
    res = client.get("/api/system/info")
    assert res.status_code == 200
    data = res.json()
    assert "controller" in data
    assert "robot" in data
    assert data["robot"]["mechanical_unit"] == "ROB_1"


def test_events(client):
    """Verify events logging, querying, and clearing."""
    res = client.get("/api/events")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert len(events) > 0

    # Clear events
    clear_res = client.post("/api/events/clear")
    assert clear_res.status_code == 200
    assert clear_res.json()["success"] is True

    # Check reset
    res2 = client.get("/api/events")
    assert len(res2.json()) == 1  # 1 new event saying cleared
