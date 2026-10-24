// Settings: printer, how the app looks, and what this device keeps
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Segmented, Select, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, updateSettings } from '../app.js';
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

    <section class="card">
      <h2 class="card-title">Your data</h2>
      <p>Your labels, settings and added fonts are kept in this browser on this device. Nothing is sent to the server.</p>
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
