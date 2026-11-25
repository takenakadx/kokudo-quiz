# 経路の組み立てのテスト（生データもネットワークも使わない）
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import process_routes as pr  # noqa: E402

fail = []


def check(name, cond, extra=None):
    print(("PASS" if cond else "FAIL") + "  " + name + (f"  {extra}" if extra is not None else ""))
    if not cond:
        fail.append(name)


def line(a, b, n):
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


# ---------------------------------------------------------------------------
# 行って戻るだけの経路を片道にする
#
# 上下線が別々の道として入っている区間では、上り線を端まで行って下り線で戻る形が
# グラフ上は一本道になる。最短経路としては正しいが、地図の上では往復していて
# 長さも倍になる（第三京浜=国道466号、国道129号など）。
# ---------------------------------------------------------------------------
out = line((35.0, 139.0), (35.3, 139.0), 60)
back = [(p[0], p[1] + 0.0005) for p in out[::-1]]      # 50mほど隣を戻る＝下り線
doubled = out + back[1:]
cut = pr.undouble(doubled)
check("往復している経路は片道になる",
      len(cut) == len(out) and cut[-1][0] > 35.29,
      f"{len(doubled)}点 {pr.chain_length_km(doubled):.1f}km → "
      f"{len(cut)}点 {pr.chain_length_km(cut):.1f}km")

straight = line((35.0, 139.0), (35.3, 139.5), 60)
check("ふつうの経路はそのまま", pr.undouble(straight) == straight)

# 環状の路線は両端が近いが、後半は前半から離れている（国道468号＝圏央道など）
ring = (line((35.0, 139.0), (35.3, 139.0), 20) + line((35.3, 139.0), (35.3, 139.4), 20)[1:]
        + line((35.3, 139.4), (35.0, 139.4), 20)[1:] + line((35.0, 139.4), (35.0, 139.0), 20)[1:])
check("環状の経路は切らない", pr.undouble(ring) == ring,
      f"端点間 {pr.haversine(ring[0], ring[-1]):.2f}km")

tail = out + [(p[0], p[1] + 0.0005) for p in out[::-1][:6]]
check("終わりが少し戻るだけなら切らない", pr.undouble(tail) == tail,
      f"{len(tail)}点のうち戻りは{6}点")

check("点が少なすぎる経路はそのまま", pr.undouble(out[:4]) == out[:4])


# ---------------------------------------------------------------------------
# 最後の区間は終点ぎりぎりまで歩く
#
# 途中の経由地は「近くまで来たら次の区間へ」でよいが、最後の経由地＝路線の終点で
# 同じ4kmで止めると、終点の手前数kmで経路が終わる（国道2号の門司、22号の岐阜）。
# ---------------------------------------------------------------------------
# 本線（約30km）と、その先に別々の線として入っている終点側の区間（約3km）。
# 生データでは橋やトンネルが別のwayになっていて、こう分かれていることが多い。
chain = line((35.0, 139.0), (35.27, 139.0), 110)
tip = line((35.27, 139.0), (35.3, 139.0), 12)
target = tip[-1]


def walk(stop_km):
    sig = [list(chain), list(tip)]
    lens = [pr.chain_length_km(c) for c in sig]
    return pr.walk_leg(sig, lens, [False, False], chain[0], target, stop_km=stop_km)[0]


far = walk(None)        # 既定（4kmで止まる）
near = walk(0.3)
d_far = pr.haversine(far[-1], target)
d_near = pr.haversine(near[-1], target)
check("既定では終点の手前で止まる", d_far > 1.0, f"終点まで{d_far:.1f}km")
check("stop_kmを小さくすると終点まで歩く", d_near < 0.5, f"終点まで{d_near:.1f}km")
check("終点まで歩いたほうが経路は長い",
      pr.chain_length_km(near) > pr.chain_length_km(far),
      f"{pr.chain_length_km(far):.1f}km → {pr.chain_length_km(near):.1f}km")

# 最後の区間にだけ効いていること（経由地が3つなら、途中は既定のまま）
mid = chain[55]
path, legs = pr.bridge_via_checkpoints([list(chain), list(tip)], [chain[0], mid, target])
check("経由地つきでも終点まで届く", pr.haversine(path[-1], target) < 0.5,
      f"終点まで{pr.haversine(path[-1], target):.1f}km")

print()
if fail:
    print(f"{len(fail)} 件失敗: {fail}")
    sys.exit(1)
print("すべて合格")
