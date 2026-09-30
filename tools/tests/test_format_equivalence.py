# fetch_raw.py が書き出す形（way単位→stitch）に作り直した生データで
# process_routes.py を通し、現行の復元結果と一致することを確かめる
import json, os, random, shutil, subprocess, sys, tempfile, importlib.util
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec=importlib.util.spec_from_file_location('fr', os.path.join(ROOT,'tools/fetch_raw.py'))
fr=importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)
TARGETS=[1,2,13,29,31,45,46,50,57,58,176,439]
work=tempfile.mkdtemp()
shutil.copytree(os.path.join(ROOT,'tools'), os.path.join(work,'tools'))
os.makedirs(os.path.join(work,'data-raw'))
rng=random.Random(11)
for n in TARGETS:
    g=json.load(open(f'{ROOT}/data-raw/{n}.geojson',encoding='utf-8'))
    feats=[]
    for f in g['features']:
        gm=f['geometry']
        subs=gm['coordinates'] if gm['type']=='MultiLineString' else [gm['coordinates']]
        ways=[]
        for sub in subs:
            i=0
            while i<len(sub)-1:   # way 1本ぶんくらいに刻み、向きもランダムにする
                k=min(len(sub)-1,i+rng.randint(1,7))
                piece=sub[i:k+1]
                ways.append(piece[::-1] if rng.random()<0.5 else piece); i=k
        feats.append({'type':'Feature','properties':f['properties'],
                      'geometry':{'type':'MultiLineString','coordinates':fr.stitch(ways)},
                      'id':f.get('id')})
    json.dump({'type':'FeatureCollection','features':feats},
              open(f'{work}/data-raw/{n}.geojson','w',encoding='utf-8'),ensure_ascii=False)
r=subprocess.run([sys.executable,'tools/process_routes.py'],cwd=work,capture_output=True,text=True)
if r.returncode!=0: print(r.stdout[-1500:],r.stderr[-1500:]); sys.exit(1)
fail=[]
for n in TARGETS:
    a=json.load(open(f'{ROOT}/tools/processed/{n}.json'))
    b=json.load(open(f'{work}/tools/processed/{n}.json'))
    ok=a==b
    print(('PASS' if ok else 'FAIL')+f'  国道{n}号: fetch_raw形式でも復元結果が現行と完全一致 ({len(a)}点)')
    if not ok: fail.append(n)
shutil.rmtree(work)
print()
print('FAILED:' if fail else 'all checks passed', fail if fail else '')
sys.exit(1 if fail else 0)
