def test_hello(env):
    assert env.client.get("/api/hello").json()["message"].startswith("Hello")
    assert "Фокус-пруд" in env.client.get("/").text
