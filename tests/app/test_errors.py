def test_unknown_job_is_job_not_found(client):
    response = client.get("/api/jobs/unknown-id")

    body = response.json()
    assert response.status_code == 404
    assert set(body) == {"error", "message"}
    assert body["error"] == "job_not_found"
    assert isinstance(body["message"], str) and body["message"]


def test_empty_body_is_invalid_request(client):
    response = client.post("/api/jobs", json={})

    body = response.json()
    assert response.status_code == 400
    assert set(body) == {"error", "message"}
    assert body["error"] == "invalid_request"
    assert body["message"]


def test_unknown_route_is_not_found(client):
    response = client.get("/api/nope")

    body = response.json()
    assert response.status_code == 404
    assert set(body) == {"error", "message"}
    assert body["error"] == "not_found"


def test_wrong_method_is_method_not_allowed(client):
    response = client.delete("/api/styles")

    assert response.status_code == 405
    assert response.json()["error"] == "method_not_allowed"
