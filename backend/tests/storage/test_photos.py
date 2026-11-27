"""사진 파일 저장·삭제 테스트 (스펙 3.6)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.storage import photos
from app.storage.photos import clear_photos, new_photo_id, save_photo_bytes

PHOTO_ID_PATTERN = re.compile(r"ph_[0-9a-f]{32}")
VALID_ID = "ph_" + "0123456789abcdef" * 2
DATA = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"


def _entries(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def test_new_photo_id_matches_format() -> None:
    assert PHOTO_ID_PATTERN.fullmatch(new_photo_id())


def test_new_photo_id_is_unique_per_call() -> None:
    assert new_photo_id() != new_photo_id()


def test_save_photo_bytes_writes_jpg_and_returns_path(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()

    path = save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert path == photos_dir / f"{VALID_ID}.jpg"
    assert path.read_bytes() == DATA


def test_save_photo_bytes_creates_missing_dir(tmp_path: Path) -> None:
    photos_dir = tmp_path / "var" / "photos"

    path = save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert photos_dir.is_dir()
    assert path.read_bytes() == DATA


def test_save_photo_bytes_leaves_no_temp_file(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"

    save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert _entries(photos_dir) == [f"{VALID_ID}.jpg"]


def test_save_photo_bytes_overwrites_existing_file(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    save_photo_bytes(photos_dir, VALID_ID, b"old")

    path = save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert path.read_bytes() == DATA
    assert _entries(photos_dir) == [f"{VALID_ID}.jpg"]


@pytest.mark.parametrize(
    "photo_id",
    [
        "../x",
        "ph_" + "ABCDEF0123456789" * 2,
        "ph_" + "a" * 31,
        "ph_" + "a" * 33,
        "ph_" + "a" * 30 + "/a",
        "ph_" + "a" * 30 + "\\a",
        "ph_../" + "a" * 29,
        "",
        "ph_" + "a" * 32 + "\n",
        "xx_" + "a" * 32,
    ],
)
def test_save_photo_bytes_rejects_invalid_id_without_creating_files(
    tmp_path: Path, photo_id: str
) -> None:
    photos_dir = tmp_path / "photos"

    with pytest.raises(ValueError):
        save_photo_bytes(photos_dir, photo_id, DATA)

    assert _entries(tmp_path) == []


def test_save_photo_bytes_rejects_target_resolving_outside_dir(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    (photos_dir / f"{VALID_ID}.jpg").symlink_to(outside)

    with pytest.raises(ValueError):
        save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert outside.read_bytes() == b"outside"
    assert _entries(photos_dir) == [f"{VALID_ID}.jpg"]


def test_save_photo_bytes_removes_temp_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    photos_dir = tmp_path / "photos"

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(photos.os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        save_photo_bytes(photos_dir, VALID_ID, DATA)

    assert _entries(photos_dir) == []


def test_clear_photos_removes_regular_files_and_keeps_subdirs(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    save_photo_bytes(photos_dir, VALID_ID, DATA)
    (photos_dir / "note.txt").write_text("x")
    subdir = photos_dir / "sub"
    subdir.mkdir()
    (subdir / "inner.jpg").write_bytes(DATA)

    clear_photos(photos_dir)

    assert _entries(photos_dir) == ["sub"]
    assert (subdir / "inner.jpg").read_bytes() == DATA


def test_clear_photos_does_not_follow_symlinks(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    outside_file = tmp_path / "outside.jpg"
    outside_file.write_bytes(DATA)
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "keep.jpg").write_bytes(DATA)
    (photos_dir / "file_link.jpg").symlink_to(outside_file)
    (photos_dir / "dir_link").symlink_to(outside_dir, target_is_directory=True)

    clear_photos(photos_dir)

    # 링크 자체는 지우고, 링크가 가리키는 바깥 파일·디렉토리는 그대로 둔다.
    assert _entries(photos_dir) == []
    assert outside_file.read_bytes() == DATA
    assert (outside_dir / "keep.jpg").read_bytes() == DATA


def test_clear_photos_is_noop_when_dir_missing(tmp_path: Path) -> None:
    photos_dir = tmp_path / "photos"

    clear_photos(photos_dir)

    assert not photos_dir.exists()
