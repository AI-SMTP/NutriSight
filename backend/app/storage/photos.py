"""사진 파일 저장과 삭제 (스펙 3.6).

사진 파일 이름은 서버가 만든 `photo_id`로만 정한다. 업로드 파일명은 경로에 쓰지 않는다.
이미지 내용 검증과 크기 상한은 업로드 API가 맡는다.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path

PHOTO_ID_PREFIX = "ph_"
PHOTO_SUFFIX = ".jpg"
_PHOTO_ID_RE = re.compile(r"ph_[0-9a-f]{32}")


def new_photo_id() -> str:
    """새 사진 ID(`ph_` + 32자리 소문자 16진수)를 만든다."""
    return f"{PHOTO_ID_PREFIX}{uuid.uuid4().hex}"


def _validate_photo_id(photo_id: str) -> None:
    if not _PHOTO_ID_RE.fullmatch(photo_id):
        raise ValueError(f"사진 ID 형식이 올바르지 않다: {photo_id!r}")


def _target_path(photos_dir: Path, photo_id: str) -> Path:
    """`<photos_dir>/<photo_id>.jpg`를 돌려준다. 실제 위치가 `photos_dir` 밖이면 `ValueError`."""
    target = photos_dir / f"{photo_id}{PHOTO_SUFFIX}"
    resolved_dir = photos_dir.resolve()
    if target.resolve().parent != resolved_dir:
        raise ValueError(f"사진 경로가 사진 디렉토리 밖을 가리킨다: {target}")
    return target


def save_photo_bytes(photos_dir: Path, photo_id: str, data: bytes) -> Path:
    """사진 바이트를 `<photos_dir>/<photo_id>.jpg`에 쓰고 그 경로를 돌려준다.

    `photo_id`가 `^ph_[0-9a-f]{32}$`가 아니면 파일·디렉토리를 만들지 않고 `ValueError`를 던진다.
    같은 디렉토리의 임시 파일에 쓴 뒤 `os.replace`로 옮기므로, 실패해도 반쯤 쓴 파일이나
    임시 파일이 남지 않는다. 같은 ID의 파일이 있으면 덮어쓴다.
    """
    _validate_photo_id(photo_id)
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = _target_path(photos_dir, photo_id)

    fd, tmp_name = tempfile.mkstemp(dir=photos_dir, prefix=f".{photo_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
        os.replace(tmp_name, target)
    finally:
        # 교체에 성공했으면 임시 파일은 이미 없다. 실패했을 때만 실제로 지운다.
        Path(tmp_name).unlink(missing_ok=True)
    return target


def clear_photos(photos_dir: Path) -> None:
    """`photos_dir` 바로 아래의 일반 파일과 심볼릭 링크를 지운다.

    하위 디렉토리는 남기고 들어가지 않는다. 심볼릭 링크는 따라가지 않고 링크 자체만 지우므로
    링크가 가리키는 바깥 파일·디렉토리는 그대로 남는다. 디렉토리가 없으면 아무것도 하지 않는다.
    """
    if not photos_dir.is_dir():
        return
    with os.scandir(photos_dir) as entries:
        removable = [
            entry.path
            for entry in entries
            if entry.is_symlink() or entry.is_file(follow_symlinks=False)
        ]
    for path in removable:
        Path(path).unlink(missing_ok=True)
