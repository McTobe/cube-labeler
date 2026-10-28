// What a sync with Google Drive changes, worked out from fingerprints (see backup_item_digests
// in cube_web.py) of three sides: this device now, the newest backup in Drive, and both of them
// as they were at this device's last sync (the base). Only what one side changed since the base
// moves to the other, so an edit made while offline is never undone by an older copy, and a
// thing is only deleted when the other device deleted it. No imports, so tests run it in Node.

// Icons or templates. local and remote map a key to its fingerprint; base is {l, r}, the two
// sides' fingerprints at the last sync, or null when there is no last sync to go by (a device
// that has just signed in): then nothing is deleted, and things that differ are kept twice.
// Returns {take: keys to take from Drive, conflict: keys both sides changed (Drive's is added
// as a copy), drop: keys to delete here because Drive deleted them}.
export function planItems(local, remote, base) {
  const plan = { take: [], conflict: [], drop: [] };
  const keys = new Set([...Object.keys(local), ...Object.keys(remote)]);
  for (const key of keys) {
    const mine = local[key];
    const theirs = remote[key];
    const changedHere = !base || base.l[key] !== mine;
    const changedThere = !base || base.r[key] !== theirs;
    if (mine !== undefined && theirs !== undefined) {
      if (mine === theirs || !changedThere) continue;
      if (!changedHere) plan.take.push(key);
      else plan.conflict.push(key);
    } else if (mine !== undefined) {
      // Gone from Drive: deleted on another device, unless it was only ever here or edited since
      if (base && key in base.r && !changedHere) plan.drop.push(key);
    } else if (!(base && key in base.l && !changedThere)) {
      // New in Drive, or edited there after this device deleted it
      plan.take.push(key);
    }
  }
  return plan;
}

// Settings, one by one: a setting changed only in Drive is taken; one changed here, or on both
// sides, stays as it is here. Returns the keys to take from Drive.
export function planSettings(local, remote, base) {
  const take = [];
  for (const [key, theirs] of Object.entries(remote)) {
    const mine = local[key];
    if (mine === theirs) continue;
    // Without a last sync (a device joining) Drive's settings are taken, as on a new device
    const changedHere = base ? base.l[key] !== mine : false;
    const changedThere = !base || base.r[key] !== theirs;
    if (changedThere && !changedHere) take.push(key);
  }
  return take;
}

// The base to merge with. synced: the Drive file this device last synced with; newest: the
// newest backup in Drive; files: the backups in Drive, each with the backup it was made on top
// of (appProperties.parent) when the app that made it says so. Returns
//   {how: 'kept'}   the newest backup was made on top of this device's last sync, so the base
//                   kept from then holds (also when an older version of the app made it and
//                   does not say what it was made on, as before)
//   {how: 'parent', id}  two devices synced at once: the newest backup and this device's last
//                   sync both started from backup id, so the merge has to start from there
//   {how: 'none'}   nothing to go by (no last sync, another account, or the backups in between
//                   are gone): the merge only adds
export function baseFor(base, synced, newest, account, files = []) {
  if (!base || !synced || base.account !== account) return { how: 'none' };
  const byId = new Map(files.map((f) => [f.id, f]));
  const parentOf = (id) => {
    const file = byId.get(id);
    return file && file.appProperties ? file.appProperties.parent || null : null;
  };
  // This device's last sync and what it was made on
  const mine = new Set();
  for (let id = synced, n = 0; id && !mine.has(id) && n < 1000; id = parentOf(id), n++) mine.add(id);
  // Back from the newest backup to where it meets them
  const seen = new Set();
  for (let file = newest; file && !seen.has(file.id); file = byId.get(file.appProperties && file.appProperties.parent)) {
    seen.add(file.id);
    const parent = file.appProperties && file.appProperties.parent;
    if (!parent) return { how: 'kept' };
    if (parent === synced) return { how: 'kept' };
    if (mine.has(parent)) return byId.has(parent) ? { how: 'parent', id: parent } : { how: 'none' };
  }
  return { how: 'none' };
}

// Which backups to move to Drive's bin: everything but the newest `recent` and the newest one of
// each of the last `days` days. files: [{id, createdTime}] newest first. Returns ids.
export function pruneBackups(files, { recent = 10, days = 14, now = Date.now() } = {}) {
  const day = (iso) => {
    const d = new Date(iso);
    return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  };
  const seenDays = new Set();
  const out = [];
  files.forEach((file, index) => {
    const time = Date.parse(file.createdTime);
    const recentDay = now - time < days * 24 * 3600 * 1000;
    const firstOfDay = recentDay && !seenDays.has(day(file.createdTime));
    if (recentDay) seenDays.add(day(file.createdTime));
    if (index >= recent && !firstOfDay) out.push(file.id);
  });
  return out;
}
