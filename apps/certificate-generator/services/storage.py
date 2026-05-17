from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable
import shutil


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def slugify_filename(value: str, default: str = 'file') -> str:
    text = re.sub(r'\s+', ' ', str(value or '').strip())
    text = re.sub(r'[\\/:*?"<>|]+', '-', text)
    text = text.replace("'", '')
    text = re.sub(r'\s*-\s*', ' - ', text)
    text = re.sub(r'\s+', ' ', text).strip(' .')
    return text or default


def write_json(path: str | Path, data: dict):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path: str | Path, default=None):
    target = Path(path)
    if not target.exists():
        return {} if default is None else default
    return json.loads(target.read_text(encoding='utf-8'))


def remove_files(paths: Iterable[str | Path]):
    for item in paths:
        try:
            Path(item).unlink(missing_ok=True)
        except Exception:
            pass


def remove_dir(path: str | Path):
    try:
        shutil.rmtree(Path(path), ignore_errors=True)
    except Exception:
        pass
