const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage({ viewport: { width: 900, height: 800 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (msg) => {
    const t = msg.text();
    if (msg.type() === 'error' && !t.includes('ERR_TUNNEL') && !t.includes('Failed to load resource')) {
      errors.push('console.error: ' + t);
    }
  });

  await page.addInitScript({ path: path.join(__dirname, 'leaflet-stub.js') });
  await page.goto('file://' + path.join(__dirname, 'index.html'));
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
  await page.click('#tab-quiz');
  await page.waitForTimeout(200);
  const quizLog = [];
  for (let round = 0; round < 6; round++) {
    await page.click('#quiz-start');
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
      const overlay = document.getElementById('quiz-overlay');
      const r = overlay.getBoundingClientRect();
      const h = (typeof currentHighway !== "undefined" && currentHighway) ? currentHighway : null;
      if (!h) return null;
      const pts = [];
      const step = Math.max(1, Math.floor(h.path.length / 60));
      for (let i = 0; i < h.path.length; i += step) {
        const p = quizMap.latLngToContainerPoint(h.path[i]);
        pts.push([r.x + p.x, r.y + p.y]);
      }
      const fire = (type, xy) => overlay.dispatchEvent(new PointerEvent(type, {
        pointerId: 1, bubbles: true, cancelable: true, clientX: xy[0], clientY: xy[1],
      }));
      fire('pointerdown', pts[0]);
      for (const xy of pts.slice(1)) fire('pointermove', xy);
      fire('pointerup', pts[pts.length - 1]);
      return { id: h.id, points: pts.length };
    });
    // 一筆ごとに採点されなくなったので、明示的に採点ボタンを押す
    await page.evaluate(() => {
      const b = document.getElementById('quiz-submit');
      if (b && !b.disabled) b.click();
    });
    await page.waitForTimeout(250);
    const res0 = traced; const res = await page.evaluate(() => ({
      prompt: document.getElementById('quiz-prompt').textContent.trim().slice(0, 30),
      result: document.getElementById('quiz-result-body').textContent.trim().slice(0, 45),
    }));
    quizLog.push(Object.assign({traced: res0}, res));
    const nextEnabled = await page.evaluate(() => {
      const b = document.getElementById('quiz-next');
      return !!b && !b.disabled && b.offsetParent !== null;
    });
    if (nextEnabled) { await page.click('#quiz-next'); await page.waitForTimeout(150); }
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
