"""締切カレンダーのサイト（index.html）と、スマホのカレンダーに登録できる .ics を作る。"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .dates import JST, WD

KINDS = ("懸賞", "ポイ活")
ICS_FILES = {"all": "すべて", "kensho": "懸賞", "poikatsu": "ポイ活"}


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s).astimezone(JST) if s else None


def active_entries(entries: list[dict], now: datetime) -> list[dict]:
    act = [e for e in entries if e.get("deadline") and _dt(e["deadline"]) > now]
    return sorted(act, key=lambda e: (e["deadline"], e.get("name", "")))


def _days_left(d: datetime, now: datetime) -> int:
    return (d.date() - now.astimezone(JST).date()).days


def _when_label(days: int) -> str:
    return "今日" if days == 0 else "明日" if days == 1 else f"あと{days}日"


def _wd_class(d: datetime) -> str:
    return {5: "sat", 6: "sun"}.get(d.weekday(), "")


def _e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _card(e: dict) -> str:
    kind = e.get("kind", "懸賞")
    dl = _dt(e["deadline"])
    label = e.get("deadline_label") or "締切"
    label_text = {"応募": "応募締切", "エントリー": "エントリー締切", "締切": "締切", "期間": "期間終了"}.get(label, "締切")
    facts = []
    if e.get("prize"):
        facts.append(f'<span class="fact-main">{_e(e["prize"])}</span>')
    if e.get("winners"):
        facts.append(f'<span class="fact-num">{int(e["winners"]):,}名</span>')
    if e.get("reward"):
        facts.append(f'<span class="fact-main">{_e(e["reward"])}</span>')
    period = ""
    if e.get("period_end"):
        pe = _dt(e["period_end"])
        period = f'<p class="period">対象期間は {pe.month}/{pe.day}({WD[pe.weekday()]}) {pe:%H:%M} まで</p>'
    tags = "".join(f"<li>{_e(t)}</li>" for t in e.get("tags", []))
    summary = f'<p class="summary">{_e(e["summary"])}</p>' if e.get("summary") else ""
    aff = ""
    if e.get("affiliate_url"):
        aff = (f'<a class="btn btn-pr" href="{_e(e["affiliate_url"])}" rel="sponsored nofollow noopener" '
               f'target="_blank"><span class="pr">PR</span>お得に申し込む</a>')
    return f"""
      <article class="card" data-kind="{_e(kind)}" data-deadline="{_e(e['deadline'])}">
        <div class="card-head">
          <span class="kind kind-{'k' if kind == '懸賞' else 'p'}">{_e(kind)}</span>
          <span class="due"><span class="due-label">{_e(label_text)}</span> <span class="due-time">{dl:%H:%M}</span></span>
        </div>
        <h3>{_e(e.get('name'))}</h3>
        {'<p class="facts">' + ''.join(facts) + '</p>' if facts else ''}
        {period}
        {summary}
        {'<ul class="tags">' + tags + '</ul>' if tags else ''}
        <div class="actions">
          <a class="btn" href="{_e(e.get('url'))}" rel="nofollow noopener" target="_blank">公式ページを見る</a>
          {aff}
        </div>
      </article>"""


STYLE = """
/* レイアウト：日めくりの日付ブロック（左）に、その日が締切のカードを並べる。スマホでは日付が上に来る */
:root {
  --bg: #f3f5f8; --surface: #ffffff; --ink: #1a2130; --muted: #586174; --line: #dce1e9;
  --shu: #c63a2f; --shu-soft: #fbe9e6; --kensho: #a63d64; --kensho-soft: #f8e8ef;
  --poikatsu: #18785a; --poikatsu-soft: #e3f3ec; --sat: #2360b5; --focus: #2360b5; --on-shu: #ffffff;
  --font-display: "Zen Kaku Gothic New", "Hiragino Sans", "Noto Sans JP", sans-serif;
  --font-body: "Zen Kaku Gothic New", "Hiragino Sans", "Noto Sans JP", sans-serif;
  --font-num: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11151c; --surface: #191e27; --ink: #e7eaf0; --muted: #9aa3b3; --line: #2a313d;
  --shu: #ff6d60; --shu-soft: #3a1f1d; --kensho: #e88fb0; --kensho-soft: #35202a;
  --poikatsu: #5fcfa5; --poikatsu-soft: #16302a; --sat: #82b1f2; --focus: #82b1f2; --on-shu: #2a0f0c; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #11151c; --surface: #191e27; --ink: #e7eaf0; --muted: #9aa3b3; --line: #2a313d;
  --shu: #ff6d60; --shu-soft: #3a1f1d; --kensho: #e88fb0; --kensho-soft: #35202a;
  --poikatsu: #5fcfa5; --poikatsu-soft: #16302a; --sat: #82b1f2; --focus: #82b1f2; --on-shu: #2a0f0c; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 15px; line-height: 1.7; }
.wrap { max-width: 760px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px)); }
header.site { padding-block: 28px 8px; display: grid; gap: 6px; }
.brand { display: flex; align-items: center; gap: 12px; }
.shime { flex: none; width: 44px; height: 44px; border: 2px solid var(--shu); color: var(--shu); border-radius: 50%;
  display: grid; place-items: center; font-family: var(--font-display); font-weight: 900; font-size: 24px; transform: rotate(-8deg); }
h1 { margin: 0; font-family: var(--font-display); font-weight: 900; font-size: 26px; letter-spacing: .02em; text-wrap: balance; }
.tagline { margin: 0; color: var(--muted); font-size: 14px; }
.stats { margin: 6px 0 0; color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
.stats b { color: var(--shu); font-family: var(--font-num); font-size: 18px; font-weight: 700; }
nav.filter { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--bg);
  padding-block: 10px; border-bottom: 1px solid var(--line); }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--bg); }
.seg { display: flex; gap: 6px; }
.seg button { font: inherit; font-size: 14px; font-weight: 700; padding: 6px 14px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: var(--surface); color: var(--muted); }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.seg button:focus-visible, .btn:focus-visible, .sub a:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
main { display: grid; gap: 28px; padding-block: 20px 8px; }
.day { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 14px; align-items: start; }
.leaf { position: sticky; top: calc(env(safe-area-inset-top, 0px) + 64px); text-align: center; background: var(--surface);
  border: 1px solid var(--line); border-top: 6px solid var(--ink); border-radius: 4px 4px 8px 8px; padding: 4px 0 6px; }
.leaf .mon { display: block; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.leaf .num { display: block; font-family: var(--font-num); font-weight: 700; font-size: 40px; line-height: 1; font-variant-numeric: tabular-nums; }
.leaf .wd { display: block; font-size: 13px; font-weight: 700; }
.leaf.sat .num, .leaf.sat .wd { color: var(--sat); }
.leaf.sun .num, .leaf.sun .wd { color: var(--shu); }
.leaf.today { border-top-color: var(--shu); }
.leaf .when { display: block; margin-top: 4px; font-size: 11px; font-weight: 700; color: var(--muted); }
.leaf.today .when { color: var(--shu); }
.cards { display: grid; gap: 12px; min-width: 0; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: grid; gap: 8px; min-width: 0; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.kind { font-size: 12px; font-weight: 700; padding: 1px 10px; border-radius: 999px; letter-spacing: .04em; }
.kind-k { color: var(--kensho); background: var(--kensho-soft); }
.kind-p { color: var(--poikatsu); background: var(--poikatsu-soft); }
.due { font-size: 13px; color: var(--muted); }
.due-time { font-family: var(--font-num); font-size: 18px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.today-group .due-time { color: var(--shu); }
.card h3 { margin: 0; font-size: 17px; line-height: 1.45; text-wrap: balance; overflow-wrap: anywhere; }
.facts { margin: 0; display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
.fact-main { font-weight: 700; }
.fact-num { font-family: var(--font-num); font-size: 18px; font-weight: 700; color: var(--kensho); }
.period { margin: 0; font-size: 13px; color: var(--muted); }
.summary { margin: 0; font-size: 14px; max-width: 62ch; }
.tags { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.tags li { font-size: 12px; color: var(--muted); border: 1px solid var(--line); border-radius: 4px; padding: 0 8px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 2px; }
.btn { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 700; text-decoration: none;
  padding: 7px 14px; border-radius: 8px; border: 1px solid var(--ink); color: var(--ink); background: transparent; }
.btn-pr { background: var(--shu); border-color: var(--shu); color: var(--on-shu); }
.pr { font-size: 10px; font-weight: 900; border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; letter-spacing: .06em; }
.empty { color: var(--muted); padding-block: 24px; }
.sub { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: grid; gap: 8px; }
.sub h2 { margin: 0; font-size: 15px; }
.sub p { margin: 0; font-size: 13px; color: var(--muted); }
.sub ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.sub a { font-size: 14px; font-weight: 700; color: var(--ink); }
footer.site { padding-block: 24px 40px; color: var(--muted); font-size: 12px; display: grid; gap: 4px; }
footer.site p { margin: 0; }
@media (max-width: 480px) {
  .day { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .leaf { position: static; display: flex; align-items: baseline; gap: 8px; text-align: left; padding: 4px 12px;
    border-top-width: 1px; border-left: 6px solid var(--ink); border-radius: 6px; }
  .leaf.today { border-left-color: var(--shu); }
  .leaf .num { font-size: 28px; }
  .leaf .when { margin: 0 0 0 auto; font-size: 12px; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto; } }
"""

SCRIPT = """
(function () {
  var KEY = "shimekiri-filter";
  var buttons = Array.prototype.slice.call(document.querySelectorAll(".seg button"));
  function apply(kind) {
    buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.kind === kind)); });
    var now = Date.now();
    document.querySelectorAll(".day").forEach(function (day) {
      var shown = 0;
      day.querySelectorAll(".card").forEach(function (c) {
        var ok = (kind === "all" || c.dataset.kind === kind) && Date.parse(c.dataset.deadline) > now;
        c.hidden = !ok; if (ok) shown++;
      });
      day.hidden = shown === 0;
    });
    var none = document.querySelectorAll(".day:not([hidden])").length === 0;
    var empty = document.getElementById("empty"); if (empty) empty.hidden = !none;
  }
  var saved = "all";
  try { saved = localStorage.getItem(KEY) || "all"; } catch (e) {}
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      apply(b.dataset.kind);
      try { localStorage.setItem(KEY, b.dataset.kind); } catch (e) {}
    });
  });
  apply(saved);
})();
"""


def render_html(entries: list[dict], now: datetime, standalone: bool = True, sample: bool = False) -> str:
    act = active_entries(entries, now)
    groups: dict[str, list[dict]] = {}
    for e in act:
        groups.setdefault(_dt(e["deadline"]).date().isoformat(), []).append(e)
    days_html = []
    for _, es in groups.items():
        d = _dt(es[0]["deadline"])
        left = _days_left(d, now)
        cls = " ".join(c for c in ["leaf", _wd_class(d), "today" if left == 0 else ""] if c)
        days_html.append(f"""
    <section class="day{' today-group' if left == 0 else ''}" aria-label="{d.month}月{d.day}日締切">
      <div class="{cls}"><span class="mon">{d.month}月</span><span class="num">{d.day}</span>
        <span class="wd">{WD[d.weekday()]}</span><span class="when">{_when_label(left)}</span></div>
      <div class="cards">{''.join(_card(e) for e in es)}
      </div>
    </section>""")
    n_today = len([e for e in act if _days_left(_dt(e["deadline"]), now) == 0])
    n_week = len([e for e in act if _days_left(_dt(e["deadline"]), now) < 7])
    base = config.SITE_URL.rstrip("/") + "/" if config.SITE_URL else ""
    webcal = base.replace("https://", "webcal://") if base.startswith("https://") else ""
    subs = "".join(
        f'<li><a href="{_e((webcal or "") + f"{k}.ics")}">{_e(v)}</a></li>' for k, v in ICS_FILES.items())
    sample_note = '<p class="tagline">（表示はサンプルです）</p>' if sample else ""
    body = f"""<title>{_e(config.SITE_TITLE)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="{_e(config.SITE_TAGLINE)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=Zen+Kaku+Gothic+New:wght@400;700;900&display=swap">
<style>{STYLE}</style>
<div class="wrap">
  <header class="site">
    <div class="brand"><span class="shime" aria-hidden="true">〆</span><h1>{_e(config.SITE_TITLE)}</h1></div>
    <p class="tagline">{_e(config.SITE_TAGLINE)}</p>
    {sample_note}
    <p class="stats">今日締切 <b>{n_today}</b> 件 ・ 7日以内 <b>{n_week}</b> 件 ・ 掲載中 <b>{len(act)}</b> 件</p>
  </header>
  <nav class="filter" aria-label="種類で絞り込む">
    <div class="seg">
      <button type="button" id="f-all" data-kind="all" aria-pressed="true">すべて</button>
      <button type="button" id="f-k" data-kind="懸賞" aria-pressed="false">懸賞</button>
      <button type="button" id="f-p" data-kind="ポイ活" aria-pressed="false">ポイ活</button>
    </div>
  </nav>
  <main>{''.join(days_html)}
    <p class="empty" id="empty" {'hidden' if act else ''}>いま掲載中の締切はありません。</p>
    <section class="sub" aria-labelledby="sub-h">
      <h2 id="sub-h">スマホのカレンダーに入れる</h2>
      <p>登録すると締切が自動で入り、前日と3時間前にスマホが通知します。種類ごとに選べます。</p>
      <ul>{subs}</ul>
    </section>
  </main>
  <footer class="site">
    <p>当サイトはアフィリエイト広告を利用しています。「PR」の付いたボタンは広告リンクです。</p>
    <p>掲載内容は各公式ページをもとにした個人のまとめです。応募条件や期間は変わることがあるため、必ず公式ページで確認してください。</p>
    <p>最終更新 {now.astimezone(JST):%Y年%-m月%-d日 %H:%M}</p>
  </footer>
</div>
<script>{SCRIPT}</script>
"""
    if not standalone:
        return body
    return ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n</head>\n<body>\n'
            + body + "</body>\n</html>\n")


# ---------- .ics ----------

def _ics_escape(s: str) -> str:
    return (str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> str:
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not out else 74  # 2行目以降は先頭の空白1バイト分を引く
        if len(cur) + len(b) > limit:
            out.append(cur.decode("utf-8"))
            cur = b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _utc(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render_ics(entries: list[dict], now: datetime, kind: str | None, calname: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//shimekiri-calendar//JA", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape(calname)}", "X-WR-TIMEZONE:Asia/Tokyo",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for e in sorted(entries, key=lambda x: x.get("deadline") or ""):
        if not e.get("deadline") or (kind and e.get("kind") != kind):
            continue
        dl = _dt(e["deadline"])
        if dl < now - timedelta(days=30):
            continue
        label = {"応募": "応募締切", "エントリー": "エントリー締切"}.get(e.get("deadline_label"), "締切")
        desc = "\n".join(x for x in [
            e.get("prize") and f"賞品：{e['prize']}" + (f"（{e['winners']}名）" if e.get("winners") else ""),
            e.get("reward") and f"還元：{e['reward']}",
            e.get("tags") and "条件：" + "、".join(e["tags"]),
            e.get("summary"),
            f"公式ページ：{e.get('url')}",
            "最新の条件は公式ページで確認してください",
        ] if x)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@shimekiri-calendar",
            f"DTSTAMP:{_utc(now)}",
            f"DTSTART:{_utc(dl - timedelta(minutes=30))}",
            f"DTEND:{_utc(dl)}",
            f"SUMMARY:{_ics_escape('〆 ' + e.get('name', '') + '（' + label + '）')}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"URL:{e.get('url', '')}",
            "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape('明日締切：' + e.get('name', ''))}", "END:VALARM",
            "BEGIN:VALARM", "TRIGGER:-PT3H", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape('まもなく締切：' + e.get('name', ''))}", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def build(entries: list[dict], now: datetime, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_html(entries, now), encoding="utf-8")
    kinds = {"all": None, "kensho": "懸賞", "poikatsu": "ポイ活"}
    for key, kind in kinds.items():
        name = f"{config.SITE_TITLE}（{ICS_FILES[key]}）"
        (out_dir / f"{key}.ics").write_text(render_ics(entries, now, kind, name), encoding="utf-8", newline="")
    public = [{k: e.get(k) for k in ("id", "kind", "name", "url", "deadline", "deadline_label", "prize",
                                      "winners", "reward", "tags", "summary")} for e in active_entries(entries, now)]
    (out_dir / "entries.json").write_text(json.dumps(public, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return out_dir / "index.html"
