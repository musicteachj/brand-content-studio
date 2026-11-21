"""The startup write check: the storage and Chroma directories must be writable by the
user the app runs as, or the app refuses to start and names the directory (a volume
owned by the wrong uid otherwise fails much later, on a visitor's first upload)."""
import os
import re

import pytest

from app import main as main_mod
from app.config import settings
from app.services.storage_service import StorageNotWritable, assert_writable

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write a 0o500 directory"
)


@pytest.fixture
def read_only_dir(tmp_path):
    d = tmp_path / "storage"
    d.mkdir()
    d.chmod(0o500)
    yield d
    d.chmod(0o700)


@needs_non_root
def test_startup_refuses_an_unwritable_storage_dir(read_only_dir):
    with pytest.raises(StorageNotWritable) as info:
        assert_writable(read_only_dir)
    assert str(read_only_dir) in str(info.value)
    assert f"uid {os.getuid()}" in str(info.value)


def test_a_writable_dir_passes_and_keeps_nothing(tmp_path):
    assert_writable(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_missing_dir_is_created(tmp_path):
    target = tmp_path / "a" / "b"
    assert_writable(target)
    assert target.is_dir()


@needs_non_root
async def test_the_lifespan_checks_both_data_dirs_before_anything_else(
    read_only_dir, tmp_path, monkeypatch
):
    async def must_not_connect() -> None:
        raise AssertionError("the write check must run before Mongo, Chroma, and the seed")

    monkeypatch.setattr(main_mod, "connect_to_mongo", must_not_connect)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    monkeypatch.setattr(settings, "chroma_path", str(read_only_dir))
    with pytest.raises(StorageNotWritable, match=re.escape(str(read_only_dir))):
        async with main_mod.lifespan(main_mod.app):
            pass

    monkeypatch.setattr(settings, "storage_local_dir", str(read_only_dir))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path))
    with pytest.raises(StorageNotWritable, match=re.escape(str(read_only_dir))):
        async with main_mod.lifespan(main_mod.app):
            pass
