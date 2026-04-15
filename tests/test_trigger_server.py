from fastapi.testclient import TestClient

from trigger_server import app


def test_run_single_endpoint_requires_url():
    client = TestClient(app)
    response = client.post("/run/single", json={})
    assert response.status_code == 422
