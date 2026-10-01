// 学習モードの分類セレクト・番号検索の回帰テスト
const { chromium, EXEC, APP, SPEC, STUB, DATA } = require('./harness');
const path = require('path');
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

  const nums = () => p.evaluate(() => [...document.querySelectorAll('#study-hwy-list button')].map(b => b.textContent));
  const total = await p.evaluate(() => HIGHWAYS.length);
  const inCat = key => p.evaluate(k => highwaysInCategory(MAP_CATEGORIES.find(c => c.key === k)).length, key);
  const count = () => p.evaluate(() => document.getElementById('study-count').textContent);

  check('初期表示は全国道', (await nums()).length === total, await count());
  check('件数表示は総数を含む', (await count()).includes(total + '本'), await count());

  // 分類セレクトはクイズの「マップ」と同じ選択肢
  const opts = await p.evaluate(() => ({
    study: [...document.querySelectorAll('#study-cat-select option')].map(o => o.value),
    quiz: [...document.querySelectorAll('#quiz-map-select option')].map(o => o.value),
  }));
  check('分類の選択肢がクイズのマップと一致する', JSON.stringify(opts.study) === JSON.stringify(opts.quiz), opts.study.length);

  await p.selectOption('#study-cat-select', 'digit1');
  const d1 = await inCat('digit1');
  check('一桁国道で絞ると分類の件数と一致する', (await nums()).length === d1, await nums());
  check('件数表示が追従する', (await count()).startsWith(d1 + ' /'), await count());

  await p.selectOption('#study-cat-select', 'region-kanto');
  const kanto = await nums();
  check('関東地方で絞ると関東を通る国道だけになる',
    kanto.length === await inCat('region-kanto') && kanto.includes('国道134号'), kanto.length);

  // 番号検索は部分一致（17と入れたら17号・171号・176号）
  await p.selectOption('#study-cat-select', '');
  await p.fill('#study-search', '17');
  const want17 = await p.evaluate(() =>
    HIGHWAYS.filter(h => String(Number(h.number.match(/\d+/)[0])).includes('17')).map(h => h.number));
  check('番号検索は部分一致（17を含む番号が全部出る）',
    JSON.stringify(await nums()) === JSON.stringify(want17) && want17.length >= 3,
    { got: (await nums()).slice(0, 6), want: want17.length + '件' });

  // 分類と検索の組み合わせ
  await p.selectOption('#study-cat-select', 'digit2');
  check('分類と番号検索を組み合わせられる', JSON.stringify(await nums()) === JSON.stringify(['国道17号']), await nums());

  await p.fill('#study-search', '999');
  check('該当なしのときは案内を出す',
    await p.evaluate(() => !!document.querySelector('.hwy-list-empty') && !document.querySelector('#study-hwy-list button')));

  // 選択した国道は絞り込みを変えても選択状態が残る
  await p.fill('#study-search', '');
  await p.selectOption('#study-cat-select', '');
  await p.click('#study-hwy-list button:nth-of-type(4)');
  await p.waitForTimeout(100);
  const picked = await p.evaluate(() => document.querySelector('#study-hwy-list button.active').textContent);
  await p.selectOption('#study-cat-select', 'digit1');
  const kept = await p.evaluate(() => {
    const a = document.querySelector('#study-hwy-list button.active');
    return { active: a ? a.textContent : null, info: document.getElementById('study-info').textContent };
  });
  check('絞り込みを変えても選択中の国道は選択されたまま',
    kept.active === picked && kept.info.startsWith(picked), { picked, kept: kept.active });

  // 絞り込みの選択は端末に保存される
  await p.selectOption('#study-cat-select', 'region-kyushu');
  await p.reload();
  await p.waitForTimeout(400);
  check('分類の選択がリロード後も残る',
    await p.evaluate(() => document.getElementById('study-cat-select').value) === 'region-kyushu');
  check('検索欄はリロードで空に戻る（絞り込みが残って混乱しないように）',
    await p.evaluate(() => document.getElementById('study-search').value) === '');

  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
  if (fail.length || errs.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
