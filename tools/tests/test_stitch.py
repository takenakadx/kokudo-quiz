# 既存ファイルのサブラインを細切れにしてから stitch で戻すと、元に戻ることを確かめる
import json, os, random, importlib.util, sys
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec=importlib.util.spec_from_file_location('fr', os.path.join(ROOT,'tools/fetch_raw.py'))
fr=importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)
rng=random.Random(3); fail=[]
for n in [1,2,13,31,45,50,57,58,176,439]:
    g=json.load(open(f'{ROOT}/data-raw/{n}.geojson',encoding='utf-8'))
    ok=True; tested=0
    for f in g['features']:
        gm=f['geometry']
        subs=gm['coordinates'] if gm['type']=='MultiLineString' else [gm['coordinates']]
        for sub in subs:
            if len(sub)<3: continue
            ch=[]; i=0
            while i<len(sub)-1:
                k=min(len(sub)-1,i+rng.randint(1,7))
                piece=sub[i:k+1]
                if rng.random()<0.5: piece=piece[::-1]   # wayが逆向きに入っている場合も試す
                ch.append(piece); i=k
            tested+=1
            got=fr.stitch(ch)
            # 全体が逆向きになるのは同じ線（サブラインの向きは後段で扱う）
            if got!=[sub] and got!=[sub[::-1]]: ok=False
    print(('PASS' if ok else 'FAIL')+f'  国道{n}号: 細切れ{tested}本を stitch すると元のサブラインに戻る（向きの反転は許容）')
    if not ok: fail.append(n)
print()
print('FAILED:' if fail else 'all checks passed', fail if fail else '')
sys.exit(1 if fail else 0)
