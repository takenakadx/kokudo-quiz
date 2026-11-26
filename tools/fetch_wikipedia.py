#!/usr/bin/env python3
"""
各国道のWikipedia記事の書き出し部分を取ってきて data-raw/wiki-extracts.json に置く。

豆知識（fact）を書くための下調べ用。生データのリレーションには `wikipedia` タグが
入っている（458路線中456本）ので、記事名を探す手間は要らない。取ってきた本文は
そのまま配信せず、読んで1〜2文の豆知識を書き起こすのに使う（issue #10）。

使い方:
  python3 tools/fetch_wikipedia.py            # 未取得の路線を全部
  python3 tools/fetch_wikipedia.py 101 102    # 番号を指定する
  python3 tools/fetch_wikipedia.py --list     # 対象を表示するだけ
  python3 tools/fetch_wikipedia.py --dry-run  # 投げるURLを表示するだけ

オプション:
  --chars N   1記事あたりの文字数（既定1200。概要の節まで入る長さ）
  --batch N   1リクエストあたりの記事数（既定50。APIの上限）
  --sleep S   リクエスト間の待ち時間・秒（既定2）
  --out F     出力先（既定 data-raw/wiki-extracts.json、gitには入れない）

Wikimedia のAPIは、素っ気ないUser-Agentだと429で断られる。名前と連絡の手段を
書いたUser-Agentを送ること（https://meta.wikimedia.org/wiki/User-Agent_policy）。
本文はCC BY-SAなので、文章をそのまま使うときは出典とライセンスの表示が要る。
"""
import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
RAW_DIR = os.path.join(ROOT, "data-raw")
OUT_FILE = os.path.join(RAW_DIR, "wiki-extracts.json")

API = "https://ja.wikipedia.org/w/api.php"
UA = "kokudo-quiz-dataset/1.0 (static quiz app; contact via repository issues)"
SIDE_RE = re.compile(r"(旧道|支線|バイパス|旧線|廃道|延伸|事業)")


def article_title(route_id):
    """その路線のWikipedia記事名。タグが無ければ「国道N号」を使う。"""
    f = os.path.join(RAW_DIR, "%d.geojson" % route_id)
    if not os.path.exists(f):
        return None
    doc = json.load(open(f, encoding="utf-8"))
    props = [x.get("properties") or {} for x in doc.get("features", [])]
    main = [q for q in props if not SIDE_RE.search(q.get("name", "") or "")] or props
    for q in main:
        w = q.get("wikipedia")
        # 日本語版以外を指すタグもある（国道326号は en: を指している）。
        # その場合はタグを使わず「国道N号」で引く
        if w and w.startswith("ja:"):
            return w[3:]
    return "国道%d号" % route_id


def fetch(url, tries=5):
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 20 * attempt
            print("    混雑中(HTTP %d)。%d秒待って再試行(%d/%d)"
                  % (e.code, wait, attempt, tries - 1), flush=True)
            time.sleep(wait)
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as e:
            if attempt == tries:
                raise
            print("    接続に失敗(%s)。%d秒待って再試行(%d/%d)"
                  % (e, 10 * attempt, attempt, tries - 1), flush=True)
            time.sleep(10 * attempt)
    raise RuntimeError("unreachable")


def build_url(titles):
    """記事の原文(wikitext)をまとめて取るURL。

    prop=extracts は本文を整形して返してくれるが、導入部より先を取ろうとすると
    1リクエストにつき1記事しか返さない。豆知識の種は「概要」の節にあることが
    多いので、原文を50記事ずつ取って自分で整形する。リクエスト数も減る。
    """
    params = {
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "redirects": "1", "format": "json",
        "formatversion": "2", "titles": "|".join(titles),
    }
    return API + "?" + urllib.parse.urlencode(params)


def strip_braces(text):
    """{{テンプレート}} を入れ子ごと落とす。"""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i) and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


DROP_LINK = ("ファイル:", "File:", "Image:", "画像:", "Category:", "カテゴリ:")


def strip_links(text):
    """[[リンク]] を外す。画像は入れ子の [[...]] を含むので、対応する ]] を数えて消す。"""
    out, i = [], 0
    while i < len(text):
        if text.startswith("[[", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                if text.startswith("[[", j):
                    depth += 1
                    j += 2
                elif text.startswith("]]", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            inner = text[i + 2:j - 2]
            if not inner.startswith(DROP_LINK):
                out.append(strip_links(inner.split("|")[-1]))
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def strip_wikitext(text):
    """原文から記号を落として、読める日本語にする。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref.*?</ref>", "", text, flags=re.S)
    text = strip_braces(text)
    text = strip_links(text)
    text = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^[*#:;]+\s*", "", text, flags=re.M)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# 豆知識の種がある節。路線データ(起終点の一覧)や参考文献は要らない
WANT_SECTIONS = ("概要", "歴史", "通称", "地理", "路線状況", "特徴", "沿革")


def pick_sections(text, chars):
    """導入部と、豆知識の種がありそうな節だけを残す。"""
    parts = re.split(r"^={2,}\s*(.+?)\s*={2,}\s*$", text, flags=re.M)
    out = [parts[0].strip()]
    for i in range(1, len(parts) - 1, 2):
        name, body = parts[i].strip(), parts[i + 1]
        if any(w in name for w in WANT_SECTIONS):
            out.append("【%s】%s" % (name, body.strip()))
        if sum(len(x) for x in out) > chars:
            break
    return re.sub(r"\n{2,}", "\n", "\n".join(x for x in out if x))[:chars]


def main():
    ap = argparse.ArgumentParser(description="国道のWikipedia記事の冒頭を取る")
    ap.add_argument("targets", nargs="*", type=int)
    ap.add_argument("--chars", type=int, default=1200)
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--out", default=OUT_FILE)
    ap.add_argument("--force", action="store_true", help="取得済みでも取り直す")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = args.targets or sorted(
        int(f[:-len(".geojson")]) for f in os.listdir(RAW_DIR) if f.endswith(".geojson"))
    done = {}
    if os.path.exists(args.out) and not args.force:
        done = json.load(open(args.out, encoding="utf-8"))
    todo = [i for i in ids if str(i) not in done]
    titles = {i: article_title(i) for i in todo}
    todo = [i for i in todo if titles[i]]
    if not todo:
        print("すべて取得済みです（%d件）" % len(done))
        return
    print("取得する記事: %d件" % len(todo))
    if args.list:
        for i in todo:
            print("  国道%d号 → %s" % (i, titles[i]))
        return

    groups = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    by_title = {}
    for n, group in enumerate(groups, 1):
        url = build_url([titles[i] for i in group])
        if args.dry_run:
            print(url)
            continue
        print("[%d/%d] %s ..." % (n, len(groups), titles[group[0]]), flush=True)
        data = fetch(url)
        for page in data.get("query", {}).get("pages", []):
            revs = page.get("revisions") or []
            raw = (revs[0].get("slots", {}).get("main", {}).get("content") if revs else None)
            if raw:
                by_title[page["title"]] = pick_sections(strip_wikitext(raw), args.chars)
        # リダイレクトされた記事名も引けるようにする
        for r in data.get("query", {}).get("redirects", []):
            if r.get("to") in by_title:
                by_title[r["from"]] = by_title[r["to"]]
        for i in group:
            if titles[i] in by_title:
                done[str(i)] = {"title": titles[i], "extract": by_title[titles[i]]}
            else:
                print("    国道%d号（%s）の本文が取れない" % (i, titles[i]))
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(done, f, ensure_ascii=False, indent=1, sort_keys=True)
        if n < len(groups):
            time.sleep(args.sleep)
    if not args.dry_run:
        print("%s に %d件（%.0fKB）"
              % (os.path.relpath(args.out, os.getcwd()), len(done),
                 os.path.getsize(args.out) / 1024))


if __name__ == "__main__":
    main()
