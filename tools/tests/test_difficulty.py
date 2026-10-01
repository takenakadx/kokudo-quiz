# 難易度の付き方の回帰テスト（生成済みの highways-data.js を読むだけ）
import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "highways-data.js"), encoding="utf-8").read()

routes = {}
for block in re.findall(r"\n  \{\n    id: (\d+),(.*?)\n  \}", src, re.S):
    rid = int(block[0])
    body = block[1]
    routes[rid] = {
        "start": re.search(r'startLabel: "([^"]*)"', body).group(1),
        "end": re.search(r'endLabel: "([^"]*)"', body).group(1),
        "diff": int(re.search(r"difficulty: (\d)", body).group(1)),
        "len": int(re.search(r"lengthKm: (\d+)", body).group(1)),
        "fact": "fact:" in body,
    }

fail = []
def check(name, cond, extra=None):
    print(("PASS" if cond else "FAIL") + "  " + name + (f"  {extra}" if extra is not None else ""))
    if not cond:
        fail.append(name)

dist = collections.Counter(r["diff"] for r in routes.values())
total = len(routes)
check("全路線に難易度が付いている", total > 0 and set(dist) <= {1, 2, 3}, dict(sorted(dist.items())))

# 441路線もあると「かんたん」は相対的な尺度なので、どの段階にも実用的な数が要る。
# 以前は ★1=8 / ★2=80 / ★3=353 で、絞り込みがほとんど機能していなかった
for level in (1, 2, 3):
    share = dist[level] / total
    check(f"★{level} が全体の10%以上を占める（絞り込みとして使える）", share >= 0.10,
          f"{dist[level]}本 ({share*100:.0f}%)")
check("どの段階も全体の6割を超えない（1つに偏っていない）",
      max(dist.values()) / total <= 0.6, f"最大 {max(dist.values())}本 ({max(dist.values())/total*100:.0f}%)")

# 誰もが知っている幹線は「かんたん」側に入っていてほしい
for rid in (1, 2, 4, 6, 7, 8, 58):
    if rid in routes:
        check(f"国道{rid}号（主要幹線）は★1", routes[rid]["diff"] == 1,
              f"{routes[rid]['start']}→{routes[rid]['end']} ★{routes[rid]['diff']}")

# 豆知識を書いた路線は「特徴がある」とみなす。短くても★3には落とさない
for rid in (134, 135):
    if rid in routes:
        r = routes[rid]
        check(f"国道{rid}号（短いが有名、豆知識あり）は★3にならない", r["diff"] <= 2,
              f"{r['len']}km ★{r['diff']}")

# 長さだけで決まっていないこと（以前は200km以上かどうかの1条件だけだった）
short_easy = [i for i, r in routes.items() if r["len"] < 200 and r["diff"] == 1]
long_hard = [i for i, r in routes.items() if r["len"] >= 200 and r["diff"] == 3]
check("200km未満でも★1になる路線がある", len(short_easy) >= 5, f"{len(short_easy)}本")
check("200km以上でも★3になる路線がある", len(long_hard) >= 5, f"{len(long_hard)}本")

# 豆知識のある路線は、無い路線より易しい側に寄る（ボーナスが効いている）
with_fact = [r["diff"] for r in routes.values() if r["fact"]]
without = [r["diff"] for r in routes.values() if not r["fact"]]
check("豆知識のある路線のほうが平均的に易しい",
      sum(with_fact) / len(with_fact) < sum(without) / len(without),
      f"あり {sum(with_fact)/len(with_fact):.2f} / なし {sum(without)/len(without):.2f}")

print()
print("FAILED:" if fail else "all checks passed", fail if fail else "")
sys.exit(1 if fail else 0)
