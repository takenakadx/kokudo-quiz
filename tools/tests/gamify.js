// Issue #4: ストリーク・習熟度バッジ・制覇率・学習モードの閲覧記録
const { chromium, EXEC, APP, STUB } = require('./harness');
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

  // 採点を直接呼ぶのではなく、実際になぞって答える（記録は採点経路でしか動かないため）
  await p.addScriptTag({ content: `
    window.G = {
      answer(id, correct) {
        currentHighway = HIGHWAYS.find(h => h.id === id);
        hintUsed = false; answered = false;
        clearStrokes(); quizLayerGroup.clearLayers(); hideResult();
        refitMap(quizMap);
        quizMap.fitBounds(highwayBounds(currentHighway), { padding: [40, 40], animate: false });
        updateOfficialDenseCache(); renderQuiz(); renderInkGauge();
        const ov = document.getElementById('quiz-overlay'), r = ov.getBoundingClientRect();
        const fire = (t, x, y) => ov.dispatchEvent(new PointerEvent(t, {
          pointerId: 1, pointerType: 'touch', bubbles: true, cancelable: true, clientX: x, clientY: y }));
        const h = currentHighway;
        const at = i => { const q = quizMap.latLngToContainerPoint(h.path[i]); return { x: r.x + q.x, y: r.y + q.y }; };
        if (correct) {
          fire('pointerdown', at(0).x, at(0).y);
          for (let i = 1; i < h.path.length; i++) { const q = at(i); fire('pointermove', q.x, q.y); }
          fire('pointerup', at(h.path.length - 1).x, at(h.path.length - 1).y);
        } else {
          // 起点だけ触れて離す＝ほとんど塗れないので不正解になる
          const q = at(0);
          fire('pointerdown', q.x, q.y); fire('pointermove', q.x + 4, q.y); fire('pointerup', q.x + 4, q.y);
        }
        document.getElementById('quiz-submit').click();
        return { grade: document.getElementById('quiz-result').className, stats: loadStats() };
      },
      reset() { localStorage.removeItem('kokudoQuizStats.v1'); renderStats(); renderStudyList(); },
    };
  `});
  await p.click('#tab-quiz'); await p.waitForTimeout(150);

  // ---- ストリーク ----
  let r = await p.evaluate(() => { G.reset();
    const a = G.answer(4, true), b2 = G.answer(5, true), c = G.answer(6, true);
    return { streak: c.stats.streak, best: c.stats.best, correct: c.stats.correct, total: c.stats.total,
             grades: [a.grade, b2.grade, c.grade] }; });
  check('正解を重ねると連続正解数が伸びる', r.streak === 3 && r.best === 3, r);
  check('通算の正解数・出題数も増える', r.correct === 3 && r.total === 3, r);

  const banner = await p.evaluate(() => document.getElementById('quiz-stats').textContent);
  check('成績表示に連続正解数と制覇率が出る',
    banner.includes('3問連続') && /制覇 3 \/ \d+/.test(banner), banner);

  const reward = await p.evaluate(() => document.getElementById('quiz-result-body').innerHTML);
  check('3問連続で結果パネルにごほうびが出る', reward.includes('3問連続正解'), reward.slice(0, 120));

  // ---- 不正解で途切れる ----
  r = await p.evaluate(() => { const x = G.answer(7, false); return { streak: x.stats.streak, best: x.stats.best }; });
  check('不正解で連続正解は0に戻る', r.streak === 0, r);
  check('最高記録は残る', r.best === 3, r);

  // ---- 習熟度バッジ（3回正解でマスター）----
  r = await p.evaluate(() => { G.reset();
    const out = [];
    for (let i = 0; i < 3; i++) {
      const x = G.answer(4, true);
      out.push({ correct: x.stats.byHighway[4].correct,
                 reward: document.getElementById('quiz-result-body').innerHTML.includes('マスター') });
    }
    return out; });
  check('同じ国道を3回正解するとマスターになる', r[2].correct === 3 && r[2].reward === true, r);
  check('2回目まではマスターにならない', r[0].reward === false && r[1].reward === false, r);

  const marked = await p.evaluate(() => {
    document.getElementById('tab-study').click();
    document.getElementById('study-search').value = '4';
    document.getElementById('study-search').dispatchEvent(new Event('input'));
    const btn = [...document.querySelectorAll('#study-hwy-list button')].find(b => b.textContent.includes('国道4号'));
    return { text: btn.textContent, cls: btn.className, count: document.getElementById('study-count').textContent };
  });
  check('マスターした国道は学習モードの一覧で★が付く',
    marked.text.startsWith('★') && marked.cls.includes('mastered'), marked);
  check('一覧にマスター数が出る', marked.count.includes('★1'), marked.count);

  // ---- 学習モードの閲覧記録 ----
  r = await p.evaluate(() => {
    G.reset();
    document.getElementById('study-search').value = '';
    document.getElementById('study-search').dispatchEvent(new Event('input'));
    const before = loadStats().viewed;
    document.querySelector('#study-hwy-list button:nth-of-type(2)').click();
    const btn = document.querySelectorAll('#study-hwy-list button')[1];
    return { beforeCount: Object.keys(before).length,
             afterCount: Object.keys(loadStats().viewed).length,
             cls: btn.className, count: document.getElementById('study-count').textContent };
  });
  check('学習モードで開いた国道が記録される', r.beforeCount === 0 && r.afterCount === 1, r);
  check('見た国道に印が付く', r.cls.includes('seen') || r.cls.includes('active'), r.cls);
  check('一覧に「見た」件数が出る', r.count.includes('見た 1'), r.count);

  // ---- 古い保存データでも落ちない ----
  r = await p.evaluate(() => {
    localStorage.setItem('kokudoQuizStats.v1', JSON.stringify({ total: 5, correct: 2, byHighway: { 4: { attempts: 2, correct: 1 } } }));
    renderStats(); renderStudyList();
    const s = loadStats();
    return { streak: s.streak, best: s.best, viewed: s.viewed, total: s.total,
             text: document.getElementById('quiz-stats').textContent };
  });
  check('項目が欠けた古い保存データを読んでも落ちない',
    r.streak === 0 && r.best === 0 && typeof r.viewed === 'object' && r.total === 5, r);
  check('古いデータでも成績表示が出る', r.text.includes('正解 2 / 出題 5'), r.text);

  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
  if (fail.length || errs.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
