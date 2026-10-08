#!/usr/bin/env bash
# テストを全部走らせる。引数に名前を渡すとその1本だけ実行する。
#   bash tools/tests/run_all.sh
#   bash tools/tests/run_all.sh cheat
set -u
cd "$(dirname "$0")"

filter="${1:-}"
pass=0; fail=0; failed=()

run() {  # run <表示名> <コマンド...>
  local name="$1"; shift
  if [ -n "$filter" ] && [[ "$name" != *"$filter"* ]]; then return; fi
  printf '%-26s ' "$name"
  if out=$("$@" 2>&1); then
    echo "OK"; pass=$((pass+1))
  else
    echo "NG"; fail=$((fail+1)); failed+=("$name")
    echo "$out" | tail -12 | sed 's/^/    /'
  fi
}

# 生データの取得まわり（ネットワークにはつながない）
for t in test_fetch_raw test_stitch test_format_equivalence test_difficulty; do
  run "$t" python3 "$t.py"
done

# アプリ本体（Playwright + leaflet-stub.js。地図タイルは読まない）
for t in smoke screens stages ux fit filters studyfilter study-zoom cheat zoomink issue7 gamify speccheck allroutes; do
  run "$t" node "$t.js"
done

echo
if [ "$fail" -eq 0 ]; then
  echo "すべて合格（$pass 本）"
else
  echo "$fail 本が失敗: ${failed[*]}  （合格 $pass 本）"
  exit 1
fi
