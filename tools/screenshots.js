// Takes the web usage guide's screenshots (docs/images/guide/) from the real web app.
//
//   python web/build.py
//   npm install --no-save playwright && npx playwright install chromium   (once)
//   node tools/screenshots.js
//
// It serves web/dist on a local port, drives the app through its own modules and fakes a
// connected printer with a tape roll, so no printer is needed. The first start downloads
// Pyodide from jsDelivr; set PYODIDE_DIR to a folder with the extracted Pyodide 0.29.5 release
// to load it from disk instead.
const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium, devices } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'web', 'dist');
const OUT = path.join(ROOT, 'docs', 'images', 'guide');
const PORT = 8765;
const URL = `http://localhost:${PORT}/`;
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/';
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.svg': 'image/svg+xml', '.zip': 'application/zip',
  '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2' };

function serve() {
  return http.createServer((req, res) => {
    let file = path.join(DIST, decodeURIComponent(req.url.split('?')[0]));
    if (!file.startsWith(DIST)) { res.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    if (!fs.existsSync(file)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  }).listen(PORT);
}

async function newContext(browser, options) {
  const ctx = await browser.newContext({ locale: 'en-GB', ...options });
  if (process.env.PYODIDE_DIR) {
    await ctx.route(`${PYODIDE_URL}**`, (route) => {
      const file = path.join(process.env.PYODIDE_DIR, route.request().url().slice(PYODIDE_URL.length).split('?')[0]);
      if (fs.existsSync(file)) route.fulfill({ path: file }); else route.continue();
    });
  }
  return ctx;
}

// Opens the app and waits until Python has started
async function open(page) {
  page.on('pageerror', (err) => console.warn('Page error:', err.message));
  await page.goto(URL);
  for (let i = 0; i < 360; i++) {
    const phase = await page.evaluate(async () => (await import('/js/app.js')).boot.get().phase);
    if (phase === 'ready') break;
    if (phase === 'failed') throw new Error('The app failed to start');
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(1500);
}

// A connected PT-P300BT with 12 mm tape and an 8 m roll that is partly used
async function fakePrinter(page) {
  await page.evaluate(async () => {
    const app = await import('/js/app.js');
    const tape = await import('/js/tape.js');
    const info = { model: 'PT-P300BT', tape_width_mm: 12, tape_type: 'Laminated', tape_color: 'White',
      text_color: 'Black', power: 'Battery, full', errors: [], tape_loaded: true };
    const roll = tape.newRoll(8000);
    roll.loaded = new Date(Date.now() - 9 * 864e5).toISOString();
    roll.used = { 'this-device': 1840 };
    roll.prints = { 'this-device': 41 };
    await app.updateSettings({ tape_rolls: { [tape.tapeKey(info)]: roll } });
    app.printer.set({ ...app.printer.get(), transport: {}, state: 'ready', info });
  });
  await page.waitForTimeout(400);
}

async function setText(page, text) {
  await page.evaluate(async (t) => (await import('/js/app.js')).updateLabel({ text: t }), text);
  await page.waitForTimeout(1500);
}

async function setMode(page, mode) {
  await page.evaluate(async (m) => (await import('/js/app.js')).setMode(m), mode);
  await page.waitForTimeout(1500);
}

async function goTo(page, id) {
  await page.evaluate((id) => { location.hash = `#/${id}`; }, id);
  await page.waitForTimeout(2500);
}

const shot = (name) => path.join(OUT, `${name}.png`);

// Opens a top bar chip's sheet and takes the sheet
async function sheetShot(page, chipText, name) {
  await page.locator('button.printer-chip:visible', { hasText: chipText }).first().click();
  // No dimmed backdrop in the sheet's rounded corners
  const style = await page.addStyleTag({ content: 'dialog.sheet::backdrop { background: transparent !important; }' });
  await page.waitForTimeout(700);
  await page.locator('dialog.sheet[open]').screenshot({ path: shot(name) });
  await style.evaluate((el) => el.remove());
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
}

async function desktop(browser) {
  const ctx = await newContext(browser, { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.25 });
  const page = await ctx.newPage();
  await open(page);
  await fakePrinter(page);

  await setText(page, '# **Garage**\n-# Shelf 3 · Paint & glue');
  await page.screenshot({ path: shot('label') });
  await page.locator('.mode-switch').first().screenshot({ path: shot('kinds') });
  await sheetShot(page, 'left', 'printer');
  await sheetShot(page, 'Sync', 'sync');

  for (const [mode, text] of [['bin', null], ['ports', null], ['flag', 'Switch → NAS']]) {
    await setMode(page, mode);
    if (text) await setText(page, text);
    await page.locator('section.card.preview').first().screenshot({ path: shot(`kind-${mode}`) });
  }
  await setMode(page, 'text');

  for (const text of ['# Screws', '# Nails', '# Wall plugs']) {
    await setText(page, text);
    await page.evaluate(async () => (await import('/js/app.js')).addToQueue());
  }
  await goTo(page, 'queue');
  await page.evaluate(async () => (await import('/js/app.js')).say(''));
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot('queue') });

  // The queue as printed labels in the history
  await page.evaluate(async () => {
    const app = await import('/js/app.js');
    await (await import('/js/history.js')).recordPrinted(app.app.get().queue);
  });
  await goTo(page, 'history');
  await page.screenshot({ path: shot('history') });
  await ctx.close();
}

async function phone(browser) {
  const ctx = await newContext(browser, { ...devices['Pixel 7'] });
  const page = await ctx.newPage();
  await open(page);
  await fakePrinter(page);
  await setText(page, '# **Garage**\n-# Shelf 3 · Paint & glue');
  await page.screenshot({ path: shot('phone') });
  await ctx.close();
}

(async () => {
  if (!fs.existsSync(path.join(DIST, 'index.html'))) throw new Error('Build the web app first: python web/build.py');
  fs.mkdirSync(OUT, { recursive: true });
  const server = serve();
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: 'localhost' } : undefined;
  const browser = await chromium.launch({ proxy });
  try {
    await desktop(browser);
    await phone(browser);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(`Screenshots saved in ${path.relative(ROOT, OUT)}`);
})().catch((err) => { console.error(err); process.exit(1); });
