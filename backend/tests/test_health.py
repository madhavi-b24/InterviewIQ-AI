from httpx import AsyncClient


async def test_health_reports_ok_when_dependencies_are_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": True, "redis": True}
