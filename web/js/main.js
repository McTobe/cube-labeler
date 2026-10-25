// Cube Labeler web app: the shell (navigation, top bar) and the page router.
import { render } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { PrinterChip } from './printer-ui.js';
import { LabelPage } from './pages/label.js';
import { SettingsPage, SyncPanel } from './pages/settings.js';
import { Sheet } from './ui.js';
import { QueuePage } from './pages/queue.js';
import { IconsPage } from './pages/icons.js';
import { TemplatesPage } from './pages/templates.js';
import { app, start, pageChanged, queueLabelCount } from './app.js';
import { useStore } from './state.js';
import { startAutoBackup, autoBackup } from './autobackup.js';
import { drive } from './gdrive.js';
import { APP_VERSION } from './version.js';

const REPO_URL = 'https://github.com/McTobe/cube-labeler';
const KOFI_URL = 'https://ko-fi.com/thetobek';

const PAGES = [
  { id: 'label', title: 'Label', icon: 'label' },
  { id: 'queue', title: 'Queue', icon: 'queue' },
  { id: 'icons', title: 'Icons', icon: 'icons' },
  { id: 'templates', title: 'Templates', icon: 'templates' },
  { id: 'settings', title: 'Settings', icon: 'settings' },
];

function currentPage() {
  const id = location.hash.replace(/^#\/?/, '');
  return PAGES.find((p) => p.id === id) || PAGES[0];
}

// Google Drive sync at a glance: green when syncing works, amber when Google wants the
// hourly click, red after an error, grey when it is off. Clicking it opens the sync box.
function SyncChip() {
  const d = useStore(drive);
  const auto = useStore(autoBackup);
  const [open, setOpen] = useState(false);
  let state = 'off';
  let title = 'Sync is off. Click to set up Google Drive sync, so your icons, templates and settings are on every device.';
  if (d.on && !d.token) {
    state = 'paused';
    title = 'Sync is paused: Google asks you to continue once an hour.';
  } else if (d.on && auto.driveError) {
    state = 'error';
    title = `Sync failed: ${auto.driveError}`;
  } else if (d.on) {
    state = auto.busy ? 'busy' : 'ready';
    title = auto.busy ? 'Syncing with Google Drive…' : `Synced with Google Drive${d.email ? ` (${d.email})` : ''}.`;
  }
  return html`<button class=${`printer-chip sync-chip state-${state}`} title=${title} aria-label=${title} onClick=${() => setOpen(true)}>
      <span class="dot" aria-hidden="true"></span><${Icon} name="cloud" size=${18} /><span class="chip-label">Sync</span>
    </button>
    <${Sheet} open=${open} title="Sync with Google Drive" onClose=${() => setOpen(false)}>
      <${SyncPanel} />
    <//>`;
}

function App() {
  const [page, setPage] = useState(currentPage);
  const { queue } = useStore(app);
  useEffect(() => {
    const onHash = () => { pageChanged(); setPage(currentPage()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => { document.title = page.id === 'label' ? 'Cube Labeler' : `${page.title} · Cube Labeler`; }, [page]);

  let body;
  if (page.id === 'label') body = html`<${LabelPage} />`;
  else if (page.id === 'queue') body = html`<${QueuePage} />`;
  else if (page.id === 'icons') body = html`<${IconsPage} />`;
  else if (page.id === 'templates') body = html`<${TemplatesPage} />`;
  else body = html`<${SettingsPage} />`;

  return html`<div class=${`shell page-${page.id}`}>
    <nav class="nav" aria-label="Pages">
      <a class="brand" href="#/label"><img src="icon-192.png" alt="" width="28" height="28" /><span>Cube Labeler</span></a>
      ${PAGES.map((p) => html`<a href=${`#/${p.id}`} class=${p.id === page.id ? 'active' : ''}
        aria-current=${p.id === page.id ? 'page' : undefined}>
        <${Icon} name=${p.icon} /><span>${p.title}</span>${p.id === 'queue' && queue.length > 0 && html`<span class="nav-count">${queueLabelCount(queue)}</span>`}</a>`)}
    </nav>
    <div class="main-col">
      <header class="topbar">
        <h1>${page.id === 'label' ? html`<span class="brand-inline">Cube Labeler</span><span class="page-name">Label</span>` : page.title}</h1>
        <span class="top-chips">
          <a class="printer-chip link-chip wide-only" href=${`${REPO_URL}/releases`} target="_blank" rel="noopener"
            title="What's new in each version">v${APP_VERSION}</a>
          <a class="printer-chip link-chip wide-only" href=${REPO_URL} target="_blank" rel="noopener" title="Cube Labeler on GitHub">
            <${Icon} name="github" size=${17} /><span class="chip-label">GitHub</span></a>
          <a class="printer-chip link-chip support-chip wide-only" href=${KOFI_URL} target="_blank" rel="noopener"
            title="Support Cube Labeler on Ko-fi"><${Icon} name="heart" size=${16} /><span class="chip-label">Support</span></a>
          <span class="chip-divider wide-only" aria-hidden="true"></span>
          <${SyncChip} /><${PrinterChip} />
        </span>
      </header>
      <main>${body}</main>
    </div>
  </div>`;
}

render(html`<${App} />`, document.getElementById('root'));
start();
startAutoBackup().catch((err) => console.warn('Automatic backups', err));

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  navigator.serviceWorker.register('sw.js').catch((err) => console.warn('Offline cache unavailable:', err));
}
