"""标签、数据集、抽帧入集与引用硬删 409。"""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.media.ffmpeg import make_sample_video


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def test_tags_and_extract_into_dataset_then_delete_guard(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "t.mp4", seconds=0.8, fps=10)
    raw = video_path.read_bytes()

    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "入集"}, headers=_h("d1")
        ).json()["id"]
        fid = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "根"},
            headers=_h("d1"),
        ).json()["id"]

        tag = client.post(
            f"/api/v1/projects/{pid}/tags",
            json={"name": "夜班"},
            headers=_h("d1"),
        )
        assert tag.status_code == 201
        tid = tag.json()["id"]
        assert (
            client.post(
                f"/api/v1/projects/{pid}/tags",
                json={"name": "夜班"},
                headers=_h("d1"),
            ).status_code
            == 409
        )

        img = b"\x89PNG\r\n\x1a\n" + b"\x01" * 32
        image = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("d1"),
            files={"file": ("a.png", img, "image/png")},
        ).json()
        assert (
            client.put(
                f"/api/v1/assets/{image['id']}/tags",
                json={"tag_ids": [tid]},
                headers=_h("d1"),
            ).status_code
            == 200
        )
        filtered = client.get(
            f"/api/v1/projects/{pid}/assets",
            params=[("tag_ids", str(tid))],
            headers=_h("d1"),
        )
        assert filtered.status_code == 200
        assert any(a["id"] == image["id"] for a in filtered.json())

        vid = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("d1"),
            files={"file": ("v.mp4", raw, "video/mp4")},
        ).json()["id"]
        ex = client.post(
            f"/api/v1/assets/{vid}/extract-jobs",
            json={"mode": "stride_frames", "stride": 5, "max_frames": 3},
            headers=_h("d1"),
        ).json()
        eid = ex["id"]
        deadline = time.time() + 30
        while time.time() < deadline:
            st = client.get(f"/api/v1/extract-jobs/{eid}", headers=_h("d1")).json()
            if st["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.2)
        assert st["status"] == "succeeded"

        ds = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "检测集", "enabledAnnotationTypes": ["rect"]},
            headers=_h("d1"),
        )
        assert ds.status_code == 201, ds.text
        did = ds.json()["id"]
        assert ds.json()["classes"] == []
        assert ds.json()["enabled_annotation_types"] == ["rect"]

        added = client.post(
            f"/api/v1/datasets/{did}/assets/from-extract",
            json={"extract_job_id": eid},
            headers=_h("d1"),
        )
        assert added.status_code == 200, added.text
        members = added.json()
        assert len(members) >= 1
        assert all(m["media_kind"] == "frame" for m in members)

        # 同集再加上传图
        mix = client.post(
            f"/api/v1/datasets/{did}/assets",
            json={"asset_ids": [image["id"]]},
            headers=_h("d1"),
        )
        assert mix.status_code == 200
        all_m = client.get(
            f"/api/v1/datasets/{did}/assets", headers=_h("d1")
        ).json()
        kinds = {m["media_kind"] for m in all_m}
        assert "frame" in kinds and "image" in kinds

        frame_id = members[0]["asset_id"]
        blocked = client.delete(f"/api/v1/assets/{frame_id}", headers=_h("d1"))
        assert blocked.status_code == 409

        client.delete(
            f"/api/v1/datasets/{did}/assets/{frame_id}", headers=_h("d1")
        )
        ok = client.delete(f"/api/v1/assets/{frame_id}", headers=_h("d1"))
        assert ok.status_code == 204
