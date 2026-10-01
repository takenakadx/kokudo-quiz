const { chromium, EXEC, APP, SPEC, STUB, DATA } = require('./harness');
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
  await page.waitForTimeout(500);

  // helpers injected into the page for driving pointer gestures on the overlay
  await page.addScriptTag({ content: `
    window.T = {
      ov: () => document.getElementById('quiz-overlay'),
      rect: () => document.getElementById('quiz-overlay').getBoundingClientRect(),
      // route point i -> client coords
      rp(i) {
        const h = currentHighway, r = this.rect();
        const n = h.path.length;
        const p = quizMap.latLngToContainerPoint(h.path[Math.min(n - 1, Math.max(0, i))]);
        return { x: r.x + p.x, y: r.y + p.y };
      },
      ev(type, o) {
        this.ov().dispatchEvent(new PointerEvent(type, Object.assign({
          pointerId: 1, pointerType: 'touch', button: 0, buttons: 1, bubbles: true, cancelable: true
        }, o)));
      },
      // draw one stroke along route points [from..to]
      stroke(from, to, pointerId) {
        const id = pointerId || 1;
        const step = (to - from) / 12;
        const first = this.rp(from);
        this.ev('pointerdown', { pointerId: id, clientX: first.x, clientY: first.y });
        for (let k = 1; k <= 12; k++) {
          const p = this.rp(Math.round(from + step * k));
          this.ev('pointermove', { pointerId: id, clientX: p.x, clientY: p.y });
        }
        const last = this.rp(to);
        this.ev('pointerup', { pointerId: id, clientX: last.x, clientY: last.y });
      },
      pick(id) {
        currentHighway = HIGHWAYS.find(h => h.id === id);
        hintUsed = false; answered = false;
        clearStrokes();
        quizLayerGroup.clearLayers();
        hideResult();
        document.getElementById('quiz-hint').textContent = '';
        document.getElementById('quiz-next').disabled = true;
        refitMap(quizMap);
        updateOfficialDenseCache();
        renderQuiz();
        renderInkGauge();
        if (routeTooSmallToTrace()) document.getElementById('quiz-hint').textContent = ZOOM_ADVICE;
        return T.state();
      },
      routePx() { return Math.round(routeLengthPx); },
      state() {
        return {
          strokes: strokes.length,
          points: strokes.reduce((n, s) => n + s.latlngs.length, 0),
          zoom: quizMap.getZoom(),
          pan: [quizMap._state.panX, quizMap._state.panY],
          answered, penEmpty,
          drawn: Math.round(drawnInk), budget: Math.round(inkBudget),
          submitDisabled: document.getElementById('quiz-submit').disabled,
          undoDisabled: document.getElementById('quiz-undo').disabled,
          clearDisabled: document.getElementById('quiz-retry').disabled,
          nextDisabled: document.getElementById('quiz-next').disabled,
          result: document.getElementById('quiz-result-body').textContent.slice(0, 40),
          hint: document.getElementById('quiz-hint').textContent,
        };
      },
      // where is the first stroke's first point on screen right now?
      firstStrokeScreen() {
        if (!strokes.length) return null;
        const p = quizProjector.project(strokes[0].latlngs[0][0], strokes[0].latlngs[0][1]);
        return { x: Math.round(p.x), y: Math.round(p.y) };
      }
    };
  `});

  await page.click('#tab-quiz');
  await page.click('#quiz-start');
  await page.waitForTimeout(150);
  // 日本全体の縮尺でも十分な長さがある国道4号(東京-青森)に固定して、
  // ランダム出題で短い国道が選ばれても結果が変わらないようにする
  await page.evaluate(() => T.pick(4));

  // ---- 1. multiple strokes ----
  let s = await page.evaluate(() => { T.stroke(0, 30); return T.state(); });
  check('1本目を描いたらストローク1本', s.strokes === 1, s);
  check('1本目のあと採点ボタンが押せる', s.submitDisabled === false);
  check('1本目のあとまだ採点されていない', s.answered === false);

  s = await page.evaluate(() => { T.stroke(40, 80, 2); return T.state(); });
  check('2本目を描き足せる（複数回に分けて描ける）', s.strokes === 2, { strokes: s.strokes });

  s = await page.evaluate(() => { T.stroke(90, 130, 3); return T.state(); });
  check('3本目も描き足せる', s.strokes === 3);

  // ---- 2. undo one stroke ----
  const before = s.drawn;
  s = await page.evaluate(() => { document.getElementById('quiz-undo').click(); return T.state(); });
  check('1本消すとストロークが減る', s.strokes === 2);
  check('1本消すとペン残量が戻る', s.drawn < before, { before, after: s.drawn });

  // ---- 3. two-finger pan moves the map, not the pen ----
  const panBefore = await page.evaluate(() => ({ st: T.state(), pt: T.firstStrokeScreen() }));
  s = await page.evaluate(() => {
    const r = T.rect();
    const a = { x: r.x + 300, y: r.y + 300 }, b = { x: r.x + 400, y: r.y + 300 };
    T.ev('pointerdown', { pointerId: 11, clientX: a.x, clientY: a.y });
    T.ev('pointerdown', { pointerId: 12, clientX: b.x, clientY: b.y });
    for (let k = 1; k <= 5; k++) {
      T.ev('pointermove', { pointerId: 11, clientX: a.x + k * 12, clientY: a.y + k * 6 });
      T.ev('pointermove', { pointerId: 12, clientX: b.x + k * 12, clientY: b.y + k * 6 });
    }
    T.ev('pointerup', { pointerId: 11, clientX: a.x + 60, clientY: a.y + 30 });
    T.ev('pointerup', { pointerId: 12, clientX: b.x + 60, clientY: b.y + 30 });
    return T.state();
  });
  const panAfter = await page.evaluate(() => T.firstStrokeScreen());
  check('2本指で地図がpanする', s.pan[0] !== panBefore.st.pan[0] || s.pan[1] !== panBefore.st.pan[1], { pan: s.pan });
  check('2本指ドラッグでは線が増えない', s.strokes === panBefore.st.strokes, { strokes: s.strokes });
  check('panすると描いた線も地図と一緒に動く（画面座標が変わる）',
    panAfter.x !== panBefore.pt.x || panAfter.y !== panBefore.pt.y, { before: panBefore.pt, after: panAfter });

  // ---- 4. two-finger pinch zooms ----
  const zoomBefore = s.zoom;
  s = await page.evaluate(() => {
    const r = T.rect();
    const cx = r.x + 350, cy = r.y + 350;
    T.ev('pointerdown', { pointerId: 21, clientX: cx - 30, clientY: cy });
    T.ev('pointerdown', { pointerId: 22, clientX: cx + 30, clientY: cy });
    for (let k = 1; k <= 6; k++) {
      T.ev('pointermove', { pointerId: 21, clientX: cx - 30 - k * 20, clientY: cy });
      T.ev('pointermove', { pointerId: 22, clientX: cx + 30 + k * 20, clientY: cy });
    }
    T.ev('pointerup', { pointerId: 21, clientX: cx - 150, clientY: cy });
    T.ev('pointerup', { pointerId: 22, clientX: cx + 150, clientY: cy });
    return T.state();
  });
  check('2本指を広げるとズームインする', s.zoom > zoomBefore, { before: zoomBefore, after: s.zoom });

  // ---- 5. a second finger landing mid-stroke discards that stroke ----
  s = await page.evaluate(() => {
    const start = T.rp(0);
    T.ev('pointerdown', { pointerId: 31, clientX: start.x, clientY: start.y });
    for (let k = 1; k <= 4; k++) {
      const p = T.rp(k * 3);
      T.ev('pointermove', { pointerId: 31, clientX: p.x, clientY: p.y });
    }
    const n = strokes.length;
    // second finger arrives: this should be read as "I meant to move the map"
    T.ev('pointerdown', { pointerId: 32, clientX: start.x + 80, clientY: start.y + 80 });
    T.ev('pointerup', { pointerId: 31, clientX: start.x, clientY: start.y });
    T.ev('pointerup', { pointerId: 32, clientX: start.x + 80, clientY: start.y + 80 });
    return Object.assign(T.state(), { strokesBeforeSecondFinger: n });
  });
  check('描き始めに2本目の指が触れたら、その線は破棄される',
    s.strokes === s.strokesBeforeSecondFinger, { now: s.strokes, was: s.strokesBeforeSecondFinger });

  // ---- 6. mouse: left draws, middle pans ----
  const mouseBefore = await page.evaluate(() => T.state());
  s = await page.evaluate(() => {
    const p = T.rp(0);
    T.ev('pointerdown', { pointerId: 41, pointerType: 'mouse', button: 0, clientX: p.x, clientY: p.y });
    for (let k = 1; k <= 8; k++) {
      const q = T.rp(k * 4);
      T.ev('pointermove', { pointerId: 41, pointerType: 'mouse', clientX: q.x, clientY: q.y });
    }
    const e = T.rp(32);
    T.ev('pointerup', { pointerId: 41, pointerType: 'mouse', button: 0, clientX: e.x, clientY: e.y });
    return T.state();
  });
  check('マウス左ドラッグで描ける', s.strokes === mouseBefore.strokes + 1, { was: mouseBefore.strokes, now: s.strokes });

  const midBefore = s;
  s = await page.evaluate(() => {
    const r = T.rect();
    const x = r.x + 300, y = r.y + 300;
    T.ev('pointerdown', { pointerId: 42, pointerType: 'mouse', button: 1, buttons: 4, clientX: x, clientY: y });
    for (let k = 1; k <= 5; k++) {
      T.ev('pointermove', { pointerId: 42, pointerType: 'mouse', buttons: 4, clientX: x - k * 10, clientY: y - k * 8 });
    }
    T.ev('pointerup', { pointerId: 42, pointerType: 'mouse', button: 1, clientX: x - 50, clientY: y - 40 });
    return T.state();
  });
  check('マウス中ドラッグで地図がpanする',
    s.pan[0] !== midBefore.pan[0] || s.pan[1] !== midBefore.pan[1], { before: midBefore.pan, after: s.pan });
  check('マウス中ドラッグでは線が増えない', s.strokes === midBefore.strokes);

  // ---- 7. wheel zoom ----
  const wheelBefore = s.zoom;
  s = await page.evaluate(() => {
    const r = T.rect();
    T.ov().dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: r.x + 300, clientY: r.y + 300, bubbles: true, cancelable: true }));
    return T.state();
  });
  check('ホイールでズームする', s.zoom > wheelBefore, { before: wheelBefore, after: s.zoom });

  // ---- 8. submit scores the attempt ----
  s = await page.evaluate(() => { document.getElementById('quiz-submit').click(); return T.state(); });
  check('採点ボタンで採点される', s.answered === true && s.result.length > 0, { result: s.result });
  check('採点後は採点ボタンが無効', s.submitDisabled === true);
  check('採点後は次の問題へ進める', s.nextDisabled === false);

  // ---- 9. clear all ----
  s = await page.evaluate(() => { document.getElementById('quiz-retry').click(); return T.state(); });
  check('全部消すで線が消える', s.strokes === 0 && s.answered === false, s);

  // ---- 10. short route: tell the user to zoom in instead of silently running dry ----
  s = await page.evaluate(() => T.pick(22)); // 国道22号(名古屋-岐阜, 約26km)
  const px22 = await page.evaluate(() => T.routePx());
  check('短い国道では拡大を促す案内が出る', s.hint.includes('拡大して'), { hint: s.hint, routePx: px22 });
  s = await page.evaluate(() => {
    const r = T.rect();
    for (let i = 0; i < 6; i++) {
      T.ov().dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: r.x + 300, clientY: r.y + 300, bubbles: true, cancelable: true }));
    }
    return T.state();
  });
  check('拡大したら案内が消える', !s.hint.includes('拡大して'), { hint: s.hint });
  check('拡大したらペン残量も実用的な長さになる', await page.evaluate(() => T.routePx()) > 60, { routePx: await page.evaluate(() => T.routePx()) });

  // ---- 11. tracing the whole route in several strokes still scores 正解 ----
  await page.evaluate(() => T.pick(4));
  s = await page.evaluate(() => {
    const n = currentHighway.path.length;
    const thirds = [[0, Math.floor(n / 3)], [Math.floor(n / 3), Math.floor(2 * n / 3)], [Math.floor(2 * n / 3), n - 1]];
    thirds.forEach(([a, b], i) => T.stroke(a, b, 50 + i));
    document.getElementById('quiz-submit').click();
    return T.state();
  });
  check('分割してなぞっても正解判定になる', s.result.includes('正解'), { result: s.result, strokes: s.strokes });

  console.log('\nerrors:', errors.length ? errors : 'none');
  await browser.close();
  if (fail.length || errors.length) { console.log('\nFAILED:', fail); process.exit(1); }
  console.log('\nall checks passed');
})();
