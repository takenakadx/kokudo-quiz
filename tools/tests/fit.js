const { chromium, EXEC, APP, STUB, openQuiz } = require('./harness');
const path = require('path');
const sizes = [
  ['phone-small', 360, 640], ['phone', 390, 844], ['phone-landscape', 844, 390],
  ['tablet', 768, 1024], ['desktop', 1280, 800], ['desktop-short', 1280, 600],
];
(async () => {
  const b = await chromium.launch(EXEC);
  let bad = 0;
  for (const [name, w, h] of sizes) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.addInitScript({ path: STUB });
    await p.goto('file://' + APP);
    await p.waitForTimeout(300);
    await openQuiz(p, 200);
    // 結果パネルも出ている状態にして、それでも1画面に収まるかを見る
    await p.evaluate(() => {
      QZ.startRandom();
      QZ.ask(4);
      QZ.stroke(0, QZ.points() - 1, 1, 20);
      QZ.submit();
    });
    await p.waitForTimeout(250);
    const m = await p.evaluate(() => {
      const de = document.documentElement;
      const btns = [...document.querySelectorAll('#panel-quiz .controls button')];
      const lastBtn = btns[btns.length - 1].getBoundingClientRect();
      const stats = document.getElementById('quiz-stats').getBoundingClientRect();
      const map = document.querySelector('#panel-quiz .map-wrap').getBoundingClientRect();
      return {
        pageScrollY: de.scrollHeight - de.clientHeight,
        pageScrollX: de.scrollWidth - de.clientWidth,
        buttonsVisible: lastBtn.bottom <= window.innerHeight + 0.5 && lastBtn.top >= 0,
        statsVisible: stats.bottom <= window.innerHeight + 0.5,
        mapH: Math.round(map.height),
        buttonRows: new Set(btns.map(x => Math.round(x.getBoundingClientRect().top))).size,
        resultShown: document.getElementById('quiz-result').classList.contains('show'),
      };
    });
    const ok = m.pageScrollY <= 0 && m.pageScrollX <= 0 && m.buttonsVisible && m.statsVisible && m.mapH > 100;
    if (!ok) bad++;
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name} ${w}x${h}`, JSON.stringify(m));
    if (process.env.SHOT) await p.screenshot({ path: `/tmp/kokudo-test/fit-${name}.png` });
    await p.close();
  }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
