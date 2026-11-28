"""YOLO zip 导入：解析、去重、非库可见、非法包拒绝。"""

from __future__ import annotations

import io
import struct
import time
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from app.services.import_yolo import parse_data_yaml_names, parse_yolo_zip


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def _png(w: int = 100, h: int = 80, pad: bytes = b"") -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk + pad


def _yolo_zip(*, with_box: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "data.yaml",
            'path: .\ntrain: train/images\nnames:\n  0: "缺陷"\n',
        )
        zf.writestr("train/images/a.png", _png(100, 80, b"\x11"))
        if with_box:
            # cx=0.5 cy=0.5 w=0.2 h=0.2 → xyxy 40,32,60,48 on 100x80
            zf.writestr("train/labels/a.txt", "0 0.5 0.5 0.2 0.2\n")
        else:
            zf.writestr("train/labels/a.txt", "")
        zf.writestr("train/images/b.png", _png(100, 80, b"\x22"))
        zf.writestr("train/labels/b.txt", "")
    return buf.getvalue()


def test_parse_data_yaml_variants() -> None:
    assert parse_data_yaml_names("names: ['a', 'b']\n") == ["a", "b"]
    assert parse_data_yaml_names("names:\n  0: person\n  1: car\n") == [
        "person",
        "car",
    ]
    classes, images = parse_yolo_zip(_yolo_zip())
    assert classes == ["缺陷"]
    assert len(images) == 2


def test_import_creates_hidden_assets_and_dedup() -> None:
    z1 = _yolo_zip()
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "导入测"}, headers=_h("imp-owner")
        ).json()["id"]

        # 非法包
        bad = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
            data={"datasetName": "坏包"},
        )
        assert bad.status_code == 422, bad.text

        r = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("demo.zip", z1, "application/zip")},
            data={"datasetName": "导入集"},
        )
        assert r.status_code == 202, r.text
        import_id = r.json()["id"]
        dataset_id = r.json()["dataset_id"]
        assert dataset_id

        row = None
        for _ in range(80):
            row = client.get(
                f"/api/v1/dataset-imports/{import_id}", headers=_h("imp-owner")
            ).json()
            if row["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.15)
        assert row is not None
        assert row["status"] == "succeeded", row
        assert row["stats"]["images"] == 2
        assert row["stats"]["created"] == 2

        imported = client.get(
            f"/api/v1/datasets/{dataset_id}", headers=_h("imp-owner")
        ).json()
        assert imported["classes"][0]["name"] == "缺陷"
        class_id = imported["classes"][0]["id"]
        vocab = client.get(
            f"/api/v1/projects/{pid}/classes", headers=_h("imp-owner")
        ).json()
        assert [c["id"] for c in vocab] == [class_id]

        mem = client.get(
            f"/api/v1/datasets/{dataset_id}/assets", headers=_h("imp-owner")
        ).json()
        assert len(mem) == 2

        # 素材库目录不应出现导入图
        folders = client.get(
            f"/api/v1/projects/{pid}/folders", headers=_h("imp-owner")
        ).json()
        if folders:
            page = client.get(
                f"/api/v1/folders/{folders[0]['id']}/assets?media_kind=image",
                headers=_h("imp-owner"),
            ).json()
            ids = {a["id"] for a in page.get("items", page if isinstance(page, list) else [])}
            for m in mem:
                assert m["asset_id"] not in ids

        # 标注可读
        ann = client.get(
            f"/api/v1/datasets/{dataset_id}/assets/{mem[0]['asset_id']}/annotation",
            headers=_h("imp-owner"),
        ).json()
        assert ann["status"] == "submitted"

        # 血缘含 importId
        lin = client.get(
            f"/api/v1/assets/{mem[0]['asset_id']}/lineage",
            headers=_h("imp-owner"),
        ).json()
        assert lin.get("importId") == import_id

        # 再次导入相同内容到新空集 → reused
        empty = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "空集复用"},
            headers=_h("imp-owner"),
        ).json()["id"]
        r2 = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("demo2.zip", z1, "application/zip")},
            data={"datasetId": empty},
        )
        assert r2.status_code == 202, r2.text
        iid2 = r2.json()["id"]
        row2 = None
        for _ in range(80):
            row2 = client.get(
                f"/api/v1/dataset-imports/{iid2}", headers=_h("imp-owner")
            ).json()
            if row2["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.15)
        assert row2["status"] == "succeeded", row2
        assert row2["stats"]["reused"] == 2
        assert row2["stats"]["created"] == 0
        reused_ds = client.get(
            f"/api/v1/datasets/{empty}", headers=_h("imp-owner")
        ).json()
        assert reused_ds["classes"][0]["id"] == class_id
        vocab_after = client.get(
            f"/api/v1/projects/{pid}/classes", headers=_h("imp-owner")
        ).json()
        assert len(vocab_after) == 1
