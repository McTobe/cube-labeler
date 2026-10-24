// Cube Labeler web app: the shell (navigation, top bar) and the page router.
import { render } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { PrinterChip } from './printer-ui.js';
import { LabelPage } from './pages/label.js';
import { SettingsPage } from './pages/settings.js';
import { SoonPage } from './pages/soon.js';
import { start } from './app.js';

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

function App() {
  const [page, setPage] = useState(currentPage);
  useEffect(() => {
    const onHash = () => { setPage(currentPage()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => { document.title = page.id === 'label' ? 'Cube Labeler' : `${page.title} · Cube Labeler`; }, [page]);

  let body;
  if (page.id === 'label') body = html`<${LabelPage} />`;
  else if (page.id === 'settings') body = html`<${SettingsPage} />`;
  else body = html`<${SoonPage} page=${page.id} title=${page.title} />`;

  return html`<div class=${`shell page-${page.id}`}>
    <nav class="nav" aria-label="Pages">
      <a class="brand" href="#/label"><img src="icon-192.png" alt="" width="28" height="28" /><span>Cube Labeler</span></a>
      ${PAGES.map((p) => html`<a href=${`#/${p.id}`} class=${p.id === page.id ? 'active' : ''}
        aria-current=${p.id === page.id ? 'page' : undefined}>
        <${Icon} name=${p.icon} /><span>${p.title}</span></a>`)}
    </nav>
    <div class="main-col">
      <header class="topbar">
        <h1>${page.id === 'label' ? html`<span class="brand-inline">Cube Labeler</span><span class="page-name">Label</span>` : page.title}</h1>
        <${PrinterChip} />
      </header>
      <main>${body}</main>
    </div>
  </div>`;
}

render(html`<${App} />`, document.getElementById('root'));
start();

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  navigator.serviceWorker.register('sw.js').catch((err) => console.warn('Offline cache unavailable:', err));
}
