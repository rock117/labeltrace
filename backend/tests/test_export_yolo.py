"""YOLO 导出：文件名规则、坐标换算、按版本打 zip。"""

from __future__ import annotations

import io
import struct
import zipfile
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.export_yolo import (
    export_stem,
    sanitize_stem,
    xyxy_to_yolo,
)


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def _png(w: int = 100, h: int = 80) -> bytes:
    # 最小合法 IHDR PNG（无像素数据也可被 image_size_from_bytes 读尺寸）
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    # len + type + data + crc(假)
    chunk = struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk + b"\x00" * 16


def test_sanitize_and_unique_stem() -> None:
    assert sanitize_stem("图 1.jpg") == "1"
    assert sanitize_stem("示意图.jpg") == "img"
    assert sanitize_stem("frame_000054.jpg") == "frame_000054"
    assert sanitize_stem("a b c.jpg") == "a_b_c"
    a = uuid4()
    b = uuid4()
    used: set[str] = set()
    s1 = export_stem(a, "frame_000054.jpg", used)
    s2 = export_stem(b, "frame_000054.jpg", used)
    assert s1 != s2
    assert s1.startswith(str(a).replace("-", "")[:8])
    assert s2.startswith(str(b).replace("-", "")[:8])


def test_xyxy_to_yolo_center() -> None:
    # 100x100 图，框 [25,25,75,75] → cx=0.5 cy=0.5 w=0.5 h=0.5
    r = xyxy_to_yolo([25, 25, 75, 75], 100, 100)
    assert r is not None
    cx, cy, nw, nh = r
    assert abs(cx - 0.5) < 1e-6
    assert abs(cy - 0.5) < 1e-6
    assert abs(nw - 0.5) < 1e-6
    assert abs(nh - 0.5) < 1e-6


def test_export_zip_matches_snapshot() -> None:
    png = _png(200, 100)
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "导出测"}, headers=_h("exp-owner")
        ).json()["id"]
        fid = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "图"},
            headers=_h("exp-owner"),
        ).json()["id"]
        # 两张同名图，验证 stem 不冲突
        img1 = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("exp-owner"),
            files={"file": ("frame_000054.jpg", png, "image/png")},
        ).json()["id"]
        png2 = _png(200, 100) + b"\x01"  # 不同 hash
        img2 = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("exp-owner"),
            files={"file": ("frame_000054.jpg", png2, "image/png")},
        ).json()["id"]

        ds_body = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "导出集", "enabled_annotation_types": ["rect"]},
            headers=_h("exp-owner"),
        ).json()
        ds = ds_body["id"]
        created_cls = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "缺陷"},
            headers=_h("exp-owner"),
        )
        assert created_cls.status_code == 201, created_cls.text
        cid = created_cls.json()["id"]
        classed = client.put(
            f"/api/v1/datasets/{ds}/classes",
            json={"classIds": [cid]},
            headers=_h("exp-owner"),
        )
        assert classed.status_code == 200, classed.text
        client.post(
            f"/api/v1/datasets/{ds}/assets",
            json={"asset_ids": [img1, img2]},
            headers=_h("exp-owner"),
        )
        # 一张有框，一张空提交（负样本）
        assert (
            client.put(
                f"/api/v1/datasets/{ds}/assets/{img1}/annotation",
                json={
                    "shapes": {
                        "format": "xyxy_abs",
                        "items": [
                            {
                                "type": "rect",
                                "classId": cid,
                                "bbox": [10, 10, 50, 50],
                            }
                        ],
                    },
                    "status": "submitted",
                },
                headers=_h("exp-owner"),
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/v1/datasets/{ds}/assets/{img2}/annotation",
                json={
                    "shapes": {"format": "xyxy_abs", "items": []},
                    "status": "submitted",
                },
                headers=_h("exp-owner"),
            ).status_code
            == 200
        )

        ver = client.post(
            f"/api/v1/datasets/{ds}/versions",
            json={
                "name": "v1",
                "split_train": 1.0,
                "split_val": 0.0,
                "split_test": 0.0,
                "split_seed": 1,
            },
            headers=_h("exp-owner"),
        ).json()
        version_id = ver["id"]

        enq = client.post(
            f"/api/v1/versions/{version_id}/export",
            headers=_h("exp-owner"),
        )
        assert enq.status_code == 202, enq.text
        job_id = enq.json()["job_id"]

        job = None
        for _ in range(80):
            job = client.get(f"/api/v1/jobs/{job_id}", headers=_h("exp-owner")).json()
            if job["status"] in ("succeeded", "failed"):
                break
            import time

            time.sleep(0.15)
        assert job is not None
        assert job["status"] == "succeeded", job

        dl = client.get(
            f"/api/v1/versions/{version_id}/export/download",
            headers=_h("exp-owner"),
        )
        assert dl.status_code == 200, dl.text
        assert dl.headers.get("content-type", "").startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            names = set(zf.namelist())
            assert "data.yaml" in names
            assert "manifest.csv" not in names
            images = [n for n in names if "/images/" in n]
            labels = [n for n in names if "/labels/" in n]
            assert len(images) == 2
            assert len(labels) == 2
            # 同原名 → 不同包内名
            stems = {n.rsplit("/", 1)[-1].rsplit(".", 1)[0] for n in images}
            assert len(stems) == 2
            yaml_text = zf.read("data.yaml").decode("utf-8")
            assert "缺陷" in yaml_text or "0:" in yaml_text
            # 至少一个非空 label、一个空 label
            nonempty = 0
            empty = 0
            for ln in labels:
                body = zf.read(ln).decode("utf-8").strip()
                if body:
                    nonempty += 1
                    parts = body.split()
                    assert len(parts) == 5
                    assert parts[0] == "0"
                else:
                    empty += 1
            assert nonempty == 1
            assert empty == 1

        # 8.4：移出工作区后，因仍在版本快照中，硬删 409；导出仍可下载
        rem = client.delete(
            f"/api/v1/datasets/{ds}/assets/{img1}",
            headers=_h("exp-owner"),
        )
        assert rem.status_code == 204, rem.text
        rem2 = client.delete(
            f"/api/v1/datasets/{ds}/assets/{img2}",
            headers=_h("exp-owner"),
        )
        assert rem2.status_code == 204, rem2.text
        hard = client.delete(
            f"/api/v1/assets/{img1}",
            headers=_h("exp-owner"),
        )
        assert hard.status_code == 409, hard.text
        dl2 = client.get(
            f"/api/v1/versions/{version_id}/export/download",
            headers=_h("exp-owner"),
        )
        assert dl2.status_code == 200


def test_export_segment_profile_polygon_only() -> None:
    """segment 剖面只写 polygon；同图 rect 被忽略。"""
    png = _png(100, 100)
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "分割导出"}, headers=_h("seg-o")
        ).json()["id"]
        fid = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "F"},
            headers=_h("seg-o"),
        ).json()["id"]
        img = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("seg-o"),
            files={"file": ("a.png", png, "image/png")},
        ).json()["id"]
        ds = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "S"},
            headers=_h("seg-o"),
        ).json()["id"]
        cid = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "物"},
            headers=_h("seg-o"),
        ).json()["id"]
        client.put(
            f"/api/v1/datasets/{ds}/annotation-types",
            json={"enabledAnnotationTypes": ["rect", "polygon"]},
            headers=_h("seg-o"),
        )
        client.put(
            f"/api/v1/datasets/{ds}/classes",
            json={"classIds": [cid]},
            headers=_h("seg-o"),
        )
        client.post(
            f"/api/v1/datasets/{ds}/assets",
            json={"asset_ids": [img]},
            headers=_h("seg-o"),
        )
        assert (
            client.put(
                f"/api/v1/datasets/{ds}/assets/{img}/annotation",
                headers=_h("seg-o"),
                json={
                    "shapes": {
                        "format": "xyxy_abs",
                        "items": [
                            {
                                "type": "rect",
                                "classId": cid,
                                "bbox": [0, 0, 10, 10],
                            },
                            {
                                "type": "polygon",
                                "classId": cid,
                                "points": [[10, 10], [90, 10], [90, 90]],
                            },
                        ],
                    },
                    "status": "submitted",
                },
            ).status_code
            == 200
        )
        ver = client.post(
            f"/api/v1/datasets/{ds}/versions",
            json={
                "name": "v1",
                "split_train": 1.0,
                "split_val": 0.0,
                "split_test": 0.0,
            },
            headers=_h("seg-o"),
        ).json()["id"]

        enq = client.post(
            f"/api/v1/versions/{ver}/export",
            headers=_h("seg-o"),
            json={"profile": "segment"},
        )
        assert enq.status_code == 202, enq.text
        job_id = enq.json()["job_id"]
        job = None
        for _ in range(80):
            job = client.get(f"/api/v1/jobs/{job_id}", headers=_h("seg-o")).json()
            if job["status"] in ("succeeded", "failed"):
                break
            import time

            time.sleep(0.15)
        assert job is not None and job["status"] == "succeeded", job
        assert job["result"]["profile"] == "segment"

        dl = client.get(
            f"/api/v1/versions/{ver}/export/download?profile=segment",
            headers=_h("seg-o"),
        )
        assert dl.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            labels = [n for n in zf.namelist() if n.endswith(".txt")]
            assert len(labels) == 1
            body = zf.read(labels[0]).decode().strip()
            parts = body.split()
            # class + 3 points * 2 coords
            assert parts[0] == "0"
            assert len(parts) == 1 + 6
            yaml_text = zf.read("data.yaml").decode()
            assert "task: segment" in yaml_text
