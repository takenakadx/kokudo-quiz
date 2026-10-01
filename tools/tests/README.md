# テスト

```
bash tools/tests/run_all.sh          # 全部
bash tools/tests/run_all.sh cheat    # 名前で絞って1本だけ
```

Node.js と [Playwright](https://playwright.dev/) が要ります。地図タイルは読まず、
`leaflet-stub.js`（Leafletの最小限の代用）を差し込んで動かすので、
**ネットワークにつながらない環境でも全部動きます**。

Playwright と Chromium の場所は `harness.js` が解決します。見つからない場合は
`PLAYWRIGHT_CHROMIUM=/path/to/chrome` で指定してください。

| テスト | 見ていること |
| --- | --- |
| `test_fetch_raw.py` | 取得スクリプトの番号解釈・欠番の扱い・クエリの正規表現・Overpass JSONの変換 |
| `test_stitch.py` | 細切れにしたwayをつなぎ直すと元のサブラインに戻る（峠のヘアピン対策込み） |
| `test_format_equivalence.py` | `fetch_raw.py` の出力形式でも復元結果が現行と完全一致する |
| `smoke.js` | 全路線のデータ健全性、学習モードの表示、クイズを通しで6問、フィルターの選択肢 |
| `ux.js` | 複数ストローク、2本指=pan・1本指=描画、中ボタンpan、ヒント、採点 |
| `fit.js` | 6種類の画面サイズで1画面に収まる（スクロールせずボタンに届く） |
| `filters.js` | マップ×難易度の絞り込み、山札方式、0件時のフォールバック |
| `studyfilter.js` | 学習モードの分類セレクトと番号検索 |
| `study-zoom.js` | 国道を選ぶとその国道にズームする |
| `cheat.js` | 塗りつぶしで得点を稼げない（チョン置きの連打が近道にならない） |
| `zoomink.js` | ズーム・パンでペン残量が動かない |
| `issue7.js` | 回答後に地図を動かしても軌跡が地図に追従する（Issue #7の回帰） |
| `speccheck.js` | 仕様書ページの件数・欠番の位置・行へのジャンプ・横スクロール |
| `allroutes.js` | 全路線が「完璧になぞれば正解判定になる」形で収録されている |
