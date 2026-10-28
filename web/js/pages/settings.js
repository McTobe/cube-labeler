// Settings: printer, label defaults, how the app looks, AI icons, backups and sync, about
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Segmented, Sheet, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateSettings, labelDefaults } from '../app.js';
import { HISTORY_SIZES, historySizeChanged } from '../history.js';
import { saveBackup, lastBackup, readBackup, restoreBackup } from '../backup.js';
import {
  autoBackup, backupNow, chooseFolder, allowFolder, stopAutoBackup, startDriveBackup, continueDriveBackup, joinDrive, cancelJoin,
  undoLastSync, beforeSyncFile,
} from '../autobackup.js';
import { drive, driveReady, signInToDrive, signOutOfDrive, listDriveBackups, downloadDriveBackup, cancelSignIn } from '../gdrive.js';
import { ai, loadAi, setKey, setModel } from '../ai.js';
import { errorMessage } from '../../printer.js';
import { PrinterPanel } from '../printer-ui.js';
import { APP_VERSION, BUILD_CHANNEL, BUILD_COMMIT } from '../version.js';

function StorageUse() {
  const [estimate, setEstimate] = useState(null);
  useEffect(() => {
    if (navigator.storage && navigator.storage.estimate) navigator.storage.estimate().then(setEstimate, () => {});
  }, []);
  if (!estimate || !estimate.usage) return null;
  const mb = estimate.usage / 1e6;
  return html`<span>${mb < 1 ? 'Less than 1' : Math.round(mb)} MB used on this device</span>`;
}

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

// "17:42", "Yesterday 21:05", "Mon 26 Oct": short times for lists of syncs and versions
function shortDate(iso, { time = true } = {}) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const clock = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(new Date()) - day(date)) / 86400000);
  if (days === 0) return time ? clock : 'Today';
  if (days === 1) return time ? `Yesterday ${clock}` : 'Yesterday';
  return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

// "a minute ago", "5 minutes ago", "3 hours ago", or the date
function ago(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!(minutes >= 0)) return '';
  if (minutes < 2) return 'a minute ago';
  if (minutes < 60) return `${minutes} minutes ago`;
  if (minutes < 120) return 'an hour ago';
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)} hours ago`;
  return formatDate(iso);
}

function RestoreSheet({ opened, onClose, onDone }) {
  const [parts, setParts] = useState({ icons: true, settings: true, templates: true, fonts: true, history: true });
  const [onConflict, setOnConflict] = useState('skip');
  const [busy, setBusy] = useState(false);
  if (!opened) return html`<${Sheet} open=${false} title="" onClose=${onClose} />`;
  const has = {
    icons: opened.icons.length > 0,
    settings: opened.settings !== null,
    templates: opened.templates.length > 0,
    fonts: (opened.fonts || []).length > 0,
    history: (opened.history || []).length > 0,
  };
  const conflicts = (parts.icons ? opened.iconPlan.conflicts : 0) + (parts.templates ? opened.templatePlan.conflicts : 0);
  const restore = async () => {
    setBusy(true);
    try {
      onDone(await restoreBackup(opened, Object.fromEntries(Object.keys(has).map((k) => [k, parts[k] && has[k]])), onConflict));
    } catch (err) {
      onDone(null, errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const iconNote = [
    opened.iconPlan.new && `${opened.iconPlan.new} new`,
    opened.iconPlan.same && `${opened.iconPlan.same} already here`,
    opened.iconPlan.conflicts && `${opened.iconPlan.conflicts} different from yours`,
  ].filter(Boolean).join(', ');
  return html`<${Sheet} open=${true} title="Restore a backup" onClose=${onClose}>
    <p class="hint">${opened.created ? `Made ${formatDate(opened.created)}.` : 'An older backup.'} Nothing here is deleted; restoring only adds or replaces.</p>
    ${Object.values(has).filter(Boolean).length <= 1
      ? html`<p>${has.icons ? `${plural(opened.icons.length, 'icon')} (${iconNote})` : has.templates ? plural(opened.templates.length, 'template')
        : has.settings ? 'Your settings, favourites and recently used icons' : has.fonts ? plural(opened.fonts.length, 'added font')
        : has.history ? `${plural(opened.history.length, 'printed label')} from the print history`
        : 'This backup is empty.'}</p>`
      : html`<div class="restore-parts">
      ${has.icons && html`<${Toggle} label=${`${plural(opened.icons.length, 'icon')} (${iconNote})`} checked=${parts.icons}
        onChange=${(icons) => setParts({ ...parts, icons })} />`}
      ${has.templates && html`<${Toggle} label=${plural(opened.templates.length, 'template')} checked=${parts.templates}
        onChange=${(templates) => setParts({ ...parts, templates })} />`}
      ${has.settings && html`<${Toggle} label="Settings, favourites and recently used icons" checked=${parts.settings}
        onChange=${(settings) => setParts({ ...parts, settings })} />`}
      ${has.fonts && html`<${Toggle} label=${plural(opened.fonts.length, 'added font')} checked=${parts.fonts}
        onChange=${(fonts) => setParts({ ...parts, fonts })} />`}
      ${has.history && html`<${Toggle} label=${`Print history (${plural(opened.history.length, 'label')})`} checked=${parts.history}
        onChange=${(history) => setParts({ ...parts, history })} />`}
    </div>`}
    ${opened.skipped_templates.length > 0 && html`<p class="hint">Left out, could not be read: ${opened.skipped_templates.join(', ')}.</p>`}
    ${conflicts > 0 && html`<${Segmented} label=${`${plural(conflicts, 'icon or template', 'icons or templates')} with the same name as one of yours`}
      value=${onConflict} onChange=${setOnConflict}
      options=${[['skip', 'Keep mine'], ['replace', 'Use the backup'], ['keep_both', 'Keep both']]} />`}
    <div class="sheet-actions">
      <button class="secondary" onClick=${onClose}>Cancel</button>
      <button class="primary" disabled=${busy || !Object.keys(has).some((k) => has[k] && parts[k])} onClick=${restore}>${busy ? 'Restoring…' : 'Restore'}</button>
    </div>
  <//>`;
}

function BackupCard() {
  const { phase } = useStore(boot);
  const [last, setLast] = useState(null);
  const [message, setMessage] = useState({ text: '', error: false });
  const [opened, setOpened] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  useEffect(() => { lastBackup().then(setLast); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const done = await saveBackup();
      setLast(await lastBackup());
      setMessage({ text: `Saved ${plural(done.icons, 'icon')} and ${plural(done.templates, 'template')} with your settings.`, error: false });
    } catch (err) {
      setMessage({ text: `The backup failed: ${errorMessage(err)}`, error: true });
    } finally {
      setBusy(false);
    }
  };
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (!file) return;
    try {
      setOpened(await readBackup(file));
      setMessage({ text: '', error: false });
    } catch (err) {
      setMessage({ text: `${file.name}: ${errorMessage(err)}`, error: true });
    }
  };
  const done = (result, error) => {
    setOpened(null);
    setMessage(restoredMessage(result, error));
  };

  const ready = phase === 'ready';
  return html`<section class="card backups-card">
    <h2 class="card-title">Backups and sync</h2>
    <p class="hint">Your labels, icons, templates, settings and added fonts are kept in this browser on this device.
      Nothing goes to the Cube Labeler server. Save them to a file, a folder or your own Google Drive.</p>
    <div class="settings-part">
      <h3>Google Drive sync</h3>
      <${SyncPanel} />
    </div>
    <div class="settings-part">
    <h3>Backup file</h3>
    <p class="hint">One file with your own icons, templates, settings and print history. It restores here or in the desktop app, on any device.
      ${last ? ` Last backup: ${formatDate(last)}.` : ' No backup saved from this browser yet.'}</p>
    <div class="button-row">
      <button class="primary" disabled=${!ready || busy} onClick=${save}>${busy ? 'Saving…' : 'Save a backup'}</button>
      <button class="secondary" disabled=${!ready} onClick=${() => fileRef.current.click()}>Restore from a backup</button>
      <input ref=${fileRef} type="file" accept=".cubebackup,.cubeicons,application/zip" hidden onChange=${onFile} />
    </div>
    ${message.text && html`<p class=${`status-line${message.error ? ' error' : ''}`} role="status">${message.text}</p>`}
    </div>
    <${AutoBackup} ready=${ready} />
    <${RestoreSheet} opened=${opened} onClose=${() => setOpened(null)} onDone=${done} />
  </section>`;
}

// What a restore did, for a status line
function restoredMessage(result, error) {
  if (error) return { text: `Restoring failed: ${error}`, error: true };
  const said = [];
  if (result.icons) said.push(`${plural(result.icons.added + result.icons.replaced, 'icon')} restored`);
  if (result.templates) said.push(`${plural(result.templates.added + result.templates.replaced, 'template')} restored`);
  if (result.settings) said.push('settings restored');
  if (result.fonts) said.push(`${plural(result.fonts, 'font')} added`);
  if (result.history) said.push(`${plural(result.history, 'printed label')} added to the history`);
  const skipped = (result.icons ? result.icons.skipped : 0) + (result.templates ? result.templates.skipped : 0);
  if (skipped) said.push(`${skipped} kept as yours`);
  return { text: said.length ? `Done: ${said.join(', ')}.` : 'Everything in the backup was already here.', error: false };
}

// The versions in Google Drive and the copy kept here before the last sync, to pick one to restore
function VersionsSheet({ open, onClose, onPick }) {
  const [files, setFiles] = useState(null);
  const [before, setBefore] = useState(null);
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    beforeSyncFile().then(setBefore, () => setBefore(null));
    try { setFiles(await listDriveBackups()); } catch (err) { setError(errorMessage(err)); }
  };
  useEffect(() => { setFiles(null); if (open && driveReady()) load(); }, [open, driveReady()]);
  const signIn = async () => {
    setError('');
    try { await continueDriveBackup(); } catch (err) { setError(errorMessage(err)); }
  };
  const holds = (f) => {
    const p = f.appProperties || {};
    const parts = [p.device, p.icons !== undefined && plural(Number(p.icons), 'icon'), p.templates !== undefined && plural(Number(p.templates), 'template')];
    return parts.filter(Boolean).join(' · ') || f.name;
  };
  const rows = [];
  if (files) {
    files.forEach((f, i) => rows.push({ key: f.id, when: f.createdTime, what: holds(f), tag: i === 0 ? 'Newest' : i >= 10 ? 'Daily' : '', pick: () => onPick({ drive: f }) }));
  }
  if (before) {
    const at = rows.findIndex((r) => r.when < before.created);
    const row = { key: 'before', when: before.created, what: 'This device, just before the last sync', tag: 'On this device', pick: () => onPick({ file: before.file }) };
    if (at < 0) rows.push(row); else rows.splice(at, 0, row);
  }
  return html`<${Sheet} open=${open} title="Versions" onClose=${onClose}>
    ${!driveReady()
      ? html`<p>Sign in to Google again to see the versions in your Drive.</p>
        <div class="sheet-actions"><button class="primary" onClick=${signIn}>Continue with Google</button></div>`
      : files === null ? html`<p class="hint">${error || 'Looking in Google Drive…'}</p>`
        : html`<p class="hint">Pick a version to see what it holds before anything changes.</p>
          ${rows.length === 0 ? html`<p class="hint">No versions in Google Drive yet.</p>`
            : html`<ul class="drive-files">${rows.map((r) => html`<li key=${r.key}>
              <button class="drive-file version-row" onClick=${r.pick}>
                <span><span>${shortDate(r.when)}</span><span class="hint">${r.what}</span></span>
                ${r.tag ? html`<span class="tag">${r.tag}</span>` : html`<span></span>`}
              </button></li>`)}</ul>`}`}
    ${error && files !== null && html`<p class="status-line error">${error}</p>`}
  <//>`;
}

// The newest syncs, with Undo on the last one from Drive while it can be undone
function SyncLog({ log, canUndo, busy, onUndo }) {
  const shown = log.slice(0, 3);
  if (!shown.length) return null;
  const undoAt = canUndo ? shown.findIndex((e) => e.undo) : -1;
  return html`<ul class="sync-log">
    ${shown.map((e, i) => html`<li key=${`${e.at}-${i}`}>
      <span class="when">${shortDate(e.at)}</span>
      <span class="what"><strong>${e.from === 'this device' ? 'From this device' : `From ${e.from}`}</strong> · ${e.what}</span>
      ${i === undoAt ? html`<button class="link-button" disabled=${busy} onClick=${onUndo}>Undo</button>` : html`<span></span>`}
    </li>`)}
  </ul>`;
}

// Google Drive sync: sign in, see what it did, sync now, versions, sign out. Also opened from
// the Sync chip in the top bar.
export function SyncPanel() {
  const ready = useStore(boot).phase === 'ready';
  const d = useStore(drive);
  const auto = useStore(autoBackup);
  const [error, setError] = useState('');
  const [note, setNote] = useState({ text: '', error: false });
  const [versions, setVersions] = useState(false);
  const [opened, setOpened] = useState(null);
  const run = async (action) => {
    setError('');
    try { await action(); } catch (err) { setError(errorMessage(err)); }
  };
  // Syncing shows only for Sync now; the quiet syncs after changes keep the line as it is
  const [syncing, setSyncing] = useState(false);
  const syncNow = () => run(async () => { setSyncing(true); try { await backupNow(); } finally { setSyncing(false); } });
  const pick = async ({ drive: f, file }) => {
    setVersions(false);
    try {
      setOpened(await readBackup(f ? await downloadDriveBackup(f) : file));
      setNote({ text: '', error: false });
    } catch (err) {
      setNote({ text: errorMessage(err), error: true });
    }
  };
  const retention = html`<p class="hint">Google Drive keeps the last 10 versions and one a day for two weeks.</p>`;

  if (!d.on) {
    return html`<div class="sync-panel">
      <p class="hint">Sign in with Google on each device you use, and your own icons, templates, settings and print history follow you.
        Changes are saved to a ${'"Cube Labeler backups"'} folder in your Drive and picked up by your other devices when you open the app.
        The app can only see the files it made there.</p>
      ${d.signingIn
        ? html`<p class="auto-on"><span class="dot wait"></span><span>Signing in… Finish in the Google window.</span></p>
          <div class="button-row"><button class="secondary" onClick=${cancelSignIn}>Cancel</button></div>`
        : html`<div class="button-row"><button class="primary" disabled=${!ready}
            onClick=${() => run(async () => { await signInToDrive(); await startDriveBackup(); })}>Sign in with Google</button></div>`}
      ${error && html`<p class="status-line error">${error}</p>`}
    </div>`;
  }

  const who = d.email ? html`<strong>${d.email}</strong>` : 'Google Drive';
  const on = driveReady();
  let dot = 'on';
  let line = html`On, synced with ${who}`;
  let sub = auto.checked ? `Up to date. Checked ${ago(auto.checked)}.` : auto.driveLast ? `Last synced ${formatDate(auto.driveLast)}.` : '';
  if (!on) {
    dot = 'wait';
    line = d.helper ? 'Paused: Google asks you to sign in again.' : 'Paused: Google asks you to continue once an hour.';
    sub = 'Changes on this device are kept and sync once you continue.';
  } else if (syncing) {
    sub = 'Syncing…';
  } else if (auto.offline) {
    dot = 'wait';
    line = 'Waiting for the internet';
    sub = `Changes on this device sync by themselves when you are back online.${auto.driveLast ? ` Last synced ${shortDate(auto.driveLast)}.` : ''}`;
  } else if (auto.driveError) {
    dot = 'error';
    line = 'Sync has a problem';
    sub = '';
  }
  const undo = () => run(async () => { await undoLastSync(); setNote({ text: 'The last sync is undone here. Your other devices follow at their next sync.', error: false }); });
  return html`<div class="sync-panel">
    <p class="auto-on"><span class=${`dot ${dot}`}></span><span>${line}</span></p>
    ${sub && html`<p class="hint last-synced">${sub}</p>`}
    ${auto.driveError && !auto.offline && on && html`<p class="status-line error">${auto.driveError}</p>`}
    <${SyncLog} log=${auto.log} canUndo=${!!auto.undo && on} busy=${auto.busy} onUndo=${undo} />
    <div class="sync-buttons">
      ${on
        ? html`<button class="secondary" disabled=${!ready || auto.busy || auto.offline} onClick=${syncNow}>Sync now</button>`
        : html`<button class="primary" disabled=${!ready || auto.busy} onClick=${() => run(continueDriveBackup)}>Continue</button>`}
      <button class="secondary" disabled=${!ready || auto.offline} onClick=${() => setVersions(true)}>Versions</button>
      <button class="secondary" disabled=${auto.busy} onClick=${() => run(() => signOutOfDrive())}>Sign out</button>
    </div>
    ${retention}
    ${note.text && html`<p class=${`status-line${note.error ? ' error' : ''}`} role="status">${note.text}</p>`}
    ${error && html`<p class="status-line error">${error}</p>`}
    <p class="hint sync-remove"><button class="link-button" disabled=${auto.busy}
      title="Signs out every device and takes Cube Labeler off your Google account. Your backups stay in Drive."
      onClick=${() => run(() => signOutOfDrive({ everywhere: true }))}>Remove access on all devices</button></p>
    <${VersionsSheet} open=${versions} onClose=${() => setVersions(false)} onPick=${pick} />
    <${RestoreSheet} opened=${opened} onClose=${() => setOpened(null)}
      onDone=${(result, err) => { setOpened(null); setNote(restoredMessage(result, err)); }} />
  </div>`;
}

// Joining sync on a device that has things of its own: what is where, and how to join
export function JoinSheet() {
  const auto = useStore(autoBackup);
  const [how, setHow] = useState('merge');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const join = auto.join;
  const close = async () => { cancelJoin(); await signOutOfDrive(); };
  if (!join) return html`<${Sheet} open=${false} title="" onClose=${close} />`;
  const here = deviceWord();
  const list = (counts) => [counts.icons && plural(counts.icons, 'icon'), counts.templates && plural(counts.templates, 'template')]
    .filter(Boolean).join(' and ') || 'nothing';
  const inDrive = [plural(join.drive.icons, 'icon'), plural(join.drive.templates, 'template'), 'settings',
    join.drive.history && plural(join.drive.history, 'printed label')].filter(Boolean);
  const differ = [join.differ.icons && plural(join.differ.icons, 'icon'),
    join.differ.templates.length && `${plural(join.differ.templates.length, 'template')}: ${join.differ.templates.map((n) => `“${n}”`).join(', ')}`]
    .filter(Boolean).join('; ');
  const hints = {
    merge: `Keeps everything from both. Where both have a different version, Drive's is kept as a copy${join.differ.templates[0] ? `, like “${join.differ.templates[0]} (${join.from || 'Drive'})”` : ''}.`,
    drive: `This ${here} becomes like Drive: things only here are removed, and Drive's version wins.`,
    mine: `Drive becomes like this ${here}: things only in Drive are removed there and on your other devices.`,
  };
  const go = async () => {
    setBusy(true);
    setError('');
    try { await joinDrive(how); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };
  return html`<${Sheet} open=${true} title="Join Google Drive sync" onClose=${close}>
    <p>Your Google Drive already has Cube Labeler things from another device.</p>
    <dl class="join-facts">
      <dt>In Drive</dt><dd>${inDrive.slice(0, -1).join(', ')} and ${inDrive[inDrive.length - 1]}<br />
        <span class="hint">${join.from ? `From ${join.from}, ` : ''}${shortDate(join.newest.createdTime, { time: false }).toLowerCase() === 'today'
          ? 'today' : shortDate(join.newest.createdTime, { time: false })} at ${new Date(join.newest.createdTime).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span></dd>
      <dt>Only here</dt><dd>${list(join.onlyHere)}</dd>
      ${differ && html`<dt>On both, different</dt><dd>${differ}</dd>`}
    </dl>
    <${Segmented} label="How to join" value=${how} onChange=${setHow}
      options=${[['merge', 'Merge both'], ['drive', "Drive's copy"], ['mine', `This ${here}'s`]]} />
    <p class="hint">${hints[how]}</p>
    ${error && html`<p class="status-line error">${error}</p>`}
    <div class="sheet-actions">
      <button class="secondary" disabled=${busy} onClick=${close}>Cancel</button>
      <button class="primary" disabled=${busy} onClick=${go}>${busy ? 'Joining…' : 'Join sync'}</button>
    </div>
  <//>`;
}

const deviceWord = () => (/Android|iPhone/i.test(navigator.userAgent) ? 'phone' : /iPad/i.test(navigator.userAgent) ? 'tablet' : 'device');

// Automatic backups to a folder, which can be one that Google Drive, OneDrive or Dropbox syncs
function AutoBackup({ ready }) {
  const auto = useStore(autoBackup);
  const [error, setError] = useState('');
  const run = async (action) => {
    setError('');
    try { await action(); } catch (err) { setError(errorMessage(err)); }
  };
  if (!auto.supported) return null;
  let state;
  if (!auto.folder) {
    state = html`<p class="hint">Pick a folder and a backup is saved there a few seconds after your icons, templates or settings change. The newest 3 are kept.
      A folder that OneDrive or Dropbox syncs keeps them in the cloud too.</p>
      <div class="button-row"><button class="secondary" disabled=${!ready || auto.busy} onClick=${() => run(chooseFolder)}>Choose a folder</button></div>`;
  } else {
    const where = html`<strong>${auto.folder.name}</strong>`;
    state = html`
      ${auto.allowed
        ? html`<p class="auto-on"><span class="dot on"></span><span>On, saving to ${where}.${auto.last ? ` Last: ${formatDate(auto.last)}.` : ''}</span></p>`
        : html`<p class="auto-on"><span class="dot"></span><span>Paused: the browser needs your OK to save in ${where} again.</span></p>`}
      ${auto.error && html`<p class="status-line error">${auto.error}</p>`}
      <div class="button-row">
        ${!auto.allowed && html`<button class="primary" disabled=${!ready || auto.busy} onClick=${() => run(allowFolder)}>Allow</button>`}
        <button class="secondary" disabled=${!ready || auto.busy} onClick=${() => run(chooseFolder)}>Change folder</button>
        <button class="secondary" disabled=${auto.busy} onClick=${() => run(stopAutoBackup)}>Turn off</button>
      </div>`;
  }
  return html`<div class="settings-part">
    <h3>Folder on this computer</h3>
    ${state}
    ${error && html`<p class="status-line error">${error}</p>`}
  </div>`;
}

function AiCard() {
  const { phase } = useStore(boot);
  const { settings } = useStore(app);
  const state = useStore(ai);
  const [shown, setShown] = useState(false);
  useEffect(() => { if (phase === 'ready') loadAi(); }, [phase]);
  if (!state.ready) return null;
  const service = state.services.find((s) => s.id === settings.ai_provider) || state.services[0];
  const key = state.keys[service.id] || '';
  return html`<section class="card" id="ai">
    <h2 class="card-title">AI icons</h2>
    <p>The icon editor can redraw a photo as a bold icon with an AI service, using your own API key.</p>
    <${Segmented} label="Service" value=${service.id} options=${state.services.map((s) => [s.id, s.name])}
      onChange=${(ai_provider) => updateSettings({ ai_provider })} />
    <div class="field">
      <label class="field-label" for="ai-key">${service.name} API key</label>
      <div class="key-row">
        <input id="ai-key" key=${service.id} type=${shown ? 'text' : 'password'} autocomplete="off" spellcheck="false"
          value=${key} placeholder="Paste your key" onChange=${(e) => setKey(service.id, e.currentTarget.value)} />
        <button class="secondary" onClick=${() => setShown(!shown)}>${shown ? 'Hide' : 'Show'}</button>
      </div>
      <p class="hint"><a href=${service.key_url} target="_blank" rel="noopener">Get a ${service.name} key</a>. ${service.key_note}</p>
    </div>
    <p class="hint">Keys stay in this browser on this device. They are sent only to ${service.name} and never go in backups.</p>
    <details class="help advanced" open=${!!settings.ai_models[service.id]}>
      <summary>Advanced</summary>
      <div class="field">
        <label class="field-label" for="ai-model">Model</label>
        <input id="ai-model" key=${`model-${service.id}`} type="text" spellcheck="false"
          value=${settings.ai_models[service.id] || ''} placeholder=${service.default_model}
          onChange=${(e) => setModel(service.id, e.currentTarget.value)} />
        <p class="hint">Leave empty for ${service.default_model}.</p>
      </div>
    </details>
  </section>`;
}

// The tape new text labels start on and how much print history to keep; they go with backups
// and sync. Fonts and the bin label length are set where the labels are made, on the Label page.
function LabelDefaultsCard() {
  const { settings, tapeWidths } = useStore(app);
  const defaults = labelDefaults();
  return html`<section class="card">
    <h2 class="card-title">Label defaults</h2>
    <p class="hint">The tape new text labels start on and how many printed labels the history keeps. These go with your backups and sync.</p>
    <div class="defaults-rows">
      <label class="default-row">
        <span><span class="field-label">Text label tape</span><span class="hint">New text labels start on this tape width.</span></span>
        <select value=${defaults.tape_width_mm} onChange=${(e) => updateSettings({ default_tape_mm: Number(e.currentTarget.value) })}>
          ${tapeWidths.map((w) => html`<option value=${w}>${w} mm</option>`)}
        </select>
      </label>
      <label class="default-row">
        <span><span class="field-label">Print history</span><span class="hint">The newest printed labels kept. Pinned ones always stay.</span></span>
        <select value=${HISTORY_SIZES.includes(settings.history_keep) ? settings.history_keep : 50}
          onChange=${async (e) => { await updateSettings({ history_keep: Number(e.currentTarget.value) }); historySizeChanged(); }}>
          ${HISTORY_SIZES.map((n) => html`<option value=${n}>Last ${n}</option>`)}
        </select>
      </label>
    </div>
  </section>`;
}

// Theme choice as small pictures of the app in light, dark or both
function ThemePicker({ value, onChange }) {
  const themes = [['system', 'Like the device'], ['light', 'Light'], ['dark', 'Dark']];
  return html`<div class="theme-picker" role="radiogroup" aria-label="Theme">
    ${themes.map(([key, text]) => html`<label class=${'theme-option' + (value === key ? ' selected' : '')}>
      <input type="radio" name="theme" value=${key} checked=${value === key} onChange=${() => onChange(key)} />
      <span class=${'theme-thumb ' + key} aria-hidden="true">
        <span class="t-side"></span><span class="t-main"><span class="t-bar"></span><span class="t-card"></span><span class="t-card short"></span></span>
      </span>
      <span class="theme-name">${text}</span>
    </label>`)}
  </div>`;
}

export function SettingsPage() {
  const { settings } = useStore(app);
  // Three columns that end on one line (the last card in each stretches), with a slim
  // about line under them; on narrower screens the same cards in one column
  return html`<div class="settings-page">
    <div class="settings-col">
      <section class="card">
        <h2 class="card-title">Printer</h2>
        <${PrinterPanel} />
        <${Toggle} label="Set the tape width from the printer" checked=${settings.match_printer_tape}
          onChange=${(match_printer_tape) => updateSettings({ match_printer_tape })} />
      </section>
      <${LabelDefaultsCard} />
    </div>

    <div class="settings-col">
      <${AiCard} />
      <section class="card">
        <h2 class="card-title">Appearance</h2>
        <${ThemePicker} value=${settings.theme} onChange=${(theme) => updateSettings({ theme })} />
      </section>
    </div>

    <div class="settings-col"><${BackupCard} /></div>

    <footer class="about">
      <p>
        <span>Cube Labeler ${APP_VERSION}${BUILD_CHANNEL ? ` (${BUILD_CHANNEL} ${BUILD_COMMIT})` : ''} for the Brother PT-P300BT</span>
        <a href="https://github.com/McTobe/cube-labeler" target="_blank" rel="noopener" title="Cube Labeler is free software under the GNU AGPL v3">Source code</a>
        <a href="https://ko-fi.com/thetobek" target="_blank" rel="noopener">Buy me a coffee${'\u00a0'}♥</a>
        <a href="privacy.html" target="_blank" rel="noopener">Privacy</a>
        <button class="link-button" title="Something looks off after an update? Reloads the app; your labels, icons and settings stay."
          onClick=${() => window.freshCopy()}>Load a fresh copy</button>
        <${StorageUse} />
      </p>
      <p class="hint">Labels are drawn by the same Python code as the desktop app, running in this browser with Pyodide.
        Fonts under the SIL Open Font License.</p>
    </footer>
  </div>`;
}
