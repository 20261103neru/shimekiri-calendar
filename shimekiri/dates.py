"""キャンペーンページの本文から「応募期間・エントリー期間・締切」を読み取る。

対応している書き方の例:
  応募期間：～11/1(日) 23:59                     （終わりだけ・年なし・スラッシュ）
  エントリー期間：2026/10/02(金) 00:00 〜 2026/11/12(木) 23:59
  対象期間：2026年10月13日(火)00:00 〜 2026年11月12日(木)23:59まで
  エントリー締切は、2026年11月12日(木)の23:59となります。
  2026年11月30日(月)23:59まで
年が書かれていないときは、曜日と照らし合わせて年を決める。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
WD = "月火水木金土日"


def _dt(p: str) -> str:
    return (
        rf"(?:(?P<{p}y>\d{{4}})\s*年\s*)?(?P<{p}m>\d{{1,2}})\s*月\s*(?P<{p}d>\d{{1,2}})\s*日"
        rf"(?:\s*\((?P<{p}w>[月火水木金土日])(?:・?祝)?\)|\s*\(祝\))?"
        rf"(?:\s*の?\s*(?P<{p}H>\d{{1,2}})\s*(?:時(?:\s*(?P<{p}M1>\d{{1,2}})\s*分)?|:(?P<{p}M2>\d{{2}})))?"
        r"(?:\s*\(JST\))?"
    )


_SEP = r"\s*(?:~|〜|-|−|―|‐|ー|から)\s*"
RANGE_RE = re.compile(_dt("s") + _SEP + _dt("e"))
SINGLE_RE = re.compile(_dt("s"))

ACTION_LABELS = ("エントリー", "応募", "締切")  # 「これまでに何かしないといけない」締切
_NOT_DEADLINE = r"発送|当選発表|発表|付与|お届け|配送|有効期限|利用期限|使用期限|開催日|放送|掲載日|更新"


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).replace("\r", "").replace("**", "")
    t = re.sub(r"[ \t ]+", " ", t)
    # 2026/10/02, 2026.10.2 → 2026年10月02日
    t = re.sub(r"(?<!\d)(\d{4})\s*[/.]\s*(\d{1,2})\s*[/.]\s*(\d{1,2})(?!\d)", r"\1年\2月\3日", t)
    # 11/1(日) → 11月1日(日)
    t = re.sub(r"(?<![\d/.])(\d{1,2})/(\d{1,2})(?=\s*\()", r"\1月\2日", t)
    # 〜11/30、11/30〜、11/30まで、11/30 23:59まで
    t = re.sub(r"([~〜]\s*)(\d{1,2})/(\d{1,2})(?![\d/])", r"\1\2月\3日", t)
    t = re.sub(r"(?<![\d/.])(\d{1,2})/(\d{1,2})(?=\s*(?:\d{1,2}:\d{2}\s*)?(?:[~〜]|まで))", r"\1月\2日", t)
    return t


def _year_for(m: int, d: int, wd: str | None, ref: date, not_before: date | None = None) -> int | None:
    """年が省略された日付の年を決める。曜日が書いてあればそれに合う年を優先"""
    cands = []
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            cand = date(y, m, d)
        except ValueError:
            continue
        if not_before and cand < not_before:
            continue
        if wd and WD[cand.weekday()] != wd:
            continue
        cands.append(cand)
    if not cands:
        return None
    # 基準日の少し前〜1年先に入るものの中で、基準日に一番近いもの
    in_range = [c for c in cands if -120 <= (c - ref).days <= 330] or cands
    return min(in_range, key=lambda c: abs((c - ref).days)).year


def _make(gd: dict, p: str, ref: date, default_hm: tuple[int, int],
          not_before: date | None = None) -> datetime | None:
    try:
        m, d = int(gd[f"{p}m"]), int(gd[f"{p}d"])
        y = int(gd[f"{p}y"]) if gd.get(f"{p}y") else _year_for(m, d, gd.get(f"{p}w"), ref, not_before)
        if y is None:
            return None
        if gd.get(f"{p}H") is None:
            hh, mm = default_hm
        else:
            hh, mm = int(gd[f"{p}H"]), int(gd.get(f"{p}M1") or gd.get(f"{p}M2") or 0)
        extra = 0
        if hh >= 24:
            hh, extra = hh - 24, 1
        return datetime(y, m, d, hh, mm, tzinfo=JST) + timedelta(days=extra)
    except (ValueError, TypeError, KeyError):
        return None


def _heading(lines: list[str], i: int) -> str:
    j, seen = i - 1, 0
    while j >= 0 and seen < 3:
        s = lines[j].strip()
        if s:
            seen += 1
            if len(s) <= 30 and "http" not in s and not SINGLE_RE.search(s) and not s.endswith("。"):
                return s
        j -= 1
    return ""


def _label(heading: str, prefix: str, suffix: str) -> str:
    tail = prefix[-16:]
    if re.search(_NOT_DEADLINE, tail + suffix[:8]):
        return "other"
    for text in (tail, f"{heading} {prefix[-40:]} {suffix[:15]}"):
        if "エントリー" in text:
            return "エントリー"
        if re.search(r"応募|受付|募集|申込|申し込み|投稿期間", text):
            return "応募"
        if re.search(r"締切|締め切り|〆切|終了", text):
            return "締切"
        if re.search(r"期間|キャンペーン|対象", text):
            return "期間"
    return "other"


def find_windows(text: str, ref: datetime) -> list[dict]:
    """[{label, start, end, line}] を返す（start は無いこともある）"""
    lines = normalize(text).split("\n")
    refd = ref.astimezone(JST).date()
    out: list[dict] = []
    for i, line in enumerate(lines):
        used: list[tuple[int, int]] = []
        for m in RANGE_RE.finditer(line):
            gd = m.groupdict()
            s = _make(gd, "s", refd, (0, 0))
            e = _make(gd, "e", s.date() if s else refd, (23, 59), not_before=s.date() if s else None)
            if not s or not e or e <= s:
                continue
            used.append(m.span())
            lab = _label(_heading(lines, i), line[: m.start()], line[m.end():])
            out.append({"label": lab, "start": s.isoformat(), "end": e.isoformat(), "line": line.strip()[:120]})
        for m in SINGLE_RE.finditer(line):
            if any(a <= m.start() < b for a, b in used):
                continue
            prefix, suffix = line[: m.start()], line[m.end():]
            is_end = (prefix.rstrip().endswith(("~", "〜")) or suffix.lstrip().startswith("まで")
                      or re.search(r"締切|締め切り|〆切|終了", prefix[-16:]))
            if not is_end:
                continue
            e = _make(m.groupdict(), "s", refd, (23, 59))
            if not e:
                continue
            lab = _label(_heading(lines, i), prefix.rstrip(" ~〜"), suffix)
            out.append({"label": lab, "start": None, "end": e.isoformat(), "line": line.strip()[:120]})
    return _dedupe(out)


def _dedupe(ws: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for w in ws:
        key = (w["label"], w["end"])
        if key not in seen or (seen[key]["start"] is None and w["start"]):
            seen[key] = w
    return list(seen.values())


def pick_deadline(windows: list[dict], now: datetime) -> tuple[dict | None, dict | None]:
    """(行動の締切, キャンペーン期間の終わり) を返す。過ぎたものは除く"""
    future = [w for w in windows if w["label"] != "other" and datetime.fromisoformat(w["end"]) > now]
    action = [w for w in future if w["label"] in ACTION_LABELS]
    period = [w for w in future if w["label"] == "期間"]
    dl = min(action, key=lambda w: w["end"]) if action else (max(period, key=lambda w: w["end"]) if period else None)
    pe = max(period, key=lambda w: w["end"]) if period else None
    if pe and dl and pe["end"] == dl["end"]:
        pe = None
    return dl, pe


def parse_user_deadline(s: str, now: datetime) -> datetime | None:
    """フォームに手で書かれた締切（2026-11-30 23:59 / 11/30 23:59 / 11月30日 など）"""
    s = s.strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = (int(m.group(4)), int(m.group(5))) if m.group(4) else (23, 59)
        try:
            return datetime(y, mo, d, hh, mm, tzinfo=JST)
        except ValueError:
            return None
    t = normalize(s)
    t = re.sub(r"^(\d{1,2})/(\d{1,2})", r"\1月\2日", t)
    m = SINGLE_RE.search(t)
    return _make(m.groupdict(), "s", now.astimezone(JST).date(), (23, 59)) if m else None
