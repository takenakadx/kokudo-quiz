# 実ルートデータの取得手順

`highways-data.js` の `waypoints` は現在、主要都市を手動で結んだ折れ線です。
このフォルダに実際の道路線形（OpenStreetMapの経路データ）を置いてもらえれば、
Claude 側でそれを取り込んで `waypoints` をより正確な形状に置き換えます。

この開発環境からは Overpass API・OSRM などの外部APIに一切アクセスできない
状態のため、お手数をおかけしますがユーザー側で取得をお願いします。

## 使うツール

**[Overpass Turbo](https://overpass-turbo.eu/)** というブラウザで動くツールを使います。
インストール不要、ブラウザで開くだけで使えます。

## 手順（1国道ごとに繰り返す）

1. https://overpass-turbo.eu/ を開く
2. 左側のクエリ入力欄の中身を全部消して、下の「国道ごとのクエリ一覧」から
   対象の国道のクエリをコピペする
3. 上部の **Run**（▶ ボタン、またはCtrl+Enter）を押す
4. 少し待つと地図上に経路が赤くハイライトされる。だいたい正しいルート
   （起点〜終点、経由都市）になっているかサラッと目視確認する
   - 何も表示されない/エラーになる場合は、このファイル末尾の「うまく
     ヒットしない場合」を参照
5. 右上メニューの **Export** ボタン → **GeoJSON** を選ぶとダウンロードされる
6. ダウンロードしたファイルを、下の対応表のファイル名にリネームして
   このフォルダ（`data-raw/`）に置く
7. 全部の国道について1〜6を繰り返す

終わったら教えてください。こちらでファイルを取り込んで `highways-data.js` を
更新します（そのままリポジトリに置いてpushしてもらってもOKです）。

## 国道ごとのクエリ一覧・出力ファイル名

各クエリの `国道◯号` の部分だけが違います。国道名の後ろに「線」が付く
表記ゆれ（例: 「国道1号線」）にも `~` (正規表現部分一致) でマッチするように
してあります。

| 国道 | 出力ファイル名 |
|---|---|
| 国道1号 | `data-raw/1.geojson` |
| 国道2号 | `data-raw/2.geojson` |
| 国道3号 | `data-raw/3.geojson` |
| 国道4号 | `data-raw/4.geojson` |
| 国道5号 | `data-raw/5.geojson` |
| 国道6号 | `data-raw/6.geojson` |
| 国道7号 | `data-raw/7.geojson` |
| 国道8号 | `data-raw/8.geojson` |
| 国道9号 | `data-raw/9.geojson` |
| 国道10号 | `data-raw/10.geojson` |
| 国道11号 | `data-raw/11.geojson` |
| 国道12号 | `data-raw/12.geojson` |
| 国道14号 | `data-raw/14.geojson` |
| 国道15号 | `data-raw/15.geojson` |
| 国道16号 | `data-raw/16.geojson` |
| 国道17号 | `data-raw/17.geojson` |
| 国道19号 | `data-raw/19.geojson` |
| 国道20号 | `data-raw/20.geojson` |
| 国道22号 | `data-raw/22.geojson` |
| 国道23号 | `data-raw/23.geojson` |
| 国道25号 | `data-raw/25.geojson` |
| 国道41号 | `data-raw/41.geojson` |
| 国道42号 | `data-raw/42.geojson` |
| 国道43号 | `data-raw/43.geojson` |
| 国道58号 | `data-raw/58.geojson`（※大半が海上区間のため、データが取れない/歯抜けになる可能性が高いです。ダメそうなら省略してOKです） |
| 国道134号 | `data-raw/134.geojson` |
| 国道135号 | `data-raw/135.geojson` |
| 国道158号 | `data-raw/158.geojson` |
| 国道171号 | `data-raw/171.geojson` |
| 国道176号 | `data-raw/176.geojson` |
| 国道246号 | `data-raw/246.geojson` |
| 国道317号 | `data-raw/317.geojson` |
| 国道357号 | `data-raw/357.geojson` |
| 国道411号 | `data-raw/411.geojson` |
| 国道413号 | `data-raw/413.geojson` |
| 国道439号 | `data-raw/439.geojson` |

上の3〜43号の14本、134〜439号の3桁国道10本は、収録国道を増やすタスク（Issue #2）向けに新しく追加した候補です。

### クエリのテンプレート

```
[out:json][timeout:180];
area["ISO3166-1"="JP"][admin_level=2]->.jp;
relation(area.jp)["route"="road"]["name"~"国道1号"];
out body;
>;
out skel qt;
```

`"国道1号"` の部分を対象の国道名に変えて使ってください（1号なら `国道1号`、
2号なら `国道2号`、16号なら `国道16号`、246号なら `国道246号`、という具合です）。

## うまくヒットしない場合

- 結果が0件、または地図に何も表示されない場合：
  - クエリ内の `"name"~"国道1号"` を `"ref"~"1"` に変えて、
    `relation(area.jp)["route"="road"]["network"="JP:national"]["ref"~"^1$"];`
    のような形で再検索してみてください（`ref`タグの表記は路線によって
    "1" や "R1" などブレがあるため、うまくいかない場合は `^1$` の部分を
    `1` だけにしたり `R1` を試したりしてください）
  - それでもダメな場合は、画面上部の **Wizard** ボタンを押し、
    `route=road and ref=1 in "Japan"` のように入力して「Build and run query」
    を押すと、タグの組み合わせを自動で探してくれます
- 複数の経路（relation）がヒットしてしまう場合：
  - 地図を見て、実際の国道と思われるものだけを選ぶか、クエリに
    `["network"="JP:national"]` を追加して国道以外（都道府県道など）を
    除外してみてください
- 経路が途中で途切れている/一部しか表示されない場合：
  - そのままで構いません。取れた範囲のデータだけでも、今の手描きの
    折れ線よりは精度が上がります
