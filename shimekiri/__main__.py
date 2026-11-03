"""しめきりカレンダー（懸賞・ポイ活）

  python -m shimekiri intake                 # GitHub Actions 用：Issue とコメントを処理
  python -m shimekiri build --out public     # サイトと .ics を作る
  python -m shimekiri post morning|evening   # X に今日・明日の締切を投稿
  python -m shimekiri post new --entry i12   # 新しく公開したものを投稿
  python -m shimekiri add URL --kind 懸賞 --summary "..." [--publish]   # パソコンから手で登録
X のキーが未設定、または DRY_RUN=1 のときは投稿せず表示だけ。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from . import config, intake, post, site, store
from .dates import JST
from .xclient import post_thread


def _now(s: str | None) -> datetime:
    return datetime.fromisoformat(s).astimezone(JST) if s else datetime.now(JST)


def _output(**kv) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kv.items()]
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("[output] " + " ".join(lines))


def cmd_intake(a) -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    gh = intake.GitHub(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    r = intake.handle(os.environ.get("GITHUB_EVENT_NAME", ""), event, gh, _now(a.now))
    _output(changed=str(r["changed"]).lower(), new_entry=r["new_entry"])


def cmd_build(a) -> None:
    p = site.build(store.load_entries(), _now(a.now), Path(a.out))
    print(f"[build] {p}")


def cmd_post(a) -> None:
    now = _now(a.now)
    dry = a.dry_run or config.DRY_RUN or not config.x_keys_ready()
    entries = store.load_entries()
    state = store.load_state()
    if a.mode == "new":
        e = next((x for x in entries if x["id"] == a.entry), None)
        key = f"new|{a.entry}"
        if not e or key in state["posted"] or not config.POST_ON_PUBLISH:
            print("[skip] new")
            return
        texts = post.compose_new(e)
    else:
        key = f"{a.mode}|{now:%Y-%m-%d}"
        if key in state["posted"]:
            print(f"[skip] {key} は投稿済み")
            return
        texts = (post.compose_morning if a.mode == "morning" else post.compose_evening)(entries, now)
        if not texts:
            print(f"[skip] {a.mode}: 該当なし")
            return
    post_thread(texts, dry)
    if not dry:
        state["posted"][key] = now.isoformat()
        store.save_state(state)


def cmd_add(a) -> None:
    now = _now(a.now)
    n = max([int(e["id"][1:]) for e in store.load_entries() if e["id"][1:].isdigit()] + [900000]) + 1
    form = {"url": a.url, "kind": a.kind or "", "summary": a.summary or "", "name": a.name or "",
            "deadline": a.deadline or "", "prize": a.prize or "", "conditions": a.conditions or "",
            "affiliate_url": a.affiliate or ""}
    d = intake.build_draft(n, form, now)
    print(intake.draft_comment(d))
    if a.publish:
        if not d["ready"]:
            sys.exit("公開できません（締切が無いか過ぎています）")
        entry = {k: v for k, v in d.items() if k not in ("notes", "ready", "windows")}
        entry["published_at"] = now.isoformat()
        store.save_entry(entry)
        print(f"[add] 公開しました {entry['id']}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m shimekiri", description="しめきりカレンダー")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("intake"); s.add_argument("--now"); s.set_defaults(func=cmd_intake)
    s = sub.add_parser("build"); s.add_argument("--out", default="public"); s.add_argument("--now"); s.set_defaults(func=cmd_build)
    s = sub.add_parser("post"); s.add_argument("mode", choices=["morning", "evening", "new"])
    s.add_argument("--entry", default=""); s.add_argument("--dry-run", action="store_true"); s.add_argument("--now")
    s.set_defaults(func=cmd_post)
    s = sub.add_parser("add"); s.add_argument("url")
    for opt in ("kind", "summary", "name", "deadline", "prize", "conditions", "affiliate", "now"):
        s.add_argument(f"--{opt}")
    s.add_argument("--publish", action="store_true"); s.set_defaults(func=cmd_add)
    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
