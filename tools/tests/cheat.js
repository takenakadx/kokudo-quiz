const { chromium, EXEC, APP, SPEC, STUB, DATA } = require('./harness');
const path = require('path');

const fail = [];
function check(name, cond, extra) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra !== undefined ? '  ' + JSON.stringify(extra) : ''}`);
  if (!cond) fail.push(name);
}

(async () => {
  const browser = await chromium.launch(EXEC);
  const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => {
    const t = m.text();
    if (m.type() === 'error' && !t.includes('ERR_TUNNEL') && !t.includes('Failed to load resource')) errors.push(t);
  });
  await page.addInitScript({ path: STUB });
  await page.goto('file://' + APP);
  await page.waitForTimeout(400);

  await page.addScriptTag({ content: `
    window.C = {
      // 国道4号(東京-青森)に固定。日本全体の縮尺でも十分な長さがある
      reset() {
        currentHighway = HIGHWAYS.find(h => h.id === 4);
        hintUsed = false; answered = false;
        clearStrokes(); quizLayerGroup.clearLayers(); hideResult();
        refitMap(quizMap); updateOfficialDenseCache(); renderQuiz(); renderInkGauge();
      },
      at(tt) {
        const h = currentHighway, r = document.getElementById('quiz-overlay').getBoundingClientRect();
        const i = Math.min(h.path.length - 1, Math.max(0, Math.round(tt * (h.path.length - 1))));
        const p = quizMap.latLngToContainerPoint(h.path[i]);
        return { x: r.x + p.x, y: r.y + p.y };
      },
      ev(type, o) {
        document.getElementById('quiz-overlay').dispatchEvent(new PointerEvent(type, Object.assign({
          pointerId: 1, pointerType: 'touch', button: 0, buttons: 1, bubbles: true, cancelable: true
        }, o)));
      },
      // ルート上の位置ttに、ほとんど指を動かさないストロークを置く（タップに近い操作）
      dab(tt, id) {
        const p = this.at(tt);
        this.ev('pointerdown', { pointerId: id, clientX: p.x, clientY: p.y });
        this.ev('pointermove', { pointerId: id, clientX: p.x + 3, clientY: p.y });
        this.ev('pointerup',   { pointerId: id, clientX: p.x + 3, clientY: p.y });
      },
      // 区間[a,b]をきちんとなぞる
      trace(a, b, id, steps) {
        const n = steps || 60;
        const p0 = this.at(a);
        this.ev('pointerdown', { pointerId: id, clientX: p0.x, clientY: p0.y });
        for (let k = 1; k <= n; k++) {
          const p = this.at(a + (b - a) * k / n);
          this.ev('pointermove', { pointerId: id, clientX: p.x, clientY: p.y });
        }
        const p1 = this.at(b);
        this.ev('pointerup', { pointerId: id, clientX: p1.x, clientY: p1.y });
      },
      score() {
        return {
          coverage: scoreAttempt().score,
          strokes: strokes.length,
          inkPct: Math.round(drawnInk / inkBudget * 100),
          routePx: Math.round(routeLengthPx),
          penWidthPx: Math.round(traceTolerance * 2),
        };
      }
    };
  `});

  await page.click('#tab-quiz');
  await page.waitForTimeout(150);

  // ---- 1. 正攻法：1本で全体をなぞる ----
  let s = await page.evaluate(() => { C.reset(); C.trace(0, 1, 1, 120); return C.score(); });
  check('正攻法（1本で全部なぞる）は満点になる', s.coverage >= 95, s);
  const honest = s;
  const honestRate = honest.coverage / honest.inkPct;

  // ---- 2. ペンを置くだけでもインクを使う（タップがタダではなくなった） ----
  s = await page.evaluate(() => { C.reset(); C.dab(0, 1); return C.score(); });
  check('ちょんと置くだけでもペン幅の円ぶんインクを使う', s.inkPct >= 8, s);
  const perDab = s.inkPct;

  // ---- 3. 短いストロークを並べる方法は、素直になぞるより効率が悪い ----
  s = await page.evaluate(() => {
    C.reset();
    for (let k = 0; k <= 10; k++) C.dab(k / 10, k + 1);
    return C.score();
  });
  // ペン先が円である以上、円は帯より線を覆う効率が原理的に4/π倍高いので、
  // 完全に不利にはできない。「近道にならない」程度に収まっていればよい
  check('短いストロークを並べても、素直になぞるのと大差ない効率に収まる',
    (s.coverage / s.inkPct) <= honestRate * 1.15,
    { dab: (s.coverage / s.inkPct).toFixed(2), honest: honestRate.toFixed(2) });
  check('短いストロークを並べる方法もインクを大量に使う（かつては15%程度で済んでいた）',
    s.inkPct >= 60, s);

  // ---- 4. 分割してなぞっても損をしない（何本に分けても消費は変わらない） ----
  const split = await page.evaluate(() => {
    const out = [];
    for (const n of [2, 4, 8, 12]) {
      C.reset();
      for (let k = 0; k < n; k++) C.trace(k / n, (k + 1) / n, k + 1, Math.round(120 / n));
      out.push(C.score());
    }
    return out;
  });
  split.forEach(r => {
    check(`${r.strokes}本に分けてなぞっても満点になる`, r.coverage >= 95, r);
    check(`${r.strokes}本に分けてもペン消費は1本のときと同程度`,
      Math.abs(r.inkPct - honest.inkPct) <= 5, { split: r.inkPct, honest: honest.inkPct });
  });

  // ---- 5. 同じ所を往復してもインクは二重に減らない（塗られた面積で数えているため） ----
  s = await page.evaluate(() => {
    C.reset();
    C.trace(0, 1, 1, 120);
    const once = drawnInk;
    C.trace(1, 0, 2, 120); // 同じ道を逆向きにもう一度なぞる
    return { once: Math.round(once), twice: Math.round(drawnInk), pct: Math.round(drawnInk / inkBudget * 100) };
  });
  check('同じ所をなぞり直してもインクはほとんど減らない', s.twice < s.once * 1.1, s);

  console.log('\n参考: 正攻法', JSON.stringify(honest), '/ ペンを置く1回あたり', perDab + '%');
  console.log('errors:', errors.length ? errors : 'none');
  await browser.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
