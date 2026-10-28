// Drives the built web app in Chromium as several devices (browser contexts) and tabs (pages),
// with a fake Google Drive and a fake sign-in helper, for web/tests/sync_scenarios.cjs.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PYO = process.env.PYODIDE_DIR || path.join(__dirname, '..', 'node_modules', 'pyodide');
const BASE = process.env.APP_URL || 'http://localhost:8000/';

// --- Fake Drive, one per Google account -----------------------------------------------------
let clock = Date.parse('2026-10-28T10:00:00Z');
const tick = () => new Date((clock += 1000)).toISOString();
let nextId = 1;
const drives = {};  // account -> Map(id -> file)
const driveOf = (account) => (drives[account] ||= new Map());
const log = [];

function multipart(buf, contentType) {
  const boundary = /boundary=(.+)$/.exec(contentType)[1];
  const text = buf.toString('latin1');
  const parts = text.split(`--${boundary}`).slice(1, -1);
  const meta = JSON.parse(parts[0].split('\r\n\r\n').slice(1).join('\r\n\r\n').trim());
  const raw = parts[1];
  const start = raw.indexOf('\r\n\r\n') + 4;
  const data = Buffer.from(raw.slice(start, raw.length - 2), 'latin1');
  return { meta, data };
}

// hooks.beforeUpload(device) can return a promise to hold an upload
async function driveRoute(route, device, hooks) {
  const req = route.request();
  const url = new URL(req.url());
  const auth = req.headers()['authorization'] || '';
  const account = auth.replace('Bearer token-', '').split('-')[0];
  const files = driveOf(account);
  const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  const p = url.pathname;
  if (device.offline) return route.abort('internetdisconnected');
  if (p === '/drive/v3/about') return json({ user: { emailAddress: `${account}@example.com` } });
  if (p === '/upload/drive/v3/files' && req.method() === 'POST') {
    if (hooks.beforeUpload) await hooks.beforeUpload(device);
    const { meta, data } = multipart(req.postDataBuffer(), req.headers()['content-type']);
    const id = `f${nextId++}`;
    files.set(id, { id, ...meta, createdTime: tick(), data, trashed: false });
    log.push(`${device.name} uploaded ${id}`);
    return json({ id });
  }
  if (p === '/drive/v3/files' && req.method() === 'POST') {
    const meta = JSON.parse(req.postData());
    const id = `d${nextId++}`;
    files.set(id, { id, ...meta, createdTime: tick(), trashed: false });
    return json({ id });
  }
  if (p === '/drive/v3/files' && req.method() === 'GET') {
    const q = url.searchParams.get('q');
    let list = [...files.values()].filter((f) => !f.trashed);
    if (q.includes('vnd.google-apps.folder')) {
      list = list.filter((f) => f.mimeType === 'application/vnd.google-apps.folder');
      if (q.includes('appProperties has')) list = list.filter((f) => f.appProperties && f.appProperties.cubeLabeler === 'backups');
      else { const name = /name = '([^']+)'/.exec(q)[1]; list = list.filter((f) => f.name === name); }
      list.sort((a, b) => (a.createdTime < b.createdTime ? -1 : 1));
    } else {
      const parent = /'([^']+)' in parents/.exec(q)[1];
      list = list.filter((f) => (f.parents || []).includes(parent));
      list.sort((a, b) => (a.createdTime < b.createdTime ? 1 : -1));
    }
    return json({ files: list.map(({ id, name, createdTime, appProperties }) => ({ id, name, createdTime, appProperties })) });
  }
  const m = /^\/drive\/v3\/files\/([^/]+)$/.exec(p);
  if (m) {
    const f = files.get(m[1]);
    if (req.method() === 'PATCH') {
      const change = JSON.parse(req.postData());
      if (change.trashed) { f.trashed = true; log.push(`${device.name} trashed ${f.id}`); }
      if (change.appProperties) f.appProperties = { ...f.appProperties, ...change.appProperties };
      return json({ id: f.id });
    }
    if (req.method() === 'DELETE') { files.delete(m[1]); log.push(`${device.name} deleted ${m[1]}`); return route.fulfill({ status: 204, body: '' }); }
    if (!f) return json({ error: { message: 'File not found' } }, 404);
    if (url.searchParams.get('alt') === 'media') return route.fulfill({ status: 200, contentType: 'application/zip', body: f.data });
    return json({ id: f.id, trashed: f.trashed });
  }
  return json({ error: { message: `unhandled ${p}` } }, 400);
}

async function newDevice(browser, name, hooks = {}) {
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1440, height: 900 } });
  const device = { name, context, account: 'alice', signedIn: false, offline: false };
  await context.route('https://cdn.jsdelivr.net/pyodide/v0.29.5/full/**', (route) => {
    const file = path.join(PYO, new URL(route.request().url()).pathname.split('/full/')[1]);
    if (!fs.existsSync(file)) return route.fulfill({ status: 404 });
    route.fulfill({ path: file });
  });
  await context.route('**/auth/status', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ enabled: true, signedIn: device.signedIn }) }));
  await context.route('**/auth/start**', (route) => {
    device.signedIn = true;
    route.fulfill({ contentType: 'text/html', body: `<script>const c=new BroadcastChannel('cube-drive-sign-in');c.postMessage({ok:true});setTimeout(()=>window.close(),50)</script>` });
  });
  await context.route('**/auth/token', (route) => {
    if (!device.signedIn) return route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"signed_out"}' });
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ access_token: `token-${device.account}-${Math.random()}`, expires_in: 3600 }) });
  });
  await context.route('**/auth/signout', (route) => { device.signedIn = false; route.fulfill({ contentType: 'application/json', body: '{"ok":true}' }); });
  await context.route('https://www.googleapis.com/**', (route) => driveRoute(route, device, hooks));
  return device;
}

async function openTab(device) {
  const page = await device.context.newPage();
  page.on('pageerror', (e) => console.log(`[${device.name}] pageerror`, e.message));
  await page.goto(`${BASE}#/settings`);
  await page.evaluate(async () => {
    const { boot } = await import('./js/app.js');
    for (let i = 0; i < 1800 && boot.get().phase !== 'ready'; i++) await new Promise((r) => setTimeout(r, 100));
    if (boot.get().phase !== 'ready') throw new Error(`boot: ${JSON.stringify(boot.get())}`);
    const lib = await import('./js/library.js');
    for (let i = 0; i < 100 && !lib.library.get().ready; i++) await new Promise((r) => setTimeout(r, 100));
  });
  return page;
}

// Helpers run inside the page
const inPage = {
  async state(page) {
    return page.evaluate(async () => {
      const { library } = await import('./js/library.js');
      const { templates } = await import('./js/templates.js');
      const { app } = await import('./js/app.js');
      const { history } = await import('./js/history.js');
      return {
        icons: library.get().user.map((i) => i.title).sort(),
        templates: templates.get().mine.map((t) => `${t.name}:${t.item.label ? t.item.label.text : ''}`).sort(),
        theme: app.get().settings.theme,
        tape: app.get().settings.default_tape_mm,
        history: history.get().entries.length,
      };
    });
  },
  async addIcon(page, title) {
    return page.evaluate(async (title) => {
      const { saveUserIcon } = await import('./js/library.js');
      // a tiny valid PNG made on a canvas
      const c = new OffscreenCanvas(8, 8); const g = c.getContext('2d'); g.fillRect(0, 0, title.length % 8 + 1, 4);
      const png = new Uint8Array(await (await c.convertToBlob({ type: 'image/png' })).arrayBuffer());
      saveUserIcon({ title, category: 'My Icons', png });
    }, title);
  },
  async deleteIcon(page, title) {
    return page.evaluate(async (title) => {
      const { library, deleteUserIcon } = await import('./js/library.js');
      deleteUserIcon(library.get().user.find((i) => i.title === title).key);
    }, title);
  },
  async putTemplate(page, name, text) {
    return page.evaluate(async ([name, text]) => {
      const { putTemplate } = await import('./js/templates.js');
      const { currentItem } = await import('./js/app.js');
      const item = structuredClone(currentItem());
      item.label.text = text;
      putTemplate(name, item);
    }, [name, text]);
  },
  async setting(page, change) {
    return page.evaluate(async (change) => (await import('./js/app.js')).updateSettings(change), change);
  },
  async signIn(page) {
    await page.evaluate(async () => {
      const { signInToDrive } = await import('./js/gdrive.js');
      const { startDriveBackup } = await import('./js/autobackup.js');
      await signInToDrive();
      await startDriveBackup();
    });
  },
  async signOut(page) {
    await page.evaluate(async () => (await import('./js/gdrive.js')).signOutOfDrive());
  },
  // What the app does when you come back to it (another tab, the phone's app switcher)
  async comeBack(page) {
    await page.evaluate(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      const { autoBackup } = await import('./js/autobackup.js');
      await new Promise((r) => setTimeout(r, 300));
      for (let i = 0; i < 200 && autoBackup.get().busy; i++) await new Promise((r) => setTimeout(r, 100));
    });
  },
  async syncNow(page) {
    return page.evaluate(async () => {
      const { backupNow, autoBackup } = await import('./js/autobackup.js');
      for (let i = 0; i < 200 && autoBackup.get().busy; i++) await new Promise((r) => setTimeout(r, 100));
      await backupNow();
      return autoBackup.get().driveError;
    });
  },
  // Waits out the 3 s delay after a change and the sync it starts
  async settle(page) {
    await page.waitForTimeout(3600);
    await page.evaluate(async () => {
      const { autoBackup } = await import('./js/autobackup.js');
      for (let i = 0; i < 200 && autoBackup.get().busy; i++) await new Promise((r) => setTimeout(r, 100));
    });
  },
};

async function launch() {
  return chromium.launch({ proxy: { server: process.env.HTTPS_PROXY, bypass: 'localhost,127.0.0.1' } });
}

module.exports = { launch, newDevice, openTab, inPage, drives, driveOf, log };
