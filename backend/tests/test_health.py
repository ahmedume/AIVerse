from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {"success": True, "data": {"status": "ok", "version": "0.1.0"}}


async def test_health_unknown_route() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/nope")
    assert res.status_code == 404