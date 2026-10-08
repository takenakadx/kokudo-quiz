const { chromium, EXEC, APP, STUB, openQuiz } = require('./harness');
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

  await openQuiz(page);

  // ---- 1. 正攻法：1本で全体をなぞる ----
  let s = await page.evaluate(() => { QZ.ask(4); QZ.strokeT(0, 1, 1, 120); return QZ.score(); });
  check('正攻法（1本で全部なぞる）は満点になる', s.coverage >= 95, s);
  const honest = s;
  const honestRate = honest.coverage / honest.inkPct;

  // ---- 2. ペンを置くだけでもインクを使う（タップがタダではなくなった） ----
  s = await page.evaluate(() => { QZ.ask(4); QZ.dab(0, 1); return QZ.score(); });
  check('ちょんと置くだけでもペン幅の円ぶんインクを使う', s.inkPct >= 8, s);
  const perDab = s.inkPct;

  // ---- 3. 短いストロークを並べる方法は、素直になぞるより効率が悪い ----
  s = await page.evaluate(() => {
    QZ.ask(4);
    for (let k = 0; k <= 10; k++) QZ.dab(k / 10, k + 1);
    return QZ.score();
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
      QZ.ask(4);
      for (let k = 0; k < n; k++) QZ.strokeT(k / n, (k + 1) / n, k + 1, Math.round(120 / n));
      out.push(QZ.score());
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
    QZ.ask(4);
    QZ.strokeT(0, 1, 1, 120);
    const once = drawnInk;
    QZ.strokeT(1, 0, 2, 120); // 同じ道を逆向きにもう一度なぞる
    return { once: Math.round(once), twice: Math.round(drawnInk), pct: Math.round(drawnInk / inkBudget * 100) };
  });
  check('同じ所をなぞり直してもインクはほとんど減らない', s.twice < s.once * 1.1, s);

  console.log('\n参考: 正攻法', JSON.stringify(honest), '/ ペンを置く1回あたり', perDab + '%');
  console.log('errors:', errors.length ? errors : 'none');
  await browser.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
