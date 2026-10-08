// #16 フェーズ3: 演出。動きを減らす設定では最終状態をすぐ出すこと
const { chromium, EXEC, APP, STUB, loadHelper } = require('./harness');
const fail = [];
function check(n, c, e) { console.log(`${c?'PASS':'FAIL'}  ${n}${e!==undefined?'  '+JSON.stringify(e):''}`); if(!c) fail.push(n); }

async function play(b, reducedMotion) {
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, reducedMotion });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await loadHelper(p);
  await p.evaluate(() => { QZ.clearProgress(); localStorage.removeItem('kokudoQuizStats.v1'); });
  return { p, errs };
}

(async () => {
  const b = await chromium.launch(EXEC);

  // ---- 動きを減らす設定：数字はすぐ最終値になる ----
  let { p, errs } = await play(b, 'reduce');
  let r = await p.evaluate(() => {
    QZ.openStage(); QZ.startStageByKey('r1-30');
    QZ.ask(4, 'route'); QZ.traceAll(); QZ.submit();
    return { pct: document.querySelector('.pct-count').textContent,
             animates: animates(),
             anim: getComputedStyle(document.getElementById('quiz-result')).animationName };
  });
  check('動きを減らす設定では、網羅率がすぐ最終値になる', r.pct === '100', r);
  check('動きを減らす設定では、アニメーションも止める', r.anim === 'none', r.anim);
  check('animates() が false になる', r.animates === false);

  r = await p.evaluate(() => {
    while (!roundDone()) { QZ.ask(round.queue[round.index], 'route'); QZ.traceAll(); QZ.submit(); QZ.next(); }
    return { score: document.querySelector('#result-stats .score-count').textContent,
             want: String(QZ.round().correct) };
  });
  check('リザルトの正解数もすぐ最終値になる', r.score === r.want, r);
  check('エラーが出ない', errs.length === 0, errs);
  await p.close();

  // ---- 通常：数え上げてから最終値に落ち着く ----
  ({ p, errs } = await play(b, 'no-preference'));
  r = await p.evaluate(() => {
    QZ.openStage(); QZ.startStageByKey('r1-30');
    QZ.ask(4, 'route'); QZ.traceAll(); QZ.submit();
    return { pct: document.querySelector('.pct-count').textContent,
             anim: getComputedStyle(document.getElementById('quiz-result')).animationName };
  });
  check('通常は結果パネルにアニメーションが付く', r.anim !== 'none', r.anim);
  check('数え上げの途中なので、最初は最終値より小さい', Number(r.pct) < 100, r.pct);
  await p.waitForTimeout(700);
  const settled = await p.evaluate(() => document.querySelector('.pct-count').textContent);
  check('数え上げが終わると最終値になる', settled === '100', settled);

  // ---- 画面の切り替わりにアニメーションが付く ----
  const screenAnim = await p.evaluate(() => {
    QZ.quit();
    const el = document.getElementById('panel-title');
    return { cls: el.className, anim: getComputedStyle(el).animationName };
  });
  check('画面を切り替えると screen-in が付く',
    screenAnim.cls.includes('screen-in') && screenAnim.anim === 'screenIn', screenAnim);

  // ---- ごほうびのバッジにも演出が付く ----
  const reward = await p.evaluate(() => {
    QZ.openStage(); QZ.startStageByKey('r1-30');
    for (let i = 0; i < 3; i++) { QZ.ask(round.queue[round.index], 'route'); QZ.traceAll(); QZ.submit();
      if (i < 2) QZ.next(); }
    const el = document.querySelector('.reward.streak');
    return el ? { has: true, anim: getComputedStyle(el).animationName } : { has: false };
  });
  check('3問連続のごほうびに演出が付く', reward.has && reward.anim === 'rewardPop', reward);
  check('エラーが出ない（通常時）', errs.length === 0, errs);
  await p.close();

  await b.close();
  if (fail.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
