# backend/tests/test_auth.py
# Purpose: security-focused auth suite — cookie flags, no user enumeration,
#          token type separation, refresh rotation, admin gating, header hardening.

import pytest

from app.repositories import user_repo

REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": "correct-horse-battery",
    "name": "Alice",
}
LOGIN_PAYLOAD = {
    "email": REGISTER_PAYLOAD["email"],
    "password": REGISTER_PAYLOAD["password"],
}


def _cookies(response) -> dict[str, str]:
    return {name: attrs for name, _, attrs in _cookie_tuples(response)}


def _cookie_tuples(response):
    tuples = []
    for header in response.headers.get_list("set-cookie"):
        parts = header.split(";")
        name, _, value = parts[0].partition("=")
        tuples.append((name, value, ";" .join(parts[1:])))
    return tuples


async def _register(client, payload=None) -> None:
    await client.post("/auth/register", json=payload or REGISTER_PAYLOAD)


# ---------------------------------------------------------------- registration

async def test_register_sets_cookies_and_no_token_in_body(client) -> None:
    res = await client.post("/auth/register", json=REGISTER_PAYLOAD)
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["email"] == "alice@example.com"
    assert data["role"] == "admin"  # first user
    assert "password" not in str(body).lower()

    cookies = _cookie_tuples(res)
    names = [c[0] for c in cookies]
    assert "nexus_access" in names and "nexus_refresh" in names
    for _, _, attrs in cookies:
        assert "HttpOnly" in attrs
        assert "SameSite=lax" in attrs
        assert "Secure" not in attrs  # dev over http
        assert "Path=/" in attrs


async def test_register_duplicate_email_409(client) -> None:
    await _register(client)
    res = await client.post("/auth/register", json=REGISTER_PAYLOAD)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    "bad_email",
    ["not-an-email", "' OR 1=1--", "a@b", "x" * 300 + "@example.com"],
)
async def test_register_rejects_invalid_emails(client, bad_email) -> None:
    payload = {**REGISTER_PAYLOAD, "email": bad_email}
    res = await client.post("/auth/register", json=payload)
    assert res.status_code == 422, bad_email
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    # attacker's email never lands anywhere: login with it must fail too
    login = await client.post("/auth/login", json={**LOGIN_PAYLOAD, "email": bad_email})
    assert login.status_code in (401, 422)


async def test_register_short_password_422(client) -> None:
    res = await client.post("/auth/register", json={**REGISTER_PAYLOAD, "password": "short"})
    assert res.status_code == 422


async def test_register_72_byte_password_guard(client) -> None:
    too_long = "a" * 72 + "é" * 3  # 75 bytes
    res = await client.post("/auth/register", json={**REGISTER_PAYLOAD, "password": too_long})
    assert res.status_code == 422


async def test_register_extra_fields_rejected(client) -> None:
    res = await client.post(
        "/auth/register",
        json={**REGISTER_PAYLOAD, "role": "admin", "is_active": True},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------- login

async def test_login_success_sets_cookies(client) -> None:
    await _register(client)
    res = await client.post("/auth/login", json=LOGIN_PAYLOAD)
    assert res.status_code == 200
    assert res.json()["data"]["email"] == REGISTER_PAYLOAD["email"]
    assert [c[0] for c in _cookie_tuples(res)] == ["nexus_access", "nexus_refresh"]


async def test_login_wrong_password_and_unknown_email_identical(client) -> None:
    await _register(client)
    wrong_password = await client.post(
        "/auth/login", json={**LOGIN_PAYLOAD, "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/auth/login", json={**LOGIN_PAYLOAD, "email": "ghost@example.com"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()  # no user enumeration
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_inactive_user_401(client, db_engine) -> None:
    await _register(client)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        user = await user_repo.get_by_email(session, REGISTER_PAYLOAD["email"])
        assert user is not None
        user.is_active = False
        await session.commit()
    res = await client.post("/auth/login", json=LOGIN_PAYLOAD)
    assert res.status_code == 401


async def test_login_email_case_insensitive(client) -> None:
    await _register(client)
    res = await client.post(
        "/auth/login", json={**LOGIN_PAYLOAD, "email": "ALICE@EXAMPLE.COM"}
    )
    assert res.status_code == 200


# ---------------------------------------------------------------- /me

async def test_me_without_cookie_401(client) -> None:
    res = await client.get("/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_with_cookie_returns_user_settings_providers(client) -> None:
    await _register(client)
    res = await client.get("/auth/me")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert data["settings"]["default_provider"] == "zen"
    assert set(data["providers"]) == {"zen", "openai", "anthropic", "gemini", "ollama"}
    assert all(isinstance(v, bool) for v in data["providers"].values())


async def test_me_with_tampered_cookie_401(client) -> None:
    client.cookies.set("nexus_access", "tampered-token-value")
    res = await client.get("/auth/me")
    assert res.status_code == 401


# ---------------------------------------------------------------- refresh rotation

async def test_refresh_rotates_token_pair(client) -> None:
    await _register(client)
    old_access = client.cookies.get("nexus_access")
    old_refresh = client.cookies.get("nexus_refresh")
    res = await client.post("/auth/refresh")
    assert res.status_code == 200
    new_access = client.cookies.get("nexus_access")
    new_refresh = client.cookies.get("nexus_refresh")
    assert new_access and new_access != old_access
    assert new_refresh and new_refresh != old_refresh


async def test_refresh_rejects_access_token(client) -> None:
    await _register(client)
    access_value = client.cookies.get("nexus_access")
    res = await client.post("/auth/refresh", headers={"Cookie": f"nexus_refresh={access_value}"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_refresh_without_cookie_401(client) -> None:
    res = await client.post("/auth/refresh")
    assert res.status_code == 401


# ---------------------------------------------------------------- logout

async def test_logout_clears_both_cookies(client) -> None:
    await _register(client)
    res = await client.post("/auth/logout")
    assert res.status_code == 200
    cookies = _cookie_tuples(res)
    assert {c[0] for c in cookies} == {"nexus_access", "nexus_refresh"}
    assert all("Max-Age=0" in c[2] for c in cookies)
    assert client.cookies.get("nexus_access") is None


# ---------------------------------------------------------------- admin gating

async def test_admin_route_gated_by_role(client) -> None:
    await _register(client)  # alice = admin
    await client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "another-password-123"},
    )  # bob = user
    res = await client.get("/_test_admin")  # cookie jar now holds bob's session
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    await client.post("/auth/login", json=LOGIN_PAYLOAD)  # back to alice
    res = await client.get("/_test_admin")
    assert res.status_code == 200


async def test_second_user_gets_user_role(client) -> None:
    await _register(client)
    res = await client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "another-password-123"},
    )
    assert res.json()["data"]["role"] == "user"


# ---------------------------------------------------------------- headers

async def test_security_headers_present(client) -> None:
    res = await client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in res.headers  # dev only