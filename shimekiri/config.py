"""設定。多くは環境変数で上書きできる（README 参照）。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SHIMEKIRI_DATA_DIR", ROOT / "data"))
ENTRIES_DIR = DATA_DIR / "entries"
DRAFTS_DIR = DATA_DIR / "drafts"
STATE_PATH = DATA_DIR / "state.json"

SITE_TITLE = os.environ.get("SITE_TITLE", "しめきりカレンダー")
SITE_TAGLINE = os.environ.get("SITE_TAGLINE", "懸賞とポイ活の締切を、締切が近い順に")
SITE_URL = os.environ.get("SITE_URL", "")  # 例 https://<ユーザー名>.github.io/<リポジトリ名>/

USER_AGENT = os.environ.get("SHIMEKIRI_USER_AGENT", "shimekiri-calendar/0.1 (personal deadline notes)")

HASHTAGS = os.environ.get("SHIMEKIRI_HASHTAGS", "#懸賞 #ポイ活")
POST_SITE_LINK = os.environ.get("POST_SITE_LINK", "").lower() in ("1", "true", "yes")  # 朝の投稿にサイトURLを付ける（1件0.20ドル）
POST_ON_PUBLISH = os.environ.get("POST_ON_PUBLISH", "1").lower() in ("1", "true", "yes")

X_API_BASE = os.environ.get("X_API_BASE", "https://api.x.com")
X_API_KEY = os.environ.get("X_API_KEY", "")
X_API_SECRET = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

OWNER_ROLES = ("OWNER", "MEMBER", "COLLABORATOR")  # Issue・コメントを受け付ける相手


def x_keys_ready() -> bool:
    return all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET])
