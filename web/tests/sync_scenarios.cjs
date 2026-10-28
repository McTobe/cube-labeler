// Google Drive sync end to end: two devices and two tabs of the built web app against a fake
// Drive, in the situations that used to lose work. Not part of npm test, since it needs a
// browser and the full Pyodide release; run it after changing sync:
//
//   python web/build.py && python -m http.server 8000 -d web/dist
//   PYODIDE_DIR=/path/to/pyodide-0.29.5/pyodide node web/tests/sync_scenarios.cjs [scenario]
//
// PYODIDE_DIR is the extracted full release from github.com/pyodide/pyodide/releases. Needs
// Playwright with Chromium (require('playwright')).

const assert = require('node:assert/strict');
const { launch, newDevice, openTab, inPage, driveOf } = require('./sync_harness.cjs');

async function twoDevices(browser, account) {
  const pc = await newDevice(browser, 'PC'); pc.account = account;
  const phone = await newDevice(browser, 'Phone'); phone.account = account;
  return { pc, phone, a: await openTab(pc), b: await openTab(phone) };
}

const scenarios = {
  async 'a second tab never syncs an older copy'(browser) {
    const pc = await newDevice(browser, 'PC'); pc.account = 'tabs';
    const phone = await newDevice(browser, 'Phone'); phone.account = 'tabs';
    const t1 = await openTab(pc);
    await inPage.addIcon(t1, 'Screws');
    await inPage.signIn(t1); await inPage.settle(t1);
    const t2 = await openTab(pc);
    const p = await openTab(phone); await inPage.signIn(p); await inPage.settle(p);
    await inPage.addIcon(t2, 'Wago'); await inPage.settle(t2);
    await inPage.setting(t1, { default_tape_mm: 9 }); await inPage.settle(t1);
    await inPage.addIcon(t1, 'Fuse'); await inPage.settle(t1);
    await inPage.comeBack(p);
    assert.deepEqual((await inPage.state(p)).icons, ['Fuse', 'Screws', 'Wago']);
    const again = await openTab(pc);
    assert.deepEqual((await inPage.state(again)).icons, ['Fuse', 'Screws', 'Wago']);
  },

  async 'changes made offline are kept'(browser) {
    const { pc, a, b } = await twoDevices(browser, 'paused');
    await inPage.addIcon(a, 'Screws'); await inPage.putTemplate(a, 'Shelf', 'Shelf A');
    await inPage.signIn(a); await inPage.settle(a);
    await inPage.signIn(b); await inPage.settle(b);
    pc.offline = true;
    await inPage.putTemplate(a, 'Shelf', 'Shelf B');
    await inPage.setting(a, { default_tape_mm: 9 });
    await inPage.deleteIcon(a, 'Screws');
    await inPage.settle(a);
    await inPage.addIcon(b, 'Nails'); await inPage.settle(b);
    pc.offline = false;
    await inPage.comeBack(a);
    const after = await inPage.state(a);
    assert.deepEqual(after.icons, ['Nails']);
    assert.deepEqual(after.templates, ['Shelf:Shelf B']);
    assert.equal(after.tape, 9);
    await inPage.comeBack(b);
    assert.deepEqual(await inPage.state(b), after);
  },

  async 'signing in with another account only adds'(browser) {
    const bobPhone = await newDevice(browser, 'Bob phone'); bobPhone.account = 'bob';
    const bp = await openTab(bobPhone);
    await inPage.addIcon(bp, 'Bob icon'); await inPage.signIn(bp); await inPage.settle(bp);
    const pc = await newDevice(browser, 'PC'); pc.account = 'alice';
    const a = await openTab(pc);
    await inPage.addIcon(a, 'Screws'); await inPage.addIcon(a, 'Nails');
    await inPage.signIn(a); await inPage.settle(a);
    await inPage.signOut(a);
    pc.account = 'bob';
    await inPage.signIn(a); await inPage.settle(a);
    assert.deepEqual((await inPage.state(a)).icons, ['Bob icon', 'Nails', 'Screws']);
  },

  async 'two devices syncing at once keep both changes'(browser) {
    let release;
    const held = new Promise((r) => { release = r; });
    let hold = false;
    const hooks = { beforeUpload: async (device) => { if (device.name === 'Phone' && hold) await held; } };
    const pc = await newDevice(browser, 'PC', hooks); pc.account = 'race';
    const phone = await newDevice(browser, 'Phone', hooks); phone.account = 'race';
    const a = await openTab(pc), b = await openTab(phone);
    await inPage.addIcon(a, 'Screws');
    await inPage.signIn(a); await inPage.settle(a);
    await inPage.signIn(b); await inPage.settle(b);
    hold = true;
    await inPage.setting(b, { default_tape_mm: 12 });
    await b.waitForTimeout(4500);  // the phone has looked in Drive and is uploading
    await inPage.addIcon(a, 'Wago'); await inPage.settle(a);
    release(); await inPage.settle(b);
    await inPage.comeBack(a);
    const after = await inPage.state(a);
    assert.deepEqual(after.icons, ['Screws', 'Wago']);
    assert.equal(after.tape, 12);
  },

  async 'several syncs in a row from the other device all arrive'(browser) {
    const { a, b } = await twoDevices(browser, 'twice');
    await inPage.putTemplate(a, 'Shelf', 'Shelf A'); await inPage.addIcon(a, 'Screws');
    await inPage.signIn(a); await inPage.settle(a);
    await inPage.signIn(b); await inPage.settle(b);
    await inPage.putTemplate(b, 'Shelf', 'Shelf B'); await inPage.settle(b);
    await inPage.addIcon(b, 'Nails'); await inPage.settle(b);
    await inPage.deleteIcon(b, 'Screws'); await inPage.settle(b);
    await inPage.comeBack(a);
    const after = await inPage.state(a);
    assert.deepEqual(after.icons, ['Nails']);
    assert.deepEqual(after.templates, ['Shelf:Shelf B']);
  },

  async 'a template changed on both devices is kept twice'(browser) {
    const { pc, a, b } = await twoDevices(browser, 'conflict');
    await inPage.putTemplate(a, 'Shelf', 'Shelf A');
    await inPage.signIn(a); await inPage.settle(a);
    await inPage.signIn(b); await inPage.settle(b);
    pc.offline = true;
    await inPage.putTemplate(a, 'Shelf', 'PC version'); await inPage.settle(a);
    await inPage.putTemplate(b, 'Shelf', 'Phone version'); await inPage.settle(b);
    pc.offline = false; await inPage.comeBack(a);
    await inPage.comeBack(b);
    const texts = (await inPage.state(a)).templates.map((t) => t.split(':')[1]).sort();
    assert.deepEqual(texts, ['PC version', 'Phone version']);
    assert.deepEqual((await inPage.state(b)).templates, (await inPage.state(a)).templates);
  },

  async 'Drive keeps 10 backups and moves older ones to its bin'(browser) {
    const pc = await newDevice(browser, 'PC'); pc.account = 'prune';
    const a = await openTab(pc);
    await inPage.signIn(a); await inPage.settle(a);
    for (const name of 'ABCDEFGHIJKL') { await inPage.addIcon(a, name); await inPage.settle(a); }
    const files = [...driveOf('prune').values()].filter((f) => f.name.endsWith('.cubebackup'));
    assert.equal(files.filter((f) => !f.trashed).length, 10);
    assert.ok(files.some((f) => f.trashed));
  },
};

(async () => {
  const only = process.argv[2];
  const browser = await launch();
  let failed = 0;
  for (const [name, run] of Object.entries(scenarios)) {
    if (only && !name.includes(only)) continue;
    try {
      await run(browser);
      console.log(`ok   ${name}`);
    } catch (err) {
      failed++;
      console.log(`FAIL ${name}\n${err.stack}`);
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
