"""あなたが登録したURLのページ1枚だけを読む。robots.txt で禁止されていれば読まない。"""
from __future__ import annotations

import re
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import config


class FetchRefused(Exception):
    pass


def robots_allows(url: str) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = requests.get(robots_url, headers={"User-Agent": config.USER_AGENT}, timeout=10)
    except requests.RequestException:
        return True  # robots.txt が取れないときは通常のブラウザ閲覧と同じ扱い
    if r.status_code >= 400:
        return True
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(config.USER_AGENT, url)


def html_to_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"]
    elif soup.title and soup.title.string:
        title = soup.title.string
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
        t.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    for br in root.find_all("br"):
        br.replace_with("\n")
    text = root.get_text("\n")
    return title.strip(), re.sub(r"\n\s*\n+", "\n\n", text)


def fetch(url: str) -> tuple[str, str]:
    if not re.match(r"^https?://", url):
        raise FetchRefused("URL は http:// か https:// で始めてください")
    if not robots_allows(url):
        raise FetchRefused("このサイトは自動での読み取りを禁止しています（robots.txt）")
    r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=20)
    r.raise_for_status()
    if len(r.content) > 3_000_000:
        raise FetchRefused("ページが大きすぎます")
    r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
    return html_to_text(r.text)
