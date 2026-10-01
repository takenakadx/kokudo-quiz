// Issue #7: 回答後に地図を動かすと、なぞった軌跡だけ取り残されるか
const { chromium, EXEC, APP, SPEC, STUB, DATA } = require('./harness');
const path = require('path');
(async () => {
  const b = await chromium.launch(EXEC);
  const p = await b.newPage({ viewport: { width: 900, height: 900 } });
  const errs=[]; p.on('pageerror', e=>errs.push(e.message));
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await p.click('#tab-quiz'); await p.waitForTimeout(150);
  const out = await p.evaluate(() => {
    const ov = document.getElementById('quiz-overlay');
    const fire=(t,x,y)=>ov.dispatchEvent(new PointerEvent(t,{pointerId:1,pointerType:'touch',bubbles:true,cancelable:true,clientX:x,clientY:y}));
    currentHighway = HIGHWAYS.find(h=>h.id===4);
    answered=false; hintUsed=false; clearStrokes(); quizLayerGroup.clearLayers(); hideResult();
    refitMap(quizMap); updateOfficialDenseCache(); renderQuiz(); renderInkGauge();
    const r=ov.getBoundingClientRect();
    const at=i=>{const q=quizMap.latLngToContainerPoint(currentHighway.path[i]);return{x:r.x+q.x,y:r.y+q.y};};
    const n=currentHighway.path.length;
    fire('pointerdown',at(0).x,at(0).y);
    for(let i=1;i<n;i+=3){const q=at(i);fire('pointermove',q.x,q.y);}
    fire('pointerup',at(n-1).x,at(n-1).y);
    document.getElementById('quiz-submit').click();           // 採点する
    const before = strokes[0] ? strokeScreenPts(strokes[0]).map(q=>[Math.round(q.x),Math.round(q.y)]) : null;
    const beforeLL = strokes[0] ? strokes[0].latlngs.slice() : null;
    // 回答後に地図を動かす
    panMapBy(120, -80);
    zoomMapAround({x:450,y:450}, 1);
    const after = strokes[0] ? strokeScreenPts(strokes[0]).map(q=>[Math.round(q.x),Math.round(q.y)]) : null;
    const afterLL = strokes[0] ? strokes[0].latlngs.slice() : null;
    // 正解ルート（Leafletレイヤー）が動いたかの基準として、1点の画面座標を見る
    const ref = quizMap.latLngToContainerPoint(currentHighway.path[0]);
    return { answered, hasStroke: !!strokes[0],
             movedOnScreen: before && after && JSON.stringify(before)!==JSON.stringify(after),
             sameLatLng: JSON.stringify(beforeLL)===JSON.stringify(afterLL),
             sample: before && after ? {before: before[0], after: after[0]} : null };
  });
  console.log(JSON.stringify(out,null,1));
  const ok = out.answered && out.hasStroke && out.movedOnScreen && out.sameLatLng;
  console.log(ok ? '\nPASS  回答後に地図を動かしても軌跡は地図に追従する（Issue #7は解消済み）'
                 : '\nFAIL  Issue #7 の症状が残っている');
  console.log('errors:', errs.length?errs:'none');
  await b.close();
  process.exit(ok && !errs.length ? 0 : 1);
})();
