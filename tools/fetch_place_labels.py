#!/usr/bin/env python3
"""
起終点の地名が OpenStreetMap のタグから取れない路線のために、
経路の両端のいちばん近い市町村を OSM から引いて data-raw/place-labels.json に書く。

ほとんどの路線はリレーションの from / to タグに「大阪府大阪市…」のような地名が
入っていて、tools/gen_highways_data.py はそれを起終点ラベルに使う。タグが無い
路線（国道170号・175号・259号・260号）はそこで収録を見送っていた（issue #8）。
通過都道府県は県境データから求められるようになったので、残るのは地名だけ。

使い方:
  python3 tools/fetch_place_labels.py              # タグが無い路線を自動で探して取る
  python3 tools/fetch_place_labels.py 175 259      # 番号を指定する
  python3 tools/fetch_place_labels.py --dry-run    # 投げるクエリを表示するだけ
  python3 tools/fetch_place_labels.py --list       # 対象を表示するだけ

tools/process_routes.py を先に実行しておくこと（経路の両端を使うため）。
"""
import argparse
import json
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from fetch_raw import DEFAULT_ENDPOINT, fetch  # noqa: E402

ROOT = os.path.dirname(SCRIPT_DIR)
PROCESSED_DIR = os.path.join(SCRIPT_DIR, "processed")
RAW_DIR = os.path.join(ROOT, "data-raw")
OUT_FILE = os.path.join(RAW_DIR, "place-labels.json")

QUERY_TEMPLATE = """[out:json][timeout:{timeout}];
(
{clauses}
);
out body;
"""
CLAUSE = '  node(around:{radius},{lat},{lon})["place"~"^(city|town|village)$"];'

# 市町村名から「市」「町」「村」を落として、ボタンや出題文に収まる長さにする
SUFFIXES = ("市", "町", "村", "区")


def short_name(name):
    name = (name or "").strip()
    for s in SUFFIXES:
        if len(name) > 2 and name.endswith(s):
            return name[:-1]
    return name


def haversine(a, b):
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def path_ends(route_id):
    f = os.path.join(PROCESSED_DIR, "%d.json" % route_id)
    if not os.path.exists(f):
        return None
    pts = json.load(open(f, encoding="utf-8"))
    if len(pts) < 2:
        return None
    return (tuple(pts[0]), tuple(pts[-1]))


def has_from_to(route_id):
    """その路線の生データに from / to タグがあるか。"""
    f = os.path.join(RAW_DIR, "%d.geojson" % route_id)
    if not os.path.exists(f):
        return False
    doc = json.load(open(f, encoding="utf-8"))
    for feat in doc.get("features", []):
        props = feat.get("properties") or {}
        if props.get("from") and props.get("to"):
            return True
    return False


def routes_without_tags():
    """from / to タグが無く、経路はある路線を探す。"""
    out = []
    for f in sorted(os.listdir(PROCESSED_DIR)):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        rid = int(f[:-len(".json")])
        if not has_from_to(rid):
            out.append(rid)
    return out


def build_query(ends, radius, timeout):
    clauses = []
    for pair in ends.values():
        for pt in pair:
            clauses.append(CLAUSE.format(radius=radius, lat=pt[0], lon=pt[1]))
    return QUERY_TEMPLATE.format(timeout=timeout, clauses="\n".join(clauses))


def pick_labels(ends, places, max_km=8.0):
    """両端それぞれに、いちばん近い市町村を割り当てる。

    応答は全路線ぶんをまとめて受け取るので、探した半径より遠いものが「いちばん
    近い」になることがある（半径内に1つも無かった端点では、別の路線の市町村が
    何十kmも先から選ばれてしまう）。max_km より遠い候補は採らない。
    """
    labels, report = {}, []
    for rid, (a, b) in sorted(ends.items()):
        row = {}
        for key, pt in (("from", a), ("to", b)):
            near = min(places, key=lambda p: haversine(pt, (p["lat"], p["lon"])),
                       default=None)
            if near is None:
                continue
            d = haversine(pt, (near["lat"], near["lon"]))
            if d > max_km:
                continue
            row[key] = short_name((near.get("tags") or {}).get("name"))
            row[key + "Km"] = round(d, 1)
        if "from" in row and "to" in row:
            labels[str(rid)] = row
            report.append("  国道%d号: %s(%.1fkm) → %s(%.1fkm)"
                          % (rid, row["from"], row["fromKm"], row["to"], row["toKm"]))
        else:
            report.append("  国道%d号: 半径内に市町村が見つからない（--radius を広げる）" % rid)
    return labels, report


def main():
    ap = argparse.ArgumentParser(description="起終点の地名をOSMから引く")
    ap.add_argument("targets", nargs="*", type=int, help="国道の番号（省略するとタグが無い路線）")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Overpassのエンドポイント")
    ap.add_argument("--radius", type=int, default=8000, help="探す半径・m（既定8000）")
    ap.add_argument("--timeout", type=int, default=300, help="Overpass側のtimeout値")
    ap.add_argument("--out", default=OUT_FILE, help="出力先")
    ap.add_argument("--list", action="store_true", help="対象を表示するだけ")
    ap.add_argument("--dry-run", action="store_true", help="投げるクエリを表示するだけ")
    args = ap.parse_args()

    targets = args.targets or routes_without_tags()
    ends = {}
    for rid in targets:
        pair = path_ends(rid)
        if pair is None:
            print("国道%d号: 経路が無い（先に tools/process_routes.py を実行）" % rid)
            continue
        ends[rid] = pair
    if not ends:
        print("対象がありません")
        return
    print("対象 %d路線: %s" % (len(ends), ", ".join("国道%d号" % r for r in sorted(ends))))
    if args.list:
        return

    query = build_query(ends, args.radius, args.timeout)
    if args.dry_run:
        print(query)
        return

    payload = fetch(args.endpoint, query)
    places = [e for e in payload.get("elements", []) if e.get("type") == "node"]
    print("市町村の候補 %d件" % len(places))
    labels, report = pick_labels(ends, places, args.radius / 1000.0)
    for line in report:
        print(line)

    old = {}
    if os.path.exists(args.out):
        old = json.load(open(args.out, encoding="utf-8"))
    old.update(labels)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("%s に %d路線ぶん書き出しました" % (os.path.relpath(args.out, os.getcwd()), len(old)))


if __name__ == "__main__":
    main()
