// Pages that are still on their way in the 2.0 web version
import { html } from '../html.js';
import { Icon } from '../icons.js';

const PLANS = {
  icons: 'Browse the icon library, add your own icons, edit them and redraw photos with AI.',
  templates: 'Start from a ready-made label or one you saved.',
};

export function SoonPage({ page, title }) {
  return html`<section class="card soon">
    <${Icon} name=${page} size=${40} />
    <h2>${title} is coming soon</h2>
    <p>${PLANS[page]}</p>
    <p class="hint">Until then, the desktop app has it.</p>
  </section>`;
}
