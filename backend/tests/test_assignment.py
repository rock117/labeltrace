"""数据集成员任务分配：可见性、转单、标注写权限。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x02" * 40


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def test_assign_visibility_and_annotate_gate() -> None:
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "分配项目"}, headers=_h("boss")
        ).json()["id"]
        client.post(
            f"/api/v1/projects/{pid}/members",
            json={"user_id": "ann_a", "roles": ["annotator"]},
            headers=_h("boss"),
        )
        client.post(
            f"/api/v1/projects/{pid}/members",
            json={"user_id": "ann_c", "roles": ["annotator"]},
            headers=_h("boss"),
        )
        folder = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "F"},
            headers=_h("boss"),
        ).json()["id"]
        imgs = []
        for i in range(3):
            aid = client.post(
                f"/api/v1/folders/{folder}/assets",
                headers=_h("boss"),
                files={"file": (f"{i}.png", PNG + bytes([i]), "image/png")},
            ).json()["id"]
            imgs.append(aid)

        ds = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "D"},
            headers=_h("boss"),
        ).json()["id"]
        client.post(
            f"/api/v1/datasets/{ds}/assets",
            json={"asset_ids": imgs, "split": "unassigned"},
            headers=_h("boss"),
        )

        roster = client.get(
            f"/api/v1/projects/{pid}/members", headers=_h("boss")
        ).json()
        by_name = {m["username"]: m["user_id"] for m in roster}
        uid_a = by_name["ann_a"]
        uid_c = by_name["ann_c"]

        # 未分配：annotator 列表为空，写标注 403
        empty = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("ann_a")
        ).json()
        assert empty == []
        denied = client.put(
            f"/api/v1/datasets/{ds}/assets/{imgs[0]}/annotation",
            headers=_h("ann_a"),
            json={
                "shapes": {"format": "xyxy_abs", "items": []},
                "status": "draft",
            },
        )
        assert denied.status_code == 403

        # 批量：前两张给 A，第三张给 C
        assigned = client.post(
            f"/api/v1/datasets/{ds}/assignments",
            headers=_h("boss"),
            json={"assetIds": imgs[:2], "assigneeUserId": uid_a},
        )
        assert assigned.status_code == 200
        assert all(x["assignee_user_id"] == uid_a for x in assigned.json())
        client.post(
            f"/api/v1/datasets/{ds}/assignments",
            headers=_h("boss"),
            json={"assetIds": [imgs[2]], "assigneeUserId": uid_c},
        )

        a_list = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("ann_a")
        ).json()
        assert {m["asset_id"] for m in a_list} == set(imgs[:2])

        c_list = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("ann_c")
        ).json()
        assert {m["asset_id"] for m in c_list} == {imgs[2]}

        ok = client.put(
            f"/api/v1/datasets/{ds}/assets/{imgs[0]}/annotation",
            headers=_h("ann_a"),
            json={
                "shapes": {"format": "xyxy_abs", "items": []},
                "status": "draft",
            },
        )
        assert ok.status_code == 200

        steal = client.put(
            f"/api/v1/datasets/{ds}/assets/{imgs[2]}/annotation",
            headers=_h("ann_a"),
            json={
                "shapes": {"format": "xyxy_abs", "items": []},
                "status": "draft",
            },
        )
        assert steal.status_code == 403

        # 转单：C → A，A 列表合并
        client.post(
            f"/api/v1/datasets/{ds}/assignments",
            headers=_h("boss"),
            json={"assetIds": [imgs[2]], "assigneeUserId": uid_a},
        )
        a_after = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("ann_a")
        ).json()
        assert {m["asset_id"] for m in a_after} == set(imgs)
        c_after = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("ann_c")
        ).json()
        assert c_after == []

        # owner 可看全部；mine=1 只看自己的（老板未自分则空）
        all_mem = client.get(
            f"/api/v1/datasets/{ds}/assets", headers=_h("boss")
        ).json()
        assert len(all_mem) == 3
        mine_boss = client.get(
            f"/api/v1/datasets/{ds}/assets?mine=1", headers=_h("boss")
        ).json()
        assert mine_boss == []

        # annotator 不能批量分配
        forbid_assign = client.post(
            f"/api/v1/datasets/{ds}/assignments",
            headers=_h("ann_a"),
            json={"assetIds": [imgs[0]], "assigneeUserId": uid_c},
        )
        assert forbid_assign.status_code == 403
