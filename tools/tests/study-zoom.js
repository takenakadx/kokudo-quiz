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
  await page.waitForTimeout(500); // 初期表示(1号を自動選択)のアニメーションが落ち着くのを待つ

  const state = () => page.evaluate(() => ({
    zoom: studyMap.getZoom(),
    pan: [studyMap._state.panX, studyMap._state.panY],
    highwayId: studyHighway && studyHighway.id
  }));

  // ---- 1. 初期表示（1号）で、日本全体表示より拡大されている ----
  let s = await state();
  check('初期表示は国道1号が選ばれている', s.highwayId === 1, s);
  check('初期表示ですでに日本全体よりズームしている', s.zoom > 5, s);

  // ---- 2. 短い国道を選ぶと、長い国道よりさらに拡大される ----
  // 国道4号(東京-青森、約753km) と 国道43号(大阪-神戸、約26km)
  const longBtn = await page.$('#study-hwy-list button:has-text("国道4号")');
  await longBtn.click();
  await page.waitForTimeout(500); // renderStudyの経路描画アニメーション(60フレーム)を待つ
  const longState = await state();
  check('国道4号を選ぶとその国道にズームする', longState.highwayId === 4 && longState.zoom > 5, longState);

  const shortBtn = await page.$('#study-hwy-list button:has-text("国道43号")');
  await shortBtn.click();
  await page.waitForTimeout(500);
  const shortState = await state();
  check('短い国道(43号)は長い国道(4号)よりさらに拡大される',
    shortState.zoom > longState.zoom, { short: shortState.zoom, long: longState.zoom });

  // ---- 3. 選んだ国道が変わればpan(表示位置)も変わる ----
  check('国道が変わると表示位置(pan)も変わる',
    shortState.pan[0] !== longState.pan[0] || shortState.pan[1] !== longState.pan[1],
    { short: shortState.pan, long: longState.pan });

  // ---- 4. なぞった軌跡を消してから選び直しても正しくズームする(pickHighway等の副作用がないか) ----
  const loopBtn = await page.$('#study-hwy-list button:has-text("国道16号")'); // 環状路線
  await loopBtn.click();
  await page.waitForTimeout(500);
  const loopState = await state();
  check('環状路線(16号)でもズームする', loopState.highwayId === 16 && loopState.zoom > 5, loopState);

  // ---- 5. クイズタブへ行って学習タブに戻っても、選んでいた国道の表示を維持する ----
  await openQuiz(page);
  await page.waitForTimeout(150);
  await page.click('#tab-study');
  await page.waitForTimeout(150);
  const backState = await state();
  check('タブを行き来しても選択中の国道の表示を維持する',
    backState.highwayId === 16 && Math.abs(backState.zoom - loopState.zoom) < 0.5,
    { before: loopState, after: backState });

  // ---- 6. 「もう一度再生」でも同じズームを保つ ----
  await page.click('#study-replay');
  await page.waitForTimeout(500);
  const replayState = await state();
  check('再生ボタンでもズームは変わらない（同じ国道の範囲）',
    Math.abs(replayState.zoom - backState.zoom) < 0.5, { before: backState, after: replayState });

  console.log('\nerrors:', errors.length ? errors : 'none');
  await browser.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
