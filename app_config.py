"""Rutas de configuración, perfiles e historial de sesión."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from compressor import AspectMode

try:
    from platformdirs import user_data_dir
except ImportError:
    user_data_dir = None  # type: ignore[misc, assignment]


def config_dir() -> Path:
    if user_data_dir is not None:
        p = Path(user_data_dir("InstaLight", appauthor=False))
    else:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME", ".")
        p = Path(base) / "InstaLight"
    p.mkdir(parents=True, exist_ok=True)
    return p


def presets_path() -> Path:
    return config_dir() / "presets.json"


def last_session_path() -> Path:
    return config_dir() / "last_session.json"


def load_presets() -> list[dict[str, Any]]:
    path = presets_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("presets", []))
    except (OSError, json.JSONDecodeError):
        return []


def save_presets(presets: list[dict[str, Any]]) -> None:
    presets_path().write_text(
        json.dumps({"presets": presets}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_last_session() -> dict[str, Any] | None:
    path = last_session_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_last_session(payload: dict[str, Any]) -> None:
    last_session_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def session_payload_from_gui(
    input_dir: str,
    output_dir: str,
    aspect: AspectMode,
    force_jpeg: bool,
    max_kb: str,
    quality: int,
    max_width: int,
    theme: str,
    selected_preset: str,
) -> dict[str, Any]:
    max_kb_int: int | None
    try:
        max_kb_int = int(max_kb.strip()) if max_kb.strip() else None
    except ValueError:
        max_kb_int = None
    return {
        "input": input_dir,
        "output": output_dir,
        "aspect": aspect,
        "force_jpeg": force_jpeg,
        "max_kb": max_kb_int,
        "quality": quality,
        "max_width": max_width,
        "theme": theme,
        "selected_preset": selected_preset,
    }


def apply_session_to_vars(session: dict[str, Any]) -> dict[str, Any]:
    """Valores para rellenar la GUI."""
    return {
        "input": session.get("input", ""),
        "output": session.get("output", ""),
        "aspect": session.get("aspect", "none"),
        "force_jpeg": bool(session.get("force_jpeg", False)),
        "max_kb": (
            str(session["max_kb"])
            if session.get("max_kb") is not None
            else ""
        ),
        "quality": int(session.get("quality", 80)),
        "max_width": int(session.get("max_width", 2000)),
        "theme": session.get("theme", "dark"),
        "selected_preset": session.get("selected_preset", ""),
    }
