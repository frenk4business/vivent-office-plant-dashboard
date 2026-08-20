from __future__ import annotations

import json
import os
from pathlib import Path

from .models import DashboardData


def save_cache(path: Path, data: DashboardData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data.to_dict(), ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_cache(path: Path) -> DashboardData | None:
    try:
        return DashboardData.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None

