def test_signup_creates_user(client):
    resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "pw123456"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@example.com"
    assert "id" in body
    assert "hashed_password" not in body


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "pw123456"})
    resp = client.post("/auth/signup", json={"email": "a@example.com", "password": "other"})
    assert resp.status_code == 400


def test_login_success_returns_token(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "pw123456"})
    resp = client.post("/auth/login", data={"username": "a@example.com", "password": "pw123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "pw123456"})
    resp = client.post("/auth/login", data={"username": "a@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = client.post("/auth/login", data={"username": "nobody@example.com", "password": "x"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "jane@example.com"


def test_me_rejects_garbage_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
