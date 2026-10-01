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

module.exports = { chromium, EXEC, ROOT, APP, SPEC, STUB, DATA };
