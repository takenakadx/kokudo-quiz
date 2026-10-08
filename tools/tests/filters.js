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
  await page.waitForTimeout(150);

  // ---- 1. selecting a map category narrows the idle-prompt count and the pool ----
  let s = await page.evaluate(() => {
    const sel = document.getElementById('quiz-map-select');
    sel.value = 'digit1';
    sel.dispatchEvent(new Event('change'));
    return { prompt: document.getElementById('quiz-prompt').textContent, pool: currentPool().map(h => h.id).sort((a, b) => a - b) };
  });
  check('一桁国道を選ぶと対象が9問になる', s.pool.length === 9, s.pool);
  check('全部一桁の番号だけになる', s.pool.every(id => id < 10), s.pool);
  check('バナーに対象問題数が出る', s.prompt.includes('9問'), s.prompt);

  // ---- 2. every question drawn stays within the selected category, none repeats until the bag is exhausted ----
  // pickHighway()自体の挙動を見たいので、実際の解答UI操作(なぞって採点)は経由せず
  // startQuestion()を直接何度も呼ぶ(採点フローのテストはux.js側でカバー済み)。
  const seen = await page.evaluate(() => {
    const out = [];
    for (let i = 0; i < 9; i++) { startQuestion(); out.push(currentHighway.id); }
    return out;
  });
  check('9回引いても全部「一桁国道」の範囲内', seen.every(id => id < 10), seen);
  check('9回引く間、山を使い切るまでは重複しない（9問すべて別）',
    new Set(seen).size === 9, { seen, unique: new Set(seen).size });

  // ---- 3. after exhausting the bag of 9, the 10th draw reshuffles and still stays in-category ----
  const tenth = await page.evaluate(() => { startQuestion(); return currentHighway.id; });
  check('山を使い切った後もカテゴリ内から出題され続ける', tenth < 10, tenth);

  // ---- 4. switching to a narrow region category that has no "むずかしい" falls back gracefully ----
  s = await page.evaluate(() => {
    document.getElementById('quiz-map-select').value = 'region-hokkaido-tohoku';
    document.getElementById('quiz-map-select').dispatchEvent(new Event('change'));
    document.getElementById('quiz-diff-select').value = '3'; // むずかしい: 北海道・東北地方には0件
    document.getElementById('quiz-diff-select').dispatchEvent(new Event('change'));
    const cat = MAP_CATEGORIES.find(c => c.key === 'region-hokkaido-tohoku');
    return { pool: currentPool().map(h => h.id),
             expected: highwaysInCategory(cat).map(h => h.id),
             prompt: document.getElementById('quiz-prompt').textContent };
  });
  check('マップ×難易度が0件でもプールが空にならない（マップ優先でフォールバック）',
    s.pool.length > 0, s);
  check('フォールバック後もマップの範囲(北海道・東北)は守られる',
    s.pool.every(id => s.expected.includes(id)), { pool: s.pool, expected: s.expected });

  // ---- 5. all-highways option still offers every route ----
  s = await page.evaluate(() => {
    document.getElementById('quiz-diff-select').value = '';
    document.getElementById('quiz-diff-select').dispatchEvent(new Event('change'));
    document.getElementById('quiz-map-select').value = '';
    document.getElementById('quiz-map-select').dispatchEvent(new Event('change'));
    return { pool: currentPool().length, total: HIGHWAYS.length };
  });
  check('「すべての国道」に戻すと収録している全問が対象になる', s.pool === s.total, s);

  console.log('\nerrors:', errors.length ? errors : 'none');
  await browser.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
