/* テスト共通のセットアップ。
   playwright と Chromium の場所は環境によって違うので、ここで吸収する。
   アプリ本体はリポジトリ直下にあり、テストは tools/tests/ にあるので、
   パスもここで解決してテスト側は相対パスを書かない。 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const APP = path.join(ROOT, "index.html");
const SPEC = path.join(ROOT, "spec", "index.html");
const STUB = path.join(__dirname, "leaflet-stub.js");
const DATA = path.join(ROOT, "highways-data.js");

function requirePlaywright() {
  const tries = [
    "playwright",
    "/opt/node22/lib/node_modules/playwright",
    path.join(ROOT, "node_modules", "playwright"),
  ];
  for (const p of tries) {
    try { return require(p); } catch (e) { /* 次を試す */ }
  }
  throw new Error(
    "playwright が見つかりません。`npm i -g playwright` などで入れるか、\n" +
    "NODE_PATH に playwright のあるディレクトリを指定してください。");
}

const { chromium } = requirePlaywright();

/* Chromium の実行ファイル。見つからなければ playwright 既定のものに任せる
   （PLAYWRIGHT_CHROMIUM 環境変数があればそれを最優先）。 */
function chromiumExecutable() {
  if (process.env.PLAYWRIGHT_CHROMIUM) return process.env.PLAYWRIGHT_CHROMIUM;
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  try {
    const dir = fs.readdirSync(base).find(d => d.startsWith("chromium"));
    if (dir) {
      const exe = path.join(base, dir, "chrome-linux", "chrome");
      if (fs.existsSync(exe)) return exe;
    }
  } catch (e) { /* 既定に任せる */ }
  return null;
}

const exe = chromiumExecutable();
const EXEC = exe ? { executablePath: exe } : {};

/* クイズを操作するためのヘルパー。
   テストから「クイズ画面に入る」「この国道を1問出す」「なぞる」「採点する」を
   呼べるようにして、UIの作りをここ1か所に閉じ込める。画面遷移を入れるなど
   クイズの画面構成を変えたときに直すのは、このファイルだけで済むようにするため。 */
const QUIZ_HELPER = `
window.QZ = {
  /* ===== 画面の操作（UIを変えたらここを直す） ===== */
  /* タイトル → ステージ選択 → 出題 と進んで、なぞれる状態にする */
  enter() {
    showScreen('title');
    document.getElementById('go-play').click();   // ステージ選択へ
    this.startRandom();                            // 出題へ
  },
  startRandom() { document.getElementById('quiz-start').click(); },
  /* ステージを選んで始める（keyを省略すると選択中のもの） */
  startStageByKey(key) {
    if (key) { selectedStageKey = key; refreshIdlePrompt(); }
    document.getElementById('quiz-start').click();
  },
  stageKeys() { return STAGES.map(st => st.key); },
  round() { return round && { stageKey: round.stageKey, index: round.index,
                              total: round.queue.length, correct: round.correct,
                              best: round.best, mastered: round.mastered.slice() }; },
  progress() { return loadProgress(); },
  clearProgress() { localStorage.removeItem('kokudoQuizProgress.v1'); refreshIdlePrompt(); },
  quit() { document.getElementById('quiz-quit').click(); },
  screen() { return screen; },
  /* 図鑑（学習モード）を開く */
  openStudy() { showScreen('title'); document.getElementById('go-study').click(); },
  /* ステージ選択を開く */
  openStage() { showScreen('title'); document.getElementById('go-play').click(); },
  /* 「このマップで始める」ボタンの文言（対象問題数が入る） */
  startLabel() { return document.getElementById('quiz-start').textContent; },
  submit() { document.getElementById('quiz-submit').click(); },
  next() { document.getElementById('quiz-next').click(); },
  hint() { document.getElementById('quiz-hint-btn').click(); },
  undo() { document.getElementById('quiz-undo').click(); },
  clearAll() { document.getElementById('quiz-retry').click(); },
  /* いまどのボタンが押せるか。disabled属性を直接見ずにこれを使う */
  can() {
    const d = id => {
      const b = document.getElementById(id);
      return !!b && !b.disabled && !b.hidden;
    };
    return { submit: d('quiz-submit'), undo: d('quiz-undo'), clear: d('quiz-retry'),
             next: d('quiz-next'), hint: d('quiz-hint-btn'), start: d('quiz-start') };
  },
  prompt() { return document.getElementById('quiz-prompt').textContent.trim(); },
  result() { return document.getElementById('quiz-result-body').textContent.trim(); },
  resultHtml() { return document.getElementById('quiz-result-body').innerHTML; },
  hintText() { return document.getElementById('quiz-hint').textContent; },
  overlay() { return document.getElementById('quiz-overlay'); },

  /* 指定した国道を1問出し、なぞれる状態にする。
     zoom: 'japan' なら日本全体のまま、'route' ならその国道いっぱいに寄る */
  ask(id, zoom) {
    currentHighway = HIGHWAYS.find(h => h.id === id);
    hintUsed = false; answered = false;
    clearStrokes();
    quizLayerGroup.clearLayers();
    hideResult();
    document.getElementById('quiz-hint').textContent = '';
    refitMap(quizMap);
    if (zoom === 'route') {
      quizMap.fitBounds(highwayBounds(currentHighway), { padding: [40, 40], animate: false });
    }
    updateOfficialDenseCache();
    renderQuiz();
    renderInkGauge();
    if (zoom !== 'route' && routeTooSmallToTrace()) {
      document.getElementById('quiz-hint').textContent = ZOOM_ADVICE;
    }
    return this.state();
  },

  /* ===== なぞる操作（画面構成に依存しない） ===== */
  current() { return currentHighway; },
  points() { return currentHighway.path.length; },
  /* 正解ルートのi番目の点の、いまの画面座標。
     rect を渡すとそれを基準にする。なぞっている最中はヒントの文言が変わって
     地図の位置が上下にずれることがあるので、1ストロークの間は最初に測った
     位置を使い続ける（実際の指も、画面がずれても同じ場所を触り続ける） */
  at(i, rect) {
    const r = rect || this.overlay().getBoundingClientRect();
    const n = currentHighway.path.length;
    const idx = Math.min(n - 1, Math.max(0, Math.round(i)));
    const q = quizMap.latLngToContainerPoint(currentHighway.path[idx]);
    return { x: r.x + q.x, y: r.y + q.y };
  },
  /* 0〜1の位置で指定する版 */
  atT(t) { return this.at(t * (currentHighway.path.length - 1)); },
  ev(type, opts) {
    this.overlay().dispatchEvent(new PointerEvent(type, Object.assign({
      pointerId: 1, pointerType: 'touch', button: 0, buttons: 1,
      bubbles: true, cancelable: true }, opts)));
  },
  /* ルートのfrom番目からto番目までをなぞる */
  stroke(from, to, pointerId, steps) {
    const id = pointerId || 1, n = steps || 12;
    const r = this.overlay().getBoundingClientRect();
    const a = this.at(from, r);
    this.ev('pointerdown', { pointerId: id, clientX: a.x, clientY: a.y });
    for (let k = 1; k <= n; k++) {
      const p = this.at(from + (to - from) * k / n, r);
      this.ev('pointermove', { pointerId: id, clientX: p.x, clientY: p.y });
    }
    const b = this.at(to, r);
    this.ev('pointerup', { pointerId: id, clientX: b.x, clientY: b.y });
  },
  /* 0〜1の位置で指定する版 */
  strokeT(from, to, pointerId, steps) {
    const n = currentHighway.path.length - 1;
    this.stroke(from * n, to * n, pointerId, steps);
  },
  /* ルート全体を、間引かずに全点なぞる */
  traceAll() {
    const n = currentHighway.path.length;
    const r = this.overlay().getBoundingClientRect();
    const a = this.at(0, r);
    this.ev('pointerdown', { clientX: a.x, clientY: a.y });
    for (let i = 1; i < n; i++) { const p = this.at(i, r); this.ev('pointermove', { clientX: p.x, clientY: p.y }); }
    const b = this.at(n - 1, r);
    this.ev('pointerup', { clientX: b.x, clientY: b.y });
  },
  /* ほとんど指を動かさないストローク（タップに近い操作） */
  dab(t, pointerId) {
    const id = pointerId || 1, p = this.atT(t);
    this.ev('pointerdown', { pointerId: id, clientX: p.x, clientY: p.y });
    this.ev('pointermove', { pointerId: id, clientX: p.x + 3, clientY: p.y });
    this.ev('pointerup', { pointerId: id, clientX: p.x + 3, clientY: p.y });
  },

  /* 既存テストが使っている別名 */
  rect() { return this.overlay().getBoundingClientRect(); },
  ov() { return this.overlay(); },
  rp(i) { return this.at(i); },
  pick(id) { return this.ask(id); },

  state() {
    const c = this.can();
    return {
      strokes: strokes.length,
      points: strokes.reduce((n, s) => n + s.latlngs.length, 0),
      zoom: quizMap.getZoom(),
      pan: [quizMap._state.panX, quizMap._state.panY],
      answered, penEmpty,
      drawn: Math.round(drawnInk), budget: Math.round(inkBudget),
      submitDisabled: !c.submit, undoDisabled: !c.undo,
      clearDisabled: !c.clear, nextDisabled: !c.next,
      result: this.result().slice(0, 40),
      hint: this.hintText(),
    };
  },
  /* 採点結果とペンの消費。採点ボタンは押さずに今の状態を測るだけ */
  score() {
    return {
      coverage: scoreAttempt().score,
      strokes: strokes.length,
      inkPct: Math.round(drawnInk / inkBudget * 100),
      routePx: Math.round(routeLengthPx),
      penWidthPx: Math.round(traceTolerance * 2),
    };
  },
  routePx() { return Math.round(routeLengthPx); },
  firstStrokeScreen() {
    if (!strokes.length) return null;
    const p = quizProjector.project(strokes[0].latlngs[0][0], strokes[0].latlngs[0][1]);
    return { x: Math.round(p.x), y: Math.round(p.y) };
  },
};
`;

/* クイズ画面を開き、window.QZ を使えるようにする。
   テストはページを開いたあと必ずこれを呼ぶ。 */
async function openQuiz(page, waitMs) {
  await page.addScriptTag({ content: QUIZ_HELPER });
  await page.evaluate(() => QZ.enter());
  await page.waitForTimeout(waitMs === undefined ? 150 : waitMs);
}

/* クイズ画面には入らず、ヘルパーだけ読み込む */
async function loadHelper(page) {
  await page.addScriptTag({ content: QUIZ_HELPER });
}

/* 図鑑（学習モード）を開く。タブが無くなったので、テストもタイトルから入る */
async function openStudy(page, waitMs) {
  await page.addScriptTag({ content: QUIZ_HELPER });
  await page.evaluate(() => QZ.openStudy());
  await page.waitForTimeout(waitMs === undefined ? 150 : waitMs);
}

module.exports = { chromium, EXEC, ROOT, APP, SPEC, STUB, DATA, openQuiz, openStudy, loadHelper };

