// Settings: printer, label defaults, how the app looks, AI icons, backups and sync, about
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Segmented, Sheet, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateSettings, labelDefaults } from '../app.js';
import { FACTORY_LABEL_MM } from './bin.js';
import { saveBackup, lastBackup, readBackup, restoreBackup } from '../backup.js';
import { autoBackup, backupNow, chooseFolder, allowFolder, stopAutoBackup, startDriveBackup, continueDriveBackup } from '../autobackup.js';
import { drive, driveReady, signInToDrive, signOutOfDrive, listDriveBackups, downloadDriveBackup } from '../gdrive.js';
import { ai, loadAi, setKey, setModel } from '../ai.js';
import { errorMessage } from '../../printer.js';
import { PrinterPanel } from '../printer-ui.js';
import { APP_VERSION } from '../version.js';

function StorageUse() {
  const [estimate, setEstimate] = useState(null);
  useEffect(() => {
    if (navigator.storage && navigator.storage.estimate) navigator.storage.estimate().then(setEstimate, () => {});
  }, []);
  if (!estimate || !estimate.usage) return null;
  const mb = estimate.usage / 1e6;
  return html`<p class="hint">This app uses ${mb < 1 ? 'less than 1' : Math.round(mb)} MB on this device${mb > 5 ? ', most of it for Python' : ''}.</p>`;
}

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function RestoreSheet({ opened, onClose, onDone }) {
  const [parts, setParts] = useState({ icons: true, settings: true, templates: true, fonts: true });
  const [onConflict, setOnConflict] = useState('skip');
  const [busy, setBusy] = useState(false);
  if (!opened) return html`<${Sheet} open=${false} title="" onClose=${onClose} />`;
  const has = {
    icons: opened.icons.length > 0,
    settings: opened.settings !== null,
    templates: opened.templates.length > 0,
    fonts: (opened.fonts || []).length > 0,
  };
  const conflicts = (parts.icons ? opened.iconPlan.conflicts : 0) + (parts.templates ? opened.templatePlan.conflicts : 0);
  const restore = async () => {
    setBusy(true);
    try {
      onDone(await restoreBackup(opened, { icons: parts.icons && has.icons, settings: parts.settings && has.settings, templates: parts.templates && has.templates, fonts: parts.fonts && has.fonts }, onConflict));
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
  const [picking, setPicking] = useState(false);
  const d = useStore(drive);
  const fromDrive = async (file) => {
    setPicking(false);
    try {
      setOpened(await readBackup(await downloadDriveBackup(file)));
      setMessage({ text: '', error: false });
    } catch (err) {
      setMessage({ text: `${file.name}: ${errorMessage(err)}`, error: true });
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
    if (error) { setMessage({ text: `Restoring failed: ${error}`, error: true }); return; }
    const said = [];
    if (result.icons) said.push(`${plural(result.icons.added + result.icons.replaced, 'icon')} restored`);
    if (result.templates) said.push(`${plural(result.templates.added + result.templates.replaced, 'template')} restored`);
    if (result.settings) said.push('settings restored');
    if (result.fonts) said.push(`${plural(result.fonts, 'font')} added`);
    const skipped = (result.icons ? result.icons.skipped : 0) + (result.templates ? result.templates.skipped : 0);
    if (skipped) said.push(`${skipped} kept as yours`);
    setMessage({ text: said.length ? `Done: ${said.join(', ')}.` : 'Everything in the backup was already here.', error: false });
  };

  const ready = phase === 'ready';
  return html`<section class="card backups-card">
    <h2 class="card-title">Backups and sync</h2>
    <div class="settings-part">
      <h3>Google Drive sync</h3>
      <${SyncPanel} />
    </div>
    <div class="settings-part">
    <h3>Backup file</h3>
    <p class="hint">One file with your own icons, templates and settings. It restores here or in the desktop app, on any device.
      ${last ? ` Last backup: ${formatDate(last)}.` : ' No backup saved from this browser yet.'}</p>
    <div class="button-row">
      <button class="primary" disabled=${!ready || busy} onClick=${save}>${busy ? 'Saving…' : 'Save a backup'}</button>
      <button class="secondary" disabled=${!ready} onClick=${() => fileRef.current.click()}>Restore from a backup</button>
      ${d.on && html`<button class="secondary" disabled=${!ready} onClick=${() => setPicking(true)}>Restore from Google Drive</button>`}
      <input ref=${fileRef} type="file" accept=".cubebackup,.cubeicons,application/zip" hidden onChange=${onFile} />
    </div>
    ${message.text && html`<p class=${`status-line${message.error ? ' error' : ''}`} role="status">${message.text}</p>`}
    </div>
    <${AutoBackup} ready=${ready} />
    <${RestoreSheet} opened=${opened} onClose=${() => setOpened(null)} onDone=${done} />
    <${DrivePicker} open=${picking} onClose=${() => setPicking(false)} onPick=${fromDrive} />
  </section>`;
}

// The backups in Google Drive, to pick one to restore
function DrivePicker({ open, onClose, onPick }) {
  const d = useStore(drive);
  const [files, setFiles] = useState(null);
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    try { setFiles(await listDriveBackups()); } catch (err) { setError(errorMessage(err)); }
  };
  useEffect(() => { setFiles(null); if (open && driveReady()) load(); }, [open, !!d.token]);
  const signIn = async () => {
    setError('');
    try { await continueDriveBackup(); } catch (err) { setError(errorMessage(err)); }
  };
  return html`<${Sheet} open=${open} title="Restore from Google Drive" onClose=${onClose}>
    ${!driveReady()
      ? html`<p>Sign in to Google again to see your backups.</p>
        <div class="sheet-actions"><button class="primary" onClick=${signIn}>Continue with Google</button></div>`
      : files === null ? html`<p class="hint">${error || 'Looking for backups…'}</p>`
        : files.length === 0 ? html`<p class="hint">No backups in the ${'"Cube Labeler backups"'} folder yet.</p>`
          : html`<ul class="drive-files">${files.map((f) => html`<li key=${f.id}>
              <button class="drive-file" onClick=${() => onPick(f)}>
                <span>${formatDate(f.createdTime)}</span><span class="hint">${f.name}</span>
              </button></li>`)}</ul>`}
    ${error && files !== null && html`<p class="status-line error">${error}</p>`}
  <//>`;
}

// Google Drive sync: sign in, see that it works, sync now, sign out. Also opened from the
// Sync chip in the top bar.
export function SyncPanel() {
  const ready = useStore(boot).phase === 'ready';
  const d = useStore(drive);
  const auto = useStore(autoBackup);
  const [error, setError] = useState('');
  const run = async (action) => {
    setError('');
    try { await action(); } catch (err) { setError(errorMessage(err)); }
  };
  // Syncing shows only for Sync now; the quiet syncs after changes keep the time
  const [syncing, setSyncing] = useState(false);
  const syncNow = () => run(async () => { setSyncing(true); try { await backupNow(); } finally { setSyncing(false); } });
  const lastLine = syncing ? html`<p class="hint last-synced">Syncing…</p>`
    : auto.driveLast ? html`<p class="hint last-synced">Last synced: ${formatDate(auto.driveLast)}</p>` : null;
  let state;
  if (!d.on) {
    state = html`<p class="hint">Sign in with Google on each device you use, and your own icons, templates and settings follow you.
      Changes are saved to a ${'"Cube Labeler backups"'} folder in your Drive and picked up by your other devices when you open the app.
      The app can only see the files it made there.</p>
      <div class="button-row"><button class="primary" disabled=${!ready} onClick=${() => run(async () => { await signInToDrive(); await startDriveBackup(); })}>Sign in with Google</button></div>`;
  } else {
    const who = d.email ? html`<strong>${d.email}</strong>` : 'Google Drive';
    state = html`
      ${d.token
        ? html`<p class="auto-on"><span class="dot on"></span><span>On, synced with ${who}.</span></p>`
        : html`<p class="auto-on"><span class="dot"></span><span>Paused: Google asks you to continue once an hour.</span></p>`}
      ${lastLine}
      ${auto.driveError && html`<p class="status-line error">${auto.driveError}</p>`}
      <div class="button-row">
        ${!d.token && html`<button class="primary" disabled=${!ready || auto.busy} onClick=${() => run(continueDriveBackup)}>Continue with Google</button>`}
        ${d.token && html`<button class="secondary" disabled=${!ready || auto.busy} onClick=${syncNow}>Sync now</button>`}
        <button class="secondary" disabled=${auto.busy} onClick=${() => run(signOutOfDrive)}>Sign out</button>
      </div>`;
  }
  return html`<div class="sync-panel">
    ${state}
    ${error && html`<p class="status-line error">${error}</p>`}
  </div>`;
}

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

// The defaults new and reset labels start from; they go with backups and sync
function LabelDefaultsCard() {
  const { settings, fonts, tapeWidths } = useStore(app);
  const [binText, setBinText] = useState(null);
  const defaults = labelDefaults();
  const onBin = (e) => {
    const text = e.currentTarget.value;
    setBinText(text);
    const mm = Number(text.replace(',', '.'));
    if (!text.trim()) updateSettings({ bin_label_mm: null });
    else if (mm >= 10 && mm <= 499) updateSettings({ bin_label_mm: mm });
  };
  return html`<section class="card">
    <h2 class="card-title">Label defaults</h2>
    <p class="hint">What Reset goes back to on the Label page. These go with your backups and sync.</p>
    <div class="defaults-grid">
      <label class="field">
        <span class="field-label">Text label tape</span>
        <select value=${defaults.tape_width_mm} onChange=${(e) => updateSettings({ default_tape_mm: Number(e.currentTarget.value) })}>
          ${tapeWidths.map((w) => html`<option value=${w}>${w} mm</option>`)}
        </select>
      </label>
      <label class="field">
        <span class="field-label">Text label font</span>
        <select value=${defaults.font_name} onChange=${(e) => updateSettings({ default_font: e.currentTarget.value })}>
          ${fonts.map((f) => html`<option value=${f}>${f}</option>`)}
        </select>
      </label>
      <label class="field">
        <span class="field-label">Bin label length</span>
        <span class="unit-input">
          <input type="text" inputmode="decimal" value=${binText ?? String(settings.bin_label_mm || '')}
            placeholder=${String(FACTORY_LABEL_MM)} onInput=${onBin} onBlur=${() => setBinText(null)} />
          <span>mm</span>
        </span>
      </label>
    </div>
  </section>`;
}

export function SettingsPage() {
  const { settings } = useStore(app);
  return html`<div class="settings-page">
    <section class="card">
      <h2 class="card-title">Printer</h2>
      <${PrinterPanel} />
      <${Toggle} label="Set the tape width from the printer" checked=${settings.match_printer_tape}
        onChange=${(match_printer_tape) => updateSettings({ match_printer_tape })} />
    </section>

    <${LabelDefaultsCard} />

    <section class="card">
      <h2 class="card-title">Appearance</h2>
      <${Segmented} label="Theme" value=${settings.theme}
        options=${[['system', 'Like the device'], ['light', 'Light'], ['dark', 'Dark']]}
        onChange=${(theme) => updateSettings({ theme })} />
    </section>

    <${AiCard} />

    <${BackupCard} />

    <section class="card about">
      <h2 class="card-title">About</h2>
      <p>Cube Labeler ${APP_VERSION} for the Brother PT-P300BT. <a href="https://github.com/McTobe/cube-labeler" target="_blank" rel="noopener">On GitHub</a></p>
      <p>Cube Labeler is free. If it saves you time, you can <a href="https://ko-fi.com/thetobek" target="_blank" rel="noopener">buy me a coffee on Ko-fi${'\u00a0'}♥</a></p>
      <h3>Your data</h3>
      <p class="hint">Your labels, icons, templates, settings and added fonts are kept in this browser on this device. Nothing is sent to the Cube Labeler server; with Google Drive sync on, a backup of them also goes to your own Drive.</p>
      <${StorageUse} />
      <p class="hint">Something looks off after an update? <button class="link-button" onClick=${() => window.freshCopy()}>Load a fresh copy</button> of the app. Your labels, icons and settings stay.</p>
      <p class="hint">Labels are drawn by the same Python code as the desktop app, running in this browser with Pyodide.
        Arimo font under the SIL Open Font License.</p>
    </section>
  </div>`;
}
