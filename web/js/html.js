// JSX-like templates without a build step: html`<div class=${cls}>${children}</div>`
import { h } from 'preact';
import htm from '../vendor/htm.module.js';

export const html = htm.bind(h);
