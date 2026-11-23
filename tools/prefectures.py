#!/usr/bin/env python3
"""
都道府県の多角形を作る・引く部品。

tools/fetch_prefectures.py が OpenStreetMap の admin_level=4 リレーションから
data-raw/prefectures.json を作るときと、tools/gen_highways_data.py が経路の
通過都道府県を求めるときに使う。

多角形は「県境は細かく、海岸線は粗く」簡略化してある。2県が共有する way
(=県境)は細かく、1県にしか現れない way (=海岸線や国境)は粗くする。
判定に効くのは県境のほうで、海岸線の精度は要らない——陸の上の点はどこかの県に
必ず入るので、海岸が数百m内側にずれても、その点は「どの県にも入らない」になる
だけで、そのときは一番近い県に寄せれば正しい答えになる。

way ごとに(両端を動かさずに)簡略化するので、共有された way は両方の県で
まったく同じ形に簡略化される。県境に隙間や重なりができない。
"""
import bisect
import json
import math
import os
import time

PREF_NAMES = {
    "JP-01": "北海道", "JP-02": "青森県", "JP-03": "岩手県", "JP-04": "宮城県",
    "JP-05": "秋田県", "JP-06": "山形県", "JP-07": "福島県", "JP-08": "茨城県",
    "JP-09": "栃木県", "JP-10": "群馬県", "JP-11": "埼玉県", "JP-12": "千葉県",
    "JP-13": "東京都", "JP-14": "神奈川県", "JP-15": "新潟県", "JP-16": "富山県",
    "JP-17": "石川県", "JP-18": "福井県", "JP-19": "山梨県", "JP-20": "長野県",
    "JP-21": "岐阜県", "JP-22": "静岡県", "JP-23": "愛知県", "JP-24": "三重県",
    "JP-25": "滋賀県", "JP-26": "京都府", "JP-27": "大阪府", "JP-28": "兵庫県",
    "JP-29": "奈良県", "JP-30": "和歌山県", "JP-31": "鳥取県", "JP-32": "島根県",
    "JP-33": "岡山県", "JP-34": "広島県", "JP-35": "山口県", "JP-36": "徳島県",
    "JP-37": "香川県", "JP-38": "愛媛県", "JP-39": "高知県", "JP-40": "福岡県",
    "JP-41": "佐賀県", "JP-42": "長崎県", "JP-43": "熊本県", "JP-44": "大分県",
    "JP-45": "宮崎県", "JP-46": "鹿児島県", "JP-47": "沖縄県",
}

KM_PER_DEG = 111.32


# ---------------------------------------------------------------------------
# 多角形を作る
# ---------------------------------------------------------------------------
def simplify(points, tol):
    """Douglas-Peucker。両端は必ず残すので、つなぎ目がずれない。"""
    if len(points) <= 2 or tol <= 0:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        ax, ay = points[lo][1], points[lo][0]
        bx, by = points[hi][1], points[hi][0]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        far, far_d = -1, -1.0
        for i in range(lo + 1, hi):
            px, py = points[i][1], points[i][0]
            if norm == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dx * (py - ay) - dy * (px - ax)) / norm
            if d > far_d:
                far, far_d = i, d
        if far_d > tol:
            keep[far] = True
            stack.append((lo, far))
            stack.append((far, hi))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(points, tol):
    """閉じた線の簡略化。

    Douglas-Peucker は両端を結ぶ線からの距離で点を選ぶが、閉じた線では
    両端が同じ点なので基準線が点に潰れてしまい、小さい島が丸ごと消える。
    一番遠い点で2つに割ってから、それぞれを簡略化する。
    """
    if len(points) < 4:
        return list(points)
    y0, x0 = points[0]
    far = max(range(1, len(points) - 1),
              key=lambda i: (points[i][0] - y0) ** 2 + (points[i][1] - x0) ** 2)
    return simplify(points[:far + 1], tol)[:-1] + simplify(points[far:], tol)


def chain_rings(ways):
    """way をつないで閉じた環にする。閉じなかったものは別に返す。"""
    remaining = [list(w) for w in ways if len(w) >= 2]
    rings, open_parts = [], []
    while remaining:
        cur = remaining.pop()
        joined = True
        while joined and cur[0] != cur[-1]:
            joined = False
            for i, w in enumerate(remaining):
                if w[0] == cur[-1]:
                    cur.extend(w[1:])
                elif w[-1] == cur[-1]:
                    cur.extend(w[-2::-1])
                elif w[-1] == cur[0]:
                    cur[:0] = w[:-1]
                elif w[0] == cur[0]:
                    cur[:0] = w[:0:-1]
                else:
                    continue
                remaining.pop(i)
                joined = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
        else:
            open_parts.append(cur)
    return rings, open_parts


def ring_area_km2(ring):
    """環の面積。緯度による経度1度の縮みだけ補正した概算。"""
    if len(ring) < 4:
        return 0.0
    lat0 = sum(p[0] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    s = 0.0
    for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
        s += (x1 * k) * y2 - (x2 * k) * y1
    return abs(s) / 2.0 * KM_PER_DEG * KM_PER_DEG


def _members(rel):
    """境界を作る way だけ取り出す。subarea / label / admin_centre は見ない。"""
    out = []
    for m in rel.get("members") or []:
        if m.get("type") != "way":
            continue
        role = m.get("role") or "outer"
        if role not in ("outer", "inner"):
            continue
        geom = m.get("geometry") or []
        pts = [(g["lat"], g["lon"]) for g in geom if g is not None]
        if len(pts) >= 2:
            out.append((m.get("ref"), role, pts))
    return out


def build_polygons(rels, border_tol=0.0005, coast_tol=0.003, min_area_km2=30.0, today=None):
    """{コード: リレーション} から簡略化した多角形の束を作る。"""
    shared = {}
    for code, rel in rels.items():
        for ref, _role, _pts in _members(rel):
            shared.setdefault(ref, set()).add(code)

    cache = {}
    prefs, report = [], []
    nodes_in = nodes_out = 0
    for code in sorted(rels):
        rel = rels[code]
        name = (rel.get("tags") or {}).get("name") or PREF_NAMES.get(code, code)
        by_role = {"outer": [], "inner": []}
        tiny = 0
        for ref, role, pts in _members(rel):
            nodes_in += len(pts)
            is_border = len(shared.get(ref, ())) >= 2
            closed = pts[0] == pts[-1]
            key = (ref, is_border, len(pts))
            if key not in cache:
                fn = simplify_ring if closed else simplify
                cache[key] = fn(pts, border_tol if is_border else coast_tol)
            line = cache[key]
            if closed and len(line) < 4:
                tiny += 1       # 簡略化で潰れた＝1点ぶんの大きさしかない小島
                continue
            by_role[role].append(line)

        rings, open_parts = chain_rings(by_role["outer"])
        holes, _ = chain_rings(by_role["inner"])
        rings.sort(key=ring_area_km2, reverse=True)
        kept = [r for i, r in enumerate(rings) if i == 0 or ring_area_km2(r) >= min_area_km2]
        dropped = len(rings) - len(kept) + tiny
        nodes_out += sum(len(r) for r in kept) + sum(len(h) for h in holes)

        prefs.append({
            "code": code,
            "name": name,
            "rings": [[[round(p[0], 5), round(p[1], 5)] for p in r] for r in kept],
            "holes": [[[round(p[0], 5), round(p[1], 5)] for p in h] for h in holes],
        })
        note = "%s %s: 環%d(小島%d個は省略) 穴%d" % (code, name, len(kept), dropped, len(holes))
        if open_parts:
            note += " ※閉じない線が%d本" % len(open_parts)
        report.append(note)

    report.append("点の数 %d → %d (%.1f%%に圧縮)"
                  % (nodes_in, nodes_out, 100.0 * nodes_out / max(nodes_in, 1)))
    doc = {
        "source": "OpenStreetMap (admin_level=4), ODbL",
        "generated": today or time.strftime("%Y-%m-%d", time.gmtime()),
        "simplify": {"border": border_tol, "coast": coast_tol, "minAreaKm2": min_area_km2},
        "prefectures": prefs,
    }
    return doc, report


def write_polygons(doc, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 点がどの県にあるかを引く
#
# 多角形をそのまま総当たりすると、路線1本あたり数百点 × 441路線では遅すぎる。
# 緯度を細い帯(既定0.002度≒220m)に切って、帯ごとに「この経度からこの経度までは
# この県」という区間の表をあらかじめ作る。引くときは帯を選んで二分探索するだけ。
# ---------------------------------------------------------------------------
ROW_DEG = 0.002

# 経路を割り直す間隔と、区間として認める最小の長さ、道と見なす区間の上限
STEP_KM = 1.0
MIN_RUN_KM = 3.0
MAX_GAP_KM = 30.0


class PrefIndex:
    def __init__(self, doc, row_deg=ROW_DEG):
        self.row_deg = row_deg
        self.names = [p["name"] for p in doc["prefectures"]]
        crossings = {}
        for idx, pref in enumerate(doc["prefectures"]):
            for ring in list(pref.get("rings") or []) + list(pref.get("holes") or []):
                for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
                    if y1 == y2:
                        continue
                    lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                    for r in range(self._row(lo), self._row(hi) + 1):
                        y = (r + 0.5) * row_deg
                        if (y1 <= y) == (y2 <= y):
                            continue
                        x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        crossings.setdefault((idx, r), []).append(x)

        self.rows = {}
        for (idx, r), xs in crossings.items():
            xs.sort()
            # 偶奇規則。穴の中は区間から外れるので、穴も同じ表に入れてよい
            for a, b in zip(xs[0::2], xs[1::2]):
                self.rows.setdefault(r, []).append((a, b, idx))
        for r in self.rows:
            self.rows[r].sort()
        self._starts = {r: [s[0] for s in spans] for r, spans in self.rows.items()}
        # 区間は始まりの経度で並んでいるので、引くときは手前へ戻りながら探す。
        # 一番幅の広い区間より手前まで戻れば、それ以上戻っても届かない
        # (北海道は海域を含むので経度7度ぶんの幅がある)
        self._widest = {r: max((b - a for a, b, _ in spans), default=0.0)
                        for r, spans in self.rows.items()}

    def _row(self, lat):
        return int(math.floor(lat / self.row_deg))

    @classmethod
    def load(cls, path, row_deg=ROW_DEG):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), row_deg=row_deg)

    def locate(self, lat, lon):
        """その点を含む県。どの県にも入らなければ None。"""
        r = self._row(lat)
        spans = self.rows.get(r)
        if not spans:
            return None
        i = bisect.bisect_right(self._starts[r], lon) - 1
        while i >= 0:
            a, b, idx = spans[i]
            if a <= lon <= b:
                return self.names[idx]
            if lon - a > self._widest[r]:   # これ以上手前の区間は届かない
                break
            i -= 1
        return None

    def nearest(self, lat, lon, limit_km=8.0):
        """海側にはみ出た点などを、一番近い県に寄せる。遠すぎれば None。"""
        best, best_d = None, limit_km / KM_PER_DEG
        k = max(math.cos(math.radians(lat)), 0.1)
        rows = int(best_d / self.row_deg) + 1
        r0 = self._row(lat)
        for r in range(r0 - rows, r0 + rows + 1):
            spans = self.rows.get(r)
            if not spans:
                continue
            dy = abs((r + 0.5) * self.row_deg - lat)
            if dy >= best_d:
                continue
            i = bisect.bisect_right(self._starts[r], lon)
            for j in (i - 1, i):
                if not 0 <= j < len(spans):
                    continue
                a, b, idx = spans[j]
                dx = 0.0 if a <= lon <= b else min(abs(lon - a), abs(lon - b)) * k
                d = math.hypot(dx, dy)
                if d < best_d:
                    best, best_d = self.names[idx], d
        return best

    def locate_or_nearest(self, lat, lon, limit_km=8.0):
        return self.locate(lat, lon) or self.nearest(lat, lon, limit_km)


def _haversine(a, b):
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def densify(path, step_km=STEP_KM, max_gap_km=MAX_GAP_KM):
    """経路を約step_kmごとに割り直し、[(点, その点が受け持つ長さkm), ...] を返す。

    元の経路は点の間隔がばらばら（簡略化で10km以上空くこともある）なので、
    そのまま数えると、県境の外に1点あるだけで何kmぶんも数えてしまう。
    等間隔に割り直してから数えると、区間の長さが点の間隔に左右されなくなる。

    max_gap_km を超える区間は、道ではなく生データの切れ目（フェリーの海上区間
    など。国道58号の鹿児島〜沖縄は246km）と見なして、割り直さず長さも数えない。
    日本一長い直線道路は国道12号の美唄〜滝川の29.2kmなので、30kmを超える直線は
    道として存在しない。
    """
    if len(path) < 2:
        return [(tuple(p), 0.0) for p in path]
    out = [[tuple(path[0]), 0.0]]
    for a, b in zip(path, path[1:]):
        d = _haversine(a, b)
        if d > max_gap_km:
            out.append([tuple(b), 0.0])     # 海の上は県に数えない
            continue
        n = max(1, int(math.ceil(d / step_km)))
        for k in range(1, n + 1):
            t = k / n
            out[-1][1] += d / n / 2
            out.append([(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), d / n / 2])
    return [(tuple(p), w) for p, w in out]


def prefecture_runs(index, path, limit_km=8.0, step_km=STEP_KM, max_gap_km=MAX_GAP_KM):
    """経路を「同じ県が続く区間」に分ける。[(県名, その区間の長さkm), ...]"""
    runs = []
    for pt, weight in densify(path, step_km, max_gap_km):
        name = index.locate_or_nearest(pt[0], pt[1], limit_km)
        if runs and runs[-1][0] == name:
            runs[-1][1] += weight
        else:
            runs.append([name, weight])
    return [(n, d) for n, d in runs]


def prefecture_sequence(index, path, min_run_km=MIN_RUN_KM, limit_km=8.0,
                        step_km=STEP_KM, max_gap_km=MAX_GAP_KM, keep_ends=()):
    """経路が通る県を順番に並べる。

    min_run_km より短い区間は捨てる。県境のすぐ外を通っただけの点や、
    簡略化した境界のずれで1点だけ隣の県に入った点を拾わないため。
    同じ県に戻ってくる路線(環状など)では最初に出てきた位置に置く。

    ただし経路の両端の区間は、keep_ends に挙げた県なら短くても残す。国道の
    起点・終点は市街地にあり、県境のすぐ内側で終わる路線(国道264号の久留米など)
    が実際にある。そこを県境のずれと区別できないので、別の裏付け——OSMの
    from/to タグが指す県——が一致したときだけ残す。
    """
    runs = [(n, d) for n, d in prefecture_runs(index, path, limit_km, step_km, max_gap_km)
            if n]
    ends = {0, len(runs) - 1}
    keep = [n for i, (n, d) in enumerate(runs)
            if d >= min_run_km or (i in ends and n in keep_ends)]
    if not keep:
        keep = [n for n, _ in sorted(runs, key=lambda r: -r[1])[:1]]
    out = []
    for n in keep:
        if n not in out:
            out.append(n)
    return out
