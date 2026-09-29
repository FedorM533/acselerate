from fastapi.testclient import TestClient

from focusfarm.api.server import create_app


def test_hello():
    client = TestClient(create_app())
    assert client.get("/api/hello").json()["message"].startswith("Hello")
    assert "Фокус-ферма" in client.get("/").text
