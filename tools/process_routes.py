#!/usr/bin/env python3
"""
data-raw/ に置かれた国道の実ルートGeoJSON(Overpass Turboで取得したもの)を、
なぞりクイズ用の1本の折れ線(始点→終点)に変換するスクリプト。

Overpassからのエクスポートは、ルートを構成する多数の断片的な線分
(MultiLineStringの各サブライン)がバラバラの順序・向きで入っているため、
以下の手順で1本のルートに組み立てる。

1. 端点の座標が完全一致する断片同士を連結する(exact_merge)
2. CHECKPOINTS に人手で与えた経由都市を、実データ上の最も近い点にスナップする
   (snap_checkpoints)
3. 経由地から次の経由地までを1区間として、その区間内で断片をつないでいく
   (walk_leg)。足元につながっている道を優先し、つながっていなければ段階的に
   探索範囲を広げる。長い断片には途中から進入でき、使わなかった部分は
   あとの区間のために戻す。区間を短く切ることで、分岐を取り違えても
   影響がその区間内に収まる。
4. Douglas-Peucker法で間引いて、ゲームで使うのに十分な点数(300点以下)まで
   単純化する。

出力は tools/processed/<id>.json に [緯度, 経度] の配列として保存される。
生成後は表示される品質指標を必ず確認すること。特に maxjump(経路上で連続する
2点間の最大距離)が大きい場合は、その付近で生データが欠けているか、経由地が
実際の道から離れた場所を指している。環状路線(16号など)は始点=終点なので、
端点の一致だけでは正しさを判定できない点にも注意。

使い方: python3 tools/process_routes.py
"""
import json, math, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data-raw")
OUT_DIR = os.path.join(SCRIPT_DIR, "processed")
os.makedirs(OUT_DIR, exist_ok=True)


# 各国道が通る主要都市・峠を、通る順(起点→終点)に並べたもの。先頭が起点、末尾が終点。
# Overpassのエクスポートは順序も向きもバラバラな断片の集まりなので、単純な
# 「起点から近い断片を貪欲につなぐ」方式では長い路線で経路が迷子になる。経由地間の
# 短い区間に分けて組み立てることで、分岐を取り違えてもその区間内に影響が収まる。
# 座標は大まかでよい(実データ上の最も近い点に自動でスナップされる)が、通る順序と
# 「どの道を通るか」は正しく与える必要がある。実在しない経由地を書くと、そこへ
# 向かおうとして経路が乱れる(下の 9号・19号・439号 のコメント参照)。
# 生データの実際の始点・終点が公式の起点・終点と違う路線もある(11/23/25/357/411号)。
CHECKPOINTS = {
    1: [(35.68, 139.77), (35.53, 139.70), (35.44, 139.64), (35.34, 139.49), (35.26, 139.16),
        (35.10, 138.86), (35.16, 138.68), (34.98, 138.38), (34.77, 137.99), (34.71, 137.73),
        (34.77, 137.39), (34.95, 137.17), (35.18, 136.91), (35.13, 136.79), (35.11, 136.72),
        (35.06, 136.69), (34.97, 136.62), (34.86, 136.45), (34.85, 136.39), (34.93, 136.20),
        (34.97, 136.17), (35.00, 136.03), (35.02, 135.96), (35.01, 135.87), (35.01, 135.77),
        (34.69, 135.50)],
    2: [(34.69, 135.50), (34.69, 135.19), (34.65, 134.99), (34.75, 134.84), (34.82, 134.69),
        (34.85, 134.55), (34.80, 134.47), (34.74, 134.19), (34.66, 133.92), (34.60, 133.77),
        (34.51, 133.51), (34.49, 133.36), (34.41, 133.20), (34.40, 133.08), (34.43, 132.74),
        (34.40, 132.46), (34.35, 132.33), (34.17, 132.22), (34.10, 132.05), (34.05, 131.81),
        (34.05, 131.57), (34.09, 131.40), (34.00, 131.18), (33.95, 130.94), (33.94, 130.96)],
    # 3号は大牟田市街は通らず南関・玉東を経て熊本へ
    3: [(33.94, 130.96), (33.88, 130.88), (33.86, 130.76), (33.65, 130.43), (33.59, 130.41),
        (33.53, 130.47), (33.38, 130.51), (33.32, 130.51), (33.21, 130.52), (33.06, 130.58),
        (32.95, 130.60), (32.80, 130.71), (32.69, 130.66), (32.51, 130.60), (32.30, 130.51),
        (32.21, 130.40), (32.09, 130.35), (32.02, 130.20), (31.81, 130.30), (31.60, 130.56)],
    4: [(35.68, 139.77), (35.75, 139.80), (35.83, 139.81), (35.98, 139.75), (36.19, 139.70),
        (36.31, 139.80), (36.56, 139.88), (36.81, 139.93), (36.96, 140.05), (37.13, 140.21),
        (37.40, 140.36), (37.76, 140.47), (38.00, 140.62), (38.26, 140.87), (38.57, 140.96),
        (38.93, 141.13), (39.29, 141.11), (39.70, 141.15), (39.92, 141.25), (40.27, 141.30),
        (40.38, 141.26), (40.61, 141.21), (40.87, 141.12), (40.82, 140.74)],
    5: [(41.77, 140.73), (41.86, 140.69), (41.98, 140.67), (42.11, 140.58), (42.25, 140.27),
        (42.51, 140.38), (42.81, 140.51), (42.80, 140.69), (42.90, 140.75), (43.19, 140.79),
        (43.19, 141.00), (43.09, 141.24), (43.06, 141.35)],
    6: [(35.68, 139.77), (35.73, 139.80), (35.79, 139.90), (35.86, 139.97), (35.91, 140.06),
        (35.95, 140.15), (36.08, 140.20), (36.19, 140.29), (36.37, 140.47), (36.59, 140.65),
        (36.71, 140.71), (36.80, 140.75), (37.05, 140.89), (37.22, 141.00), (37.40, 141.00),
        (37.64, 140.97), (37.80, 140.92), (38.10, 140.87), (38.26, 140.87)],
    7: [(37.92, 139.04), (37.95, 139.33), (38.05, 139.42), (38.22, 139.48), (38.48, 139.55),
        (38.73, 139.83), (38.91, 139.84), (38.92, 139.91), (39.20, 139.91), (39.39, 140.05),
        (39.72, 140.10), (39.95, 140.05), (40.21, 140.03), (40.22, 140.37), (40.27, 140.57),
        (40.60, 140.46), (40.82, 140.74)],
    8: [(37.92, 139.04), (37.63, 138.96), (37.45, 138.85), (37.37, 138.56), (37.15, 138.24),
        (37.04, 137.86), (36.87, 137.45), (36.70, 137.21), (36.75, 137.03), (36.56, 136.65),
        (36.41, 136.45), (36.06, 136.22), (35.65, 136.07), (35.38, 136.28), (35.27, 136.26),
        (35.13, 136.10), (35.02, 135.96), (35.01, 135.77)],
    # 9号は豊岡/長門は通らない(和田山経由・萩から内陸へ入り山口/小郡を通って下関)
    9: [(35.01, 135.77), (35.02, 135.57), (35.30, 135.13), (35.34, 134.85), (35.50, 134.24),
        (35.40, 133.84), (35.43, 133.33), (35.47, 133.05), (35.37, 132.76), (35.19, 132.50),
        (34.90, 132.08), (34.67, 131.85), (34.41, 131.40), (34.18, 131.47), (34.09, 131.40),
        (33.95, 130.94)],
    # 10号の生データは門司ではなく小倉付近から始まる
    10: [(33.88, 130.88), (33.73, 130.98), (33.60, 131.19), (33.53, 131.35),
         (33.28, 131.49), (33.24, 131.61), (33.12, 131.72), (32.96, 131.85), (32.79, 131.75),
         (32.58, 131.66), (32.42, 131.62), (32.25, 131.55), (32.12, 131.50), (31.91, 131.42),
         (31.72, 131.06), (31.74, 130.76), (31.60, 130.56)],
    # 11号は「松山→高知」ではなく徳島市→松山市(生データのbboxでも確認済み)
    11: [(34.07, 134.55), (34.13, 134.44), (34.22, 134.34), (34.32, 134.17), (34.34, 134.05),
         (34.33, 133.95), (34.32, 133.86), (34.29, 133.80), (34.24, 133.74), (34.13, 133.66),
         (33.98, 133.55), (33.96, 133.28), (33.92, 133.18), (33.87, 132.98), (33.84, 132.77)],
    12: [(43.06, 141.35), (43.10, 141.54), (43.20, 141.78), (43.33, 141.85), (43.49, 141.90),
         (43.56, 141.91), (43.72, 142.05), (43.77, 142.36)],
    # 13号は米沢から南陽(赤湯)・上山を経て山形へ。新庄以北は金山・雄勝峠を越えて湯沢へ
    13: [(37.76, 140.47), (37.82, 140.32), (37.91, 140.12), (38.05, 140.17), (38.15, 140.27),
         (38.25, 140.34), (38.36, 140.38), (38.48, 140.38), (38.60, 140.40), (38.76, 140.30),
         (38.88, 140.34), (39.17, 140.50), (39.31, 140.55), (39.45, 140.48), (39.55, 140.32),
         (39.72, 140.10)],
    14: [(35.68, 139.77), (35.69, 139.79), (35.70, 139.81), (35.70, 139.83), (35.72, 139.93),
         (35.70, 139.98), (35.66, 140.05), (35.61, 140.11)],
    15: [(35.68, 139.77), (35.67, 139.76), (35.63, 139.74), (35.59, 139.73), (35.56, 139.72),
         (35.53, 139.70), (35.51, 139.68), (35.47, 139.63)],
    # 16号はさいたま市中心部や船橋市街ではなく、その外側(西大宮・岩槻・白井)を通る
    16: [(35.44, 139.64), (35.55, 139.45), (35.66, 139.32), (35.83, 139.39), (35.92, 139.48),
         (35.89, 139.56), (35.91, 139.62), (35.95, 139.70), (35.98, 139.75), (35.95, 139.87),
         (35.85, 139.93), (35.79, 140.05), (35.70, 140.08), (35.60, 140.12), (35.38, 139.92),
         (35.28, 139.67), (35.44, 139.64)],
    17: [(35.68, 139.77), (35.71, 139.76), (35.75, 139.74), (35.86, 139.66), (35.91, 139.62),
         (35.98, 139.59), (36.14, 139.39), (36.20, 139.28), (36.24, 139.19), (36.32, 139.00),
         (36.39, 139.07), (36.49, 139.00), (36.65, 139.05), (36.68, 138.99), (36.79, 138.83),
         (36.94, 138.82), (37.07, 138.88), (37.24, 138.95), (37.31, 138.80), (37.45, 138.85),
         (37.53, 138.92), (37.63, 138.96), (37.92, 139.04)],
    # 18号は碓氷峠を越えて信濃路へ。長野以北は牟礼・信濃町・妙高高原を経て上越へ
    18: [(36.32, 139.00), (36.32, 138.89), (36.30, 138.80), (36.35, 138.63), (36.32, 138.42),
         (36.40, 138.25), (36.46, 138.18), (36.53, 138.13), (36.65, 138.19), (36.70, 138.26),
         (36.78, 138.22), (36.85, 138.20), (36.87, 138.19), (37.02, 138.25), (37.15, 138.24)],
    # 19号は松本から犀川沿い(明科・信州新町)を北上する。千曲市は通らない(18号)
    19: [(35.18, 136.91), (35.25, 136.97), (35.33, 137.13), (35.36, 137.18), (35.36, 137.25),
         (35.45, 137.41), (35.49, 137.50), (35.60, 137.60), (35.71, 137.72), (35.78, 137.75),
         (35.85, 137.69), (36.11, 137.95), (36.24, 137.97), (36.31, 137.93), (36.43, 137.92),
         (36.52, 138.02), (36.65, 138.18)],
    20: [(35.68, 139.77), (35.69, 139.73), (35.69, 139.70), (35.68, 139.61), (35.65, 139.54),
         (35.67, 139.48), (35.66, 139.32), (35.64, 139.27), (35.61, 139.16), (35.61, 138.94),
         (35.66, 138.57), (35.71, 138.45), (35.87, 138.32), (35.99, 138.16), (36.04, 138.11),
         (36.06, 138.05), (36.11, 137.95)],
    # 21号は中山道筋。瑞浪から御嵩・坂祝を経て木曽川南岸を西進し、関ケ原を越えて米原へ
    21: [(35.36, 137.25), (35.35, 137.18), (35.42, 137.13), (35.43, 137.06), (35.41, 136.97),
         (35.40, 136.85), (35.39, 136.76), (35.39, 136.69), (35.36, 136.62), (35.37, 136.53),
         (35.37, 136.46), (35.32, 136.29)],
    22: [(35.17, 136.89), (35.21, 136.86), (35.24, 136.85), (35.28, 136.80), (35.30, 136.80),
         (35.37, 136.77), (35.39, 136.76)],
    # 23号の起点は名古屋ではなく豊橋(名豊道路〜名四国道を経て伊勢へ)
    23: [(34.76, 137.38), (34.83, 137.22), (34.86, 137.13), (34.87, 137.05), (34.89, 136.94),
         (35.02, 136.89), (35.09, 136.88), (35.02, 136.68), (34.96, 136.63), (34.88, 136.58),
         (34.72, 136.51), (34.58, 136.53), (34.49, 136.71)],
    # 24号は奈良盆地を南下し、橿原から大和高田・御所・五條を経て紀の川沿いを下る
    24: [(34.99, 135.76), (34.93, 135.76), (34.89, 135.80), (34.85, 135.78), (34.79, 135.79),
         (34.73, 135.82), (34.68, 135.80), (34.65, 135.78), (34.60, 135.77), (34.51, 135.79),
         (34.51, 135.73), (34.46, 135.74), (34.35, 135.69), (34.32, 135.60), (34.27, 135.40),
         (34.26, 135.31), (34.23, 135.17)],
    # 25号の名古屋〜四日市は国道1号との重複区間で、生データには四日市以西しかない
    25: [(34.93, 136.62), (34.86, 136.45), (34.85, 136.39), (34.77, 136.13), (34.60, 135.84),
         (34.65, 135.78), (34.59, 135.70), (34.58, 135.63), (34.63, 135.60), (34.69, 135.50)],
    26: [(34.69, 135.50), (34.57, 135.47), (34.53, 135.44), (34.50, 135.41), (34.46, 135.37),
         (34.44, 135.36), (34.40, 135.32), (34.36, 135.27), (34.35, 135.24), (34.31, 135.16),
         (34.23, 135.17)],
    27: [(35.65, 136.06), (35.60, 135.95), (35.52, 135.90), (35.50, 135.75), (35.48, 135.55),
         (35.45, 135.33), (35.30, 135.25), (35.16, 135.41)],
    # 28号は明石海峡と鳴門海峡が海上区間で、生データはその2か所で必ず途切れる
    28: [(34.66, 135.15), (34.59, 135.02), (34.44, 134.90), (34.34, 134.90), (34.25, 134.75),
         (34.17, 134.61), (34.07, 134.55)],
    # 29号は姫路から夢前・安富を経て山崎へ。波賀から戸倉峠を越えて若桜・八頭へ。
    # 生データは姫路市街を含まず市北部(砥堀付近)から始まり、鳥取側も市街手前で終わる
    29: [(34.86, 134.62), (34.90, 134.58), (34.99, 134.59), (35.12, 134.57), (35.21, 134.52),
         (35.32, 134.42), (35.38, 134.29), (35.47, 134.24)],
    # 30号は宇野〜高松が宇高航路(海上区間)なので、生データは玉野市で途切れる
    30: [(34.66, 133.92), (34.49, 133.95), (34.34, 134.05)],
    31: [(34.37, 132.53), (34.32, 132.51), (34.25, 132.56)],
    # 32号は讃岐から猪ノ鼻峠を越えて池田へ。以降は吉野川・大歩危沿いに南下する
    32: [(34.34, 134.05), (34.22, 133.95), (34.19, 133.82), (34.11, 133.77), (34.06, 133.79),
         (34.03, 133.81), (33.87, 133.80), (33.77, 133.66), (33.58, 133.64), (33.56, 133.53)],
    # 33号は仁淀川沿いに佐川・越知を経て遡り、三坂峠を越えて松山へ下りる
    33: [(33.56, 133.53), (33.55, 133.43), (33.53, 133.36), (33.50, 133.28), (33.54, 133.25),
         (33.58, 133.13), (33.65, 132.90), (33.72, 132.85), (33.84, 132.77)],
    # 34号は長崎街道筋。嬉野から俵坂峠を越えて東彼杵・大村湾沿いへ入る
    34: [(33.38, 130.51), (33.31, 130.37), (33.26, 130.30), (33.27, 130.20), (33.19, 130.02),
         (33.10, 129.99), (33.02, 129.91), (32.90, 129.96), (32.84, 130.05), (32.75, 129.87)],
    41: [(35.17, 136.92), (35.24, 136.94), (35.38, 136.94), (35.44, 137.01), (35.55, 137.08),
         (35.63, 137.13), (35.72, 137.16), (35.80, 137.24), (36.03, 137.25), (36.14, 137.25),
         (36.34, 137.30), (36.44, 137.23), (36.70, 137.21)],
    42: [(34.23, 135.17), (33.89, 135.15), (33.73, 135.38), (33.55, 135.52), (33.72, 135.98),
         (33.90, 136.10), (34.07, 136.20), (34.58, 136.53)],
    43: [(34.69, 135.50), (34.71, 135.42), (34.71, 135.36), (34.73, 135.34), (34.72, 135.30),
         (34.71, 135.26), (34.69, 135.22)],
    # 58号は大半が海上区間(フェリー)なので、島ごとの上陸地点をチェックポイントにする
    58: [(31.60, 130.56), (30.73, 131.00), (28.38, 129.49), (26.59, 127.98),
         (26.33, 127.80), (26.21, 127.68)],
    134: [(35.28, 139.67), (35.29, 139.58), (35.31, 139.55), (35.31, 139.53), (35.31, 139.48),
          (35.32, 139.40), (35.31, 139.34), (35.31, 139.33)],
    135: [(35.10, 139.07), (35.03, 139.09), (34.97, 139.10), (34.93, 139.13), (34.89, 139.13),
          (34.87, 139.11), (34.83, 139.05), (34.79, 139.04), (34.76, 139.02), (34.68, 138.95)],
    158: [(36.06, 136.25), (35.98, 136.49), (35.93, 136.70), (35.90, 136.88), (36.14, 137.25),
          (36.16, 137.34), (36.17, 137.55), (36.15, 137.60), (36.14, 137.68), (36.13, 137.77),
          (36.20, 137.87), (36.23, 137.95)],
    171: [(34.98, 135.75), (34.95, 135.70), (34.93, 135.70), (34.85, 135.62), (34.82, 135.57),
          (34.78, 135.52), (34.78, 135.47), (34.78, 135.40), (34.74, 135.34), (34.69, 135.22)],
    176: [(34.70, 135.50), (34.72, 135.48), (34.77, 135.47), (34.82, 135.43), (34.84, 135.42),
          (34.80, 135.36), (34.89, 135.23), (35.07, 135.22), (35.30, 135.13), (35.45, 135.33)],
    246: [(35.68, 139.74), (35.66, 139.70), (35.55, 139.45), (35.44, 139.36), (35.37, 139.22),
          (35.31, 138.93), (35.10, 138.86)],
    # 357号の起点は木更津ではなく千葉市(生データのbboxでも確認済み)
    357: [(35.58, 140.12), (35.65, 140.06), (35.65, 139.90), (35.63, 139.80), (35.60, 139.75),
          (35.55, 139.76), (35.51, 139.72), (35.46, 139.64), (35.44, 139.67), (35.32, 139.66)],
    # 411号の新宿〜青梅は青梅街道の重複区間で、生データには青梅以西しかない
    411: [(35.79, 139.32), (35.81, 139.10), (35.78, 138.94), (35.76, 138.83), (35.70, 138.73),
          (35.66, 138.57)],
    413: [(35.60, 139.34), (35.58, 139.25), (35.55, 139.15), (35.52, 139.02), (35.42, 138.87),
          (35.49, 138.79)],
    # 439号は吉野川北岸(192号)ではなく神山・木屋平・剣山の山間部を抜ける
    439: [(34.07, 134.55), (34.07, 134.44), (33.93, 134.35), (33.88, 134.13), (33.86, 133.93),
          (33.77, 133.66), (33.75, 133.60), (33.73, 133.53), (33.65, 133.33), (33.56, 133.15),
          (33.39, 132.93), (33.15, 132.98), (32.98, 132.94)],
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

def nearest_index(chain, pt, coarse=160):
    """Index of the chain point closest to pt. Scanned coarsely first and then refined
    around the winner, so joining a 3000-point chain mid-way stays cheap."""
    n = len(chain)
    if n <= coarse:
        return min(range(n), key=lambda k: haversine(chain[k], pt))
    stride = n // coarse + 1
    idxs = range(0, n, stride)
    best = min(idxs, key=lambda k: haversine(chain[k], pt))
    lo, hi = max(0, best - stride), min(n, best + stride + 1)
    return min(range(lo, hi), key=lambda k: haversine(chain[k], pt))

def walk_leg(sig, sig_lens, used, cur_pt, target_pt, entry_radius_km=8.0,
             max_bridge_km=30.0, arrive_km=4.0, max_steps=60):
    """Checkpoint-mode leg walk: at each step, among chains whose entry point is
    reasonably close to the current position, pick whichever one's closest approach
    to THIS leg's target gets us nearest (not simply "longest nearby chain", which is
    wrong once legs are short - a long chain heading the wrong way looks tempting but
    doesn't serve a short leg). Truncate at that closest-approach point and push the
    remainder back into the pool for later legs."""
    path = [cur_pt]
    bridges = []
    for _ in range(max_steps):
        current = path[-1]
        d_to_target = haversine(current, target_pt)
        if d_to_target <= arrive_km:
            break
        all_entries = []
        for i, c in enumerate(sig):
            if used[i]:
                continue
            e = nearest_index(c, current)
            d = haversine(c[e], current)
            if d <= max_bridge_km:
                all_entries.append((d, i, e))
        if not all_entries:
            break

        # Widen the search in tiers: keep following road that actually connects to
        # where we stand before considering a jump across a gap. Ranking purely by
        # "gets closest to the target" would happily leap to a stray fragment several
        # km away instead of taking the road at our feet.
        advanced = False
        for radius in (0.5, 2.0, 5.0, entry_radius_km, max_bridge_km):
            ranked = []
            for d_entry, i, e in all_entries:
                if d_entry > radius or used[i]:
                    continue
                c = sig[i]
                # from the entry point the chain can be followed either way; take
                # whichever direction comes closest to this leg's target
                for direction in (1, -1):
                    sub = c[e:] if direction == 1 else c[e::-1]
                    if len(sub) < 2:
                        continue
                    dists = [haversine(p, target_pt) for p in sub]
                    idx_min = min(range(len(dists)), key=lambda k: dists[k])
                    ranked.append((dists[idx_min], d_entry, i, e, direction, idx_min, sub))
            ranked.sort(key=lambda r: (r[0], r[1]))
            for approach_dist, d_entry, i, e, direction, idx_min, sub in ranked:
                if approach_dist >= d_to_target:
                    break  # nothing in this tier gets us closer than we already are
                seg = sub[:idx_min + 1]
                if seg and haversine(seg[0], current) < 0.001:
                    seg = seg[1:]  # entry point coincides with where we stand
                if not seg:
                    continue       # this chain would add nothing - try the next one
                used[i] = True
                # the parts of the chain this leg did not consume go back into the pool
                c = sig[i]
                if direction == 1:
                    remainders = [c[:e + 1], c[e + idx_min:]]
                else:
                    remainders = [c[e:], c[:e - idx_min + 1]]
                for rem in remainders:
                    if len(rem) >= 2 and chain_length_km(rem) >= 0.5:
                        sig.append(rem)
                        sig_lens.append(chain_length_km(rem))
                        used.append(False)
                if d_entry > 0.05:
                    bridges.append(round(d_entry, 2))
                path.extend(seg)
                advanced = True
                break
            if advanced:
                break
        if not advanced:
            break
    reached = haversine(path[-1], target_pt) <= 8.0
    return path, bridges, reached

def bridge_via_checkpoints(chains, checkpoints, min_significant_km=0.2, max_bridge_km=15.0, near_radius_km=5.0):
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
    prev_reached = True
    for i in range(len(checkpoints) - 1):
        a, b = checkpoints[i], checkpoints[i + 1]
        # continue from where the previous leg actually ended, so the path stays
        # continuous - but if that leg failed to arrive, re-enter at this checkpoint
        # instead, otherwise one gap in the data derails every remaining leg
        start_pt = full_path[-1] if (full_path and prev_reached) else a
        leg_path, leg_bridges, reached = walk_leg(sig, sig_lens, used, start_pt, b)
        prev_reached = reached
        end_mismatch = round(haversine(leg_path[-1], b), 1)
        legs.append({"leg": i, "reached": reached, "end_mismatch_km": end_mismatch,
                     "bridges": leg_bridges, "points": len(leg_path)})
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

def checkpoint_coverage(route_id):
    """For each checkpoint, the distance to the nearest point present in the raw data.
    A large value means the export simply has no road there (so no amount of
    checkpoint tuning will help), as opposed to a checkpoint placed on the wrong road."""
    geojson = json.load(open(os.path.join(DATA_DIR, f"{route_id}.geojson")))
    pts = [p for s in extract_segments(geojson) for p in s]
    out = []
    for i, cp in enumerate(CHECKPOINTS[route_id]):
        out.append((i, round(min(haversine(p, cp) for p in pts), 1)))
    return out

def snap_checkpoints(checkpoints, segs):
    """Move each hand-typed checkpoint onto the nearest point that actually exists in
    the data. The checkpoints only need to convey *order and direction*; their exact
    position is better taken from the road itself, and a target that lies on the road
    is one walk_leg can actually reach."""
    pts = [p for s in segs for p in s]
    snapped, dists = [], []
    for cp in checkpoints:
        best = min(pts, key=lambda p: haversine(p, cp))
        snapped.append(best)
        dists.append(round(haversine(best, cp), 1))
    return snapped, dists

def process(route_id):
    path_file = os.path.join(DATA_DIR, f"{route_id}.geojson")
    if not os.path.exists(path_file):
        return {"id": route_id, "error": "missing geojson file"}
    geojson = json.load(open(path_file))
    segs = extract_segments(geojson)
    if not segs:
        return {"id": route_id, "error": "no line segments"}

    chains = exact_merge(segs)
    checkpoints, snap_dists = snap_checkpoints(CHECKPOINTS[route_id], segs)
    # 経由地の先頭/末尾がその国道の起点/終点そのものなので、ズレの基準にも使う
    exp_start, exp_end = CHECKPOINTS[route_id][0], CHECKPOINTS[route_id][-1]
    walked, legs = bridge_via_checkpoints(chains, checkpoints)
    bridges = [b for leg in legs for b in leg["bridges"]]
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
        "used_checkpoints": True,
        "checkpoint_snap_km": snap_dists,
        "legs": legs,
        "raw_points": len(walked),
        "simplified_points": len(simplified),
        "len_km": round(total_len, 1),
        # Biggest straight-line gap between consecutive points of the walked path -
        # what a "teleport" looks like to the user on the map. Measured on the raw
        # walked path, NOT the simplified one: simplification legitimately collapses a
        # genuinely straight road (国道12号の日本一長い直線29kmなど) into one long
        # segment, which would otherwise be misread as a gap in the data.
        "max_jump_km": round(max((haversine(walked[i-1], walked[i])
                                  for i in range(1, len(walked))), default=0.0), 1),
        "jumps_over_10km": sorted((round(haversine(walked[i-1], walked[i]), 1)
                                   for i in range(1, len(walked))
                                   if haversine(walked[i-1], walked[i]) > 10), reverse=True),
        "start_mismatch_km": round(haversine(walked[0], exp_start), 1),
        "end_mismatch_km": round(haversine(walked[-1], exp_end), 1),
        "num_bridges": len(bridges),
        "bridge_dists_km": bridges,
    }

if __name__ == "__main__":
    results = [process(i) for i in sorted(CHECKPOINTS)]
    for r in results:
        if "error" in r:
            print(f"{r['id']:>4} | ERROR: {r['error']}")
            continue
        flag = ""
        if r["start_mismatch_km"] > 8: flag += " ⚠START"
        if r["end_mismatch_km"] > 8: flag += " ⚠END"
        if r["max_jump_km"] > 15: flag += " ⚠JUMP"
        via = "cp" if r["used_checkpoints"] else "  "
        print(f"{r['id']:>4} |{via}| len={r['len_km']:>7}km | pts {r['raw_points']:>6}→{r['simplified_points']:>3} | "
              f"start_mm={r['start_mismatch_km']:>5} end_mm={r['end_mismatch_km']:>6} | "
              f"maxjump={r['max_jump_km']:>5}km jumps>10={r['jumps_over_10km']}{flag}")
        if r["legs"]:
            bad_legs = [l for l in r["legs"] if l["end_mismatch_km"] > 5]
            if bad_legs:
                print(f"      leg mismatch: {[(l['leg'], l['end_mismatch_km']) for l in bad_legs]}")
        if r.get("checkpoint_snap_km"):
            big_snaps = [(i, d) for i, d in enumerate(r["checkpoint_snap_km"]) if d > 5]
            if big_snaps:
                print(f"      cp snapped far: {big_snaps}")
    json.dump(results, open(os.path.join(OUT_DIR, "_report.json"), "w"), ensure_ascii=False, indent=2)
