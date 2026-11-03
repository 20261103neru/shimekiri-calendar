"""登録フォーム（GitHub Issue）→ 下書き → あなたの「公開」コメントで掲載、までの流れ。"""
from __future__ import annotations

import re
from datetime import datetime

import requests

from . import config, hints, store
from .dates import JST, WD, find_windows, pick_deadline, parse_user_deadline
from .fetchpage import FetchRefused, fetch as fetch_page

KINDS = ("懸賞", "ポイ活")
FORM_MARKER = "### 公式ページのURL"
_FIELD_RULES = [  # 見出しに含まれる語 → 項目名（フォームの見出しを多少変えても動くように）
    ("URL", "url"), ("種類", "kind"), ("紹介", "summary"), ("キャンペーン名", "name"),
    ("締切", "deadline"), ("賞品", "prize"), ("条件", "conditions"), ("アフィリエイト", "affiliate_url"),
]


def parse_form(body: str) -> dict:
    form: dict[str, str] = {}
    for block in re.split(r"^###\s+", body or "", flags=re.M)[1:]:
        heading, _, value = block.partition("\n")
        value = value.strip()
        if value in ("_No response_", "None", "なし"):
            value = ""
        for word, key in _FIELD_RULES:
            if word in heading and key not in form:
                form[key] = value
                break
    return form


def _fmt(iso: str | None) -> str:
    if not iso:
        return "—"
    d = datetime.fromisoformat(iso).astimezone(JST)
    return f"{d.month}/{d.day}({WD[d.weekday()]}) {d:%H:%M}"


def build_draft(number: int, form: dict, now: datetime, fetch=fetch_page) -> dict:
    notes: list[str] = []
    url = form.get("url", "").strip()
    title, text = "", ""
    if url:
        try:
            title, text = fetch(url)
        except FetchRefused as ex:
            notes.append(f"ページを読みませんでした：{ex}。締切や賞品はフォームに書いてください。")
        except requests.RequestException as ex:
            notes.append(f"ページを開けませんでした（{type(ex).__name__}）。締切や賞品はフォームに書いてください。")
    else:
        notes.append("公式ページのURLがありません。")

    windows = find_windows(text, now) if text else []
    deadline, label, period_end, source = None, "締切", None, ""
    if form.get("deadline"):
        d = parse_user_deadline(form["deadline"], now)
        if d:
            deadline, source = d.isoformat(), "フォームの値"
        else:
            notes.append(f"締切「{form['deadline']}」を日付として読めませんでした。例：2026-11-30 23:59")
    dl, pe = pick_deadline(windows, now)
    if not deadline and dl:
        deadline, label, source = dl["end"], dl["label"], "自動読み取り"
    elif dl:
        label = dl["label"]
    if pe:
        period_end = pe["end"]
    if not deadline:
        notes.append("締切が見つかりませんでした。フォームの「締切」欄に書いてください。")
    elif datetime.fromisoformat(deadline) <= now:
        notes.append("締切がもう過ぎています。")

    kind = form.get("kind") if form.get("kind") in KINDS else hints.guess_kind(text)
    name = form.get("name") or hints.campaign_name(title) or "（名前未設定）"
    if kind == "ポイ活":
        prize, winners = "", None
        reward = form.get("prize") or hints.reward(text)
    else:
        prize, winners = form.get("prize") or hints.prize(text), hints.winners(text)
        reward = ""
    if form.get("conditions"):
        tags = [t.strip() for t in re.split(r"[、,，/／\n]", form["conditions"]) if t.strip()]
    else:
        tags = hints.tags(text)
    aff = form.get("affiliate_url", "").strip()
    if aff and not re.match(r"^https?://", aff):
        notes.append("アフィリエイトリンクが http(s):// で始まっていないので外しました。")
        aff = ""
    summary = form.get("summary", "").strip()
    if not summary:
        notes.append("「ひとこと紹介」が空です。自分の言葉で一言あると、読む人に伝わりやすく、ページの丸写しにもなりません。")
    if len(summary) > 140:
        summary = summary[:139] + "…"

    return {
        "id": f"i{number}", "issue": number, "kind": kind, "name": name, "url": url,
        "summary": summary, "prize": prize, "winners": winners, "reward": reward, "tags": tags[:6],
        "deadline": deadline, "deadline_label": label, "deadline_source": source, "period_end": period_end,
        "affiliate_url": aff or None, "windows": windows, "notes": notes, "checked_at": now.isoformat(),
        "ready": bool(url and deadline and datetime.fromisoformat(deadline) > now),
    }


def draft_comment(d: dict) -> str:
    label = {"応募": "応募締切", "エントリー": "エントリー締切", "期間": "期間終了"}.get(d["deadline_label"], "締切")
    prize = d["reward"] if d["kind"] == "ポイ活" else (d["prize"] + (f" ／ {d['winners']:,}名" if d["winners"] else ""))
    rows = [
        ("種類", d["kind"]), ("キャンペーン名", d["name"]),
        ("締切", f"{_fmt(d['deadline'])}（{label}・{d['deadline_source']}）" if d["deadline"] else "—"),
        ("対象期間の終わり", _fmt(d["period_end"])) if d["period_end"] else None,
        ("還元" if d["kind"] == "ポイ活" else "賞品", prize or "—"),
        ("条件", "、".join(d["tags"]) or "—"),
        ("ひとこと紹介", d["summary"] or "—"),
        ("広告リンク", "あり（PR表記つき）" if d["affiliate_url"] else "なし"),
    ]
    table = "\n".join(f"| {k} | {str(v).replace('|', '／')} |" for k, v in (r for r in rows if r))
    found = "\n".join(f"- {w['label']}：{_fmt(w['start']) + ' 〜 ' if w['start'] else '〜 '}{_fmt(w['end'])}"
                      for w in d["windows"]) or "- （見つかりませんでした）"
    notes = "\n".join(f"> 注意：{n}" for n in d["notes"])
    action = ("このままでよければ、このIssueに **公開** とコメントしてください。"
              if d["ready"] else "**このままでは公開できません。** 上の注意を直してから、もう一度保存してください。")
    return f"""**下書きを作りました**（まだ公開していません）

| 項目 | 内容 |
|---|---|
{table}

<details><summary>ページから見つけた日付</summary>

{found}
</details>

{notes}

{action}
直したいときは Issue を編集してください（フォームに書いた内容が、自動読み取りより優先されます）。
"""


class GitHub:
    def __init__(self, token: str, repo: str):
        self.base = f"https://api.github.com/repos/{repo}"
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def comment(self, number: int, body: str) -> None:
        requests.post(f"{self.base}/issues/{number}/comments", json={"body": body}, headers=self.h, timeout=20).raise_for_status()

    def close(self, number: int) -> None:
        requests.patch(f"{self.base}/issues/{number}", json={"state": "closed", "state_reason": "completed"},
                       headers=self.h, timeout=20).raise_for_status()


def handle(event_name: str, event: dict, gh, now: datetime, fetch=fetch_page) -> dict:
    """戻り値 {'changed': サイトを作り直す必要があるか, 'new_entry': 新しく公開したID}"""
    result = {"changed": False, "new_entry": ""}
    issue = event.get("issue") or {}
    if issue.get("pull_request") or FORM_MARKER not in (issue.get("body") or ""):
        return result
    number = issue["number"]
    form = parse_form(issue["body"])

    if event_name == "issues":
        if issue.get("author_association") not in config.OWNER_ROLES:
            return result
        if event.get("action") not in ("opened", "edited", "reopened"):
            return result
        d = build_draft(number, form, now, fetch)
        store.save_draft(d)
        gh.comment(number, draft_comment(d))
        return result

    if event_name == "issue_comment":
        c = event.get("comment") or {}
        if c.get("author_association") not in config.OWNER_ROLES:
            return result
        cmd = (c.get("body") or "").strip().splitlines()[0].strip() if (c.get("body") or "").strip() else ""
        if cmd == "公開":
            d = store.load_draft(f"i{number}") or build_draft(number, form, now, fetch)
            if not d.get("ready") or datetime.fromisoformat(d["deadline"]) <= now:
                gh.comment(number, "公開できませんでした。締切が無いか、もう過ぎています。Issue を編集して締切を直してください。")
                return result
            entry = {k: v for k, v in d.items() if k not in ("notes", "ready", "windows")}
            entry["published_at"] = now.isoformat()
            store.save_entry(entry)
            store.delete_draft(d["id"])
            gh.comment(number, f"公開しました（締切 {_fmt(entry['deadline'])}）。サイトとカレンダーは数分で更新されます。\n"
                               "取り下げるときは、このIssueに **取り下げ** とコメントしてください。")
            gh.close(number)
            return {"changed": True, "new_entry": entry["id"]}
        if cmd in ("取り下げ", "非公開"):
            gone = store.delete_entry(f"i{number}")
            gh.comment(number, "取り下げました。サイトとカレンダーは数分で更新されます。" if gone else "公開中のものはありませんでした。")
            return {"changed": gone, "new_entry": ""}
        if cmd == "再読み取り":
            d = build_draft(number, form, now, fetch)
            store.save_draft(d)
            gh.comment(number, draft_comment(d))
    return result
