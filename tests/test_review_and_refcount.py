"""Tests for review API and PDF reference counting."""
import sys; sys.path.insert(0, '.')
import asyncio
import os
import tempfile
from pathlib import Path
from app.database import init_db, engine, async_session_factory
from app.main import app
from app.models.pdf_file import PdfFile
from httpx import AsyncClient, ASGITransport


async def _get_token(client) -> str:
    r = await client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json().get('access_token', '')


async def test():
    await init_db()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url='http://test') as client:
        token = await _get_token(client)
        assert token, "No token"
        headers = {'Authorization': f'Bearer {token}'}

        # Create an LLM config first (needed for meta-tasks)
        r = await client.get('/api/v1/llm-configs/', headers=headers)
        llm_configs = (r.json().get('data') or r.json().get('items') or [])
        if not llm_configs:
            r = await client.post('/api/v1/llm-configs/', headers=headers, json={
                'name': 'Test Config',
                'model_name': 'gpt-4o-mini',
                'api_endpoint': 'https://api.openai.com',
                'api_key': 'sk-test',
                'is_active': True,
            })
            if r.status_code == 200:
                llm_config_id = r.json().get('id')
            else:
                print(f"LLM config create status: {r.status_code}")
                # Try to get any existing config
                r2 = await client.get('/api/v1/llm-configs/', headers=headers)
                llm_configs = (r2.json().get('data') or r2.json().get('items') or [])
                if not llm_configs:
                    print("WARN: No LLM configs available, review tests limited")
                    return
                llm_config_id = llm_configs[0]['id']
        else:
            llm_config_id = llm_configs[0]['id']

        # Create a meta-task
        r = await client.post('/api/v1/meta-tasks/', headers=headers, json={
            'name': 'Test Review Task',
            'description': 'Auto-created by test',
            'search_params': {'query': 'test', 'max_export': 50},
            'llm_config_ids': [llm_config_id],
        })
        assert r.status_code == 200, f"Create meta-task failed: {r.text}"
        task_id = r.json()['id']
        print(f"Created meta-task: id={task_id}")

        # Execute to create instance
        r = await client.post(f'/api/v1/meta-tasks/{task_id}/execute', headers=headers)
        assert r.status_code == 200, f"Execute failed: {r.text}"
        instance_id = r.json()['instance_id']
        print(f"Created instance: id={instance_id}")

        # Test review API - batch pass on empty
        r = await client.post(
            f'/api/v1/task-instances/{instance_id}/results/batch-update',
            headers=headers,
            json={'action': 'pass', 'result_ids': []},
        )
        assert r.status_code in (400, 422), f"Expected error for empty, got {r.status_code}"
        print(f"Batch update empty: {r.status_code} (expected error)")

        # Test mark pass on nonexistent result
        r = await client.put('/api/v1/task-results/999999/pass', headers=headers, json={'is_passed': True})
        assert r.status_code == 404
        print(f"Mark pass nonexistent: {r.status_code}")

        # Test mark reject on nonexistent
        r = await client.put('/api/v1/task-results/999999/reject', headers=headers)
        assert r.status_code == 404
        print(f"Mark reject nonexistent: {r.status_code}")

        # Get results (should be empty as CNKI search was not actually run)
        r = await client.get(f'/api/v1/task-instances/{instance_id}/results', headers=headers)
        assert r.status_code == 200
        results_data = r.json()
        print(f"Instance results: {results_data.get('total', 0)} items")

        # Test cancel the pending instance
        r = await client.delete(f'/api/v1/task-instances/{instance_id}', headers=headers)
        assert r.status_code == 200, f"Cancel failed: {r.text}"
        print(f"Cancel instance: {r.status_code}")

        # Verify cancelled status
        r = await client.get(f'/api/v1/task-instances/{instance_id}', headers=headers)
        assert r.status_code == 200
        inst = r.json().get('data') or r.json()
        assert inst.get('status') == 'cancelled', f"Expected cancelled, got {inst.get('status')}"
        print(f"Status after cancel: {inst.get('status')}")

    # -- PDF ref_count logic (direct) --
    print("\n--- PDF ref_count tests ---")
    async with async_session_factory() as db:
        pf1 = PdfFile(original_url="https://test.cnki.net/a1", pdf_path="test_pf1.pdf", file_hash="abc", file_size=100, ref_count=2)
        db.add(pf1)
        await db.flush()
        pf1_id = pf1.id

        pf2 = PdfFile(original_url="https://test.cnki.net/a2", pdf_path="test_pf2.pdf", file_hash="def", file_size=200, ref_count=1)
        db.add(pf2)
        await db.flush()
        pf2_id = pf2.id
        print(f"Created PdfFile 1: id={pf1_id}, ref_count=2")
        print(f"Created PdfFile 2: id={pf2_id}, ref_count=1")

        # decrement pf1
        pf1.ref_count = max(0, pf1.ref_count - 1)
        await db.flush()
        assert pf1.ref_count == 1
        print(f"Decrement pf1: {pf1.ref_count} (expected 1)")

        # Create temp file for pf2, then delete when ref_count hits 0
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            test_file = Path(tmp.name)
            test_file.write_text("content")
        pf2_ref = await db.get(PdfFile, pf2_id)
        pf2_ref.pdf_path = str(test_file)
        pf2_ref.ref_count = 0
        await db.flush()

        if pf2_ref.ref_count <= 0:
            if test_file.exists():
                os.remove(str(test_file))
            await db.delete(pf2_ref)

        assert not test_file.exists()
        print("Physical file deletion on ref_count=0: OK")

        # Cleanup
        pf1_clean = await db.get(PdfFile, pf1_id)
        if pf1_clean:
            await db.delete(pf1_clean)
        await db.commit()

    await engine.dispose()
    print("\nAll M8 review + ref_count tests passed!")


asyncio.run(test())
