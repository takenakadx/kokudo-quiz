#!/usr/bin/env python3
"""
都道府県の境界(OpenStreetMapのadmin_level=4)を取得して、
簡略化した多角形を data-raw/prefectures.json に書き出すスクリプト。

これがあると、経路上の点がどの都道府県にあるかを正確に判定できる。
tools/gen_highways_data.py はこのファイルがあれば通過都道府県をここから作る
(無ければ from/to タグの2県だけになる。issue #11)。

使い方:
  python3 tools/fetch_prefectures.py              # 取得して多角形を作る
  python3 tools/fetch_prefectures.py --fetch-only # 取得だけ(あとで --build-only)
  python3 tools/fetch_prefectures.py --build-only # 取得済みの生データから作り直す
  python3 tools/fetch_prefectures.py --only JP-09,JP-10
  python3 tools/fetch_prefectures.py --endpoint https://overpass.kumi.systems/api/interpreter

オプション:
  --raw-dir D     生データの置き場所(既定 data-raw/prefectures-raw、gitには入れない)
  --out F         出力先(既定 data-raw/prefectures.json)
  --border-tol T  県境の簡略化の強さ・度(既定0.0005≒55m)
  --coast-tol T   海岸線の簡略化の強さ・度(既定0.003≒330m)
  --min-area A    残す島の最小面積・km2(既定30)
  --batch N       1クエリあたりの県数(既定8)。多いほど速いがタイムアウトしやすい
  --endpoint U    Overpassのエンドポイント。混んでいるときは別のミラーを指定する
  --sleep S       クエリ間の待ち時間・秒(既定5)

県境(2県が共有する way)は細かく、海岸線は粗く簡略化する。判定に効くのは県境の
ほうで、海岸線の精度は要らない——陸の上の点はどこかの県に必ず入るので、海岸が
数百m内側にずれても、その点は「どの県にも入らない」になるだけで、
そのときは一番近い県に寄せれば正しい答えになる。
"""
import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from prefectures import (  # noqa: E402
    PREF_NAMES,
    build_polygons,
    write_polygons,
)

DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data-raw")
DEFAULT_RAW_DIR = os.path.join(DATA_DIR, "prefectures-raw")
DEFAULT_OUT = os.path.join(DATA_DIR, "prefectures.json")
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

QUERY_TEMPLATE = """[out:json][timeout:{timeout}];
relation["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"~"^JP-({alt})$"];
out geom;
"""


def raw_path(raw_dir, code):
    return os.path.join(raw_dir, "%s.json" % code)


def fetch(endpoint, query, tries=6):
    """Overpass に問い合わせる。混雑(429)やサーバ側の不調(502/503/504)は待って繰り返す。"""
    data = query.encode("utf-8")
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(
            endpoint, data=data,
            headers={"User-Agent": "kokudo-quiz/1.0 (https://github.com/takenakadx/kokudo-quiz)"})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or attempt == tries:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * attempt
            print("    サーバが混雑中(HTTP %d)。%d秒待って再試行します(%d/%d)"
                  % (e.code, wait, attempt, tries - 1), flush=True)
            time.sleep(wait)
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as e:
            # 接続の切断(RemoteDisconnected)やタイムアウトもここに来る。
            # OSError は urllib.error.URLError と ConnectionError を含む
            if attempt == tries:
                raise
            wait = 15 * attempt
            print("    接続に失敗(%s)。%d秒待って再試行します(%d/%d)"
                  % (e, wait, attempt, tries - 1), flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def query_for(codes, timeout):
    return QUERY_TEMPLATE.format(timeout=timeout,
                                 alt="|".join(c.split("-")[1] for c in codes))


def save_batch(payload, codes, raw_dir):
    """1クエリの応答を県ごとのファイルに振り分ける。"""
    got = {}
    for el in payload.get("elements", []):
        if el.get("type") != "relation":
            continue
        code = (el.get("tags") or {}).get("ISO3166-2")
        if code in codes:
            got[code] = el
    missing = [c for c in codes if c not in got]
    if missing:
        raise SystemExit("応答に入っていない県があります: %s"
                         % ", ".join("%s(%s)" % (c, PREF_NAMES.get(c, "?")) for c in missing))
    for code in codes:
        el = got[code]
        nodes = sum(len(m.get("geometry") or []) for m in el.get("members", []))
        with open(raw_path(raw_dir, code), "w", encoding="utf-8") as f:
            json.dump({"elements": [el]}, f, ensure_ascii=False)
        print("    %s %s: %d点" % (code, (el.get("tags") or {}).get("name", "?"), nodes),
              flush=True)


def fetch_all(codes, raw_dir, endpoint, timeout, sleep, force, dry_run, tries=6, batch=8):
    """未取得の都道府県をまとめて取得する。途中で止めても同じコマンドで続けられる。"""
    os.makedirs(raw_dir, exist_ok=True)
    todo = [c for c in codes if force or not os.path.exists(raw_path(raw_dir, c))]
    if not todo:
        print("生データは取得済みです(%d県)" % len(codes))
        return
    groups = [todo[i:i + batch] for i in range(0, len(todo), max(batch, 1))]
    print("取得する都道府県: %d県(%dクエリ)" % (len(todo), len(groups)))
    for i, group in enumerate(groups, 1):
        query = query_for(group, timeout)
        if dry_run:
            print("--- %s ---\n%s" % (",".join(group), query))
            continue
        print("[%d/%d] %s を取得中..."
              % (i, len(groups), "・".join(PREF_NAMES[c] for c in group)), flush=True)
        save_batch(fetch(endpoint, query, tries), group, raw_dir)
        if i < len(groups):
            time.sleep(sleep)


def load_raw(codes, raw_dir):
    """生データを {コード: リレーション} の形で読む。"""
    rels = {}
    missing = []
    for code in codes:
        path = raw_path(raw_dir, code)
        if not os.path.exists(path):
            missing.append(code)
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        els = [e for e in payload.get("elements", []) if e.get("type") == "relation"]
        if not els:
            missing.append(code)
            continue
        rels[code] = els[0]
    if missing:
        raise SystemExit("生データが足りません: %s\n--fetch-only で取得してください"
                         % ", ".join(missing))
    return rels


def main():
    ap = argparse.ArgumentParser(description="都道府県の境界をOverpass APIから取得する")
    ap.add_argument("--raw-dir", default=DEFAULT_RAW_DIR, help="生データの置き場所")
    ap.add_argument("--out", default=DEFAULT_OUT, help="出力先")
    ap.add_argument("--only", help="対象のISO3166-2コード(例 JP-09,JP-10)")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Overpassのエンドポイント")
    ap.add_argument("--timeout", type=int, default=600, help="Overpass側のtimeout値")
    ap.add_argument("--tries", type=int, default=6, help="1クエリあたりの試行回数")
    ap.add_argument("--batch", type=int, default=8, help="1クエリあたりの県数(既定8)")
    ap.add_argument("--sleep", type=float, default=5.0, help="クエリ間の待ち時間・秒")
    ap.add_argument("--border-tol", type=float, default=0.0005, help="県境の簡略化の強さ・度")
    ap.add_argument("--coast-tol", type=float, default=0.003, help="海岸線の簡略化の強さ・度")
    ap.add_argument("--min-area", type=float, default=30.0, help="残す島の最小面積・km2")
    ap.add_argument("--force", action="store_true", help="取得済みでも取り直す")
    ap.add_argument("--fetch-only", action="store_true", help="取得だけして多角形は作らない")
    ap.add_argument("--build-only", action="store_true", help="取得済みの生データから作り直す")
    ap.add_argument("--dry-run", action="store_true", help="投げるクエリを表示するだけ")
    args = ap.parse_args()

    codes = sorted(PREF_NAMES)
    if args.only:
        codes = [c.strip().upper() for c in args.only.split(",") if c.strip()]
        unknown = [c for c in codes if c not in PREF_NAMES]
        if unknown:
            raise SystemExit("知らないコードです: %s" % ", ".join(unknown))

    if not args.build_only:
        fetch_all(codes, args.raw_dir, args.endpoint, args.timeout,
                  args.sleep, args.force, args.dry_run, args.tries, args.batch)
    if args.fetch_only or args.dry_run:
        return

    if len(codes) < len(PREF_NAMES) and os.path.abspath(args.out) == os.path.abspath(DEFAULT_OUT):
        raise SystemExit("--only で県を絞ったまま %s を作ると、残りの県が抜けた\n"
                         "ファイルになります。--out で別の場所に出すか、--fetch-only に\n"
                         "してください（全県そろってから --build-only で作り直せます）"
                         % os.path.relpath(DEFAULT_OUT, os.getcwd()))

    rels = load_raw(codes, args.raw_dir)
    doc, report = build_polygons(rels, border_tol=args.border_tol,
                                 coast_tol=args.coast_tol, min_area_km2=args.min_area)
    write_polygons(doc, args.out)
    for line in report:
        print(line)
    print("%s に書き出しました(%.0fKB)" % (args.out, os.path.getsize(args.out) / 1024))


if __name__ == "__main__":
    main()
