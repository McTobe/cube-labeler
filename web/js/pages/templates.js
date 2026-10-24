// The Templates page: labels you saved to start from again, and the ready-made starting points.
// Template files are the desktop app's .json files, so they move between the two.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Field, Menu, Sheet, downloadBlob } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, say, openItem, itemTitle, currentItem } from '../app.js';
import { errorMessage } from '../../printer.js';
import {
  templates, loadTemplates, findTemplate, saveCurrentAsTemplate, deleteTemplate, thumbnail, templateFile,
  readTemplateFile, putTemplate,
} from '../templates.js';

function Thumb({ thumbKey, item }) {
  const { thumbs } = useStore(templates);
  const { phase } = useStore(boot);
  useEffect(() => { if (phase === 'ready') thumbnail(thumbKey, item); }, [thumbKey, phase]);
  return html`<span class="template-thumb">${thumbs[thumbKey] ? html`<img src=${thumbs[thumbKey]} alt="" />` : null}</span>`;
}

function MyTemplate({ entry }) {
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const use = () => { openItem(entry.item); say(`Opened ${entry.name}.`); };
  const download = async () => downloadBlob(await templateFile(entry), `${entry.name}.json`);
  return html`<li class="card template-card">
    <button class="template-open" onClick=${use} title=${`Open ${entry.name}`}>
      <${Thumb} thumbKey=${`mine:${entry.name.toLowerCase()}`} item=${entry.item} />
      <span class="template-name">${entry.name}</span>
      <span class="hint">${entry.item.mode === 'bin' ? 'Bin label' : 'Text label'}</span>
    </button>
    <span class="menu-anchor">
      <button class="icon-button" aria-label=${`More for ${entry.name}`} onClick=${() => setMenu(true)}><${Icon} name="more" /></button>
      <${Menu} open=${menu} onClose=${() => setMenu(false)} items=${[
        { label: 'Open', icon: 'edit', action: use },
        { label: 'Download file', icon: 'download', action: download },
        { label: 'Delete', icon: 'trash', action: () => setConfirm(true) },
      ]} />
    </span>
    <${Sheet} open=${confirm} title="Delete this template?" onClose=${() => setConfirm(false)}>
      <p>${entry.name} is deleted from this device. Labels you made from it stay as they are.</p>
      <div class="sheet-actions">
        <button class="secondary" onClick=${() => setConfirm(false)}>Keep it</button>
        <button class="primary danger" onClick=${() => { deleteTemplate(entry.name); setConfirm(false); say(`Deleted ${entry.name}.`); }}>Delete</button>
      </div>
    <//>
  </li>`;
}

function SaveSheet({ open, onClose }) {
  const [name, setName] = useState('');
  const { mode, label, bin } = useStore(app);
  useEffect(() => { if (open) setName(itemTitle(currentItem())); }, [open]);
  const taken = name.trim() && findTemplate(name);
  const save = (e) => {
    e.preventDefault();
    const saved = saveCurrentAsTemplate(name);
    say(`Saved ${saved} as a template.`);
    onClose();
  };
  return html`<${Sheet} open=${open} title="Save as a template" onClose=${onClose}>
    <form onSubmit=${save}>
      <p class="hint">Saves the ${mode === 'bin' ? 'bin label' : 'label'} you are editing, with all its settings${mode !== 'bin' && label.image ? ' and its picture' : ''}.</p>
      <${Field} label="Name" hint=${taken ? `This replaces your template ${taken.name}.` : ''}>
        <input type="text" value=${name} maxLength="80" onInput=${(e) => setName(e.currentTarget.value)} />
      <//>
      <div class="sheet-actions">
        <button type="button" class="secondary" onClick=${onClose}>Cancel</button>
        <button type="submit" class="primary" disabled=${!name.trim() || (mode === 'bin' && !bin)}>${taken ? 'Replace' : 'Save'}</button>
      </div>
    </form>
  <//>`;
}

export function TemplatesPage() {
  const state = useStore(templates);
  const { phase } = useStore(boot);
  const { status } = useStore(app);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => { if (phase === 'ready' && !state.ready) loadTemplates().catch((err) => say(errorMessage(err), true)); }, [phase]);

  const onFile = async (e) => {
    const files = [...e.currentTarget.files];
    e.currentTarget.value = '';
    let opened = null;
    for (const file of files) {
      try {
        const item = await readTemplateFile(file);
        const name = putTemplate(file.name.replace(/\.json$/i, ''), item);
        opened = opened || { name, item };
      } catch (err) {
        say(`${file.name}: ${errorMessage(err)}`, true);
        return;
      }
    }
    if (opened) say(files.length > 1 ? `Added ${files.length} templates.` : `Added ${opened.name} to your templates.`);
  };

  const ready = phase === 'ready' && state.ready;
  return html`<section class="templates-page">
    <header class="page-head">
      <p class="hint">Start a label from one you saved or a ready-made one. Template files work in the desktop app too.</p>
      <span class="head-buttons">
        <button class="secondary" disabled=${!ready} onClick=${() => fileRef.current.click()}>Open file</button>
        <button class="primary" disabled=${!ready} onClick=${() => setSaving(true)}><${Icon} name="plus" size=${18} />Save current label</button>
      </span>
      <input ref=${fileRef} type="file" accept=".json,application/json" multiple hidden onChange=${onFile} />
    </header>
    ${status.text && html`<p class=${`status-line${status.error ? ' error' : ''}`} role="status">${status.text}</p>`}

    ${!ready ? html`<div class="card stage-message"><div class="spinner" aria-hidden="true"></div><span>Loading templates…</span></div>` : html`
      <h2 class="section-heading">My templates</h2>
      ${state.mine.length
        ? html`<ul class="template-grid">${state.mine.map((entry) => html`<${MyTemplate} key=${entry.name} entry=${entry} />`)}</ul>`
        : html`<p class="hint empty-note card">Labels you save with “Save current label” show up here. They go in backups too.</p>`}
      <h2 class="section-heading">Starting points</h2>
      <ul class="template-grid">
        ${state.presets.map((preset) => html`<li class="card template-card" key=${preset.key}>
          <button class="template-open" onClick=${() => { openItem(preset); say(`Started from ${preset.name}.`); }}>
            <${Thumb} thumbKey=${`preset:${preset.key}`} item=${preset} />
            <span class="template-name">${preset.name}</span>
            <span class="hint">${preset.description}</span>
          </button>
        </li>`)}
      </ul>`}
    <${SaveSheet} open=${saving} onClose=${() => setSaving(false)} />
  </section>`;
}
