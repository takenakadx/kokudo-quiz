// ズーム/パンしてもペン残量が動かないことの回帰テスト
const { chromium, EXEC, APP, SPEC, STUB, DATA } = require('./harness');
const path = require('path');
const fail = [];
function check(name, cond, extra) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra !== undefined ? '  ' + JSON.stringify(extra) : ''}`);
  if (!cond) fail.push(name);
}
(async () => {
  const b = await chromium.launch(EXEC);
  const p = await b.newPage({ viewport: { width: 900, height: 900 } });
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await p.click('#tab-quiz');
  const out = await p.evaluate(() => {
    const ov = document.getElementById('quiz-overlay');
    const fire = (t, x, y) => ov.dispatchEvent(new PointerEvent(t, {
      pointerId: 1, pointerType: 'touch', bubbles: true, cancelable: true, clientX: x, clientY: y }));
    const res = {};
    // 長い国道・短い国道・日本全体では数pxしかない国道をまぜて確認する
    for (const id of [4, 1, 42, 134, 43]) {
      const h = HIGHWAYS.find(x => x.id === id);
      currentHighway = h; answered = false; hintUsed = false;
      clearStrokes(); quizLayerGroup.clearLayers(); hideResult();
      refitMap(quizMap); updateOfficialDenseCache(); renderQuiz(); renderInkGauge();
      // 半分だけなぞる（上限に当たっていない状態で残量の動きを見たい）
      const r = ov.getBoundingClientRect();
      const at = i => { const q = quizMap.latLngToContainerPoint(h.path[i]); return { x: r.x + q.x, y: r.y + q.y }; };
      const half = Math.floor(h.path.length / 2);
      fire('pointerdown', at(0).x, at(0).y);
      for (let i = 1; i <= half; i++) { const q = at(i); fire('pointermove', q.x, q.y); }
      fire('pointerup', at(half).x, at(half).y);
      const pct = () => drawnInk / inkBudget * 100;
      const base = pct();
      const seen = [];
      const mid = { x: 450, y: 450 };
      for (const dz of [1, 2, 3, -1]) {
        for (let k = 0; k < Math.abs(dz); k++) zoomMapAround(mid, dz > 0 ? 1 : -1);
        seen.push({ how: 'zoom' + (dz > 0 ? '+' : '') + dz, pct: pct(), penPx: +(traceTolerance * 2).toFixed(1) });
        for (let k = 0; k < Math.abs(dz); k++) zoomMapAround(mid, dz > 0 ? -1 : 1);
      }
      for (const d of [7, 13, 40, 300]) {
        quizMap.panBy([d, d], { animate: false }); afterMapMoved();
        seen.push({ how: 'pan' + d, pct: pct(), penPx: +(traceTolerance * 2).toFixed(1) });
        quizMap.panBy([-d, -d], { animate: false }); afterMapMoved();
      }
      res[h.number] = { base, seen };
    }
    return res;
  });
  for (const [num, { base, seen }] of Object.entries(out)) {
    const worst = seen.reduce((a, s) => Math.max(a, Math.abs(s.pct - base)), 0);
    check(`${num}：ズーム/パンしてもペン残量が変わらない`, worst < 0.05,
      { base: base.toFixed(2) + '%', worst: worst.toFixed(3) + 'pt' });
    // ペン幅（なぞり判定の許容範囲）は、これまで通り画面の縮尺に比例して変わる
    const pens = [...new Set(seen.map(s => s.penPx))];
    check(`${num}：画面上のペン幅はズームに応じて変わる（従来通り）`, pens.length > 1, pens.slice(0, 6));
  }
  console.log('errors:', errors.length ? errors : 'none');
  await b.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
