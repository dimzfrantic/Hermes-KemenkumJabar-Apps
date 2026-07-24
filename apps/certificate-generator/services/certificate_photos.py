from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from services.google_drive import download_drive_file_with_config, extract_drive_file_id
from services.storage import slugify_filename

PHOTO_PLACEHOLDER = '{{foto}}'
PHOTO_COLUMN_ALIASES = [
    'foto',
    'photo',
    'pasfoto',
    'pasphoto',
    'uploadfoto',
    'unggahfoto',
    'filefoto',
    'linkfoto',
    'fotopeserta',
]


def normalize_header_key(value: str) -> str:
    import re
    return re.sub(r'[^a-z0-9]+', '', (value or '').strip().lower())


def detect_photo_column(headers: list[str]) -> str | None:
    normalized_map = {normalize_header_key(header): header for header in headers}
    return next((normalized_map[key] for key in PHOTO_COLUMN_ALIASES if key in normalized_map), None)


def _first_photo_ref(value: str | None) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    for separator in ('\n', ',', ';'):
        if separator in text:
            return next((part.strip() for part in text.split(separator) if part.strip()), '')
    return text


def _optimize_photo(input_path: Path, output_path: Path, max_side: int = 900) -> str:
    with Image.open(input_path) as img:
        image = ImageOps.exif_transpose(img).convert('RGB')
        image.thumbnail((max_side, max_side), Image.LANCZOS)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format='JPEG', quality=88, optimize=True, progressive=True)
    return str(output_path)


def prepare_certificate_photo(
    photo_ref: str | None,
    runtime_root: Path,
    *,
    google_token_path: str,
    drive_scopes: list[str],
    row_number: int | None = None,
    use_cached_service: bool = True,
) -> str | None:
    ref = _first_photo_ref(photo_ref)
    if not ref:
        return None

    runtime_root.mkdir(parents=True, exist_ok=True)
    label = slugify_filename(f'foto-{row_number or uuid4().hex}', default='foto')
    downloaded_path = runtime_root / f'{uuid4().hex}-{label}.source'

    local_path = Path(ref).expanduser()
    if local_path.exists() and local_path.is_file():
        source_path = local_path
    elif extract_drive_file_id(ref):
        source_path = Path(download_drive_file_with_config(
            ref,
            str(downloaded_path),
            google_token_path,
            drive_scopes,
            use_cached_service=use_cached_service,
        ))
    else:
        raise RuntimeError('Foto peserta belum dapat dibaca. Gunakan link Google Drive/file upload Google Form atau path file lokal yang valid.')

    optimized_path = runtime_root / f'{uuid4().hex}-{label}.jpg'
    result = _optimize_photo(source_path, optimized_path)
    if source_path == downloaded_path:
        try:
            downloaded_path.unlink(missing_ok=True)
        except Exception:
            pass
    return result
