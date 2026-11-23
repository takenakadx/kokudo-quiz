# 都道府県の多角形を作る・引く部品のテスト（ネットワークにはつながない）
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from prefectures import (  # noqa: E402
    PREF_NAMES,
    PrefIndex,
    build_polygons,
    chain_rings,
    prefecture_runs,
    prefecture_sequence,
    ring_area_km2,
    simplify,
    simplify_ring,
    write_polygons,
)

fail = []


def check(name, cond, extra=None):
    print(("PASS" if cond else "FAIL") + "  " + name + (f"  {extra}" if extra is not None else ""))
    if not cond:
        fail.append(name)


def way(ref, pts, role="outer"):
    return {"type": "way", "ref": ref, "role": role,
            "geometry": [{"lat": p[0], "lon": p[1]} for p in pts]}


def rel(code, name, ways):
    return {"type": "relation", "tags": {"name": name, "ISO3166-2": code,
                                         "admin_level": "4", "boundary": "administrative"},
            "members": ways}


def line(a, b, n=40, wiggle=0.0):
    """a→b をn等分した線。wiggleを指定すると細かいジグザグを足す。"""
    pts = []
    for i in range(n + 1):
        t = i / n
        lat = a[0] + (b[0] - a[0]) * t
        lon = a[1] + (b[1] - a[1]) * t
        if wiggle and 0 < i < n:
            lon += wiggle * (1 if i % 2 else -1)
        pts.append((round(lat, 6), round(lon, 6)))
    return pts


# ---------------------------------------------------------------------------
# 簡略化
# ---------------------------------------------------------------------------
straight = line((35.0, 139.0), (36.0, 139.0), n=50)
check("まっすぐな線は2点に減る", simplify(straight, 0.001) == [straight[0], straight[-1]],
      f"{len(straight)}点 → {len(simplify(straight, 0.001))}点")

jag = line((35.0, 139.0), (36.0, 139.0), n=50, wiggle=0.001)
fine, coarse = simplify(jag, 0.0005), simplify(jag, 0.003)
check("細かい簡略化はジグザグを残す", len(fine) > 10, f"{len(jag)}点 → {len(fine)}点")
check("粗い簡略化はジグザグを消す", len(coarse) == 2, f"{len(jag)}点 → {len(coarse)}点")
check("簡略化しても両端は動かない",
      all(s[0] == jag[0] and s[-1] == jag[-1] for s in (fine, coarse)))

# 閉じた線（島）は、両端が同じ点なのでDPの基準線が潰れる。専用の簡略化を使う
island = [(38.0, 139.0), (38.0, 139.3), (38.3, 139.3), (38.3, 139.0), (38.0, 139.0)]
dense_island = []
for a, b in zip(island, island[1:]):
    dense_island += line(a, b, n=20)[:-1]
dense_island.append(island[0])
check("島を簡略化しても四隅が残る", len(simplify_ring(dense_island, 0.003)) >= 5,
      f"{len(dense_island)}点 → {len(simplify_ring(dense_island, 0.003))}点")
check("ふつうのDPだと島が潰れてしまう（だから専用の処理がある）",
      len(simplify(dense_island, 0.5)) == 2)
speck = [(38.0, 139.0), (38.0, 139.001), (38.001, 139.001), (38.0, 139.0)]
check("1点ぶんの大きさしかない島は潰れる（面積で捨てるので問題ない）",
      len(simplify_ring(speck, 0.01)) < 4, f"{len(simplify_ring(speck, 0.01))}点")

# ---------------------------------------------------------------------------
# way をつないで環にする
# ---------------------------------------------------------------------------
sq = [(35.0, 139.0), (35.0, 140.0), (36.0, 140.0), (36.0, 139.0)]
parts = [[sq[0], sq[1]], [sq[2], sq[1]], [sq[2], sq[3]], [sq[3], sq[0]]]  # 向きはばらばら
rings, open_parts = chain_rings(parts)
check("向きがばらばらの線でも環になる", len(rings) == 1 and not open_parts,
      f"環{len(rings)} 閉じない線{len(open_parts)}")
check("環は閉じている", rings and rings[0][0] == rings[0][-1])
check("閉じない線は別に返る", chain_rings(parts[:3])[0] == [] and len(chain_rings(parts[:3])[1]) == 1)

area = ring_area_km2(rings[0] if rings else [])
check("1度×1度の面積がおおよそ合う", 9800 < area < 10500, f"{area:.0f}km2")

# ---------------------------------------------------------------------------
# 多角形の束を作る（隣り合う2県。県境の way は共有する）
# ---------------------------------------------------------------------------
# A県: 経度139〜140 / B県: 経度140〜141。経度140の線が県境で、両県が同じ ref を持つ。
# 県境と海岸線の両方に同じジグザグを入れて、県境だけ細かく残ることを確かめる。
border = line((35.0, 140.0), (36.0, 140.0), n=40, wiggle=0.001)
a_west = line((36.0, 139.0), (35.0, 139.0), n=40, wiggle=0.001)
b_east = line((35.0, 141.0), (36.0, 141.0), n=40, wiggle=0.001)
rels = {
    "JP-09": rel("JP-09", "A県", [
        way(100, border),
        way(101, [(36.0, 140.0), (36.0, 139.0)]),
        way(102, a_west),
        way(103, [(35.0, 139.0), (35.0, 140.0)]),
    ]),
    "JP-10": rel("JP-10", "B県", [
        way(100, border),
        way(201, [(36.0, 140.0), (36.0, 141.0)]),
        way(202, b_east),
        way(203, [(35.0, 141.0), (35.0, 140.0)]),
    ]),
}
doc, report = build_polygons(rels, border_tol=0.0005, coast_tol=0.003, min_area_km2=30.0,
                             today="2026-01-01")
pa = next(p for p in doc["prefectures"] if p["code"] == "JP-09")
pb = next(p for p in doc["prefectures"] if p["code"] == "JP-10")
check("県ごとに1つの環ができる", len(pa["rings"]) == 1 and len(pb["rings"]) == 1)

ring_a = pa["rings"][0]
on_border_a = [p for p in ring_a if abs(p[1] - 140.0) < 0.01]
on_coast_a = [p for p in ring_a if abs(p[1] - 139.0) < 0.01]
check("県境は細かく残る", len(on_border_a) > 10, f"{len(on_border_a)}点")
check("海岸線は粗くなる", len(on_coast_a) <= 3, f"{len(on_coast_a)}点")

shared_a = sorted(tuple(p) for p in ring_a if abs(p[1] - 140.0) < 0.01)
shared_b = sorted(tuple(p) for p in pb["rings"][0] if abs(p[1] - 140.0) < 0.01)
check("共有する way は両県で同じ形に簡略化される（県境に隙間ができない）",
      shared_a == shared_b, f"A県{len(shared_a)}点 / B県{len(shared_b)}点")

# 小島は面積で捨てる。ただし一番大きい環は必ず残す
islands = dict(rels)
islands["JP-11"] = rel("JP-11", "C県", [
    way(300, [(37.0, 139.0), (37.0, 139.3), (37.3, 139.3), (37.3, 139.0), (37.0, 139.0)]),
    way(301, [(38.0, 139.0), (38.0, 139.01), (38.01, 139.01), (38.01, 139.0), (38.0, 139.0)]),
])
doc2, _ = build_polygons(islands, min_area_km2=30.0)
pc = next(p for p in doc2["prefectures"] if p["code"] == "JP-11")
check("小さすぎる島は省略される", len(pc["rings"]) == 1, f"環{len(pc['rings'])}")

tiny_only = {"JP-11": rel("JP-11", "C県", [way(301, [
    (38.0, 139.0), (38.0, 139.01), (38.01, 139.01), (38.01, 139.0), (38.0, 139.0)])])}
doc3, _ = build_polygons(tiny_only, min_area_km2=30.0)
check("小さい島しか無い県でも環は残る",
      len(doc3["prefectures"][0]["rings"]) == 1)

# ---------------------------------------------------------------------------
# 点がどの県にあるかを引く
# ---------------------------------------------------------------------------
index = PrefIndex(doc)
check("A県の中の点はA県", index.locate(35.5, 139.5) == "A県", index.locate(35.5, 139.5))
check("B県の中の点はB県", index.locate(35.5, 140.5) == "B県", index.locate(35.5, 140.5))
check("どちらでもない点はNone", index.locate(35.5, 142.0) is None, index.locate(35.5, 142.0))
check("県の外(緯度)の点はNone", index.locate(34.0, 139.5) is None)
check("少しはみ出た点は一番近い県に寄る",
      index.locate_or_nearest(35.5, 141.02) == "B県", index.locate_or_nearest(35.5, 141.02))
check("遠くはみ出た点はNoneのまま",
      index.locate_or_nearest(35.5, 143.0) is None, index.locate_or_nearest(35.5, 143.0))

# 穴（県の中にある他県の飛び地）は、その県に入らない
holed = {"JP-09": rel("JP-09", "A県", [
    way(100, [(35.0, 139.0), (35.0, 140.0), (36.0, 140.0), (36.0, 139.0), (35.0, 139.0)]),
    way(150, [(35.4, 139.4), (35.4, 139.6), (35.6, 139.6), (35.6, 139.4), (35.4, 139.4)], "inner"),
])}
doc4, _ = build_polygons(holed)
check("穴を1つ持つ", len(doc4["prefectures"][0]["holes"]) == 1)
ix4 = PrefIndex(doc4)
check("穴の中の点は県に入らない", ix4.locate(35.5, 139.5) is None, ix4.locate(35.5, 139.5))
check("穴の外・県の中の点は県に入る", ix4.locate(35.2, 139.5) == "A県", ix4.locate(35.2, 139.5))

# ---------------------------------------------------------------------------
# 経路が通る県を順番に並べる
# ---------------------------------------------------------------------------
path = [(35.5, 139.0 + 0.02 * i) for i in range(101)]      # A県 → B県 を横断（約180km）
check("通過県が順番に並ぶ", prefecture_sequence(index, path) == ["A県", "B県"],
      prefecture_sequence(index, path))
check("逆向きの経路は逆の順に並ぶ", prefecture_sequence(index, path[::-1]) == ["B県", "A県"],
      prefecture_sequence(index, path[::-1]))

# B県へ1点だけはみ出す経路（県境の0.4km先まで）。短い区間は拾わない
dip = ([(35.5, 139.5 + 0.005 * i) for i in range(100)]
       + [(35.5, 140.004)]
       + [(35.5, 140.0 - 0.005 * i) for i in range(100)])
runs = prefecture_runs(index, dip)
check("短い区間も runs には出る", [n for n, _ in runs] == ["A県", "B県", "A県"],
      [(n, round(d, 1)) for n, d in runs])
check("短すぎる区間は通過県に入れない", prefecture_sequence(index, dip, min_run_km=3.0) == ["A県"],
      prefecture_sequence(index, dip, min_run_km=3.0))
check("しきい値を下げれば拾う",
      prefecture_sequence(index, dip, min_run_km=0.0) == ["A県", "B県"],
      prefecture_sequence(index, dip, min_run_km=0.0))

# 経路の端の短い区間は、起終点の裏付け(OSMのfrom/toタグ)があれば残す。
# 国道264号の久留米のように、県境のすぐ内側で終わる路線が実際にある
tail = [(35.5, 139.5 + 0.005 * i) for i in range(101)] + [(35.5, 140.004)]
check("端の短い区間は裏付けがあれば残す",
      prefecture_sequence(index, tail, keep_ends=("B県",)) == ["A県", "B県"],
      prefecture_sequence(index, tail, keep_ends=("B県",)))
check("裏付けが無ければ端でも捨てる",
      prefecture_sequence(index, tail) == ["A県"], prefecture_sequence(index, tail))
check("途中の短い区間は裏付けがあっても拾わない",
      prefecture_sequence(index, dip, keep_ends=("B県",)) == ["A県"],
      prefecture_sequence(index, dip, keep_ends=("B県",)))

# 同じ県に戻ってくる経路は、最初に出てきた位置に1回だけ
loop = ([(35.5, 139.5 + 0.02 * i) for i in range(51)]
        + [(35.5, 140.5 - 0.02 * i) for i in range(51)])
# 海上区間（生データの切れ目）は長さに数えない。国道58号の鹿児島〜沖縄のように
# 240km超の「飛び」があり、そこに道は無いので県の通過距離として数えてはいけない
jumped = [(35.5, 139.5), (35.5, 139.6), (35.5, 140.9), (35.5, 140.95)]
runs2 = prefecture_runs(index, jumped)
by_pref = dict(runs2)
check("海上区間ぶんの長さは数えない",
      [n for n, _ in runs2] == ["A県", "B県"]
      and 8 < by_pref["A県"] < 11 and 3 < by_pref["B県"] < 6,
      [(n, round(d, 1)) for n, d in runs2])

check("戻ってくる県は1回だけ並ぶ", prefecture_sequence(index, loop) == ["A県", "B県"],
      prefecture_sequence(index, loop))

# 書き出して読み直しても同じ答えになる
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "prefectures.json")
    write_polygons(doc, out)
    reloaded = PrefIndex.load(out)
    check("書き出して読み直しても同じ答え",
          reloaded.locate(35.5, 139.5) == "A県" and reloaded.locate(35.5, 140.5) == "B県")
    check("書き出したJSONに出典が入る",
          json.load(open(out, encoding="utf-8"))["source"].find("ODbL") >= 0)

check("47都道府県ぶんの名前を持っている", len(PREF_NAMES) == 47)

# ---------------------------------------------------------------------------
# 取得スクリプトのクエリ組み立てと振り分け（ネットワークにはつながない）
# ---------------------------------------------------------------------------
import fetch_prefectures as fp  # noqa: E402

q = fp.query_for(["JP-09", "JP-10", "JP-11"], 600)
check("まとめて取るクエリになる", '"ISO3166-2"~"^JP-(09|10|11)$"' in q, q.strip().splitlines()[1])
check("クエリにtimeoutが入る", "[timeout:600]" in q)

payload = {"elements": [
    {"type": "relation", "tags": {"ISO3166-2": "JP-09", "name": "栃木県"},
     "members": [way(1, [(36.0, 139.0), (36.0, 140.0)])]},
    {"type": "relation", "tags": {"ISO3166-2": "JP-10", "name": "群馬県"},
     "members": [way(2, [(36.5, 138.5), (36.5, 139.5)])]},
    {"type": "node", "id": 1},
]}
with tempfile.TemporaryDirectory() as tmp:
    fp.save_batch(payload, ["JP-09", "JP-10"], tmp)
    files = sorted(os.listdir(tmp))
    check("1クエリの応答が県ごとのファイルに分かれる", files == ["JP-09.json", "JP-10.json"], files)
    one = json.load(open(os.path.join(tmp, "JP-09.json"), encoding="utf-8"))
    check("分けたファイルは1県ぶんだけ持つ",
          len(one["elements"]) == 1 and one["elements"][0]["tags"]["name"] == "栃木県")
    try:
        fp.save_batch(payload, ["JP-09", "JP-10", "JP-11"], tmp)
        check("応答に足りない県があれば止まる", False, "止まらなかった")
    except SystemExit as e:
        check("応答に足りない県があれば止まる", "JP-11" in str(e), str(e))

# ---------------------------------------------------------------------------
# 実データ（data-raw/prefectures.json）があれば、知っている地点で答え合わせする
# ---------------------------------------------------------------------------
REAL = os.path.join(ROOT, "data-raw", "prefectures.json")
KNOWN = [
    ("札幌駅", 43.0686, 141.3507, "北海道"),
    ("青森駅", 40.8278, 140.7351, "青森県"),
    ("仙台駅", 38.2601, 140.8821, "宮城県"),
    ("東京駅", 35.6812, 139.7671, "東京都"),
    ("横浜駅", 35.4660, 139.6220, "神奈川県"),
    ("新潟駅", 37.9123, 139.0617, "新潟県"),
    ("甲府駅", 35.6641, 138.5685, "山梨県"),
    ("名古屋駅", 35.1709, 136.8815, "愛知県"),
    ("金沢駅", 36.5781, 136.6477, "石川県"),
    ("京都駅", 34.9858, 135.7588, "京都府"),
    ("大阪駅", 34.7025, 135.4959, "大阪府"),
    ("和歌山駅", 34.2306, 135.1917, "和歌山県"),
    ("松江駅", 35.4551, 133.0617, "島根県"),
    ("広島駅", 34.3978, 132.4757, "広島県"),
    ("高松駅", 34.3524, 134.0467, "香川県"),
    ("高知駅", 33.5667, 133.5425, "高知県"),
    ("博多駅", 33.5897, 130.4207, "福岡県"),
    ("長崎駅", 32.7525, 129.8742, "長崎県"),
    ("鹿児島中央駅", 31.5833, 130.5417, "鹿児島県"),
    ("那覇(県庁前)", 26.2124, 127.6792, "沖縄県"),
]
if os.path.exists(REAL):
    real = PrefIndex.load(REAL)
    check("47都道府県ぶんの多角形がある", len(real.names) == 47, f"{len(real.names)}県")
    check("都道府県名がすべて正しい", sorted(real.names) == sorted(PREF_NAMES.values()),
          sorted(set(PREF_NAMES.values()) - set(real.names)) or "一致")
    wrong = [(nm, real.locate_or_nearest(la, lo), want)
             for nm, la, lo, want in KNOWN if real.locate_or_nearest(la, lo) != want]
    check("主要駅の所在県が全部当たる", not wrong, wrong or f"{len(KNOWN)}地点すべて一致")
else:
    print("SKIP  実データ(data-raw/prefectures.json)が無いので実地の確認は飛ばします")

# ---------------------------------------------------------------------------
# 生成済みの highways-data.js の通過県（パイプライン全体の回帰テスト）
# ---------------------------------------------------------------------------
import re  # noqa: E402

DATA = os.path.join(ROOT, "highways-data.js")
if os.path.exists(DATA) and os.path.exists(REAL):
    src = open(DATA, encoding="utf-8").read()
    routes = {}
    for rid, body in re.findall(r"\n  \{\n    id: (\d+),(.*?)\n  \}", src, re.S):
        routes[int(rid)] = re.findall(
            r'"([^"]+)"', re.search(r"prefectures: \[(.*?)\]", body, re.S).group(1))
    check("全路線に通過県が入っている",
          routes and all(routes.values()), len(routes))
    check("通過県の名前がすべて実在する",
          not {p for v in routes.values() for p in v} - set(PREF_NAMES.values()),
          sorted({p for v in routes.values() for p in v} - set(PREF_NAMES.values())) or "一致")

    # 途中の県が出ていること。以前は from/to タグ頼みで、手書き以外は必ず2県以下だった
    many = [r for r, v in routes.items() if len(v) >= 3]
    check("3県以上を通る路線が80本以上ある（以前は手書きの28本だけ）", len(many) >= 80,
          f"{len(many)}本")

    # 自動生成の路線のうち、通る県を地図で確かめられるもの
    EXPECT = {
        122: ["栃木県", "群馬県", "埼玉県", "東京都"],
        254: ["東京都", "埼玉県", "群馬県", "長野県"],
        294: ["千葉県", "茨城県", "栃木県", "福島県"],
        365: ["石川県", "福井県", "滋賀県", "岐阜県", "三重県"],
        468: ["神奈川県", "東京都", "埼玉県", "茨城県", "千葉県"],
        477: ["三重県", "滋賀県", "京都府", "兵庫県", "大阪府"],
    }
    for rid, want in EXPECT.items():
        if rid in routes:
            check(f"国道{rid}号の通過県", routes[rid] == want, " → ".join(routes[rid]))

print()
if fail:
    print(f"{len(fail)} 件失敗: {fail}")
    sys.exit(1)
print("すべて合格")
