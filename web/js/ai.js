// AI icons: a picture redrawn as an icon by Gemini, OpenAI or OpenRouter. The page sends the
// request itself with the user's own key, which stays in this browser and never goes in a
// backup. Python builds the request and reads the answer the desktop app's way.

import { createStore } from './state.js';
import * as storage from './storage.js';
import { app, updateSettings, aiServices, aiModels, aiRequest, aiAnswer } from './app.js';

const TIMEOUT_MS = 120000;

export const ai = createStore({ ready: false, services: [], presets: [], custom: 'Custom', keys: {} });

export async function loadAi() {
  if (ai.get().ready) return;
  const [info, keys] = await Promise.all([aiServices(), storage.load('aiKeys', {})]);
  ai.set({ ready: true, ...info, keys });
}

export function currentService() {
  const { services } = ai.get();
  return services.find((s) => s.id === app.get().settings.ai_provider) || services[0];
}

export function setKey(service, key) {
  const keys = { ...ai.get().keys, [service]: key.trim() };
  if (!keys[service]) delete keys[service];
  ai.set({ keys });
  storage.save('aiKeys', keys);
}

export function setModel(service, model) {
  updateSettings({ ai_models: { ...app.get().settings.ai_models, [service]: model.trim() } });
}

// Redraws the picture (PNG bytes) with the chosen service; returns the new picture as PNG bytes
export async function redraw(picture, preset, custom) {
  await loadAi();
  const service = currentService();
  const key = ai.get().keys[service.id];
  if (!key) throw new Error(`${service.name} needs an API key. Add one under Settings.`);
  const models = await aiModels(service.id, app.get().settings.ai_models[service.id] || '');
  let lastError = `${service.name} could not make the icon.`;
  for (const model of models) {
    const req = await aiRequest(service.id, picture, preset, custom, model);
    let response;
    try {
      response = await fetch(req.url, {
        method: 'POST',
        headers: { ...req.headers, [req.key_header]: req.key_prefix + key },
        body: req.body,
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch (err) {
      if (err.name === 'TimeoutError') throw new Error(`${service.name} took too long to answer. Try again.`);
      throw new Error(`Could not reach ${service.name}. Check the internet connection and try again.`);
    }
    const answer = await aiAnswer(service.id, model, response.status, await response.text());
    if (answer.png) return answer.png;
    lastError = answer.error;
    if (!answer.try_next_model) break;
  }
  throw new Error(lastError);
}
