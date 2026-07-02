from __future__ import annotations

import json
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


APP_ROOT = app_root()
BUNDLE_ROOT = bundle_root()
DEFAULT_STORAGE = APP_ROOT / "data" / "devices"
DEFAULT_PHOTOS = APP_ROOT / "data" / "photos"
DEFAULT_REPORTS = APP_ROOT / "Reports"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "checklist_config.json"

LOGO_CANDIDATES = [
    BUNDLE_ROOT / "logo.png",
    BUNDLE_ROOT / "Logo.png",
    BUNDLE_ROOT / "logo.jpg",
    BUNDLE_ROOT / "Logo.jpg",
    BUNDLE_ROOT / "logo.jpeg",
    BUNDLE_ROOT / "Logo.jpeg",
    APP_ROOT / "logo.spg",
    APP_ROOT / "Logo.spg",
    APP_ROOT / "logo.png",
    APP_ROOT / "Logo.png",
    APP_ROOT / "logo.jpg",
    APP_ROOT / "Logo.jpg",
    APP_ROOT / "logo.jpeg",
    APP_ROOT / "Logo.jpeg",
]

DEVICE_STATUSES = {
    "received": "#ffffff",
    "recived": "#ffffff",
    "tested": "#fff2b8",
    "dismantled": "#ffd7a8",
    "dismanteled": "#ffd7a8",
    "notFixable": "#f6b8b8",
    "fixed": "#cfeecf",
}
EDITABLE_DEVICE_STATUSES = ["received", "tested", "dismantled", "notFixable", "fixed"]
STATUS_ALIASES = {
    "recived": "received",
    "dismanteled": "dismantled",
}
CHECKLIST_START_BY_STATUS = {
    "received": "assessment",
    "tested": "disassembly",
    "dismantled": "assembly",
    "fixed": "Final test",
}
STATUS_FILTER_OPTIONS = ["All", *EDITABLE_DEVICE_STATUSES]


def resolve_config_path(config_path: Path) -> Path:
    candidates = [
        config_path,
        Path.cwd() / "checklist_config.json",
        Path(__file__).resolve().parent.parent / "checklist_config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return config_path


def normalize_device_status(status: str) -> str:
    return STATUS_ALIASES.get(status, status)


def load_checklist_config(config_path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Checklist config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    checklists = config.get("checklists")
    status_after_checklist = config.get("status_after_checklist", {})

    if not isinstance(checklists, dict) or not checklists:
        raise ValueError("checklist_config.json must contain a non-empty 'checklists' object")

    cleaned_checklists: dict[str, list[str]] = {}
    for category, items in checklists.items():
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Checklist category names must be non-empty strings")
        if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
            raise ValueError(f"Checklist '{category}' must contain a list of non-empty item names")
        cleaned_checklists[category.strip()] = [item.strip() for item in items]

    if not isinstance(status_after_checklist, dict):
        raise ValueError("'status_after_checklist' must be an object")

    cleaned_statuses = {
        category: normalize_device_status(str(status_after_checklist.get(category, "tested")).strip())
        for category in cleaned_checklists
    }
    return cleaned_checklists, cleaned_statuses
