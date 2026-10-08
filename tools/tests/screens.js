// #16 フェーズ1: 画面遷移と、その場面で出るボタン
const { chromium, EXEC, APP, STUB, loadHelper } = require('./harness');
const fail = [];
function check(n, c, e) { console.log(`${c?'PASS':'FAIL'}  ${n}${e!==undefined?'  '+JSON.stringify(e):''}`); if(!c) fail.push(n); }
(async () => {
  const b = await chromium.launch(EXEC);
  const p = await b.newPage({ viewport: { width: 390, height: 844 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { const t = m.text();
    if (m.type() === 'error' && !t.includes('ERR_TUNNEL') && !t.includes('Failed to load resource')) errs.push(t); });
  await p.addInitScript({ path: STUB });
  await p.goto('file://' + APP);
  await p.waitForTimeout(400);
  await loadHelper(p);

  // いま見えている画面と、押せるボタンの文言
  const view = () => p.evaluate(() => ({
    screen: QZ.screen(),
    panels: ['panel-title','panel-stage','panel-quiz','panel-study']
      .filter(id => !document.getElementById(id).hidden),
    buttons: [...document.querySelectorAll('button')]
      .filter(b => b.offsetParent !== null && !b.closest('.hwy-list') && !b.closest('.stage-list'))
      .map(b => b.textContent.trim()),
    overflowY: document.documentElement.scrollHeight - document.documentElement.clientHeight,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));

  // ---- 起動はタイトル ----
  let v = await view();
  check('起動するとタイトル画面', v.screen === 'title' && v.panels.join() === 'panel-title', v);
  check('タイトルの主役は「あそぶ」', v.buttons[0] === 'あそぶ', v.buttons);
  check('タブは無くなっている', await p.evaluate(() => !document.getElementById('tab-quiz')));

  // ---- タイトル → ステージ選択 ----
  await p.click('#go-play'); await p.waitForTimeout(120);
  v = await view();
  check('「あそぶ」でステージ選択へ', v.screen === 'stage' && v.panels.join() === 'panel-stage', v);
  check('ステージ選択に出題数つきの開始ボタンがある',
    v.buttons.some(t => /はじめる（\d+問）/.test(t)), v.buttons);
  const cards = await p.evaluate(() => ({
    range: document.querySelectorAll('#stage-list-range .stage-card').length,
    map: document.querySelectorAll('#stage-list-map .stage-card').length,
  }));
  check('番号帯のステージが16個並ぶ', cards.range === 16, cards);
  check('まとめて遊ぶマップも並ぶ', cards.map >= 9, cards);

  // ---- ステージ選択 → 出題 ----
  await p.click('#quiz-start'); await p.waitForTimeout(150);
  v = await view();
  check('「始める」で出題画面へ', v.screen === 'playing' && v.panels.join() === 'panel-quiz', v);
  check('なぞる前は「採点する」を出さない', !v.buttons.includes('採点する'), v.buttons);
  check('なぞる前でもヒントとやめるは出す',
    v.buttons.includes('ヒント') && v.buttons.includes('やめる'), v.buttons);

  // ---- なぞると採点・消去が出る ----
  await p.evaluate(() => { QZ.ask(4); QZ.stroke(0, 40, 1, 20); });
  await p.waitForTimeout(120);
  v = await view();
  check('なぞると「採点する」「1本消す」「全部消す」が出る',
    ['採点する','1本消す','全部消す'].every(t => v.buttons.includes(t)), v.buttons);
  check('なぞっている間は「次の問題へ」を出さない', !v.buttons.includes('次の問題へ'), v.buttons);

  // ---- 採点 → 判定 ----
  await p.evaluate(() => QZ.submit()); await p.waitForTimeout(150);
  v = await view();
  check('採点すると判定画面になる', v.screen === 'judge', v);
  check('判定の主役は「次の問題へ」', v.buttons.includes('次の問題へ'), v.buttons);
  check('判定では採点・消去を出さない',
    !v.buttons.includes('採点する') && !v.buttons.includes('全部消す'), v.buttons);
  check('判定でも地図は見えている', v.panels.join() === 'panel-quiz', v);

  // ---- 次の問題へ ----
  await p.evaluate(() => QZ.next()); await p.waitForTimeout(150);
  v = await view();
  check('「次の問題へ」で出題画面に戻る', v.screen === 'playing', v);
  check('次の問題では線が消えて採点ボタンも消える',
    !v.buttons.includes('採点する') && (await p.evaluate(() => QZ.state().strokes)) === 0, v.buttons);

  // ---- 採点しても、拡大してなぞった構図のままにする ----
  // 短い国道は拡大してなぞるので、採点した瞬間に日本全体へ戻ると
  // 正解ルートがどこだったのか確認できなくなる
  const camera = await p.evaluate(() => {
    QZ.ask(134);                       // 湘南の134号。日本全体では数pxしかない
    zoomMapAround({ x: 195, y: 300 }, 1);
    zoomMapAround({ x: 195, y: 300 }, 1);
    zoomMapAround({ x: 195, y: 300 }, 1);
    panMapBy(40, -30);
    const before = { zoom: quizMap.getZoom(), pan: [quizMap._state.panX, quizMap._state.panY] };
    QZ.stroke(0, QZ.points() - 1, 1, 20);
    QZ.submit();
    const judged = { zoom: quizMap.getZoom(), pan: [quizMap._state.panX, quizMap._state.panY] };
    QZ.next();
    const nextQ = { zoom: quizMap.getZoom() };
    return { before, judged, nextQ };
  });
  check('採点しても拡大・移動した構図が保たれる',
    camera.judged.zoom === camera.before.zoom &&
    JSON.stringify(camera.judged.pan) === JSON.stringify(camera.before.pan), camera);
  check('次の問題へ進むと日本全体の構図に戻る', camera.nextQ.zoom < camera.before.zoom, camera);

  // ---- 「全部消す」は同じ問題のやり直しなので構図を変えない ----
  const retried = await p.evaluate(() => {
    QZ.ask(134);
    zoomMapAround({ x: 195, y: 300 }, 1);
    zoomMapAround({ x: 195, y: 300 }, 1);
    const before = quizMap.getZoom();
    QZ.stroke(0, 20, 1, 10);
    QZ.clearAll();
    return { before, after: quizMap.getZoom() };
  });
  check('「全部消す」でも構図は変わらない', retried.after === retried.before, retried);

  // ---- やめる → タイトル ----
  await p.evaluate(() => QZ.quit()); await p.waitForTimeout(150);
  v = await view();
  check('「やめる」でタイトルへ戻る', v.screen === 'title', v);

  // ---- 図鑑 ----
  await p.click('#go-study'); await p.waitForTimeout(150);
  v = await view();
  check('タイトルから図鑑へ行ける', v.screen === 'study' && v.panels.join() === 'panel-study', v);
  await p.click('#study-back'); await p.waitForTimeout(120);
  check('図鑑からタイトルへ戻れる', (await view()).screen === 'title');

  // ---- どの画面でも1画面に収まる ----
  for (const [name, go] of [['タイトル', () => QZ.screen()],
                            ['ステージ選択', () => QZ.openStage()],
                            ['出題', () => QZ.enter()],
                            ['図鑑', () => QZ.openStudy()]]) {
    await p.evaluate(go); await p.waitForTimeout(200);
    const m = await view();
    check(`${name}が1画面に収まる`, m.overflowY <= 0 && m.overflowX <= 0,
      { 縦: m.overflowY, 横: m.overflowX });
  }

  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
  if (fail.length || errs.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
