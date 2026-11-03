"""data/entries/*.json（公開中）・data/drafts/*.json（下書き）・data/state.json（投稿記録）"""
from __future__ import annotations

import json
from pathlib import Path

from . import config


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_entries() -> list[dict]:
    if not config.ENTRIES_DIR.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(config.ENTRIES_DIR.glob("*.json"))]


def save_entry(entry: dict) -> None:
    _write(config.ENTRIES_DIR / f"{entry['id']}.json", entry)


def delete_entry(entry_id: str) -> bool:
    p = config.ENTRIES_DIR / f"{entry_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def load_draft(entry_id: str) -> dict | None:
    return _read(config.DRAFTS_DIR / f"{entry_id}.json")


def save_draft(draft: dict) -> None:
    _write(config.DRAFTS_DIR / f"{draft['id']}.json", draft)


def delete_draft(entry_id: str) -> None:
    p = config.DRAFTS_DIR / f"{entry_id}.json"
    if p.exists():
        p.unlink()


def load_state() -> dict:
    st = _read(config.STATE_PATH, {}) or {}
    st.setdefault("posted", {})
    return st


def save_state(state: dict) -> None:
    posted = state.get("posted", {})
    if len(posted) > 3000:
        for k in sorted(posted, key=posted.get)[:-3000]:
            posted.pop(k, None)
    _write(config.STATE_PATH, state)
