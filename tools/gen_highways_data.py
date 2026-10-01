#!/usr/bin/env python3
"""Build highways-data.js from the processed OpenStreetMap routes.

Run tools/process_routes.py first: it turns the raw Overpass exports in data-raw/
into an ordered path per route under tools/processed/. This script just attaches
the human-facing metadata (labels, prefectures, difficulty, trivia) to each path.
"""
import json
import math
import os
import re

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "processed")
OUT_FILE = os.path.join(os.path.dirname(__file__), os.pardir, "highways-data.js")

# id: (number, startLabel, endLabel, prefectures, difficulty, fact)
# difficulty は手で固定したいときだけ 1〜3 を入れる。None なら経路と起終点から
# 自動で決める（下の difficulty_of）。路線が441本あると難易度は相対的な尺度に
# しかならないので、既定では全路線を同じ基準で機械的に判定している。
META = {
    1: ("国道1号", "東京", "大阪",
        ["東京都", "神奈川県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府"], None,
        "旧東海道にほぼ沿って東京と大阪を結ぶ、日本を代表する幹線国道。"),
    2: ("国道2号", "大阪", "北九州(門司)",
        ["大阪府", "兵庫県", "岡山県", "広島県", "山口県", "福岡県"], None,
        "大阪から瀬戸内海沿いを西へ進み、関門海峡を越えて北九州まで至る。"),
    3: ("国道3号", "北九州(門司)", "鹿児島",
        ["福岡県", "佐賀県", "熊本県", "鹿児島県"], None,
        "国道2号の終点から続き、福岡・熊本を経て九州を縦断する大動脈。"),
    4: ("国道4号", "東京", "青森",
        ["東京都", "埼玉県", "茨城県", "栃木県", "福島県", "宮城県", "岩手県", "青森県"], None,
        "日本で最も長い国道。東京から東北地方を縦断し青森まで続く。"),
    5: ("国道5号", "函館", "札幌",
        ["北海道"], None,
        "函館から長万部・倶知安・小樽を経て札幌に至る、北海道の主要国道。"),
    6: ("国道6号", "東京", "仙台",
        ["東京都", "千葉県", "茨城県", "福島県", "宮城県"], None,
        "東京から水戸・いわきなど太平洋沿いを北上して仙台に至る。"),
    7: ("国道7号", "新潟", "青森",
        ["新潟県", "山形県", "秋田県", "青森県"], None,
        "日本海沿いに新潟から酒田・秋田・弘前を経て青森まで北上する。"),
    8: ("国道8号", "新潟", "京都",
        ["新潟県", "富山県", "石川県", "福井県", "滋賀県", "京都府"], None,
        "日本海側の新潟・富山・金沢・福井を結び京都へ至る北陸の大動脈。"),
    9: ("国道9号", "京都", "下関",
        ["京都府", "兵庫県", "鳥取県", "島根県", "山口県"], None,
        "山陰地方(日本海側)を横断して京都から下関まで結ぶ。"),
    10: ("国道10号", "北九州(小倉)", "鹿児島",
         ["福岡県", "大分県", "宮崎県", "鹿児島県"], None,
         "3号とは反対に、東九州側(別府・大分・宮崎)を回って鹿児島へ至る。"),
    11: ("国道11号", "徳島", "松山",
         ["徳島県", "香川県", "愛媛県"], None,
         "徳島から高松・西条を経て松山へ、瀬戸内海側の四国を横断する。"),
    12: ("国道12号", "札幌", "旭川",
         ["北海道"], None,
         "札幌と旭川を結ぶ。美唄〜滝川には日本最長29.2kmの直線区間がある。"),
    13: ("国道13号", "福島", "秋田",
         ["福島県", "山形県", "秋田県"], None,
         "奥羽山脈の西側を縦断し、米沢・山形・新庄・横手を経て秋田へ至る。"),
    14: ("国道14号", "東京(日本橋)", "千葉",
         ["東京都", "千葉県"], None,
         "東京・日本橋から市川・船橋を経て千葉へ至る、京葉間の旧来の幹線。"),
    15: ("国道15号", "東京(日本橋)", "横浜",
         ["東京都", "神奈川県"], None,
         "第一京浜。日本橋から品川・川崎を経て横浜へ至る旧東海道の一部。"),
    16: ("国道16号", "横浜", "横浜(一周)",
         ["神奈川県", "東京都", "埼玉県", "千葉県"], None,
         "東京都心を通らず、横浜・八王子・さいたま・千葉をぐるっと環状に結ぶ首都圏の大動脈。"),
    17: ("国道17号", "東京", "新潟",
         ["東京都", "埼玉県", "群馬県", "新潟県"], None,
         "中山道・三国街道にあたり、東京から高崎・三国峠を越えて新潟へ至る。"),
    18: ("国道18号", "高崎", "上越",
         ["群馬県", "長野県", "新潟県"], None,
         "中山道・北国街道筋。碓氷峠で上州から信州へ入り、長野を経て日本海側へ抜ける。"),
    19: ("国道19号", "名古屋", "長野",
         ["愛知県", "岐阜県", "長野県"], None,
         "中山道の木曽路を通り、名古屋から塩尻・松本を経て長野へ至る。"),
    20: ("国道20号", "東京", "塩尻",
         ["東京都", "神奈川県", "山梨県", "長野県"], None,
         "旧甲州街道にあたり、東京から山梨・諏訪を経て塩尻で中山道と合流する。"),
    21: ("国道21号", "瑞浪", "米原",
         ["岐阜県", "滋賀県"], None,
         "中山道にほぼ沿う短い国道。大垣から関ケ原を越えて近江へ入る。"),
    22: ("国道22号", "名古屋", "岐阜",
         ["愛知県", "岐阜県"], None,
         "名岐バイパス。名古屋と岐阜を結ぶ中部圏の主要幹線。"),
    23: ("国道23号", "豊橋", "伊勢",
         ["愛知県", "三重県"], None,
         "豊橋から名豊道路・名四国道を経て四日市・津・松阪を通り、伊勢神宮のある伊勢市へ至る。"),
    24: ("国道24号", "京都", "和歌山",
         ["京都府", "奈良県", "和歌山県"], None,
         "奈良盆地を南北に貫き、五條から紀の川沿いを下って和歌山へ至る。"),
    25: ("国道25号", "四日市", "大阪",
         ["三重県", "奈良県", "大阪府"], None,
         "名阪国道。四日市から亀山・天理を経て大阪へ至る(起点の名古屋〜四日市は国道1号との重複区間)。"),
    26: ("国道26号", "大阪", "和歌山",
         ["大阪府", "和歌山県"], None,
         "大阪湾の東岸を堺・岸和田と南下する。24号とは違い海沿いを通る和歌山への道。"),
    27: ("国道27号", "敦賀", "京丹波",
         ["福井県", "京都府"], None,
         "若狭湾に沿って敦賀から小浜・舞鶴へ。丹波で国道9号に合流して終わる。"),
    28: ("国道28号", "神戸", "徳島",
         ["兵庫県", "徳島県"], None,
         "淡路島を縦断して本州と四国を結ぶ。明石海峡と鳴門海峡は海上区間。"),
    29: ("国道29号", "姫路", "鳥取",
         ["兵庫県", "鳥取県"], None,
         "戸倉峠を越えて播磨から因幡へ抜ける、中国山地を南北に横断する道。"),
    30: ("国道30号", "岡山", "高松",
         ["岡山県", "香川県"], None,
         "岡山から玉野市宇野まで南下し、宇高航路(海上区間)で高松へ渡る。"),
    31: ("国道31号", "海田", "呉",
         ["広島県"], None,
         "広島県内だけで完結する約19kmの短い国道。海田町から広島湾沿いに呉へ至る。"),
    32: ("国道32号", "高松", "高知",
         ["香川県", "徳島県", "高知県"], None,
         "讃岐から猪ノ鼻峠を越え、吉野川沿いに大歩危を経て高知へ。四国を縦断する。"),
    33: ("国道33号", "高知", "松山",
         ["高知県", "愛媛県"], None,
         "仁淀川沿いに遡り、三坂峠を越えて松山へ下る。四国山地を斜めに横断する。"),
    34: ("国道34号", "鳥栖", "長崎",
         ["佐賀県", "長崎県"], None,
         "長崎街道筋。佐賀・武雄・嬉野を経て、大村湾沿いに長崎へ至る。"),
    35: ("国道35号", "佐世保", "武雄",
         ["長崎県", "佐賀県"], None,
         "佐世保から早岐・有田を経て武雄へ至る、県境をまたぐ約30kmの短い国道。"),
    36: ("国道36号", "札幌", "室蘭",
         ["北海道"], None,
         "札幌と道南を結ぶ大動脈。千歳・苫小牧を経て太平洋沿いに室蘭へ至る。"),
    37: ("国道37号", "長万部", "室蘭",
         ["北海道"], None,
         "内浦湾(噴火湾)の北岸を回り、洞爺湖・伊達を経て室蘭へ。5号と36号をつなぐ。"),
    38: ("国道38号", "滝川", "釧路",
         ["北海道"], None,
         "富良野から狩勝峠を越えて十勝平野へ下り、帯広を経て釧路まで道央と道東を結ぶ。"),
    39: ("国道39号", "旭川", "網走",
         ["北海道"], None,
         "石北峠で大雪山系を越え、北見・美幌を経てオホーツク海側の網走へ至る。"),
    40: ("国道40号", "旭川", "稚内",
         ["北海道"], None,
         "天塩川に沿って北上し、日本最北の都市・稚内まで道北を縦断する。"),
    41: ("国道41号", "名古屋", "富山",
         ["愛知県", "岐阜県", "富山県"], None,
         "飛騨街道。名古屋から下呂・高山を経て富山へ、中部地方を縦断する。"),
    42: ("国道42号", "和歌山", "松阪",
         ["和歌山県", "三重県"], None,
         "紀伊半島の海沿いをぐるっと回り、和歌山から新宮を経て松阪へ至る。"),
    43: ("国道43号", "大阪", "神戸",
         ["大阪府", "兵庫県"], None,
         "阪神国道。大阪と神戸を結ぶ、片側5車線もある幅の広い幹線道路。"),
    44: ("国道44号", "釧路", "根室",
         ["北海道"], None,
         "釧路湿原の南から厚岸・浜中を経て、日本最東端の都市・根室へ至る。"),
    45: ("国道45号", "仙台", "青森",
         ["宮城県", "岩手県", "青森県"], None,
         "三陸海岸に沿って東北の太平洋側を縦断する。4号と対をなす道。"),
    46: ("国道46号", "盛岡", "秋田",
         ["岩手県", "秋田県"], None,
         "仙岩峠で奥羽山脈を越え、田沢湖・角館を経て秋田へ。東北を横断する。"),
    47: ("国道47号", "仙台", "酒田",
         ["宮城県", "山形県"], None,
         "鳴子温泉から最上町へ抜け、新庄から最上川沿いに日本海側の酒田へ下る。"),
    48: ("国道48号", "仙台", "山形",
         ["宮城県", "山形県"], None,
         "作並・関山峠を越えて仙台と山形を最短で結ぶ、通称・関山街道。"),
    49: ("国道49号", "いわき", "新潟",
         ["福島県", "新潟県"], None,
         "郡山・会津若松を経て阿賀野川沿いに下り、太平洋側と日本海側を結ぶ。"),
    50: ("国道50号", "前橋", "水戸",
         ["群馬県", "栃木県", "茨城県"], None,
         "東京を通らずに北関東を東西に貫く。桐生・足利・佐野と両毛地域を結ぶ。"),
    51: ("国道51号", "千葉", "水戸",
         ["千葉県", "茨城県"], None,
         "成田・佐原を経て利根川を渡り、霞ヶ浦の東側を回って水戸へ至る。"),
    52: ("国道52号", "静岡(清水)", "甲斐",
         ["静岡県", "山梨県"], None,
         "富士川沿いに身延を経て甲府盆地へ。駿河と甲斐を結ぶ旧・身延道。"),
    53: ("国道53号", "岡山", "鳥取",
         ["岡山県", "鳥取県"], None,
         "津山から黒尾峠を越えて智頭へ。中国地方を南北に横断する。"),
    54: ("国道54号", "広島", "松江",
         ["広島県", "島根県"], None,
         "三次から赤名峠を越えて出雲へ。瀬戸内側と山陰側を最短で結ぶ。"),
    55: ("国道55号", "徳島", "高知",
         ["徳島県", "高知県"], None,
         "四国の太平洋側を回り、室戸岬を経て高知へ至る。56号と合わせて四国を一周する。"),
    56: ("国道56号", "高知", "松山",
         ["高知県", "愛媛県"], None,
         "四万十・宿毛から豊後水道沿いを北上し、宇和島・大洲を経て松山へ至る長大路線。"),
    57: ("国道57号", "大分", "長崎",
         ["大分県", "熊本県", "長崎県"], None,
         "阿蘇の外輪山を越えて熊本へ。熊本〜島原はフェリーの海上区間になっている。"),
    58: ("国道58号", "鹿児島", "那覇",
         ["鹿児島県", "沖縄県"], None,
         "日本一長い国道。大半が海上区間(フェリー)で、種子島・奄美群島を経て沖縄・那覇まで続く。"),
    134: ("国道134号", "横須賀", "大磯",
          ["神奈川県"], None,
          "湘南海岸線。鎌倉・江ノ島・茅ヶ崎など有名な海沿いを走る。"),
    135: ("国道135号", "熱海", "下田",
          ["静岡県"], None,
          "伊豆半島東岸。熱海から伊東・河津を経て下田へ至る観光道路。"),
    158: ("国道158号", "福井", "松本",
          ["福井県", "岐阜県", "長野県"], None,
          "福井から九頭竜湖・高山・安房峠を越えて松本へ至る山岳国道。上高地への入口。"),
    171: ("国道171号", "京都", "神戸",
          ["京都府", "大阪府", "兵庫県"], None,
          "西国街道。京都から高槻・西宮を経て神戸へ至る。"),
    176: ("国道176号", "大阪", "舞鶴",
          ["大阪府", "兵庫県", "京都府"], None,
          "大阪から宝塚・三田・福知山を経て舞鶴へ。渋滞の名所としても有名。"),
    246: ("国道246号", "東京(三宅坂)", "沼津",
          ["東京都", "神奈川県", "静岡県"], None,
          "東京の三宅坂を起点に渋谷・厚木・御殿場を経て沼津で国道1号と合流する。"),
    357: ("国道357号", "千葉", "横須賀",
          ["千葉県", "東京都", "神奈川県"], None,
          "東京湾岸道路。千葉から東京・横浜を経て横須賀へ、東京湾をぐるりと結ぶ。"),
    411: ("国道411号", "青梅", "甲府",
          ["東京都", "山梨県"], None,
          "青梅街道。青梅から奥多摩湖・柳沢峠を越えて甲府へ至る(起点は新宿)。"),
    413: ("国道413号", "相模原", "富士吉田",
          ["神奈川県", "山梨県"], None,
          "道志みち。相模原から道志・山中湖を経て富士吉田へ、ツーリングで有名。"),
    439: ("国道439号", "徳島", "四万十",
          ["徳島県", "高知県"], None,
          "「酷道」として全国的に有名。徳島から剣山周辺の山間部を抜けて四万十へ至る。"),
}


# ---------------------------------------------------------------------------
# META に手書きしていない路線ぶんの自動生成
#
# 459路線ぜんぶに起終点・通過県・豆知識を手で書くのは現実的でないので、
# 生データ(OpenStreetMap)のタグから機械的に作る。
#   起終点ラベル … リレーションの from / to タグ（99%の路線が持っている）
#   通過都道府県 … from / to の都道府県名。途中の県はタグから分からないので入れない
#   地方         … 経路上の点を、全路線の from / to から作った基準点で分類して求める
#                  （マップの絞り込みは地方単位なので、都道府県より粗くて済む）
#   豆知識       … 手で書けないので付けない（アプリ側で無い場合は表示しない）
# ---------------------------------------------------------------------------
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data-raw")
# 神奈川県・和歌山県・鹿児島県は「3文字＋県」なので、..県 では取りこぼす
PREF_RE = re.compile(r"^(北海道|東京都|京都府|大阪府|.{2,3}県)")
SIDE_RE = re.compile(r"(旧道|支線|バイパス|旧線|廃道|延伸|事業)")

PREF_REGION = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北", "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東", "埼玉県": "関東", "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部", "山梨県": "中部", "長野県": "中部",
    "岐阜県": "中部", "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿", "大阪府": "近畿", "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国", "島根県": "中国", "岡山県": "中国", "広島県": "中国", "山口県": "中国",
    "徳島県": "四国", "香川県": "四国", "愛媛県": "四国", "高知県": "四国",
    "福岡県": "九州", "佐賀県": "九州", "長崎県": "九州", "熊本県": "九州", "大分県": "九州", "宮崎県": "九州",
    "鹿児島県": "九州", "沖縄県": "九州",
}


def haversine(a, b):
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def clean_place(value):
    """タグの値を整える。稀に「北海道浦河町\tto=北海道釧路市」のように
    2つのタグが1つの値に潰れているものがあるので、そこで切る。"""
    if not value:
        return None
    return re.split(r"[\t\n]|\bto=", value)[0].strip() or None


def raw_endpoints(route_id):
    """その路線の from / to タグを返す。旧道・支線のリレーションは見ない。"""
    f = os.path.join(RAW_DIR, "%d.geojson" % route_id)
    if not os.path.exists(f):
        return None, None
    with open(f, encoding="utf-8") as fh:
        doc = json.load(fh)
    props = [feat.get("properties") or {} for feat in doc.get("features", [])]
    main = [q for q in props if not SIDE_RE.search(q.get("name", "") or "")] or props
    for q in main:
        frm, to = clean_place(q.get("from")), clean_place(q.get("to"))
        if frm and to:
            return frm, to
    # from と to が1つのタグに潰れている場合は、そこから両方を取り出す
    for q in main:
        raw = q.get("from") or ""
        m = re.search(r"\bto=(.+)$", raw)
        if m and clean_place(raw):
            return clean_place(raw), m.group(1).strip()
    return None, None


def city_label(place):
    """「福岡県北九州市八幡西区」→「北九州」。ボタンや出題文に収まる長さにする。
    郡名は地名として通じない（「福島県耶麻郡西会津町」は耶麻ではなく西会津）ので、
    郡の部分は読み飛ばして町村名を採る。"""
    if not place:
        return None
    body = PREF_RE.sub("", place)
    body = re.sub(r"^.{1,4}郡", "", body)  # 郡は飛ばす
    m = re.match(r"(.+?)(市|区|町|村)", body)
    name = (m.group(1) if m else body).strip()
    if name:
        return name
    m = PREF_RE.match(place)
    return m.group(1) if m else place


def build_region_seeds(paths):
    """全路線の起終点を「この座標はこの地方」という基準点として集める。"""
    seeds = []
    for rid, path in paths.items():
        frm, to = raw_endpoints(rid)
        for place, pt in ((frm, path[0]), (to, path[-1])):
            m = PREF_RE.match(place or "")
            if m and m.group(1) in PREF_REGION:
                seeds.append((tuple(pt), PREF_REGION[m.group(1)]))
    return seeds


def regions_of(path, seeds, k=5, min_share=0.05):
    """経路上の点を近くの基準点で分類し、全体の5%以上を占めた地方を採用する。
    県境付近の1点だけで地方が付いてしまうのを防ぐため。"""
    tally, total = {}, 0
    step = max(1, len(path) // 80)
    for q in path[::step]:
        near = sorted(seeds, key=lambda sd: haversine(sd[0], q))[:k]
        weight = {}
        for pt, reg in near:
            weight[reg] = weight.get(reg, 0.0) + 1.0 / max(haversine(pt, q), 0.5)
        best = max(weight.items(), key=lambda kv: kv[1])[0]
        tally[best] = tally.get(best, 0) + 1
        total += 1
    return {r for r, c in tally.items() if c / total >= min_share}


def auto_meta(route_id, path, length_km, seeds):
    """タグから1路線ぶんのメタデータを作る。作れなければ (None, 理由) を返す。"""
    frm, to = raw_endpoints(route_id)
    if not frm or not to:
        return None, "from/toタグが無い"
    mf, mt = PREF_RE.match(frm), PREF_RE.match(to)
    if not mf or not mt:
        return None, "from/toから都道府県を読み取れない"
    prefs = [mf.group(1)] + ([mt.group(1)] if mt.group(1) != mf.group(1) else [])
    regions = regions_of(path, seeds) | {PREF_REGION[p] for p in prefs}
    return {
        "number": "国道%d号" % route_id,
        "startLabel": city_label(frm),
        "endLabel": city_label(to),
        "prefectures": prefs,
        "regions": sorted(regions),
        # 長い路線ほど名前が知られているので、そこだけ難易度を分ける
        "difficulty": 2 if length_km >= 200 else 3,
    }, None



# ---------------------------------------------------------------------------
# 難易度の判定
#
# 441路線もあると「かんたん」は相対的な意味しか持たないので、絶対的な知名度では
# なく、路線ごとの「特徴の多さ」を点数にして3段階に割る。ここでいう特徴とは、
# 地図の上でその国道を思い出す手がかりになるもの——番号の桁数、起終点が有名な
# 都市か、長さ、複数の地方にまたがるか、海上区間・環状・ほぼ直線といった形の
# 目印、そして調べて豆知識が書けるだけの特筆すべき点があるか。
#
# OSMのタグ(wikipedia等)は455/458の路線が持っていて差がつかないため使っていない。
# ---------------------------------------------------------------------------

# 県庁所在地(47)と政令指定都市(20)。どちらも場所がすぐ浮かぶ都市
MAJOR_CITIES = set((
    "札幌 青森 盛岡 仙台 秋田 山形 福島 水戸 宇都宮 前橋 さいたま 千葉 東京 横浜 新潟 富山 "
    "金沢 福井 甲府 長野 岐阜 静岡 名古屋 津 大津 京都 大阪 神戸 奈良 和歌山 鳥取 松江 岡山 "
    "広島 山口 徳島 高松 松山 高知 福岡 佐賀 長崎 熊本 大分 宮崎 鹿児島 那覇 "
    "川崎 相模原 浜松 堺 北九州").split())

# 県庁所在地ではないが名前で場所が浮かぶ都市（中核市・観光地など）
KNOWN_CITIES = set((
    "旭川 函館 釧路 帯広 苫小牧 室蘭 網走 稚内 八戸 弘前 宮古 釜石 石巻 気仙沼 会津若松 "
    "いわき 郡山 日光 高崎 柏崎 長岡 上越 松本 上田 諏訪 下田 熱海 沼津 豊橋 四日市 伊勢 "
    "彦根 舞鶴 姫路 明石 倉敷 福山 尾道 下関 今治 宇和島 佐世保 久留米 別府 延岡 名護 "
    "米子 出雲 日田 横須賀").split())

DIFF_EASY = 4.5     # これ以上なら ★☆☆
DIFF_NORMAL = 2.0   # これ以上なら ★★☆


def difficulty_score(route_id, path, length_km, labels, regions, max_jump_km, has_fact):
    """特徴が多いほど高くなる点数。難易度はこれを区切って決める。"""
    score = {1: 4.0, 2: 2.0, 3: 0.0}[len(str(route_id))]
    score += 1.5 * sum(1 for x in labels if x in MAJOR_CITIES)
    score += 0.75 * sum(1 for x in labels if x in KNOWN_CITIES)
    score += 2.0 if length_km >= 400 else 1.0 if length_km >= 200 else 0.5 if length_km >= 100 else 0.0
    if len(regions) >= 2:
        score += 1.0
    if max_jump_km > 10:
        score += 1.0          # 海上区間がある＝形の目印になる
    if length_km:
        direct = haversine(path[0], path[-1])
        if direct / length_km < 0.12:
            score += 1.0      # 起点と終点が近い＝環状
        elif length_km >= 50 and direct / length_km >= 0.75:
            score += 1.0      # 寄り道が少なくほぼ一直線
    if has_fact:
        # 豆知識を書いてあるのは、調べて特筆すべき点が見つかった路線ということ。
        # 湘南の134号や伊豆の135号のように、短くても誰もが知っている道を拾う
        score += 1.5
    return score


def difficulty_of(*args):
    score = difficulty_score(*args)
    return 1 if score >= DIFF_EASY else 2 if score >= DIFF_NORMAL else 3


def fmt_path(points):
    rows = ",\n      ".join("[%.5f, %.5f]" % (p[0], p[1]) for p in points)
    return "[\n      " + rows + "\n    ]"

def js_str_list(items):
    return "[" + ", ".join('"%s"' % s for s in items) + "]"

# 表示用の総距離は、間引く前の経路の長さ(process_routes.pyが出力したlen_km)を使う。
# path は300点以下に間引いてあるので、そこから測ると実際よりわずかに短くなる。
report_file = os.path.join(PROCESSED_DIR, "_report.json")
lengths = {}
if os.path.exists(report_file):
    for r in json.load(open(report_file)):
        if "len_km" in r:
            lengths[r["id"]] = r["len_km"]

# 品質の基準。これを外れた路線は問題として成立しないので収録しない。
#
# 経路の「飛び」は厳しく見ない。自動組み立ては生データの線分だけを辺にした
# グラフの最短経路なので、組み立てを誤って離れた場所へ飛ぶことが原理的に起きず、
# 飛びが出るのは生データ側が途切れている所（フェリーの海上区間など）だけに限られる。
# 国道58号(鹿児島〜沖縄)の246kmの飛びと同じで、これは正しい姿。ただし経路の
# 大半が1回の飛びという場合は、復元できていないとみなして外す。
MIN_LENGTH_KM = 10.0       # 日本全体の縮尺では数pxしかなく、なぞりようがない
MIN_POINTS = 10            # 形が無さすぎるとなぞりようがない
MAX_JUMP_RATIO = 0.6       # 全長の6割が1回の飛び＝つながりが復元できていない

paths = {}
for f in os.listdir(PROCESSED_DIR):
    if f.endswith(".json") and not f.startswith("_"):
        paths[int(f[:-len(".json")])] = json.load(open(os.path.join(PROCESSED_DIR, f)))

jumps = {}
for r in json.load(open(report_file)) if os.path.exists(report_file) else []:
    if "max_jump_km" in r:
        jumps[r["id"]] = r["max_jump_km"]

seeds = build_region_seeds(paths)

blocks = []
missing = []
excluded = []
difficulties = {}   # 仕様書ページ用に、決まった難易度を控えておく
auto_count = 0
for hid in sorted(set(META) | set(paths)):
    pts = paths.get(hid)
    if not pts:
        missing.append(hid)
        continue
    length_km = lengths.get(hid, 0)
    fact = None
    if hid in META:
        number, start_label, end_label, prefs, diff, fact = META[hid]
        regions = None
    else:
        meta, why = auto_meta(hid, pts, length_km, seeds)
        if meta is None:
            excluded.append((hid, why))
            continue
        number = meta["number"]
        start_label, end_label = meta["startLabel"], meta["endLabel"]
        prefs, regions, diff = meta["prefectures"], meta["regions"], None
        # 手で内容を確かめていない路線は、品質の基準を満たすものだけ収録する
        jump = jumps.get(hid, 0)
        if length_km < MIN_LENGTH_KM:
            excluded.append((hid, f"短すぎる({length_km}km)"))
            continue
        if len(pts) < MIN_POINTS:
            excluded.append((hid, f"経路の点が少なすぎる({len(pts)}点)"))
            continue
        if length_km and jump > length_km * MAX_JUMP_RATIO:
            excluded.append((hid, f"経路の大半が1回の飛び({jump}km / 全長{length_km}km)"))
            continue
        auto_count += 1
    # 難易度は、METAで手で指定していなければ経路と起終点から決める
    if diff is None:
        diff = difficulty_of(hid, pts, length_km, [start_label, end_label],
                             regions or sorted({PREF_REGION[p] for p in prefs if p in PREF_REGION}),
                             jumps.get(hid, 0), bool(fact))
    difficulties[hid] = diff
    fields = [
        f"    id: {hid}",
        f'    number: "{number}"',
        f'    startLabel: "{start_label}"',
        f'    endLabel: "{end_label}"',
        f"    prefectures: {js_str_list(prefs)}",
    ]
    if regions:
        fields.append(f"    regions: {js_str_list(regions)}")
    fields += [
        f"    difficulty: {diff}",
        f"    lengthKm: {round(length_km)}",
    ]
    if fact:
        fields.append(f'    fact: "{fact}"')
    fields.append(f"    path: {fmt_path(pts)}")
    blocks.append("  {\n" + ",\n".join(fields) + "\n  }")

header = '''/*
 * 国道データ
 * ------------------------------------------------------------
 * このファイルは tools/gen_highways_data.py が生成しています。
 * 直接編集せず、国道の追加・修正は下記の手順で行ってください。
 *   1. data-raw/README.md の手順でOverpassから生データを取得
 *   2. tools/process_routes.py の CHECKPOINTS に経由都市を追記
 *   3. tools/process_routes.py → tools/gen_highways_data.py を実行
 *
 * path: [緯度, 経度] の配列（先頭が起点、末尾が終点）。
 *   OpenStreetMapの実際の道路線形から生成した実ルートです。
 *   起点・終点の地名表示には path ではなく startLabel/endLabel を使う。
 *
 * lengthKm: 経路の総距離(km)。補足情報として表示する。
 * difficulty: 1(易)〜3(難) の目安。難易度フィルターに利用。
 * fact: 学習モードで表示するトリビア。
 */

const HIGHWAYS = [
'''

with open(OUT_FILE, "w") as f:
    f.write(header + ",\n".join(blocks) + "\n];\n")

# 仕様書ページ用の一覧も出す。highways-data.js は1.4MBあって仕様書から読むには
# 重いので、経路を含まない軽い一覧を別に書き出す。
SPEC_FILE = os.path.join(os.path.dirname(__file__), os.pardir, "spec", "routes.js")
spec_rows = []
for hid in sorted(set(META) | set(paths)):
    why = dict(excluded).get(hid)
    if hid in META:
        number, start_label, end_label, prefs, _diff, _fact = META[hid]
        auto = False
    else:
        meta, _ = auto_meta(hid, paths[hid], lengths.get(hid, 0), seeds) if hid in paths else (None, None)
        if meta:
            number, start_label, end_label = meta["number"], meta["startLabel"], meta["endLabel"]
            prefs, auto = meta["prefectures"], True
        else:
            # メタデータを作れなかった路線も、見送った理由とともに一覧には残す
            start_label = end_label = "不明"
            prefs, auto = [], True
    spec_rows.append('  { num: %d, start: "%s", end: "%s", prefs: %s, diff: %d, len: %d, auto: %s%s }' % (
        hid, start_label, end_label, js_str_list(prefs), diff, round(lengths.get(hid, 0)),
        "true" if auto else "false",
        ', excluded: "%s"' % why if why else ""))
os.makedirs(os.path.dirname(SPEC_FILE), exist_ok=True)
with open(SPEC_FILE, "w", encoding="utf-8") as f:
    f.write("/* tools/gen_highways_data.py が生成。直接編集しない。\n"
            "   仕様書ページ用の軽い一覧（経路の座標は含まない）。 */\nconst SPEC_ROUTES = [\n"
            + ",\n".join(spec_rows) + "\n];\n")
print("wrote", os.path.normpath(SPEC_FILE), f"({len(spec_rows)} routes)")

print("wrote", os.path.normpath(OUT_FILE))
print(f"routes: {len(blocks)} (手書きのMETA {len(blocks) - auto_count} / タグから自動生成 {auto_count})")
if missing:
    print("SKIPPED (no processed path):", missing)
if excluded:
    print(f"EXCLUDED {len(excluded)}路線:")
    for hid, why in excluded:
        print(f"  国道{hid}号: {why}")
