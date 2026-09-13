#!/usr/bin/env python3
"""
data-raw/ に置かれた国道の実ルートGeoJSON(Overpass Turboで取得したもの)を、
なぞりクイズ用の1本の折れ線(始点→終点)に変換するスクリプト。

Overpassからのエクスポートは、ルートを構成する多数の断片的な線分
(MultiLineStringの各サブライン)がバラバラの順序・向きで入っているため、
以下の手順で1本のルートに組み立てる。

1. 端点の座標が完全一致する断片同士を連結する(exact_merge)
2. ある程度の長さを持つ断片(min_significant_km以上)だけを残し、
   始点に近いものから順に、現在の終端に最も近い断片を貪欲につないでいく
   (bridge_chains)。断片同士に小さな隙間がある場合はそのまま橋渡しする。
   近い断片が複数ある場合は、たまたま近くにあるだけの短い断片ではなく
   より長い(=本線である可能性が高い)断片を優先する。
3. Douglas-Peucker法で間引いて、ゲームで使うのに十分な点数(300点以下)まで
   単純化する。

出力は tools/processed/<id>.json に [緯度, 経度] の配列として保存される。
生成後は、期待する始点・終点(EXPECTED)とのズレ(start_mismatch_km /
end_mismatch_km)と、実際の道路延長として妥当な長さ(len_km)かを必ず
目視確認すること。特に環状路線(16号など)は始点=終点なので、たまたま
近くにある無関係な短い断片でも一致判定をすり抜けてしまう点に注意。
大きくズレている・長さが不自然な場合は、そのルートについては手動で
経由都市を結んだ簡略ルートのままにしておく方が安全。

使い方: python3 tools/process_routes.py
"""
import json, math, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data-raw")
OUT_DIR = os.path.join(SCRIPT_DIR, "processed")
os.makedirs(OUT_DIR, exist_ok=True)

EXPECTED = {
    1:   ((35.68, 139.77), (34.69, 135.50)),
    2:   ((34.69, 135.50), (33.94, 130.96)),
    3:   ((33.94, 130.96), (31.60, 130.56)),
    4:   ((35.68, 139.77), (40.82, 140.74)),
    5:   ((41.77, 140.73), (43.06, 141.35)),
    6:   ((35.68, 139.77), (38.27, 140.87)),
    7:   ((37.92, 139.04), (40.82, 140.74)),
    8:   ((37.92, 139.04), (35.01, 135.77)),
    9:   ((35.01, 135.77), (33.95, 130.94)),
    10:  ((33.94, 130.96), (31.60, 130.56)),
    11:  ((33.84, 132.77), (33.56, 133.53)),
    12:  ((43.06, 141.35), (43.77, 142.37)),
    14:  ((35.68, 139.77), (35.60, 140.12)),
    15:  ((35.68, 139.77), (35.44, 139.64)),
    16:  ((35.44, 139.64), (35.44, 139.64)),
    17:  ((35.68, 139.77), (37.92, 139.04)),
    19:  ((35.18, 136.91), (36.65, 138.18)),
    20:  ((35.68, 139.77), (36.11, 137.95)),
    22:  ((35.18, 136.91), (35.42, 136.76)),
    23:  ((35.18, 136.91), (34.49, 136.71)),
    25:  ((35.18, 136.91), (34.69, 135.50)),
    41:  ((35.18, 136.91), (36.70, 137.21)),
    42:  ((34.23, 135.17), (34.58, 136.53)),
    43:  ((34.69, 135.50), (34.69, 135.20)),
    58:  ((31.60, 130.56), (26.21, 127.68)),
    134: ((35.28, 139.67), (35.32, 139.31)),
    135: ((35.10, 139.07), (34.68, 138.95)),
    158: ((36.06, 136.22), (36.23, 137.97)),
    171: ((35.01, 135.77), (34.69, 135.20)),
    176: ((34.69, 135.50), (35.47, 135.33)),
    246: ((35.68, 139.74), (35.10, 138.86)),
    357: ((35.38, 139.92), (35.28, 139.67)),
    411: ((35.69, 139.70), (35.66, 138.57)),
    413: ((35.57, 139.37), (35.49, 138.79)),
    439: ((34.07, 134.56), (32.94, 132.94)),
}

# Rough intermediate checkpoints (known-to-pass-through cities) for routes whose
# plain start->end walk wandered off course. Splitting the walk into short legs
# between these checkpoints keeps a wrong turn from derailing the whole route.
CHECKPOINTS = {
    1: [(35.68, 139.77), (35.53, 139.70), (35.44, 139.64), (35.34, 139.49), (35.26, 139.16),
        (35.10, 138.86), (35.16, 138.68), (34.98, 138.38), (34.77, 137.99), (34.71, 137.73),
        (34.77, 137.39), (34.95, 137.17), (35.18, 136.91), (35.06, 136.69), (34.97, 136.62),
        (34.86, 136.45), (35.01, 135.87), (35.01, 135.77), (34.69, 135.50)],
    2: [(34.69, 135.50), (34.69, 135.20), (34.65, 134.99), (34.82, 134.69), (34.66, 133.92),
        (34.60, 133.77), (34.49, 133.36), (34.41, 133.20), (34.40, 132.46), (34.17, 132.22),
        (34.05, 131.81), (34.19, 131.47), (33.95, 130.94), (33.94, 130.96)],
    9: [(35.01, 135.77), (35.02, 135.57), (35.30, 135.13), (35.54, 134.82), (35.50, 134.24),
        (35.43, 133.82), (35.43, 133.33), (35.47, 133.05), (35.37, 132.76), (35.19, 132.50),
        (34.90, 132.08), (34.67, 131.85), (34.38, 131.19), (33.95, 130.94)],
    16: [(35.44, 139.64), (35.55, 139.45), (35.66, 139.32), (35.83, 139.39), (35.92, 139.48),
         (35.86, 139.65), (35.98, 139.75), (35.95, 139.87), (35.85, 139.93), (35.70, 139.99),
         (35.60, 140.12), (35.38, 139.92), (35.28, 139.67), (35.44, 139.64)],
    23: [(35.18, 136.91), (34.97, 136.62), (34.88, 136.58), (34.72, 136.51), (34.58, 136.53),
         (34.49, 136.71)],
    42: [(34.23, 135.17), (33.89, 135.15), (33.73, 135.38), (33.55, 135.52), (33.72, 135.98),
         (33.90, 136.10), (34.07, 136.20), (34.58, 136.53)],
    246: [(35.68, 139.74), (35.66, 139.70), (35.55, 139.45), (35.44, 139.36), (35.37, 139.22),
          (35.31, 138.93), (35.10, 138.86)],
}

def haversine(a, b):
    R = 6371.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def chain_length_km(chain):
    return sum(haversine(chain[i], chain[i+1]) for i in range(len(chain)-1))

def extract_segments(geojson):
    segs = []
    for feat in geojson.get("features", []):
        geom = feat.get("geometry") or {}
        t = geom.get("type")
        coords = geom.get("coordinates")
        if t == "LineString":
            segs.append([(c[1], c[0]) for c in coords])
        elif t == "MultiLineString":
            for line in coords:
                segs.append([(c[1], c[0]) for c in line])
    return [s for s in segs if len(s) >= 2]

def round_key(pt, decimals=6):
    return (round(pt[0], decimals), round(pt[1], decimals))

def exact_merge(segs):
    """Stitch segments that share exact (rounded) endpoints into chains."""
    endpoint_index = {}
    for i, s in enumerate(segs):
        endpoint_index.setdefault(round_key(s[0]), []).append((i, 0))
        endpoint_index.setdefault(round_key(s[-1]), []).append((i, 1))
    used = [False] * len(segs)

    def find_match(key, used_local):
        for i, end in endpoint_index.get(key, []):
            if not used_local[i]:
                return i, end
        return None, None

    chains = []
    for start_i in range(len(segs)):
        if used[start_i]:
            continue
        used[start_i] = True
        chain = list(segs[start_i])
        while True:
            i, end = find_match(round_key(chain[-1]), used)
            if i is None:
                break
            used[i] = True
            piece = segs[i]
            chain.extend((piece[1:] if end == 0 else list(reversed(piece))[1:]))
        while True:
            i, end = find_match(round_key(chain[0]), used)
            if i is None:
                break
            used[i] = True
            piece = segs[i]
            chain[0:0] = (piece[:-1] if end == 1 else list(reversed(piece))[:-1])
        chains.append(chain)
    return chains

def pick_best_candidate(candidates, near_radius_km):
    """candidates: list of (dist_km, chain_len_km, i, end). Prefer the LONGEST chain
    among those within near_radius_km (a short decoy segment that merely happens to
    sit very close to the target point should not beat a long, clearly-real chain
    that also reaches nearby); otherwise fall back to the single globally nearest."""
    near = [c for c in candidates if c[0] <= near_radius_km]
    if near:
        return max(near, key=lambda c: c[1])
    return min(candidates, key=lambda c: c[0])

def take_chain(sig, sig_lens, used, i, end, target_pt):
    """Mark chain i consumed, oriented so it starts at the entry end. If the target
    point's closest approach is somewhere in the *middle* of this chain (i.e. the
    chain overshoots what's actually needed - important for short legs grabbing a
    long chain), truncate there and push the unused remainder back into the shared
    pool as a fresh chain so a later leg can still pick it up."""
    used[i] = True
    piece = list(sig[i]) if end == 0 else list(reversed(sig[i]))
    dists = [haversine(p, target_pt) for p in piece]
    idx_min = min(range(len(piece)), key=lambda k: dists[k])
    if idx_min < len(piece) - 1 and dists[idx_min] < dists[-1]:
        leftover = piece[idx_min:]
        leftover_len = chain_length_km(leftover)
        if len(leftover) >= 2 and leftover_len >= 1.0:
            sig.append(leftover)
            sig_lens.append(leftover_len)
            used.append(False)
        piece = piece[:idx_min + 1]
    return piece

def walk_segment(sig, sig_lens, used, start_pt, end_pt, max_bridge_km, near_radius_km, end_snap_km):
    """Walk from start_pt to end_pt using chains from the shared pool `sig`, marking
    consumed chains in the shared `used` array (mutated in place) so a later leg
    (in a multi-checkpoint walk) can't re-use a chain an earlier leg already took."""
    candidates = []
    for i, c in enumerate(sig):
        if used[i]:
            continue
        for end, pt in ((0, c[0]), (1, c[-1])):
            candidates.append((haversine(pt, start_pt), sig_lens[i], i, end))
    if not candidates:
        return [start_pt], [], False
    _, _, i0, end0 = pick_best_candidate(candidates, near_radius_km)
    used[i0] = True
    path = list(sig[i0]) if end0 == 0 else list(reversed(sig[i0]))
    bridges = []

    while True:
        current = path[-1]
        d_to_end = haversine(current, end_pt)
        candidates = []
        for i, c in enumerate(sig):
            if used[i]:
                continue
            for end, pt in ((0, c[0]), (1, c[-1])):
                candidates.append((haversine(pt, current), sig_lens[i], i, end))
        if not candidates or (d_to_end <= end_snap_km and d_to_end < min(c[0] for c in candidates)):
            break
        d_next, _, i, end = pick_best_candidate(candidates, near_radius_km)
        if d_next > max_bridge_km:
            break
        used[i] = True
        piece = sig[i]
        piece = piece if end == 0 else list(reversed(piece))
        bridges.append(round(d_next, 2))
        path.extend(piece)
    reached = haversine(path[-1], end_pt) <= max(end_snap_km, 10.0)
    return path, bridges, reached

def walk_leg(sig, sig_lens, used, cur_pt, target_pt, entry_radius_km=8.0, max_steps=40):
    """Checkpoint-mode leg walk: at each step, among chains whose entry point is
    reasonably close to the current position, pick whichever one's closest approach
    to THIS leg's target gets us nearest (not simply "longest nearby chain", which is
    wrong once legs are short - a long chain heading the wrong way looks tempting but
    doesn't serve a short leg). Truncate at that closest-approach point and push the
    remainder back into the pool for later legs."""
    path = [cur_pt]
    for _ in range(max_steps):
        current = path[-1]
        if haversine(current, target_pt) <= 4.0:
            break
        entry_candidates = []
        for i, c in enumerate(sig):
            if used[i]:
                continue
            for end, pt in ((0, c[0]), (1, c[-1])):
                d = haversine(pt, current)
                if d <= entry_radius_km:
                    entry_candidates.append((d, i, end))
        if not entry_candidates:
            # nothing close enough to continue from; grab the single globally
            # nearest entry point so the leg can still make some progress
            all_candidates = []
            for i, c in enumerate(sig):
                if used[i]:
                    continue
                for end, pt in ((0, c[0]), (1, c[-1])):
                    all_candidates.append((haversine(pt, current), i, end))
            if not all_candidates:
                break
            entry_candidates = [min(all_candidates, key=lambda x: x[0])]

        best = None  # (approach_dist, i, end)
        for _d_entry, i, end in entry_candidates:
            piece = list(sig[i]) if end == 0 else list(reversed(sig[i]))
            dists = [haversine(p, target_pt) for p in piece]
            idx_min = min(range(len(piece)), key=lambda k: dists[k])
            if best is None or dists[idx_min] < best[0]:
                best = (dists[idx_min], i, end, idx_min, piece)
        approach_dist, i, end, idx_min, piece = best
        if approach_dist >= haversine(current, target_pt):
            # nothing available gets us any closer than we already are - stop rather
            # than wander
            break
        used[i] = True
        if idx_min < len(piece) - 1:
            leftover = piece[idx_min:]
            leftover_len = chain_length_km(leftover)
            if len(leftover) >= 2 and leftover_len >= 1.0:
                sig.append(leftover)
                sig_lens.append(leftover_len)
                used.append(False)
        path.extend(piece[1:idx_min + 1] if idx_min > 0 else [])
    reached = haversine(path[-1], target_pt) <= 8.0
    return path, reached

def bridge_chains(chains, start_pt, end_pt, min_significant_km=2.5, max_bridge_km=25.0, near_radius_km=5.0):
    """Single start->end walk (no intermediate checkpoints)."""
    sig = [c for c in chains if chain_length_km(c) >= min_significant_km]
    if not sig:
        sig = sorted(chains, key=chain_length_km, reverse=True)[:1]
    sig_lens = [chain_length_km(c) for c in sig]
    used = [False] * len(sig)
    path, bridges, _ = walk_segment(sig, sig_lens, used, start_pt, end_pt, max_bridge_km, near_radius_km, 15.0)
    return path, bridges, [round(l, 1) for l in sig_lens]

def bridge_via_checkpoints(chains, checkpoints, min_significant_km=2.5, max_bridge_km=15.0, near_radius_km=5.0):
    """Stitch chains start->end via a sequence of human-supplied intermediate
    checkpoints (e.g. the cities the route is known to pass through). Each
    consecutive pair of checkpoints is walked as its own short leg, which keeps the
    greedy nearest-chain search from wandering far off course on a long route -
    a wrong turn only derails the current (short) leg instead of the whole route,
    and a loop route's start/end no longer look trivially "already satisfied" by
    a nearby, unrelated short fragment.
    Returns (full_path, per_leg_info) where per_leg_info has one dict per leg with
    the leg's reached endpoint mismatch, for spot-checking which leg (if any) failed.
    """
    sig = [c for c in chains if chain_length_km(c) >= min_significant_km]
    if not sig:
        sig = sorted(chains, key=chain_length_km, reverse=True)[:1]
    sig_lens = [chain_length_km(c) for c in sig]
    used = [False] * len(sig)

    full_path = []
    legs = []
    for i in range(len(checkpoints) - 1):
        a, b = checkpoints[i], checkpoints[i + 1]
        start_pt = full_path[-1] if full_path else a
        leg_path, reached = walk_leg(sig, sig_lens, used, start_pt, b)
        end_mismatch = round(haversine(leg_path[-1], b), 1)
        legs.append({"leg": i, "reached": reached, "end_mismatch_km": end_mismatch,
                     "bridges": [], "points": len(leg_path)})
        if full_path and leg_path and full_path[-1] == leg_path[0]:
            full_path.extend(leg_path[1:])
        else:
            full_path.extend(leg_path)
    return full_path, legs

def douglas_peucker(points, tolerance_km):
    if len(points) < 3:
        return points
    def perp_dist_km(pt, a, b):
        lat0 = math.radians((a[0]+b[0])/2)
        def proj(p):
            return (p[1]*math.cos(lat0)*111.32, p[0]*111.32)
        ax, ay = proj(a); bx, by = proj(b); px, py = proj(pt)
        dx, dy = bx-ax, by-ay
        if dx == 0 and dy == 0:
            return math.hypot(px-ax, py-ay)
        t = ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)
        t = max(0, min(1, t))
        cx, cy = ax+dx*t, ay+dy*t
        return math.hypot(px-cx, py-cy)
    def rdp(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        idx, dmax = -1, 0
        for i in range(1, len(pts)-1):
            d = perp_dist_km(pts[i], a, b)
            if d > dmax:
                idx, dmax = i, d
        if dmax > tolerance_km:
            left = rdp(pts[:idx+1])
            right = rdp(pts[idx:])
            return left[:-1] + right
        return [a, b]
    return rdp(points)

def process(route_id):
    path_file = os.path.join(DATA_DIR, f"{route_id}.geojson")
    exp_start, exp_end = EXPECTED[route_id]
    if not os.path.exists(path_file):
        return {"id": route_id, "error": "missing geojson file"}
    geojson = json.load(open(path_file))
    segs = extract_segments(geojson)
    if not segs:
        return {"id": route_id, "error": "no line segments"}

    chains = exact_merge(segs)
    checkpoints = CHECKPOINTS.get(route_id)
    legs = None
    if checkpoints:
        walked, legs = bridge_via_checkpoints(chains, checkpoints)
        bridges = [b for leg in legs for b in leg["bridges"]]
    else:
        walked, bridges, _sig_lens = bridge_chains(chains, exp_start, exp_end)
    total_len = chain_length_km(walked)

    simplified = douglas_peucker(walked, tolerance_km=0.08)
    tol = 0.08
    while len(simplified) > 300 and tol < 2.0:
        tol *= 1.6
        simplified = douglas_peucker(walked, tolerance_km=tol)

    out_path = os.path.join(OUT_DIR, f"{route_id}.json")
    json.dump([[round(p[0], 5), round(p[1], 5)] for p in simplified], open(out_path, "w"), ensure_ascii=False)

    return {
        "id": route_id,
        "used_checkpoints": bool(checkpoints),
        "legs": legs,
        "raw_points": len(walked),
        "simplified_points": len(simplified),
        "len_km": round(total_len, 1),
        "start_mismatch_km": round(haversine(walked[0], exp_start), 1),
        "end_mismatch_km": round(haversine(walked[-1], exp_end), 1),
        "num_bridges": len(bridges),
        "bridge_dists_km": bridges,
    }

if __name__ == "__main__":
    results = [process(i) for i in sorted(EXPECTED.keys())]
    for r in results:
        if "error" in r:
            print(f"{r['id']:>4} | ERROR: {r['error']}")
            continue
        flag = ""
        if r["start_mismatch_km"] > 8: flag += " ⚠START"
        if r["end_mismatch_km"] > 8: flag += " ⚠END"
        if r["bridge_dists_km"] and max(r["bridge_dists_km"]) > 15: flag += " ⚠BIGBRIDGE"
        via = " (checkpoints)" if r["used_checkpoints"] else ""
        print(f"{r['id']:>4} | len={r['len_km']:>7}km | pts {r['raw_points']:>6}→{r['simplified_points']:>3} | "
              f"start_mm={r['start_mismatch_km']:>5}km end_mm={r['end_mismatch_km']:>6}km | "
              f"bridges={r['bridge_dists_km']}{flag}{via}")
        if r["legs"]:
            bad_legs = [l for l in r["legs"] if l["end_mismatch_km"] > 5]
            if bad_legs:
                print(f"      leg mismatches: {[(l['leg'], l['end_mismatch_km']) for l in bad_legs]}")
    json.dump(results, open(os.path.join(OUT_DIR, "_report.json"), "w"), ensure_ascii=False, indent=2)
