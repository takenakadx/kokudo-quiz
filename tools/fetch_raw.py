#!/usr/bin/env python3
"""
国道の生データ(GeoJSON)を Overpass API から自動取得して data-raw/ に置くスクリプト。

overpass-turbo をブラウザで開いて1路線ずつ Export する作業を置き換える。
1回のクエリで複数路線をまとめて取りに行き(既定15路線)、取得済みのファイルは
飛ばすので、途中で止まっても同じコマンドを打ち直せば続きから再開できる。

使い方:
  python3 tools/fetch_raw.py                 # 未取得の国道を全部取る
  python3 tools/fetch_raw.py 317             # 317号だけ
  python3 tools/fetch_raw.py 101-150 200     # 番号と範囲を混ぜて指定
  python3 tools/fetch_raw.py --list          # 何が未取得かだけ表示する
  python3 tools/fetch_raw.py --dry-run 1-20  # 投げるクエリを表示するだけ
  python3 tools/fetch_raw.py --force 50      # 取得済みでも取り直す

  # overpass-turbo で手動実行した結果(JSON)を取り込むこともできる
  python3 tools/fetch_raw.py --from-json saved.json

オプション:
  --batch N     1クエリあたりの路線数(既定15)。多いほど速いがサーバ負荷とタイムアウトのリスクが上がる
  --endpoint U  Overpass のエンドポイント。混んでいるときは別のミラーを指定する
  --sleep S     クエリ間の待ち時間(秒、既定5)。公開サーバへの連投を避けるため

出力は overpass-turbo の Export(GeoJSON) と同じ形にしてある(リレーションごとに
1 Feature、ジオメトリは構成する way をつないだ MultiLineString)ので、
そのまま tools/process_routes.py にかけられる。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data-raw")

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

# 一般国道の番号は1〜507まで振られているが、実在するのは459路線。
# 59〜100号は将来の一級国道用に空けられたまま使われていない。
# 109号(→108号)・110号(→48号)・111号(→45号)・214〜216号(→57号)は
# 他の国道へ編入されて廃止された。合わせて48個が欠番。
MAX_ROUTE = 507
VACANT = set(range(59, 101)) | {109, 110, 111, 214, 215, 216}
ALL_ROUTES = [n for n in range(1, MAX_ROUTE + 1) if n not in VACANT]

# 「国道13号」「国道13号線」「国道50号支線」などにマッチさせ、番号だけ取り出す
NAME_RE = re.compile(r"^国道(\d+)号")

QUERY_TEMPLATE = """[out:json][timeout:{timeout}];
area["ISO3166-1"="JP"][admin_level=2]->.jp;
relation(area.jp)["route"="road"]["name"~"^国道({alt})号"];
out body;
>;
out skel qt;
"""


def parse_targets(tokens):
    """"317" や "101-150" の並びを番号の集合にする。指定がなければ全路線。"""
    if not tokens:
        return list(ALL_ROUTES)
    out = []
    for tok in tokens:
        m = re.fullmatch(r"(\d+)-(\d+)", tok)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                raise SystemExit(f"範囲の指定が逆です: {tok}")
            out += [n for n in range(lo, hi + 1) if n not in VACANT]
        elif tok.isdigit():
            n = int(tok)
            if n in VACANT:
                raise SystemExit(f"国道{n}号は欠番です")
            if not 1 <= n <= MAX_ROUTE:
                raise SystemExit(f"国道の番号は1〜{MAX_ROUTE}です: {tok}")
            out.append(n)
        else:
            raise SystemExit(f"番号か範囲で指定してください: {tok}")
    return sorted(set(out))


def out_path(num):
    return os.path.join(DATA_DIR, f"{num}.geojson")


def build_query(nums, timeout=300):
    return QUERY_TEMPLATE.format(timeout=timeout, alt="|".join(str(n) for n in nums))


def stitch(lines):
    """つながっている way どうしを1本のサブラインにまとめる。

    overpass-turbo の Export と同じ形にするための処理。リレーションの
    メンバーの並びはおおむね道の順なので、前の線の終端と次の線の端点が
    一致する間はつなぎ続ける(way が逆向きに入っていることもあるので両端を見る)。
    process_routes.py 側でも端点が一致する断片はつなぐが、細切れのまま渡すと
    断片の並びが変わり、復元結果が最大2kmほどずれることがあったため、
    ここで turbo と同じ粒度に揃えておく。
    """
    runs = []
    joined = False
    for coords in lines:
        if runs:
            cur = runs[-1]
            if cur[-1] == coords[0]:
                cur.extend(coords[1:])
                joined = True
                continue
            if cur[-1] == coords[-1]:
                cur.extend(coords[-2::-1])
                joined = True
                continue
            # まだ1本しか入っていない線は、その way 自体が逆向きに登録されて
            # いるだけかもしれないので、1度だけ裏返して繋ぎ直す。2本目以降は
            # 終端にしか伸ばさない。先頭側にも繋ごうとすると、同じ座標を2回通る
            # 箇所(峠のヘアピンなど)で線が裏返り、そこから先が繋がらなくなる
            if not joined:
                if cur[0] == coords[0]:
                    cur.reverse()
                    cur.extend(coords[1:])
                    joined = True
                    continue
                if cur[0] == coords[-1]:
                    cur.reverse()
                    cur.extend(coords[-2::-1])
                    joined = True
                    continue
        runs.append(list(coords))
        joined = False
    return runs


def overpass_to_features(payload):
    """Overpass の JSON を、番号ごとの GeoJSON Feature のリストに振り分ける。

    overpass-turbo の Export と同じく、リレーション1本につき Feature 1個、
    ジオメトリは構成する way を並べた MultiLineString にする。way の並べ直しは
    process_routes.py 側の仕事なので、ここでは順序をいじらない。
    """
    elements = payload.get("elements", [])
    nodes = {e["id"]: [e["lon"], e["lat"]] for e in elements if e["type"] == "node"}
    ways = {e["id"]: e.get("nodes", []) for e in elements if e["type"] == "way"}

    by_num = {}
    for e in elements:
        if e["type"] != "relation":
            continue
        tags = e.get("tags", {})
        m = NAME_RE.match(tags.get("name", "") or "")
        if not m:
            ref = (tags.get("ref", "") or "").strip()
            m = re.fullmatch(r"R?(\d+)", ref)
            if not m:
                continue
        num = int(m.group(1))

        lines = []
        for member in e.get("members", []):
            if member.get("type") != "way":
                continue
            coords = [nodes[nid] for nid in ways.get(member["ref"], []) if nid in nodes]
            if len(coords) >= 2:
                lines.append(coords)
        if not lines:
            continue
        lines = stitch(lines)

        props = {"@id": f"relation/{e['id']}"}
        props.update(tags)
        by_num.setdefault(num, []).append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "MultiLineString", "coordinates": lines},
            "id": f"relation/{e['id']}",
        })
    return by_num


def write_geojson(num, features):
    doc = {
        "type": "FeatureCollection",
        "generator": "kokudo-quiz tools/fetch_raw.py (Overpass API)",
        "copyright": "The data included in this document is from www.openstreetmap.org. "
                     "The data is made available under ODbL.",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "features": features,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path(num), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return sum(len(c) for feat in features for c in feat["geometry"]["coordinates"])


def fetch(endpoint, query, tries=4):
    """Overpass に問い合わせる。混雑(429)やタイムアウト(504)は待って繰り返す。"""
    data = query.encode("utf-8")
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(
            endpoint, data=data,
            headers={"User-Agent": "kokudo-quiz/1.0 (https://github.com/takenakadx/kokudo-quiz)"})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 504) or attempt == tries:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * attempt
            print(f"    サーバが混雑中(HTTP {e.code})。{wait}秒待って再試行します"
                  f"({attempt}/{tries - 1})", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == tries:
                raise
            wait = 15 * attempt
            print(f"    接続に失敗({e})。{wait}秒待って再試行します"
                  f"({attempt}/{tries - 1})", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def main():
    ap = argparse.ArgumentParser(add_help=True, description="国道の生データをOverpass APIから取得する")
    ap.add_argument("targets", nargs="*", help='国道の番号か範囲（例: 317 101-150）。省略すると未取得の全路線')
    ap.add_argument("--batch", type=int, default=15, help="1クエリあたりの路線数（既定15）")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Overpassのエンドポイント")
    ap.add_argument("--sleep", type=float, default=5.0, help="クエリ間の待ち時間・秒（既定5）")
    ap.add_argument("--timeout", type=int, default=300, help="Overpass側のtimeout値（既定300）")
    ap.add_argument("--force", action="store_true", help="取得済みのファイルも取り直す")
    ap.add_argument("--list", action="store_true", help="対象を表示するだけで取得しない")
    ap.add_argument("--dry-run", action="store_true", help="投げるクエリを表示するだけ")
    ap.add_argument("--from-json", metavar="FILE",
                    help="OverpassのJSON（手動実行の保存結果）から取り込む")
    args = ap.parse_args()

    if args.from_json:
        with open(args.from_json, encoding="utf-8") as f:
            by_num = overpass_to_features(json.load(f))
        if not by_num:
            raise SystemExit("国道のリレーションが見つかりませんでした")
        for num in sorted(by_num):
            pts = write_geojson(num, by_num[num])
            print(f"  国道{num}号 → data-raw/{num}.geojson  ({len(by_num[num])}リレーション / {pts}点)")
        return

    targets = parse_targets(args.targets)
    todo = targets if args.force else [n for n in targets if not os.path.exists(out_path(n))]
    have = len(targets) - len(todo)

    print(f"対象 {len(targets)}路線 / 取得済み {have}路線 / これから取る {len(todo)}路線")
    if args.list or not todo:
        if todo:
            print("未取得:", " ".join(str(n) for n in todo))
        else:
            print("すべて取得済みです")
        return

    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    got = missing = 0
    for bi, batch in enumerate(batches, 1):
        query = build_query(batch, args.timeout)
        head = f"[{bi}/{len(batches)}] 国道 {batch[0]}〜{batch[-1]}号 ({len(batch)}路線)"
        if args.dry_run:
            print(f"{head}\n{query}")
            continue
        print(head, flush=True)
        payload = fetch(args.endpoint, query)
        by_num = overpass_to_features(payload)
        for num in batch:
            feats = by_num.get(num)
            if not feats:
                print(f"    国道{num}号: 見つかりませんでした（名前の付き方が違う可能性）")
                missing += 1
                continue
            pts = write_geojson(num, feats)
            print(f"    国道{num}号 → data-raw/{num}.geojson ({pts}点)")
            got += 1
        if bi < len(batches) and args.sleep > 0:
            time.sleep(args.sleep)

    if args.dry_run:
        return
    print(f"\n取得 {got}路線" + (f" / 見つからず {missing}路線" if missing else ""))
    if got:
        print("続けて実行してください: python3 tools/process_routes.py")


if __name__ == "__main__":
    main()
