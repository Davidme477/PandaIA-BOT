from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "PandaIA"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)).resolve()


def user_data_root() -> Path:
    override = os.environ.get("PANDAIA_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if not is_frozen():
        return PROJECT_ROOT
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return (Path(local) / APP_NAME).resolve()


@dataclass(frozen=True)
class AppPaths:
    root: Path
    config: Path
    cache: Path
    logs: Path
    temp: Path
    credentials: Path
    animations_custom: Path
    sounds_custom: Path

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def spotify_file(self) -> Path:
        return self.config / "spotify_local.json"

    @property
    def telegram_file(self) -> Path:
        return self.config / "telegram_local.json"


def get_paths() -> AppPaths:
    root = user_data_root()
    return AppPaths(root, root / "config", root / "cache", root / "logs", root / "temp",
                    root / "credentials", root / "animations_custom", root / "sounds_custom")


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def ensure_user_directories() -> AppPaths:
    paths = get_paths()
    for directory in (paths.config, paths.cache, paths.logs, paths.temp, paths.credentials,
                      paths.animations_custom, paths.sounds_custom):
        directory.mkdir(parents=True, exist_ok=True)
    (paths.cache / "gifts").mkdir(parents=True, exist_ok=True)
    return paths


def initialize_user_data(*, legacy_root: Path | None = None) -> dict[str, object]:
    """Create user storage and migrate only absent files; existing data is never replaced."""
    paths = ensure_user_directories()
    migrated: list[str] = []
    source_root = legacy_root
    if source_root is None and is_frozen():
        source_root = Path(sys.executable).resolve().parent
    if source_root:
        for name in ("settings.json", "spotify_local.json", "telegram_local.json"):
            source = source_root / "config" / name
            target = paths.config / name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
                migrated.append(name)
    if not paths.settings_file.exists():
        defaults = resource_path("resources", "defaults", "default_settings.json")
        if defaults.is_file():
            shutil.copy2(defaults, paths.settings_file)
        else:
            paths.settings_file.write_text(json.dumps({"dashboard": {}, "tts": {}}, indent=2) + "\n", encoding="utf-8")
    return {"root": str(paths.root), "migrated": migrated, "writable": os.access(paths.root, os.W_OK)}


def configure_model_caches() -> None:
    cache = ensure_user_directories().cache / "models"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(cache / "torch"))
