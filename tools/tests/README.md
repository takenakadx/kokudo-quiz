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

## クイズを操作するヘルパー（`harness.js` の `QZ`）

クイズ画面を触るテストは、ボタンのIDや地図の座標を直接いじらず、`harness.js` が
ページに注入する `window.QZ` を通します。**クイズのUIを変えたときに直すのは
`harness.js` だけで済む**ようにするためです（#16 の画面遷移化に備えた作り）。

```js
const { chromium, EXEC, APP, STUB, openQuiz } = require('./harness');
...
await openQuiz(page);                  // タイトル→ステージ選択→出題と進み、QZ を使えるようにする
// 図鑑（学習モード）なら await openStudy(page);
await page.evaluate(() => {
  QZ.ask(4);                           // 国道4号を1問出す（'route' を渡すとその国道に寄る）
  QZ.stroke(0, QZ.points() - 1, 1, 60);// 正解ルートをなぞる
  QZ.submit();                         // 採点する
  return QZ.score();                   // 網羅率とペン消費
});
```

| 種類 | メソッド |
| --- | --- |
| 画面の操作 | `enter` `openStage` `openStudy` `startRandom` `ask` `submit` `next` `hint` `undo` `clearAll` `quit` |
| 画面の状態 | `screen` `can`（押せるボタン）`prompt` `result` `resultHtml` `hintText` `startLabel` `state` |
| なぞる | `at` `atT` `ev` `stroke` `strokeT` `traceAll` `dab` |
| 測る | `score` `routePx` `firstStrokeScreen` |

ボタンが押せるかどうかは `disabled` を直接見ずに `QZ.can()` を使います。
ボタンの配置や有無が変わってもテストが壊れないようにするためです。

なぞる操作は、1ストロークの間は最初に測った地図の位置を使い続けます。なぞっている
最中にヒントの文言が変わると地図の高さが1px動き、路線によっては網羅率が
5〜12ポイント変わるためです（実際の指も、画面が少しずれても同じ場所を触り続けます）。

| テスト | 見ていること |
| --- | --- |
| `test_fetch_raw.py` | 取得スクリプトの番号解釈・欠番の扱い・クエリの正規表現・Overpass JSONの変換 |
| `test_stitch.py` | 細切れにしたwayをつなぎ直すと元のサブラインに戻る（峠のヘアピン対策込み） |
| `test_format_equivalence.py` | `fetch_raw.py` の出力形式でも復元結果が現行と完全一致する |
| `test_difficulty.py` | 難易度がどの段階にも実用的な数で割れているか、主要幹線が★1か、豆知識が効いているか |
| `smoke.js` | 全路線のデータ健全性、学習モードの表示、クイズを通しで6問、フィルターの選択肢 |
| `screens.js` | 画面遷移（タイトル→ステージ選択→出題→判定）と、その場面で出るボタン |
| `ux.js` | 複数ストローク、2本指=pan・1本指=描画、中ボタンpan、ヒント、採点 |
| `fit.js` | 6種類の画面サイズで1画面に収まる（スクロールせずボタンに届く） |
| `filters.js` | マップ×難易度の絞り込み、山札方式、0件時のフォールバック |
| `studyfilter.js` | 学習モードの分類セレクトと番号検索 |
| `study-zoom.js` | 国道を選ぶとその国道にズームする |
| `cheat.js` | 塗りつぶしで得点を稼げない（チョン置きの連打が近道にならない） |
| `zoomink.js` | ズーム・パンでペン残量が動かない |
| `gamify.js` | 連続正解・習熟度バッジ・制覇率・学習モードの閲覧記録（Issue #4） |
| `issue7.js` | 回答後に地図を動かしても軌跡が地図に追従する（Issue #7の回帰） |
| `speccheck.js` | 仕様書ページの件数・欠番の位置・行へのジャンプ・横スクロール |
| `allroutes.js` | 全路線が「完璧になぞれば正解判定になる」形で収録されている |
