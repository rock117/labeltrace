"""LocalFsBlobStore 集成测试。"""

from pathlib import Path

from app.storage.local import LocalFsBlobStore


def test_local_put_get_exists_delete(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    key = "proj/abc/assets/deadbeef.jpg"
    payload = b"\xff\xd8\xff fake-jpeg"

    assert store.exists(key) is False
    store.put(key, payload, content_type="image/jpeg")
    assert store.exists(key) is True

    data = b"".join(store.get(key))
    assert data == payload

    store.delete(key)
    assert store.exists(key) is False
    store.delete(key)  # 幂等


def test_local_rejects_path_traversal(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    try:
        store.put("../outside.bin", b"x")
        raised = False
    except ValueError:
        raised = True
    assert raised
