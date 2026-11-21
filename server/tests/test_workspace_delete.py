"""Deleting a workspace removes its files too, not only its records: with the workspace
record gone, the cleanup job's orphan sweep (which only acts under known workspaces) would
never reach them."""
import os

import pytest

import app.routes.workspaces as workspaces_mod
from app.main import app
from app.services.storage_service import build_document_key, build_image_key, get_storage
from tests.fakes import FakeVectorStore
from tests.test_brand_images import OTHER_OID, WS_OID, _mk


def _exists(path: str) -> bool:
    return os.path.exists(path)


@pytest.mark.asyncio
async def test_deleting_a_workspace_removes_its_files(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(workspaces_mod, "get_vector_store", lambda: FakeVectorStore())
    client = await _mk(test_db, tmp_path, monkeypatch)
    storage = get_storage()
    doc_key = build_document_key(str(WS_OID), "a" * 24, "pdf")
    image_key = build_image_key(str(WS_OID), "img1", "photo.png")
    other_key = build_document_key(str(OTHER_OID), "b" * 24, "pdf")
    for key in (doc_key, image_key, other_key):
        await storage.save(key, b"file")

    async with client:
        resp = await client.delete(f"/api/workspaces/{WS_OID}")
    app.dependency_overrides.clear()

    assert resp.status_code == 204
    assert await test_db.workspaces.find_one({"_id": WS_OID}) is None
    assert not _exists(storage.local_path(doc_key))
    assert not _exists(storage.local_path(image_key))
    assert _exists(storage.local_path(other_key))  # another workspace's files stay
    get_storage.cache_clear()


@pytest.mark.asyncio
async def test_a_refused_delete_removes_no_files(test_db, tmp_path, monkeypatch):
    # Someone who doesn't own the workspace gets a 404, and its files stay.
    monkeypatch.setattr(workspaces_mod, "get_vector_store", lambda: FakeVectorStore())
    client = await _mk(test_db, tmp_path, monkeypatch, owner=OTHER_OID)
    storage = get_storage()
    doc_key = build_document_key(str(WS_OID), "a" * 24, "pdf")
    await storage.save(doc_key, b"file")

    async with client:
        resp = await client.delete(f"/api/workspaces/{WS_OID}")
    app.dependency_overrides.clear()

    assert resp.status_code == 404
    assert _exists(storage.local_path(doc_key))
    get_storage.cache_clear()
