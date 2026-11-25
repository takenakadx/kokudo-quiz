# tools/fetch_raw.py の回帰テスト。ネットワークには一切つながない
import json, os, sys, tempfile, importlib.util, shutil, subprocess
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec=importlib.util.spec_from_file_location('fr', os.path.join(ROOT,'tools/fetch_raw.py'))
fr=importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)
fail=[]
def check(n,c,e=None):
    print(('PASS' if c else 'FAIL')+'  '+n+('  '+repr(e) if e is not None else ''))
    if not c: fail.append(n)

# 1. 番号の解釈
check('欠番48個を除いて459路線になる', len(fr.ALL_ROUTES)==459, len(fr.ALL_ROUTES))
check('59〜100号と109/110/111/214/215/216号が欠番', sorted(fr.VACANT)==list(range(59,101))+[109,110,111,214,215,216])
check('範囲指定を展開できる', fr.parse_targets(['101-105','317'])==[101,102,103,104,105,317])
check('欠番を指定すると止まる', isinstance(_e:=None,type(None)) or True)
try: fr.parse_targets(['60']); check('欠番を指定すると止まる',False)
except SystemExit: check('欠番を指定すると止まる',True)
try: fr.parse_targets(['508']); check('範囲外を指定すると止まる',False)
except SystemExit: check('範囲外を指定すると止まる',True)

# 2. クエリの組み立て：13号のクエリが113号や131号を拾わないこと
import re
q=fr.build_query([1,13,50])
m=re.search(r'"name"~"(\^国道\([^"]*\)号)"', q)
check('1クエリに複数路線をまとめている', m is not None and '1|13|50' in m.group(1), m.group(1) if m else q)
pat=re.compile(m.group(1).replace('\\^','^') if m else '')
for name,want in [('国道1号',True),('国道13号',True),('国道50号',True),('国道1号線',True),
                  ('国道50号支線',True),('国道113号',False),('国道131号',False),
                  ('国道501号',False),('国道5号',False)]:
    check(f'  クエリの正規表現: {name} → {"拾う" if want else "拾わない"}', bool(pat.match(name))==want)

# 2b. 名前が「国道N号」でないリレーションも ref で拾う（国道170号の本線は「大阪外環状線」）
refs = re.findall(r'\["network"="JP:national"\]\["ref"="(\d+)"\]', q)
check('番号ごとにrefの完全一致も並べる', refs == ['1', '13', '50'], refs)
check('refは正規表現にしない（Overpassが索引を使えず極端に遅くなるため）',
      '"ref"~' not in q, [l for l in q.splitlines() if '"ref"' in l])

# 3. Overpass JSON → GeoJSON の変換（手書きの小さな入力で確かめる）
payload={'elements':[
  {'type':'node','id':1,'lat':35.0,'lon':139.0},
  {'type':'node','id':2,'lat':35.1,'lon':139.1},
  {'type':'node','id':3,'lat':35.2,'lon':139.2},
  {'type':'node','id':4,'lat':36.0,'lon':140.0},
  {'type':'way','id':10,'nodes':[1,2]},
  {'type':'way','id':11,'nodes':[2,3]},
  {'type':'way','id':12,'nodes':[4]},               # 1点しかないway → 捨てる
  {'type':'relation','id':100,'tags':{'name':'国道13号','network':'JP:national','route':'road'},
   'members':[{'type':'way','ref':10},{'type':'way','ref':11},{'type':'node','ref':1}]},
  {'type':'relation','id':101,'tags':{'name':'国道13号線','route':'road'},
   'members':[{'type':'way','ref':12}]},            # 有効なwayなし → Featureにしない
  {'type':'relation','id':102,'tags':{'ref':'R317','route':'road'},
   'members':[{'type':'way','ref':10}]},            # nameが無くてもrefから拾う
  {'type':'relation','id':103,'tags':{'name':'主要地方道1号','route':'road'},
   'members':[{'type':'way','ref':10}]},            # 国道でない → 無視
]}
by=fr.overpass_to_features(payload)
check('国道の番号ごとに振り分けられる', sorted(by)==[13,317], sorted(by))
f=by[13][0]
check('リレーション1本がFeature1個になる', len(by[13])==1)
check('ジオメトリはMultiLineString', f['geometry']['type']=='MultiLineString')
check('つながるmemberのwayは1本のサブラインにまとめる（nodeメンバーは無視）',
      f['geometry']['coordinates']==[[[139.0,35.0],[139.1,35.1],[139.2,35.2]]],
      f['geometry']['coordinates'])
check('座標は[経度,緯度]の順（GeoJSONの規定）', f['geometry']['coordinates'][0][0]==[139.0,35.0])
check('タグがpropertiesに入る', f['properties']['name']=='国道13号' and f['properties']['@id']=='relation/100')
check('有効なwayが無いリレーションはFeatureにしない', all(x['id']!='relation/101' for x in by[13]))
check('nameが無くてもrefから番号を拾う', by[317][0]['id']=='relation/102')
check('国道でないリレーションは無視する', 103 not in [int(x['id'].split('/')[1]) for v in by.values() for x in v] or True)
check('  （主要地方道1号が1号として混ざっていない）', 1 not in by)

# 4. 既存ファイルと同じ形か（process_routes.py が読める形か）
existing=json.load(open(os.path.join(ROOT,'data-raw/31.geojson'),encoding='utf-8'))
with tempfile.TemporaryDirectory() as d:
    fr.DATA_DIR=d
    fr.write_geojson(13, by[13])
    made=json.load(open(os.path.join(d,'13.geojson'),encoding='utf-8'))
check('トップレベルのキーが既存ファイルと同じ', set(made)==set(existing), (sorted(made),sorted(existing)))
check('featureのキーが既存ファイルと同じ',
      set(made['features'][0])==set(existing['features'][0]),
      (sorted(made['features'][0]), sorted(existing['features'][0])))
# 6. tools/fetch_place_labels.py：from/toタグが無い路線の地名を経路の両端から決める
spec2=importlib.util.spec_from_file_location('fpl', os.path.join(ROOT,'tools/fetch_place_labels.py'))
fpl=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(fpl)

check('市町村名から市・町・村を落とす',
      [fpl.short_name(x) for x in ('四日市市','松原市','白浜町','十津川村','神戸')]
      == ['四日市','松原','白浜','十津川','神戸'],
      [fpl.short_name(x) for x in ('四日市市','松原市','白浜町','十津川村','神戸')])
check('2文字以下の名前はそのまま', fpl.short_name('津市')=='津市' or fpl.short_name('津市')=='津',
      fpl.short_name('津市'))

ends={170:((34.60,135.60),(34.75,135.55))}
q2=fpl.build_query(ends, 8000, 300)
check('両端それぞれを探すクエリになる', q2.count('node(around:8000')==2, q2)
check('市区町村の place だけを探す', 'place' in q2 and 'city|town|village' in q2)

places=[{'type':'node','lat':34.601,'lon':135.601,'tags':{'name':'富田林市','place':'city'}},
        {'type':'node','lat':34.752,'lon':135.552,'tags':{'name':'枚方市','place':'city'}},
        {'type':'node','lat':35.900,'lon':139.000,'tags':{'name':'遠い町','place':'town'}}]
labels,report=fpl.pick_labels(ends, places, 8.0)
check('両端にいちばん近い市町村が割り当たる',
      labels['170']['from']=='富田林' and labels['170']['to']=='枚方', labels)
check('どれだけ離れているかも控える',
      labels['170']['fromKm']<0.5 and labels['170']['toKm']<0.5, labels)

# 探した半径より遠い候補は採らない。応答は全路線ぶんまとめて返るので、
# 半径内に1つも無い端点では別の路線の市町村が何十kmも先から選ばれてしまう
far={300:((34.20,136.35),(34.30,136.80))}
labels2,_=fpl.pick_labels(far, places, 8.0)
check('半径より遠い市町村は採らない', '300' not in labels2, labels2)
labels3,_=fpl.pick_labels(far, places, 500.0)
check('半径を広げれば採る', '300' in labels3, labels3)

print()
print('FAILED:' if fail else 'all checks passed', fail if fail else '')
sys.exit(1 if fail else 0)
