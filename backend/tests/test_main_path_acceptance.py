"""11.1 主体主路径：上传视频 → 抽帧 → 审查删帧 → 入集 → 标框 → 发版。"""

import time
from pathlib import Path
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import app
from app.media.ffmpeg import make_sample_video


def _h(user: str) -> dict[str, str]:
    return {"X-User-Id": user}


def test_main_path_upload_extract_review_annotate_publish(tmp_path: Path) -> None:
    video_path = make_sample_video(tmp_path / "main.mp4", seconds=1.0, fps=10)
    raw = video_path.read_bytes()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24

    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects",
            json={"name": "主路径验收"},
            headers=_h("main"),
        ).json()["id"]
        folder = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "素材"},
            headers=_h("main"),
        ).json()["id"]

        video = client.post(
            f"/api/v1/folders/{folder}/assets",
            headers=_h("main"),
            files={"file": ("验收.mp4", raw, "video/mp4")},
        ).json()
        assert video["media_kind"] == "video"

        extract = client.post(
            f"/api/v1/assets/{video['id']}/extract-jobs",
            headers=_h("main"),
            json={"mode": "stride_frames", "stride": 5, "max_frames": 20},
        ).json()
        eid = extract["id"]

        job = extract
        for _ in range(60):
            job = client.get(
                f"/api/v1/extract-jobs/{eid}", headers=_h("main")
            ).json()
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.15)
        assert job["status"] == "succeeded", job

        frames = client.get(
            f"/api/v1/extract-jobs/{eid}/frames", headers=_h("main")
        ).json()
        assert len(frames) >= 2
        times = [f["time_ms"] for f in frames]
        assert times == sorted(times)

        deleted = client.post(
            f"/api/v1/extract-jobs/{eid}/frames/batch-delete",
            headers=_h("main"),
            json={"asset_ids": [frames[0]["id"]]},
        ).json()
        assert deleted["discarded_count"] >= 1

        remaining = client.get(
            f"/api/v1/extract-jobs/{eid}/frames", headers=_h("main")
        ).json()
        assert len(remaining) == len(frames) - 1

        ds = client.post(
            f"/api/v1/projects/{pid}/datasets",
            headers=_h("main"),
            json={
                "name": "主集",
                "classes": ["obj"],
                "enabledAnnotationTypes": ["rect"],
            },
        ).json()
        did = ds["id"]
        cid = ds["classes"][0]["id"]

        listed = client.get(
            f"/api/v1/projects/{pid}/datasets", headers=_h("main")
        )
        assert listed.status_code == 200
        assert any(d["id"] == did for d in listed.json())

        added = client.post(
            f"/api/v1/datasets/{did}/assets/from-extract",
            headers=_h("main"),
            json={"extract_job_id": eid, "split": "train"},
        ).json()
        assert len(added) == len(remaining)
        asset_id = added[0]["asset_id"]

        # 已入集帧硬删 409
        ban = client.delete(
            f"/api/v1/assets/{asset_id}", headers=_h("main")
        )
        assert ban.status_code == 409

        # 全部成员提交；首张带框
        for i, m in enumerate(added):
            items = (
                [{"type": "rect", "classId": cid, "bbox": [10, 10, 80, 80]}]
                if i == 0
                else []
            )
            ann = client.put(
                f"/api/v1/datasets/{did}/assets/{m['asset_id']}/annotation",
                headers=_h("main"),
                json={
                    "shapes": {"format": "xyxy_abs", "items": items},
                    "status": "submitted",
                },
            )
            assert ann.status_code == 200, ann.text
        assert (
            client.get(
                f"/api/v1/datasets/{did}/assets/{asset_id}/annotation",
                headers=_h("main"),
            ).json()["updated_by"]
        )

        lineage = client.get(
            f"/api/v1/assets/{asset_id}/lineage", headers=_h("main")
        ).json()
        assert lineage["mediaKind"] == "frame"
        assert lineage["parentVideoId"] == video["id"]
        assert lineage["frameIndex"] is not None

        ver = client.post(
            f"/api/v1/datasets/{did}/versions",
            headers=_h("main"),
            json={"name": "v1", "note": "主路径"},
        )
        assert ver.status_code == 201, ver.text
        body = ver.json()
        assert body["entry_count"] == len(remaining)
        assert body["member_sources"]
        version_id = body["id"]
        snap_count = len(
            client.get(
                f"/api/v1/versions/{version_id}/manifest", headers=_h("main")
            ).json().get("entries")
            or []
        )

        # 发版后追加不影响已发版本
        up_img = client.post(
            f"/api/v1/folders/{folder}/assets",
            headers=_h("main"),
            files={"file": ("extra.png", png, "image/png")},
        )
        assert up_img.status_code == 201, up_img.text
        client.post(
            f"/api/v1/datasets/{did}/assets",
            headers=_h("main"),
            json={"asset_ids": [up_img.json()["id"]], "split": "val"},
        )
        manifest = client.get(
            f"/api/v1/versions/{version_id}/manifest", headers=_h("main")
        ).json()
        assert len(manifest.get("entries") or []) == snap_count

        # viewer 禁传
        client.post(
            f"/api/v1/projects/{pid}/members",
            headers=_h("main"),
            json={"user_id": "viewer1", "roles": ["viewer"]},
        )
        forbidden = client.post(
            f"/api/v1/folders/{folder}/assets",
            headers=_h("viewer1"),
            files={"file": ("no.png", png, "image/png")},
        )
        assert forbidden.status_code == 403

        # 内容可读（含中文文件名）
        content = client.get(
            f"/api/v1/assets/{video['id']}/content", headers=_h("main")
        )
        assert content.status_code == 200
        cd = content.headers.get("content-disposition", "")
        assert "filename*" in cd
        assert unquote(cd.split("filename*=UTF-8''", 1)[1]) == "验收.mp4"
