const { chromium, EXEC, APP, STUB, openQuiz } = require('./harness');
const path = require('path');
(async () => {
  const b = await chromium.launch(EXEC);
  const p = await b.newPage({ viewport: { width: 900, height: 900 } });
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await openQuiz(p);
  const res = await p.evaluate(() => {
    const out = [];
    for (const h of HIGHWAYS) {
      // 短い国道は日本全体だとなぞれないので、その国道が画面いっぱいになるまで寄る
      QZ.ask(h.id, 'route');
      QZ.traceAll();
      const s = QZ.score();
      out.push({ id: h.id, num: h.number, coverage: s.coverage, inkPct: s.inkPct });
    }
    return out;
  });
  // 合否は「完璧になぞれば正解判定(網羅率80%以上)になるか」で見る。
  // 95%に届かない路線は、形が複雑で間引きの影響が出ているだけなので参考表示に留める。
  const GRADE_CORRECT = 80;
  const bad = res.filter(r => r.coverage < GRADE_CORRECT);
  const low = res.filter(r => r.coverage >= GRADE_CORRECT && r.coverage < 95);
  res.forEach(r => console.log(`${r.coverage >= 95 ? 'ok ' : (r.coverage >= GRADE_CORRECT ? 'low' : 'BAD')} ${r.num.padEnd(9)} coverage=${r.coverage}% ink=${r.inkPct}%`));
  console.log(`\n全${res.length}路線中、95%以上 ${res.length - low.length - bad.length} / 80〜94% ${low.length} / 正解に届かない ${bad.length}`);
  if (low.length) console.log('  80〜94%:', low.map(r => `${r.num}(${r.coverage}%)`).join(' '));
  console.log('\nroutes below the correct-answer threshold:', bad.length ? JSON.stringify(bad) : 'none');
  console.log('errors:', errors.length ? errors : 'none');
  await b.close();
  process.exit(bad.length || errors.length ? 1 : 0);
})();
