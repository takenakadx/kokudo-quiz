// #16 フェーズ2: 番号帯ステージ・進捗の保存と再開・リザルト画面
const { chromium, EXEC, APP, STUB, loadHelper } = require('./harness');
const fail = [];
function check(n, c, e) { console.log(`${c?'PASS':'FAIL'}  ${n}${e!==undefined?'  '+JSON.stringify(e):''}`); if(!c) fail.push(n); }
(async () => {
  const b = await chromium.launch(EXEC);
  const p = await b.newPage({ viewport: { width: 900, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { const t = m.text();
    if (m.type() === 'error' && !t.includes('ERR_TUNNEL') && !t.includes('Failed to load resource')) errs.push(t); });
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await loadHelper(p);
  await p.evaluate(() => { QZ.clearProgress(); localStorage.removeItem('kokudoQuizStats.v1'); });

  // ---- ステージの区切り ----
  const stages = await p.evaluate(() => STAGES.filter(s => s.kind === 'range')
    .map(s => ({ key: s.key, label: s.label, n: stageHighways(s).length })));
  check('番号帯のステージは16個', stages.length === 16, stages.length);
  check('最初は国道1〜30号', stages[0].label === '国道1〜30号' && stages[0].n === 30, stages[0]);
  check('二桁の区切りは欠番の手前(58号)まで', stages[1].label === '国道31〜58号', stages[1]);
  check('三桁は101号から始まる', stages[2].label === '国道101〜130号', stages[2]);
  check('最後は507号まで', stages[15].label === '国道491〜507号', stages[15]);
  check('全ステージの合計が収録数と一致する',
    stages.reduce((a, s) => a + s.n, 0) === await p.evaluate(() => HIGHWAYS.length),
    stages.reduce((a, s) => a + s.n, 0));
  check('欠番の区間だけのステージは作らない', stages.every(s => s.n > 0));

  // ---- ステージを始めると、その番号帯からしか出ない ----
  let r = await p.evaluate(() => {
    QZ.openStage();
    QZ.startStageByKey('r101-130');
    const ids = round.queue.slice();
    return { ids, stage: QZ.round().stageKey, total: QZ.round().total, cur: QZ.current().id };
  });
  check('選んだステージの国道だけが山札に入る',
    r.ids.every(id => id >= 101 && id <= 130), r.ids.slice(0, 5));
  check('山札は重複しない', new Set(r.ids).size === r.ids.length, r.ids.length);
  check('1問目がその山札から出る', r.ids[0] === r.cur, { first: r.ids[0], cur: r.cur });

  // ---- 進捗の表示 ----
  const prompt = await p.evaluate(() => QZ.prompt());
  check('出題画面に何問目かが出る', /^1 \/ \d+問目/.test(prompt), prompt);

  // ---- 3問進めて中断し、続きから再開できる ----
  r = await p.evaluate(() => {
    for (let i = 0; i < 3; i++) {
      QZ.ask(round.queue[round.index], 'route');
      QZ.traceAll();
      QZ.submit();
      QZ.next();
    }
    return { round: QZ.round(), saved: QZ.progress()['r101-130'] };
  });
  check('3問終えるとindexが3になる', r.round.index === 3, r.round);
  check('3問とも正解している', r.round.correct === 3, r.round);
  check('進捗が端末に保存される', r.saved && r.saved.index === 3 && r.saved.correct === 3, r.saved);

  const beforeQueue = await p.evaluate(() => round.queue.slice());
  await p.evaluate(() => QZ.quit());
  await p.reload();
  await p.waitForTimeout(400);
  await loadHelper(p);
  const card = await p.evaluate(() => {
    selectedStageKey = 'r101-130';
    QZ.openStage();   // 画面を開き直すだけで、ボタンの文言も進捗に合わせて変わるはず
    const c = [...document.querySelectorAll('#stage-list-range .stage-card')]
      .find(el => el.textContent.includes('101〜130'));
    return { text: c.textContent, start: QZ.startLabel() };
  });
  check('途中のステージはカードに進捗が出る', card.text.includes('3 /'), card.text);
  check('開始ボタンが「つづきから」になる', card.start.includes('つづきから'), card.start);

  r = await p.evaluate(() => {
    QZ.startStageByKey('r101-130');
    return { index: QZ.round().index, queue: round.queue.slice(), cur: QZ.current().id };
  });
  check('リロードしても4問目から再開する', r.index === 3, r.index);
  check('山札の並びも保たれる', JSON.stringify(r.queue) === JSON.stringify(beforeQueue));
  check('再開した問題は4番目の国道', r.cur === beforeQueue[3], { cur: r.cur, want: beforeQueue[3] });

  // ---- 最後まで解くとリザルトが出る ----
  r = await p.evaluate(() => {
    // 残りを一気に片付ける（偶数問目はわざと外して正解率を作る）
    let i = 0;
    while (round.index < round.queue.length) {
      QZ.ask(round.queue[round.index], 'route');
      if (i % 2 === 0) QZ.traceAll(); else QZ.dab(0);
      QZ.submit();
      QZ.next();
      i++;
    }
    return { screen: QZ.screen(),
             stage: document.getElementById('result-stage').textContent,
             stats: document.getElementById('result-stats').textContent,
             saved: QZ.progress()['r101-130'] };
  });
  check('最後まで解くとリザルト画面になる', r.screen === 'result', r.screen);
  check('リザルトにステージ名が出る', r.stage === '国道101〜130号', r.stage);
  check('リザルトに正解数が出る', /\d+ \/ \d+正解/.test(r.stats), r.stats);
  check('やり切ったステージも進捗として残る',
    r.saved && r.saved.index === r.saved.queue.length, r.saved);

  const cleared = await p.evaluate(() => {
    QZ.openStage();
    const c = [...document.querySelectorAll('#stage-list-range .stage-card')]
      .find(el => el.textContent.includes('101〜130'));
    return { text: c.textContent, cls: c.className };
  });
  check('終えたステージには✓と正解数が出る',
    cleared.cls.includes('cleared') && cleared.text.includes('正解'), cleared);

  // ---- もう一度やると最初から ----
  r = await p.evaluate(() => {
    QZ.openStage();
    QZ.startStageByKey('r101-130');
    return QZ.round();
  });
  check('終えたステージを選び直すと最初から始まる', r.index === 0, r);

  // ---- まとめて遊ぶマップもステージとして動く ----
  r = await p.evaluate(() => { QZ.startStageByKey('mdigit1'); return QZ.round(); });
  check('マップもステージとして始められる', r.total === 9, r);

  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
  if (fail.length || errs.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
