"""视频上传 + 抽帧任务 + 审查排序与批量删除。"""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.media.ffmpeg import make_sample_video


def _h(user: str) -> dict[str, str]:
    return {"X-User-Id": user}


def test_video_upload_extract_review_and_batch_delete(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "clip.mp4", seconds=1.0, fps=10)
    raw = video_path.read_bytes()

    with TestClient(app) as client:
        proj = client.post(
            "/api/v1/projects", json={"name": "视频主路径"}, headers=_h("v1")
        )
        pid = proj.json()["id"]
        folder = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "拍摄"},
            headers=_h("v1"),
        ).json()["id"]

        up = client.post(
            f"/api/v1/folders/{folder}/assets",
            headers=_h("v1"),
            files={"file": ("样例.mp4", raw, "video/mp4")},
        )
        assert up.status_code == 201, up.text
        video = up.json()
        assert video["media_kind"] == "video"
        assert video["duration_ms"] is not None and video["duration_ms"] > 0
        assert video["fps"] and video["fps"] > 0
        assert video["width"] == 320
        assert video["library_visible"] is True
        vid = video["id"]

        # 去重
        up2 = client.post(
            f"/api/v1/folders/{folder}/assets",
            headers=_h("v1"),
            files={"file": ("again.mp4", raw, "video/mp4")},
        )
        assert up2.json()["id"] == vid

        listed = client.get(
            f"/api/v1/folders/{folder}/assets", headers=_h("v1")
        ).json()["items"]
        assert any(a["id"] == vid and a["media_kind"] == "video" for a in listed)

        ex = client.post(
            f"/api/v1/assets/{vid}/extract-jobs",
            json={"mode": "stride_frames", "stride": 5, "max_frames": 4},
            headers=_h("v1"),
        )
        assert ex.status_code == 201, ex.text
        extract_id = ex.json()["id"]
        assert ex.json()["mode"] == "stride_frames"
        assert ex.json()["stride"] == 5

        deadline = time.time() + 30
        status = "pending"
        while time.time() < deadline:
            poll = client.get(
                f"/api/v1/extract-jobs/{extract_id}", headers=_h("v1")
            )
            assert poll.status_code == 200
            body = poll.json()
            status = body["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.2)
        assert status == "succeeded", body
        assert body["stats"].get("extracted_count", 0) >= 1

        frames = client.get(
            f"/api/v1/extract-jobs/{extract_id}/frames", headers=_h("v1")
        )
        assert frames.status_code == 200
        items = frames.json()
        assert len(items) >= 1
        indexes = [f["frame_index"] for f in items]
        assert indexes == sorted(indexes)
        assert "time_label" in items[0]
        assert items[0]["time_ms"] >= 0

        # 目录列表不含 frame
        listed2 = client.get(
            f"/api/v1/folders/{folder}/assets", headers=_h("v1")
        ).json()["items"]
        assert all(a["media_kind"] != "frame" for a in listed2)

        to_del = [items[0]["id"]]
        if len(items) > 1:
            to_del.append(items[1]["id"])
        deleted_n = len(to_del)
        bd = client.post(
            f"/api/v1/extract-jobs/{extract_id}/frames/batch-delete",
            json={"asset_ids": to_del},
            headers=_h("v1"),
        )
        assert bd.status_code == 200, bd.text
        assert bd.json()["deleted"] == deleted_n
        assert bd.json()["discarded_count"] >= deleted_n

        left = client.get(
            f"/api/v1/extract-jobs/{extract_id}/frames", headers=_h("v1")
        ).json()
        left_ids = {f["id"] for f in left}
        assert not set(to_del) & left_ids

        job2 = client.get(
            f"/api/v1/extract-jobs/{extract_id}", headers=_h("v1")
        ).json()
        assert job2["stats"]["discarded_count"] >= deleted_n
