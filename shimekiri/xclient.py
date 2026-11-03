"""X API v2 への投稿（OAuth 1.0a ユーザーコンテキスト）。推し活botと同じもの。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

import requests

from . import config


def _pct(s) -> str:
    return urllib.parse.quote(str(s), safe="-._~")


def oauth1_header(method: str, url: str, consumer_key: str, consumer_secret: str,
                  token: str, token_secret: str, params: dict | None = None,
                  nonce: str | None = None, timestamp: int | None = None) -> str:
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    # JSON ボディは署名対象に含めない（クエリ・フォームのパラメータのみ）
    pairs = sorted((_pct(k), _pct(v)) for k, v in {**(params or {}), **oauth}.items())
    param_str = "&".join(f"{k}={v}" for k, v in pairs)
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


class XError(RuntimeError):
    pass


def post_tweet(text: str, reply_to: str | None = None) -> str:
    url = f"{config.X_API_BASE}/2/tweets"
    body: dict = {"text": text}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}
    auth = oauth1_header("POST", url, config.X_API_KEY, config.X_API_SECRET,
                         config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET)
    r = requests.post(url, json=body, headers={"Authorization": auth}, timeout=30)
    if r.status_code >= 300:
        raise XError(f"X API {r.status_code}: {r.text[:300]}")
    return r.json()["data"]["id"]


def post_thread(texts: list[str], dry_run: bool, log=print) -> list[str]:
    ids: list[str] = []
    for i, t in enumerate(texts):
        if dry_run:
            log(f"----- [ドライラン] 投稿 {i + 1}/{len(texts)} -----\n{t}")
            ids.append(f"dry-{i}")
            continue
        tid = post_tweet(t, reply_to=ids[-1] if ids else None)
        log(f"[posted] {tid}")
        ids.append(tid)
        time.sleep(2)
    return ids
