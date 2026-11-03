"""キャンペーン名・賞品・当選人数・還元率・応募条件の「候補」を本文から拾う。
あくまで候補で、最終的にはあなたがフォームで直せる（フォームの値が優先）。"""
from __future__ import annotations

import re

from .dates import normalize


def campaign_name(title: str) -> str:
    t = normalize(title).strip()
    t = re.split(r"\s+[|｜]\s+|\s+[-–—]\s+(?=[^-–—]+$)", t)[0]  # 「… | サイト名」「… - サイト名」を落とす
    t = re.sub(r"^(【[^】]*】\s*)+", "", t).strip(" !！")
    return t[:40]


def winners(text: str) -> int | None:
    t = normalize(text)
    m = re.search(r"抽選で\s*(?:合計|計|総計|総勢)?\s*([\d,]+)\s*名", t) or re.search(r"([\d,]+)\s*名様", t)
    return int(m.group(1).replace(",", "")) if m else None


def prize(text: str) -> str:
    t = normalize(text)
    for line in t.split("\n"):
        m = re.search(r"([^\n、。!？?]{2,30}?)\s*(?:が|を)\s*(?:抽選で|合計|計|総勢)", line)
        if m:
            return m.group(1).strip(" 「」『』:・")
        m = re.search(r"抽選で[\d,]+\s*名様?に\s*([^\n、。!]{2,30}?)\s*を?\s*プレゼント", line)
        if m:
            return m.group(1).strip(" 「」『』")
    return ""


def reward(text: str) -> str:
    """ポイ活向け：還元率と上限（例「10%還元（上限2,000ポイント）」）"""
    t = normalize(text)
    rate = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:相当|分|の)?[^\n]{0,15}?(?:還元|ポイント|戻|キャッシュバック|プレゼント|付与|OFF|オフ)", t)
    cap = (re.search(r"上限\s*[::]?\s*([\d,]+)\s*(ポイント|pt|P|円)", t)
           or re.search(r"最大\s*([\d,]+)\s*(ポイント|pt|P|円)", t))
    parts = []
    if rate:
        parts.append(f"{rate.group(1)}%還元")
    if cap:
        parts.append(f"（上限{cap.group(1)}{cap.group(2)}）" if rate else f"最大{cap.group(1)}{cap.group(2)}")
    return "".join(parts)


_TAG_RULES = [
    ("Xでフォロー＆リポスト", lambda t: "フォロー" in t and re.search(r"リポスト|RT|リツイート", t)),
    ("Instagramでフォロー", lambda t: "Instagram" in t and "フォロー" in t),
    ("LINE友だち追加", lambda t: "LINE" in t and re.search(r"友だち|友達", t)),
    ("要エントリー", lambda t: "エントリー" in t),
    ("レシート応募", lambda t: "レシート" in t),
    ("購入が条件", lambda t: re.search(r"ご購入|購入の上|購入された|購入いただ", t)),
    ("対象の支払い方法", lambda t: re.search(r"クレジット払い|カード払い|決済で|でお支払い", t)),
    ("アンケート回答", lambda t: "アンケート" in t),
    ("ハガキ応募", lambda t: re.search(r"ハガキ|はがき", t)),
    ("会員登録が必要", lambda t: "会員登録" in t),
]


def tags(text: str) -> list[str]:
    t = normalize(text)
    return [name for name, rule in _TAG_RULES if rule(t)]


def guess_kind(text: str) -> str:
    t = normalize(text)
    if re.search(r"\d+(?:\.\d+)?\s*%\s*(?:相当|分)?[^\n]{0,10}?還元|キャッシュバック|エントリー", t):
        return "ポイ活"
    return "懸賞"
