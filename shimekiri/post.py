"""X への投稿文。既定ではリンクを入れない（URL付きは1件0.20ドル、なしは0.015ドル）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .dates import JST, WD
from .site import active_entries

MAX_WEIGHT = 280


def weighted_len(text: str) -> int:
    n = 0
    for ch in text:
        cp = ord(ch)
        n += 1 if (cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F or 0x2032 <= cp <= 0x2037) else 2
    return n


def md(d: datetime) -> str:
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def _d(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(JST)


def _short(s: str, n: int = 24) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _line(e: dict) -> str:
    extra = e.get("reward") or (f"{e['winners']:,}名" if e.get("winners") else "")
    return f"・[{e.get('kind')}]{_short(e.get('name', ''))}{' ' + extra if extra else ''} {_d(e['deadline']):%H:%M}まで"


def footer() -> str:
    parts = []
    if config.POST_SITE_LINK and config.SITE_URL:
        parts.append(f"一覧 {config.SITE_URL}")
    else:
        parts.append("一覧はプロフィールのリンクから")
    if config.HASHTAGS:
        parts.append(config.HASHTAGS)
    return "\n".join(parts)


def pack(header: str, lines: list[str]) -> list[str]:
    foot = footer()
    posts, cur = [], [header]
    for ln in lines:
        trial = "\n".join(cur + [ln] + ([foot] if not posts else []))
        if weighted_len(trial) > MAX_WEIGHT and len(cur) > 1:
            posts.append(cur)
            cur = ["（続き）", ln]
        else:
            cur.append(ln)
    posts.append(cur)
    return ["\n".join(p + ([foot] if i == 0 else [])) for i, p in enumerate(posts)]


def _day(now: datetime, offset: int) -> tuple[datetime, datetime]:
    d0 = (now.astimezone(JST) + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    return d0, d0 + timedelta(days=1)


def _between(entries, now, frm, to):
    return [e for e in active_entries(entries, now) if frm <= _d(e["deadline"]) < to]


def compose_morning(entries: list[dict], now: datetime) -> list[str]:
    t0, t1 = _day(now, 0)
    rows = _between(entries, now, max(t0, now), t1)
    return pack(f"【今日締切】{md(t0)}", [_line(e) for e in rows]) if rows else []


def compose_evening(entries: list[dict], now: datetime) -> list[str]:
    t0, t1 = _day(now, 0)
    m0, m1 = _day(now, 1)
    today, tomorrow = _between(entries, now, now, t1), _between(entries, now, m0, m1)
    if not today and not tomorrow:
        return []
    lines = []
    if today:
        lines += [f"▼今日 {md(t0)}"] + [_line(e) for e in today]
    if tomorrow:
        lines += [f"▼明日 {md(m0)}"] + [_line(e) for e in tomorrow]
    return pack("【締切リマインド】", lines)


def compose_new(e: dict) -> list[str]:
    dl = _d(e["deadline"])
    label = {"応募": "応募締切", "エントリー": "エントリー締切"}.get(e.get("deadline_label"), "締切")
    lines = [f"{label} {md(dl)}{dl:%H:%M}"]
    what = e.get("reward") or " ".join(x for x in [e.get("prize"), f"{e['winners']:,}名" if e.get("winners") else ""] if x)
    if what:
        lines.append(what)
    if e.get("tags"):
        lines.append("条件：" + "、".join(e["tags"][:3]))
    return pack(f"【新着・{e.get('kind')}】{_short(e.get('name', ''), 34)}", lines)
