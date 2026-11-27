import os
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

DEFAULT_JPEG_QUALITY = 85
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 24_000_000


@dataclass(frozen=True)
class PreparedImage:
    jpeg: bytes
    original_size: tuple[int, int]
    preprocessed_size: tuple[int, int]


def _read_image(path: Path, allowed_root: Path) -> bytes:
    try:
        root = allowed_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Allowed image root must be a directory")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("Tray photo must be inside the allowed image directory")
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Tray photo must be a regular file")
        if info.st_size > MAX_IMAGE_BYTES:
            raise ValueError("Tray photo exceeds the original file size limit")
        with resolved.open("rb") as file:
            opened = os.fstat(file.fileno())
            if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(info, opened):
                raise ValueError("Tray photo changed while it was being opened")
            data = file.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Tray photo exceeds the original file size limit")
        return data
    except (OSError, RuntimeError) as error:
        raise ValueError("Tray photo path could not be resolved or read") from error


def prepare_jpeg(
    path: Path,
    *,
    allowed_root: Path,
    max_side: int = 1536,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> PreparedImage:
    """Validate a tray image and return a resized JPEG with its dimensions."""
    if max_side < 1:
        raise ValueError("max_side must be positive")
    if not 1 <= jpeg_quality <= 95:
        raise ValueError("jpeg_quality must be between 1 and 95")

    data = _read_image(path, allowed_root)
    try:
        with Image.open(BytesIO(data), formats=ALLOWED_IMAGE_FORMATS) as probe:
            width, height = original_size = probe.size
            if max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Tray photo exceeds the original image dimension or pixel limit")
            probe.verify()
        with Image.open(BytesIO(data), formats=ALLOWED_IMAGE_FORMATS) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = image.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Tray photo exceeds Pillow's image safety limit") from error
    except (OSError, EOFError, SyntaxError) as error:
        raise ValueError("Could not decode a valid JPEG or PNG tray photo") from error

    rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    rgb.info.clear()
    with BytesIO() as output:
        rgb.save(output, format="JPEG", quality=jpeg_quality)
        return PreparedImage(output.getvalue(), original_size, rgb.size)
