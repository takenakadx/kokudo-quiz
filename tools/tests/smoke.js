const { chromium, EXEC, APP, STUB, openQuiz } = require('./harness');
const path = require('path');

(async () => {
  const browser = await chromium.launch(EXEC);
  const page = await browser.newPage({ viewport: { width: 900, height: 800 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (msg) => {
    const t = msg.text();
    if (msg.type() === 'error' && !t.includes('ERR_TUNNEL') && !t.includes('Failed to load resource')) {
      errors.push('console.error: ' + t);
    }
  });

  await page.addInitScript({ path: STUB });
  await page.goto('file://' + APP);
  await page.waitForTimeout(600);

  // 1. data sanity across every route
  const data = await page.evaluate(() => {
    const bad = [];
    for (const h of HIGHWAYS) {
      if (!h.number || !h.startLabel || !h.endLabel) bad.push([h.id, 'missing labels']);
      if (!Array.isArray(h.path) || h.path.length < 5) bad.push([h.id, 'path too short']);
      if (!h.prefectures || !h.prefectures.length) bad.push([h.id, 'no prefectures']);
      if (![1, 2, 3].includes(h.difficulty)) bad.push([h.id, 'bad difficulty']);
      // 豆知識は手で書いた路線にだけ付く（自動生成の路線には無くてよい）
      for (const p of h.path) {
        if (!(p[0] > 24 && p[0] < 46 && p[1] > 122 && p[1] < 147)) { bad.push([h.id, 'point out of Japan: ' + p]); break; }
      }
    }
    const byDiff = { 1: 0, 2: 0, 3: 0 };
    HIGHWAYS.forEach(h => byDiff[h.difficulty]++);
    return { count: HIGHWAYS.length, bad, byDiff, L: typeof L };
  });
  console.log('data:', JSON.stringify(data));

  // 2. study mode: click through every highway in the list, confirm info renders
  const studyCount = await page.evaluate(() => document.querySelectorAll('#study-hwy-list button, #study-hwy-list li').length);
  console.log('study list entries:', studyCount);
  const studyResults = [];
  for (let i = 0; i < Math.min(studyCount, 35); i++) {
    const sel = `#study-hwy-list button:nth-of-type(${i + 1})`;
    const exists = await page.$(sel);
    if (!exists) break;
    await exists.click();
    await page.waitForTimeout(60);
    const info = await page.evaluate(() => document.getElementById('study-info').textContent.trim().slice(0, 40));
    studyResults.push(info.length > 0);
  }
  console.log('study renders ok:', studyResults.filter(Boolean).length, '/', studyResults.length);

  // 3. quiz mode: run several questions end to end, tracing the real route each time
  await openQuiz(page, 200);
  const quizLog = [];
  for (let round = 0; round < 6; round++) {
    await page.evaluate(() => QZ.startRandom());
    await page.waitForTimeout(200);
    const target = await page.evaluate(() => {
      // trace the actual answer route so scoring runs over real geometry
      const h = window.__testCurrent || null;
      return h ? h.id : null;
    });
    // drag along the displayed route: sample the canvas by dragging across the map
    // trace the true answer route by projecting its own lat/lngs to screen points,
    // so scoring runs over real geometry (a correct answer should score high)
    const traced = await page.evaluate(() => {
      const h = QZ.current();
      if (!h) return null;
      QZ.stroke(0, h.path.length - 1, 1, 60);   // 正解ルートをなぞる
      return { id: h.id, points: 61 };
    });
    // 一筆ごとに採点されなくなったので、明示的に採点ボタンを押す
    await page.evaluate(() => { if (QZ.can().submit) QZ.submit(); });
    await page.waitForTimeout(250);
    const res0 = traced; const res = await page.evaluate(() => ({
      prompt: QZ.prompt().slice(0, 30),
      result: QZ.result().slice(0, 45),
    }));
    quizLog.push(Object.assign({traced: res0}, res));
    const nextEnabled = await page.evaluate(() => QZ.can().next);
    if (nextEnabled) { await page.evaluate(() => QZ.next()); await page.waitForTimeout(150); }
    else quizLog[quizLog.length - 1].nextDisabled = true;
  }
  console.log('quiz rounds:');
  quizLog.forEach((q, i) => console.log(`  ${i}: prompt="${q.prompt}" traced=${JSON.stringify(q.traced)} result="${q.result}"`));

  // 4. map/difficulty filter selects exist and cover every highway
  const filters = await page.evaluate(() => {
    const mapOpts = [...document.querySelectorAll('#quiz-map-select option')].map(o => o.textContent);
    const diffOpts = [...document.querySelectorAll('#quiz-diff-select option')].map(o => o.textContent);
    const allCount = Number((mapOpts[0].match(/(\d+)問/) || [])[1]);
    return { mapOpts, diffOpts, allCount, highwaysTotal: HIGHWAYS.length };
  });
  console.log('filters:', JSON.stringify(filters));

  console.log('ERRORS:', errors.length ? JSON.stringify(errors, null, 2) : 'none');
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
