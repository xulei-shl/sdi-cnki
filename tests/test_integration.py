"""Quick integration test for main app routes."""
import sys; sys.path.insert(0, '.')
import asyncio
from app.database import init_db, engine
from app.main import app
from httpx import AsyncClient, ASGITransport


async def test():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/api/v1/health')
        print(f'Health: {r.status_code} {r.json()}')
        assert r.status_code == 200

        r2 = await client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
        print(f'Login: {r2.status_code}')
        assert r2.status_code == 200
        data = r2.json()
        token = data.get('access_token', '')
        print(f'  token: {token[:20]}... role: {data.get("role")}')
        assert token

        headers = {'Authorization': f'Bearer {token}'}
        r3 = await client.get('/api/v1/meta-tasks/', headers=headers)
        print(f'Meta-tasks list: {r3.status_code}')
        assert r3.status_code == 200

        r4 = await client.get('/api/v1/llm-configs/', headers=headers)
        print(f'LLM configs: {r4.status_code}')
        assert r4.status_code == 200

    await engine.dispose()
    print('\nAll integration tests passed!')


asyncio.run(test())
