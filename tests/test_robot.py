"""Unit and integration tests for Digital Twin robot motion and WebSocket streaming."""

import os
import sys
import time
import pytest
from starlette.testclient import TestClient

# Ensure root directory is in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.main import app
from backend.config import config
from backend.services.robot_state_service import robot_state_service


@pytest.fixture(scope="module")
def client():
    """Create test client fixture."""
    config.SIMULATION_MODE = True
    with TestClient(app) as tc:
        yield tc


def test_robot_joint_state_endpoint(client):
    """Verify /api/robot/joint-state returns 6 joints and metadata."""
    res = client.get("/api/robot/joint-state")
    assert res.status_code == 200
    data = res.json()
    assert "joints" in data
    assert isinstance(data["joints"], list)
    assert len(data["joints"]) == 6
    assert "timestamp" in data
    assert "status" in data
    assert "simulation" in data
    assert data["simulation"] is True


def test_robot_tcp_pose_endpoint(client):
    """Verify /api/robot/tcp-pose returns Cartesian coordinates."""
    res = client.get("/api/robot/tcp-pose")
    assert res.status_code == 200
    data = res.json()
    for coord in ("x", "y", "z", "q1", "q2", "q3", "q4"):
        assert coord in data
        assert isinstance(data[coord], (int, float))


def test_robot_websocket_telemetry(client):
    """Verify WebSocket /api/robot/ws delivers minimal joint packets and handles ping."""
    with client.websocket_connect("/api/robot/ws") as ws:
        # Initial packet sent on connect
        data = ws.receive_json()
        assert "j" in data
        assert isinstance(data["j"], list)
        assert len(data["j"]) == 6
        assert "t" in data

        # Send ping, should receive pong
        ws.send_text("ping")
        pong = ws.receive_text()
        assert pong == "pong"


def test_robot_websocket_multi_client(client):
    """Verify fan-out to multiple simultaneous connected clients."""
    with client.websocket_connect("/api/robot/ws") as ws1:
        with client.websocket_connect("/api/robot/ws") as ws2:
            data1 = ws1.receive_json()
            data2 = ws2.receive_json()
            assert "j" in data1
            assert "j" in data2
            assert len(data1["j"]) == 6
            assert len(data2["j"]) == 6


def test_digital_twin_static_assets(client):
    """Verify Three.js and Digital Twin scripts are served correctly."""
    res_three = client.get("/static/js/libs/three.min.js")
    assert res_three.status_code == 200
    assert len(res_three.content) > 100000

    res_controls = client.get("/static/js/libs/OrbitControls.js")
    assert res_controls.status_code == 200
    assert "OrbitControls" in res_controls.text

    res_twin = client.get("/static/js/digital_twin.js")
    assert res_twin.status_code == 200
    assert "DigitalTwinViewer" in res_twin.text
    assert "CAD SWAP-IN READY LOADER" in res_twin.text

    # Verify index.html contains Digital Twin panel and scripts
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "digital-twin-canvas-container" in res_index.text
    assert "data-view=\"twin\"" in res_index.text
    assert "IRB1660ID-6/1.55 proportions · proxy geometry, CAD swap-in ready" in res_index.text
    assert "btn-more-tools" in res_index.text
    assert "overview-last-event-card" in res_index.text

