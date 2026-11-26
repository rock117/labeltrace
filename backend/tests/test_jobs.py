"""JobService + PgJobBackend：立即返回 job_id、可轮询至成功。"""

import time
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


def test_enqueue_returns_job_id_and_poll_succeeds() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/jobs", json={"job_type": "echo", "payload": {"n": 1}}
        )
        assert resp.status_code == 201
        body = resp.json()
        job_id = body["id"]
        UUID(job_id)
        assert body["status"] in ("pending", "running", "succeeded")
        assert "X-Request-Id" in resp.headers

        deadline = time.time() + 8
        status = body["status"]
        final = body
        while time.time() < deadline:
            poll = client.get(f"/api/v1/jobs/{job_id}")
            assert poll.status_code == 200
            final = poll.json()
            status = final["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.1)

        assert status == "succeeded", final
        assert final["result"]["echo"]["n"] == 1
