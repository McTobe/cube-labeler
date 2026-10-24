// Settings: printer, how the app looks, and what this device keeps
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Segmented, Select, Sheet, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateSettings } from '../app.js';
import { saveBackup, lastBackup, readBackup, restoreBackup } from '../backup.js';
import { autoBackup, chooseFolder, allowFolder, stopAutoBackup } from '../autobackup.js';
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
  const [parts, setParts] = useState({ icons: true, settings: true, templates: true });
  const [onConflict, setOnConflict] = useState('skip');
  const [busy, setBusy] = useState(false);
  if (!opened) return html`<${Sheet} open=${false} title="" onClose=${onClose} />`;
  const has = {
    icons: opened.icons.length > 0,
    settings: opened.settings !== null,
    templates: opened.templates.length > 0,
  };
  const conflicts = (parts.icons ? opened.iconPlan.conflicts : 0) + (parts.templates ? opened.templatePlan.conflicts : 0);
  const restore = async () => {
    setBusy(true);
    try {
      onDone(await restoreBackup(opened, { icons: parts.icons && has.icons, settings: parts.settings && has.settings, templates: parts.templates && has.templates }, onConflict));
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
    <div class="restore-parts">
      ${has.icons && html`<${Toggle} label=${`${plural(opened.icons.length, 'icon')} (${iconNote})`} checked=${parts.icons}
        onChange=${(icons) => setParts({ ...parts, icons })} />`}
      ${has.templates && html`<${Toggle} label=${plural(opened.templates.length, 'template')} checked=${parts.templates}
        onChange=${(templates) => setParts({ ...parts, templates })} />`}
      ${has.settings && html`<${Toggle} label="Settings, favourites and recently used icons" checked=${parts.settings}
        onChange=${(settings) => setParts({ ...parts, settings })} />`}
    </div>
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
    if (error) { setMessage({ text: `Restoring failed: ${error}`, error: true }); return; }
    const said = [];
    if (result.icons) said.push(`${plural(result.icons.added + result.icons.replaced, 'icon')} restored`);
    if (result.templates) said.push(`${plural(result.templates.added + result.templates.replaced, 'template')} restored`);
    if (result.settings) said.push('settings restored');
    const skipped = (result.icons ? result.icons.skipped : 0) + (result.templates ? result.templates.skipped : 0);
    if (skipped) said.push(`${skipped} kept as yours`);
    setMessage({ text: said.length ? `Done: ${said.join(', ')}.` : 'Everything in the backup was already here.', error: false });
  };

  const ready = phase === 'ready';
  return html`<section class="card">
    <h2 class="card-title">Backups</h2>
    <p>One file with your own icons, templates and settings. It restores here or in the desktop app, on any device.</p>
    <p class="hint">${last ? `Last backup: ${formatDate(last)}.` : 'No backup saved from this browser yet.'}</p>
    <div class="button-row">
      <button class="primary" disabled=${!ready || busy} onClick=${save}>${busy ? 'Saving…' : 'Save a backup'}</button>
      <button class="secondary" disabled=${!ready} onClick=${() => fileRef.current.click()}>Restore from a backup</button>
      <input ref=${fileRef} type="file" accept=".cubebackup,.cubeicons,application/zip" hidden onChange=${onFile} />
    </div>
    ${message.text && html`<p class=${`status-line${message.error ? ' error' : ''}`} role="status">${message.text}</p>`}
    <${AutoBackup} ready=${ready} />
    <${RestoreSheet} opened=${opened} onClose=${() => setOpened(null)} onDone=${done} />
  </section>`;
}

// Automatic backups to a folder, which can be one that Google Drive, OneDrive or Dropbox syncs
function AutoBackup({ ready }) {
  const auto = useStore(autoBackup);
  const [error, setError] = useState('');
  const run = async (action) => {
    setError('');
    try { await action(); } catch (err) { setError(errorMessage(err)); }
  };
  let state;
  if (!auto.supported) {
    state = html`<p class="hint">Automatic backups need Chrome or Edge on a computer. On this device, save a backup by hand now and then.</p>`;
  } else if (!auto.folder) {
    state = html`<p class="hint">Pick a folder and a backup is saved there a few seconds after your icons, templates or settings change. The newest 10 are kept.
      Pick a folder that Google Drive, OneDrive or Dropbox syncs to keep them in the cloud.</p>
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
  return html`<div class="auto-backup">
    <h3>Automatic backups</h3>
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
    <div class="field">
      <label class="field-label" for="ai-model">Model</label>
      <input id="ai-model" key=${`model-${service.id}`} type="text" spellcheck="false"
        value=${settings.ai_models[service.id] || ''} placeholder=${service.default_model}
        onChange=${(e) => setModel(service.id, e.currentTarget.value)} />
      <p class="hint">Leave empty for ${service.default_model}.</p>
    </div>
    <p class="hint">Keys stay in this browser on this device. They are sent only to ${service.name} and never go in backups.</p>
  </section>`;
}

export function SettingsPage() {
  const { settings, languages } = useStore(app);
  return html`<div class="settings-page">
    <section class="card">
      <h2 class="card-title">Printer</h2>
      <${PrinterPanel} />
      <${Toggle} label="Set the tape width from the printer" checked=${settings.match_printer_tape}
        onChange=${(match_printer_tape) => updateSettings({ match_printer_tape })} />
    </section>

    <section class="card">
      <h2 class="card-title">Bin labels</h2>
      <${Select} label="Language for suggested names, like Screws or Bearings" value=${settings.label_language}
        options=${languages} onChange=${(label_language) => updateSettings({ label_language })} />
    </section>

    <section class="card">
      <h2 class="card-title">Appearance</h2>
      <${Segmented} label="Theme" value=${settings.theme}
        options=${[['system', 'Like the device'], ['light', 'Light'], ['dark', 'Dark']]}
        onChange=${(theme) => updateSettings({ theme })} />
    </section>

    <${AiCard} />

    <${BackupCard} />

    <section class="card">
      <h2 class="card-title">Your data</h2>
      <p>Your labels, icons, templates, settings and added fonts are kept in this browser on this device. Nothing is sent to the server.</p>
      <${StorageUse} />
    </section>

    <section class="card about">
      <h2 class="card-title">About</h2>
      <p>Cube Labeler ${APP_VERSION} for the Brother PT-P300BT.</p>
      <p class="hint">Labels are drawn by the same Python code as the desktop app, running in this browser with Pyodide.
        Arimo font under the SIL Open Font License.</p>
    </section>
  </div>`;
}
