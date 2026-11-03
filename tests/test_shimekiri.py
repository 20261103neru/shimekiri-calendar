"""python -m unittest discover -s tests で実行（ネットワークは使わない）"""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shimekiri import config, hints, intake, post, site, store  # noqa: E402
from shimekiri.dates import JST, find_windows, pick_deadline, parse_user_deadline  # noqa: E402
from shimekiri.fetchpage import FetchRefused, html_to_text  # noqa: E402
from shimekiri.xclient import oauth1_header  # noqa: E402


def J(s):
    return datetime.fromisoformat(s).astimezone(JST)


# 実際のキャンペーンページにあった書き方（日付・条件の行だけ）
KENSHO_PAGE = """<html><head><title>『秋のココロとカラダ整いSPECIAL!』 プレゼントキャンペーン！ | 公募情報</title></head>
<body><header>メニュー 2026/01/01 〜 2026/12/31</header><main>
<p>JRE POINT 10,000ptが 抽選で30名様に当たる!!</p>
<p>2STEPで応募完了！ 1. @example をフォロー 2.この投稿をリポスト</p>
<p>応募期間：～11/1(日) 23:59</p><p>当選発表：2026年11月20日(金)</p></main></body></html>"""

POIKATSU_PAGE = """<html><head><meta property="og:title" content="【要エントリー】対象のスーパーマーケット限定！10%ポイント還元キャンペーン | ショッピングモール"></head>
<body><main>
<p>エントリー期間: 2026/10/02(金) 00:00 〜 2026/11/12(木) 23:59</p>
<p>キャンペーン期間: 2026/10/13(火) 00:00 〜 2026/11/30(月) 23:59</p>
<p>ご利用金額の10％相当分（上限2,000ポイント）のポイントを後日プレゼント！</p>
<p>期間中にエントリーのうえ対象店舗にて、対象カードでクレジット払いいただくと、</p>
<p>エントリー締切は、2026年11月12日(木)の23:59となります。</p>
<p>ポイント付与時期：2027年1月下旬</p></main></body></html>"""


def form_body(**kw):
    fields = [
        ("公式ページのURL", kw.get("url", "https://example.com/campaign")),
        ("種類", kw.get("kind", "懸賞")),
        ("ひとこと紹介（自分の言葉で）", kw.get("summary", "_No response_")),
        ("キャンペーン名（空ならページから自動）", kw.get("name", "_No response_")),
        ("締切（空なら自動で読み取り）", kw.get("deadline", "_No response_")),
        ("賞品・還元内容（空なら自動で候補）", kw.get("prize", "_No response_")),
        ("応募・参加の条件（空なら自動で候補）", kw.get("conditions", "_No response_")),
        ("アフィリエイトリンク（任意）", kw.get("affiliate", "_No response_")),
    ]
    return "\n\n".join(f"### {k}\n\n{v}" for k, v in fields)


class FakeGH:
    def __init__(self):
        self.comments, self.closed = [], []

    def comment(self, n, body):
        self.comments.append((n, body))

    def close(self, n):
        self.closed.append(n)


class TestDates(unittest.TestCase):
    def test_end_only_slash_no_year(self):
        _, text = html_to_text(KENSHO_PAGE)
        ws = find_windows(text, J("2026-10-28T10:00+09:00"))
        dl, _ = pick_deadline(ws, J("2026-10-28T10:00+09:00"))
        self.assertEqual((dl["label"], dl["end"]), ("応募", "2026-11-01T23:59:00+09:00"))
        self.assertTrue(all("2026-12-31" not in w["end"] for w in ws))  # ヘッダーの日付は読まない
        self.assertTrue(all("11-20" not in w["end"] for w in ws if w["label"] != "other"))  # 当選発表は締切ではない

    def test_entry_deadline_before_period_end(self):
        _, text = html_to_text(POIKATSU_PAGE)
        now = J("2026-11-03T10:00+09:00")
        dl, pe = pick_deadline(find_windows(text, now), now)
        self.assertEqual((dl["label"], dl["end"]), ("エントリー", "2026-11-12T23:59:00+09:00"))
        self.assertEqual(pe["end"], "2026-11-30T23:59:00+09:00")

    def test_year_from_weekday(self):
        ws = find_windows("応募期間：12/20(日)～1/10(日)", J("2026-12-01T00:00+09:00"))
        self.assertEqual((ws[0]["start"], ws[0]["end"]), ("2026-12-20T00:00:00+09:00", "2027-01-10T23:59:00+09:00"))

    def test_user_deadline(self):
        now = J("2026-11-03T10:00+09:00")
        self.assertEqual(parse_user_deadline("2026-11-30 23:59", now).isoformat(), "2026-11-30T23:59:00+09:00")
        self.assertEqual(parse_user_deadline("11/30 18:00", now).isoformat(), "2026-11-30T18:00:00+09:00")
        self.assertEqual(parse_user_deadline("12月1日", now).isoformat(), "2026-12-01T23:59:00+09:00")
        self.assertIsNone(parse_user_deadline("来週", now))


class TestHints(unittest.TestCase):
    def test_kensho(self):
        _, t = html_to_text(KENSHO_PAGE)
        self.assertEqual(hints.winners(t), 30)
        self.assertEqual(hints.prize(t), "JRE POINT 10,000pt")
        self.assertIn("Xでフォロー＆リポスト", hints.tags(t))
        self.assertEqual(hints.guess_kind(t), "懸賞")

    def test_poikatsu(self):
        title, t = html_to_text(POIKATSU_PAGE)
        self.assertEqual(hints.reward(t), "10%還元（上限2,000ポイント）")
        self.assertEqual(hints.campaign_name(title), "対象のスーパーマーケット限定!10%ポイント還元キャンペーン")
        self.assertEqual(hints.tags(t), ["要エントリー", "対象の支払い方法"])
        self.assertEqual(hints.guess_kind(t), "ポイ活")


class DataDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(config, "ENTRIES_DIR", d / "entries"),
                        mock.patch.object(config, "DRAFTS_DIR", d / "drafts"),
                        mock.patch.object(config, "STATE_PATH", d / "state.json")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()


class TestIntake(DataDirTest):
    def issue_event(self, body, action="opened", assoc="OWNER"):
        return {"action": action, "issue": {"number": 12, "body": body, "author_association": assoc}}

    def comment_event(self, body, text, assoc="OWNER"):
        return {"action": "created", "issue": {"number": 12, "body": body, "author_association": "OWNER"},
                "comment": {"body": text, "author_association": assoc}}

    def test_parse_form(self):
        f = intake.parse_form(form_body(summary="フォローとリポストで応募", kind="ポイ活"))
        self.assertEqual(f["kind"], "ポイ活")
        self.assertEqual(f["summary"], "フォローとリポストで応募")
        self.assertEqual(f["deadline"], "")

    def test_flow_draft_publish_withdraw(self):
        gh, now = FakeGH(), J("2026-10-28T10:00+09:00")
        fetch = lambda url: html_to_text(KENSHO_PAGE)  # noqa: E731
        body = form_body(summary="1万ptが30名。フォローとリポストだけ")
        r = intake.handle("issues", self.issue_event(body), gh, now, fetch)
        self.assertFalse(r["changed"])
        self.assertIn("11/1(日) 23:59（応募締切・自動読み取り）", gh.comments[-1][1])
        self.assertIn("**公開** とコメント", gh.comments[-1][1])
        # 他人のコメントは無視
        intake.handle("issue_comment", self.comment_event(body, "公開", assoc="NONE"), gh, now, fetch)
        self.assertEqual(store.load_entries(), [])
        # あなたの「公開」で掲載
        r = intake.handle("issue_comment", self.comment_event(body, "公開"), gh, now, fetch)
        self.assertEqual(r, {"changed": True, "new_entry": "i12"})
        e = store.load_entries()[0]
        self.assertEqual((e["name"], e["winners"], e["prize"]),
                         ("『秋のココロとカラダ整いSPECIAL!』 プレゼントキャンペーン", 30, "JRE POINT 10,000pt"))
        self.assertNotIn("windows", e)
        self.assertEqual(gh.closed, [12])
        r = intake.handle("issue_comment", self.comment_event(body, "取り下げ"), gh, now, fetch)
        self.assertTrue(r["changed"])
        self.assertEqual(store.load_entries(), [])

    def test_others_issue_ignored(self):
        gh = FakeGH()
        intake.handle("issues", self.issue_event(form_body(), assoc="NONE"), gh, J("2026-10-28T10:00+09:00"),
                      lambda u: html_to_text(KENSHO_PAGE))
        self.assertEqual(gh.comments, [])

    def test_robots_refused_uses_form_values(self):
        def refuse(url):
            raise FetchRefused("このサイトは自動での読み取りを禁止しています（robots.txt）")
        gh, now = FakeGH(), J("2026-11-03T10:00+09:00")
        body = form_body(deadline="2026-11-30 23:59", name="テスト懸賞", prize="ギフト券1万円")
        intake.handle("issues", self.issue_event(body), gh, now, refuse)
        msg = gh.comments[-1][1]
        self.assertIn("ページを読みませんでした", msg)
        self.assertIn("11/30(月) 23:59（締切・フォームの値）", msg)
        self.assertTrue(store.load_draft("i12")["ready"])

    def test_cannot_publish_without_deadline(self):
        gh, now = FakeGH(), J("2026-11-03T10:00+09:00")
        body = form_body()
        intake.handle("issues", self.issue_event(body), gh, now, lambda u: ("タイトル", "本文に日付なし"))
        r = intake.handle("issue_comment", self.comment_event(body, "公開"), gh, now, lambda u: ("タイトル", "本文"))
        self.assertFalse(r["changed"])
        self.assertIn("公開できませんでした", gh.comments[-1][1])


def sample_entries():
    return [
        {"id": "i1", "kind": "懸賞", "name": "今日締切の懸賞", "url": "https://example.com/1",
         "deadline": "2026-11-03T23:59:00+09:00", "deadline_label": "応募", "prize": "ギフト券", "winners": 100,
         "tags": ["Xでフォロー＆リポスト"], "summary": "フォローとリポストだけ"},
        {"id": "i2", "kind": "ポイ活", "name": "10%還元", "url": "https://example.com/2",
         "deadline": "2026-11-04T23:59:00+09:00", "deadline_label": "エントリー", "reward": "10%還元（上限2,000ポイント）",
         "tags": ["要エントリー"], "affiliate_url": "https://example.com/aff", "period_end": "2026-11-30T23:59:00+09:00"},
        {"id": "i3", "kind": "懸賞", "name": "終わった懸賞", "url": "https://example.com/3",
         "deadline": "2026-11-01T23:59:00+09:00", "deadline_label": "応募"},
    ]


class TestSite(unittest.TestCase):
    def test_html(self):
        h = site.render_html(sample_entries(), J("2026-11-03T08:00+09:00"))
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertIn("今日締切の懸賞", h)
        self.assertNotIn("終わった懸賞", h)
        self.assertEqual(h.count('class="pr"'), 1)  # 広告リンクがある1件だけ PR 表記
        self.assertIn('rel="sponsored nofollow noopener"', h)
        self.assertIn("アフィリエイト広告を利用しています", h)
        frag = site.render_html(sample_entries(), J("2026-11-03T08:00+09:00"), standalone=False)
        self.assertTrue(frag.startswith("<title>"))

    def test_ics(self):
        ics = site.render_ics(sample_entries(), J("2026-11-03T08:00+09:00"), "懸賞", "テスト")
        self.assertIn("SUMMARY:〆 今日締切の懸賞（応募締切）", ics)
        self.assertNotIn("10%還元", ics)  # 懸賞のカレンダーにポイ活は入らない
        self.assertIn("TRIGGER:-P1D", ics)
        for line in ics.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_build_files(self):
        with tempfile.TemporaryDirectory() as d:
            site.build(sample_entries(), J("2026-11-03T08:00+09:00"), Path(d))
            names = sorted(p.name for p in Path(d).iterdir())
            self.assertEqual(names, [".nojekyll", "all.ics", "entries.json", "index.html", "kensho.ics", "poikatsu.ics"])


class TestPost(unittest.TestCase):
    def test_morning_evening_new(self):
        es, now = sample_entries(), J("2026-11-03T07:10+09:00")
        m = post.compose_morning(es, now)
        self.assertIn("【今日締切】11/3(火)", m[0])
        self.assertIn("・[懸賞]今日締切の懸賞 100名 23:59まで", m[0])
        self.assertNotIn("http", m[0])
        ev = post.compose_evening(es, J("2026-11-03T17:40+09:00"))
        self.assertIn("▼明日 11/4(水)", ev[0])
        n = post.compose_new(es[1])
        self.assertIn("【新着・ポイ活】10%還元", n[0])
        for t in m + ev + n:
            self.assertLessEqual(post.weighted_len(t), 280)


class TestOAuth(unittest.TestCase):
    def test_signature(self):
        h = oauth1_header(
            "POST", "https://api.twitter.com/1.1/statuses/update.json",
            "xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
            "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
            params={"status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true"},
            nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp=1318622958)
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', h)


if __name__ == "__main__":
    unittest.main()


class TestRealPageFixes(unittest.TestCase):
    def test_name_with_fullwidth_bar_no_spaces(self):
        self.assertEqual(
            hints.campaign_name("【要エントリー】対象のスーパーマーケット限定！10%ポイント還元キャンペーン｜ららぽーとTOKYO-BAY"),
            "対象のスーパーマーケット限定!10%ポイント還元キャンペーン")

    def test_line_share_button_is_not_a_condition(self):
        t = ("エントリーのうえ対象カードで払うと10%還元\nLINE友だち追加はこちら\n"
             "前へ 三井ショッピングパークポイントLINE公式アカウント友だちプレゼントキャンペーン")
        self.assertNotIn("LINE友だち追加", hints.tags(t))
        self.assertIn("LINE友だち追加", hints.tags("応募方法：公式LINEを友だち追加して、アンケートに回答"))
