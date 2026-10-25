// Google Drive for backups: sign in with Google, then backups go to a "Cube Labeler backups"
// folder in the user's Drive. The page asks only for the drive.file scope, so it sees the
// files it made itself and nothing else in the Drive. There is no server: Google hands the
// page a token that works for an hour, and after that one click on Continue gets a new one.

import * as storage from './storage.js';
import { createStore } from './state.js';

// From Google Cloud Console; not a secret, it is meant to ship in the page. Allowed origins:
// https://print.tobezone.com and http://localhost:8000
const CLIENT_ID = '883752261996-i1id09p1b49p304st8h3d7kdcpaps5c5.apps.googleusercontent.com';
const SCOPE = 'https://www.googleapis.com/auth/drive.file';
const GIS_URL = 'https://accounts.google.com/gsi/client';
const API = 'https://www.googleapis.com/drive/v3';
const UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id';
const FOLDER_NAME = 'Cube Labeler backups';
const FOLDER_TYPE = 'application/vnd.google-apps.folder';

export const drive = createStore({
  on: false,  // the user signed in and wants backups in Drive
  email: '',
  token: null,  // {value, expires} while Google's token is good
  folderId: null,
});

export const driveReady = () => {
  const { on, token } = drive.get();
  return on && !!token && token.expires > Date.now() + 60000;
};

let gis = null;
function loadGis() {
  if (!gis) {
    gis = new Promise((resolve, reject) => {
      const script = Object.assign(document.createElement('script'), { src: GIS_URL, async: true });
      script.onload = () => resolve(window.google.accounts.oauth2);
      script.onerror = () => { gis = null; reject(new Error('Could not reach Google. Check the internet connection.')); };
      document.head.append(script);
    });
  }
  return gis;
}

// Opens Google's sign-in window. Must run from a click, or the browser blocks the window.
async function requestToken(prompt) {
  const oauth2 = await loadGis();
  return new Promise((resolve, reject) => {
    const client = oauth2.initTokenClient({
      client_id: CLIENT_ID,
      scope: SCOPE,
      callback: (response) => {
        if (response.error) reject(new Error(response.error_description || response.error));
        else resolve({ value: response.access_token, expires: Date.now() + Number(response.expires_in || 3600) * 1000 });
      },
      error_callback: (err) => reject(new Error(err.type === 'popup_closed' ? 'Sign-in was closed.' : (err.message || 'Google sign-in failed.'))),
    });
    client.requestAccessToken({ prompt, login_hint: drive.get().email || undefined });
  });
}

async function call(url, options = {}) {
  const { token } = drive.get();
  if (!token) throw new Error('Not signed in to Google Drive.');
  const response = await fetch(url, { ...options, headers: { ...options.headers, Authorization: `Bearer ${token.value}` } });
  if (response.status === 401) {
    drive.set({ token: null });
    await storage.save('driveToken', null);
    throw new Error('Google sign-in ran out. Choose Continue to sign in again.');
  }
  if (!response.ok) {
    let message = `Google Drive said ${response.status}.`;
    try { message = (await response.json()).error.message || message; } catch (err) { /* keep the status */ }
    throw new Error(message);
  }
  return response;
}

const json = async (url, options) => (await call(url, options)).json();
const quoted = (text) => `'${text.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

// The backups folder: the one made before if it is still there, otherwise a new one
async function folderId() {
  const known = drive.get().folderId;
  if (known) {
    const folder = await json(`${API}/files/${known}?fields=id,trashed`).catch(() => null);
    if (folder && !folder.trashed) return known;
  }
  const q = `name = ${quoted(FOLDER_NAME)} and mimeType = '${FOLDER_TYPE}' and trashed = false`;
  const found = await json(`${API}/files?q=${encodeURIComponent(q)}&fields=files(id)&spaces=drive`);
  const id = found.files.length ? found.files[0].id
    : (await json(`${API}/files?fields=id`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: FOLDER_NAME, mimeType: FOLDER_TYPE }),
    })).id;
  drive.set({ folderId: id });
  await storage.save('driveFolderId', id);
  return id;
}

// The backups in the folder, newest first: [{id, name, createdTime}]
export async function listDriveBackups() {
  const parent = await folderId();
  const q = `${quoted(parent)} in parents and trashed = false`;
  const found = await json(`${API}/files?q=${encodeURIComponent(q)}&orderBy=createdTime desc&pageSize=100&fields=files(id,name,createdTime)`);
  return found.files.filter((f) => f.name.endsWith('.cubebackup'));
}

export async function downloadDriveBackup(file) {
  const data = await (await call(`${API}/files/${file.id}?alt=media`)).arrayBuffer();
  return new File([data], file.name, { type: 'application/zip' });
}

// Uploads a backup and keeps the newest `keep` of the ones the app put there
export async function uploadDriveBackup(name, data, keep) {
  const parent = await folderId();
  const boundary = `cube-${Math.random().toString(36).slice(2)}`;
  const body = new Blob([
    `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n`,
    JSON.stringify({ name, parents: [parent], mimeType: 'application/zip' }),
    `\r\n--${boundary}\r\nContent-Type: application/zip\r\n\r\n`,
    data,
    `\r\n--${boundary}--`,
  ]);
  await call(UPLOAD, { method: 'POST', headers: { 'Content-Type': `multipart/related; boundary=${boundary}` }, body });
  const all = await listDriveBackups();
  for (const old of all.slice(keep)) await call(`${API}/files/${old.id}`, { method: 'DELETE' }).catch(() => {});
}

async function keepToken(token) {
  drive.set({ token });
  await storage.save('driveToken', token);
}

// Signs in for the first time (or with another account). Must run from a click.
export async function signInToDrive() {
  await keepToken(await requestToken('select_account'));
  drive.set({ on: true });
  await storage.save('driveOn', true);
  try {
    const about = await json(`${API}/about?fields=user(emailAddress)`);
    drive.set({ email: about.user.emailAddress || '' });
    await storage.save('driveEmail', drive.get().email);
  } catch (err) { /* the address is only shown in Settings */ }
}

// Gets a new token after the old one ran out; Google skips the questions it already asked.
// Must run from a click.
export async function continueDrive() {
  await keepToken(await requestToken(''));
}

export async function signOutOfDrive() {
  const { token } = drive.get();
  if (token && window.google) window.google.accounts.oauth2.revoke(token.value, () => {});
  drive.set({ on: false, email: '', token: null });
  await Promise.all([storage.save('driveOn', false), storage.save('driveToken', null), storage.save('driveEmail', '')]);
}

export async function loadDrive() {
  const [on, email, token, folderId] = await Promise.all([
    storage.load('driveOn', false), storage.load('driveEmail', ''), storage.load('driveToken', null), storage.load('driveFolderId', null),
  ]);
  drive.set({ on, email, folderId, token: token && token.expires > Date.now() ? token : null });
}
