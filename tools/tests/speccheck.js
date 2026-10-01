const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const path = require('path');
const fail = [];
function check(n, c, e) { console.log(`${c?'PASS':'FAIL'}  ${n}${e!==undefined?'  '+JSON.stringify(e):''}`); if(!c) fail.push(n); }
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  // 仕様書の「実装済み」件数は、アプリが実際に収録している本数と一致していなければならない
  const appCount = (require('fs').readFileSync(path.join(__dirname, 'highways-data.js'), 'utf8')
    .match(/\n  \{\s*id:/g) || []).length;
  const p = await b.newPage({ viewport: { width: 1100, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('file://' + path.join(__dirname, 'spec-check.html'));
  await p.waitForTimeout(300);
  const o = await p.evaluate(() => ({
    all: +document.getElementById('statAll').textContent,
    done: +document.getElementById('statDone').textContent,
    prep: +document.getElementById('statPrep').textContent,
    todo: +document.getElementById('statTodo').textContent,
    cells: document.querySelectorAll('.cov-cell').length,
    doneCells: [...document.querySelectorAll('.cov-cell.done')].map(c => +c.textContent),
    prepCells: [...document.querySelectorAll('.cov-cell.prep')].map(c => +c.textContent),
    vacantCells: [...document.querySelectorAll('.cov-cell.vacant')].map(c => +c.textContent),
    rowIds: [...document.querySelectorAll('tbody tr[id]')].map(t => t.id).slice(0, 3),
  }));
  console.log(JSON.stringify({ ...o, doneCells: o.doneCells.length, prepCells: o.prepCells, vacantCells: o.vacantCells }, null, 1));
  check('総数459', o.all === 459);
  check('内訳の合計が総数と一致する', o.done + o.prep + o.todo === o.all, o);
  check('実装済みの数がアプリの収録数と一致する', o.done === appCount, { spec: o.done, app: appCount });
  check('欠番は109/110/111/214/215/216のみ表示（59-100は注記へ）',
    JSON.stringify(o.vacantCells) === JSON.stringify([109,110,111,214,215,216]));
  check('マス目の総数=1..58 + 101..507', o.cells === 58 + 407);
  check('実装済みのマスの数が件数表示と一致する', o.doneCells.length === o.done);
  check('色が付かないのは生データが無い路線だけ', o.todo <= 2, { todo: o.todo });
  check('収録を見送った路線は一覧に理由付きで残る', o.prepCells.length === o.prep && o.prep > 0,
    { prep: o.prep, cells: o.prepCells.length });
  // 番号を押すと該当行へ飛ぶ
  await p.click('.cov-cell.prep');
  await p.waitForTimeout(400);
  const jumped = await p.evaluate(() => {
    const r = document.querySelector('tbody tr.flash');
    return { flash: !!r, hidden: r ? r.classList.contains('hidden') : true,
             name: r ? r.querySelector('.route-name').textContent : null };
  });
  check('番号を押すと該当行が表示される', jumped.flash && !jumped.hidden && !!jumped.name, jumped);
  // フィルターで隠れた状態から飛んでも見える
  await p.click('#filters button[data-filter="done"]');
  await p.waitForTimeout(100);
  await p.click('.cov-cell.done[href="#r13"]');
  await p.waitForTimeout(400);
  const jumped2 = await p.evaluate(() => {
    const r = document.getElementById('r13');
    return { hidden: r.classList.contains('hidden'), flash: r.classList.contains('flash') };
  });
  check('フィルターで絞った状態から飛んでも隠れたままにならない', !jumped2.hidden && jumped2.flash, jumped2);
  // 横スクロールしない
  for (const w of [1100, 700, 390]) {
    await p.setViewportSize({ width: w, height: 900 });
    await p.waitForTimeout(150);
    const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`幅${w}pxで横スクロールが出ない`, over <= 0, { overflow: over });
  }
  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
  if (fail.length || errs.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
