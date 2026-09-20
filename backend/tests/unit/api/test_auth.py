import uuid

import jwt

from app.config import JWT_SECRET
from app.core.auth.jwt import create_access_token, decode_access_token
from app.core.auth.password import hash_password, verify_password
from app.db.session import session_scope
from app.features.users.models import User


def test_register_returns_a_token_and_the_user(client):
    response = client.post(
        "/auth/register",
        json={"email": "  Alice@Example.COM ", "password": "correct horse", "full_name": "Alice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"  # stored lowercased
    assert body["user"]["full_name"] == "Alice"
    assert "password" not in str(body) and "hashed" not in str(body)
    assert decode_access_token(body["access_token"]) == uuid.UUID(body["user"]["id"])


def test_the_token_never_expires(register):
    _, user = register()
    token = create_access_token(uuid.UUID(user["id"]))

    claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

    assert set(claims) == {"sub"}  # no exp, no iat


def test_registering_an_email_twice_conflicts_whatever_its_case(client, register):
    register("alice@example.com")

    response = client.post(
        "/auth/register", json={"email": "ALICE@example.com", "password": "another password"}
    )

    assert response.status_code == 409


def test_register_rejects_a_short_password_and_a_bad_email(client):
    assert client.post("/auth/register", json={"email": "a@x.com", "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={"email": "nope", "password": "long enough"}).status_code == 422


def test_login_with_the_right_password(client, register):
    _, user = register("alice@example.com", "correct horse")

    response = client.post("/auth/login", json={"email": "Alice@example.com", "password": "correct horse"})

    assert response.status_code == 200
    assert decode_access_token(response.json()["access_token"]) == uuid.UUID(user["id"])


def test_login_fails_the_same_way_for_a_wrong_password_and_an_unknown_email(client, register):
    register("alice@example.com", "correct horse")

    wrong_password = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"})
    unknown_email = client.post("/auth/login", json={"email": "nobody@example.com", "password": "correct horse"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["www-authenticate"] == "Bearer"


def test_login_refused_for_a_deactivated_user_and_for_an_unusable_hash(client, register):
    _, user = register("alice@example.com", "correct horse")
    with session_scope() as db:
        db.get(User, uuid.UUID(user["id"])).is_active = False
        db.add(User(email="dev@juno.local", hashed_password="!"))  # like scripts/seed_dev_user.py

    assert client.post("/auth/login", json={"email": "alice@example.com", "password": "correct horse"}).status_code == 401
    assert client.post("/auth/login", json={"email": "dev@juno.local", "password": "!"}).status_code == 401


def test_password_hashes_verify_and_are_salted():
    hashed = hash_password("correct horse")

    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)
    assert hash_password("correct horse") != hashed


# --- the bearer-token dependency, exercised through GET /users/me ---


def test_a_protected_route_needs_a_token(client):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_and_forged_tokens_are_rejected(client, register):
    _, user = register()
    forged = jwt.encode({"sub": user["id"]}, "some-other-secret-that-is-long-enough", algorithm="HS256")
    unsigned = jwt.encode({"sub": user["id"]}, "", algorithm="none")
    no_subject = jwt.encode({}, JWT_SECRET, algorithm="HS256")
    bad_subject = jwt.encode({"sub": "not-a-uuid"}, JWT_SECRET, algorithm="HS256")

    for token in ("garbage", forged, unsigned, no_subject, bad_subject):
        response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token


def test_a_token_for_a_user_that_no_longer_exists_is_rejected(client):
    token = create_access_token(uuid.uuid4())

    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_deactivating_a_user_cuts_off_their_existing_token(client, register):
    headers, user = register()
    assert client.get("/users/me", headers=headers).status_code == 200

    with session_scope() as db:
        db.get(User, uuid.UUID(user["id"])).is_active = False

    assert client.get("/users/me", headers=headers).status_code == 401


def test_read_and_update_the_profile(client, register):
    headers, user = register("alice@example.com", full_name="Alice")

    assert client.get("/users/me", headers=headers).json()["id"] == user["id"]

    updated = client.patch("/users/me", headers=headers, json={"full_name": "Alice B."})
    assert updated.status_code == 200 and updated.json()["full_name"] == "Alice B."
    assert client.get("/users/me", headers=headers).json()["full_name"] == "Alice B."

    cleared = client.patch("/users/me", headers=headers, json={"full_name": None})
    assert cleared.json()["full_name"] is None
