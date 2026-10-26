// Google Drive sync: sign in with Google, and the icons, templates and settings travel between
// devices as backups in a "Cube Labeler backups" folder in the user's Drive. The page asks only for the drive.file scope, so it sees the
// files it made itself and nothing else in the Drive.
//
// Two ways to sign in. When the server runs the sign-in helper (web/drive_auth.py, in the
// Docker image once it has the client secret), the user signs in once per device and the page
// asks the helper for a new one-hour token whenever it needs one. Without it (a local server,
// or the secret not set), Google hands the page a token that works for an hour, and after
// that one click on Continue gets a new one.

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
// The sign-in window tells the page how it went on this channel (see web/drive_auth.py)
const CHANNEL = 'cube-drive-sign-in';

export const drive = createStore({
  on: false,  // the user signed in and wants backups in Drive
  email: '',
  token: null,  // {value, expires} while Google's token is good
  folderId: null,
  helper: false,  // the server can keep people signed in
  kept: false,  // signed in through the helper, so new tokens come without a click
});

const fresh = (token) => !!token && token.expires > Date.now() + 60000;

export const driveReady = () => {
  const { on, token, kept } = drive.get();
  return on && (kept || fresh(token));
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

// --- The sign-in helper ---

// What the helper says: {enabled, signedIn}, or null when the server can't be reached
async function helperStatus() {
  let response;
  try {
    response = await fetch('/auth/status', { cache: 'no-store', credentials: 'same-origin' });
  } catch (err) {
    return null;
  }
  if (!response.ok) return { enabled: false, signedIn: false };
  try { return await response.json(); } catch (err) { return { enabled: false, signedIn: false }; }
}

async function setKept(kept) {
  drive.set({ kept });
  await storage.save('driveKept', kept);
}

// Signing in happens in a small window, so the label being made and the printer connection
// stay as they are. Opens the window right away, so it must run from a click.
let signingIn = null;
function signInWithHelper(hint) {
  const params = hint ? `?login_hint=${encodeURIComponent(hint)}` : '';
  const popup = window.open(`/auth/start${params}`, 'cube-google-sign-in', 'popup,width=500,height=650');
  if (!popup) throw new Error('The browser blocked the Google window. Allow pop-ups for this site and try again.');
  // Clicking again while the window is open reuses it and waits for the same answer
  if (!signingIn) signingIn = new Promise((resolve, reject) => {
    const channel = new BroadcastChannel(CHANNEL);
    const finish = (error) => {
      channel.close();
      clearTimeout(timeout);
      window.removeEventListener('focus', onFocus);
      signingIn = null;
      if (error) reject(error);
      else resolve();
    };
    channel.onmessage = ({ data }) => finish(data && data.ok ? null : new Error((data && data.error) || 'Google sign-in failed.'));
    // In case the message is missed (the window was closed by hand after signing in)
    const onFocus = () => setTimeout(async () => {
      const status = await helperStatus();
      if (signingIn && status && status.signedIn) finish(null);
    }, 800);
    window.addEventListener('focus', onFocus);
    const timeout = setTimeout(() => finish(new Error('Sign-in took too long. Try again.')), 10 * 60 * 1000);
  });
  return signingIn.then(() => setKept(true));
}

// A new one-hour token from the helper; several callers at once share one request
let refreshing = null;
function helperToken() {
  if (!refreshing) {
    refreshing = (async () => {
      let response;
      try {
        response = await fetch('/auth/token', { method: 'POST', credentials: 'same-origin' });
      } catch (err) {
        throw new Error('Could not reach the Cube Labeler server. Check the internet connection.');
      }
      if (response.status === 401) {
        await setKept(false);
        drive.set({ token: null });
        throw new Error('Google asks you to sign in again.');
      }
      let answer = {};
      try { answer = await response.json(); } catch (err) { /* keep the status */ }
      if (!response.ok) throw new Error(answer.message || `The sign-in helper said ${response.status}.`);
      const token = { value: answer.access_token, expires: Date.now() + Number(answer.expires_in || 3600) * 1000 };
      await keepToken(token);
      return token;
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}

async function accessToken() {
  const { token, kept } = drive.get();
  if (fresh(token)) return token.value;
  if (!kept) throw new Error(token ? 'Google sign-in ran out. Choose Continue to sign in again.' : 'Not signed in to Google Drive.');
  return (await helperToken()).value;
}

// --- Drive ---

async function call(url, options = {}, again = true) {
  const value = await accessToken();
  const response = await fetch(url, { ...options, headers: { ...options.headers, Authorization: `Bearer ${value}` } });
  if (response.status === 401) {
    drive.set({ token: null });
    await storage.save('driveToken', null);
    // With the helper a token that stopped working early is replaced once, without a click
    if (drive.get().kept && again) return call(url, options, false);
    throw new Error(drive.get().kept ? 'Google did not take the sign-in. Try Sync now again.' : 'Google sign-in ran out. Choose Continue to sign in again.');
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
  const found = await json(`${API}/files?q=${encodeURIComponent(q)}&orderBy=createdTime desc&pageSize=100&fields=files(id,name,createdTime,appProperties)`);
  return found.files.filter((f) => f.name.endsWith('.cubebackup'));
}

export async function downloadDriveBackup(file) {
  const data = await (await call(`${API}/files/${file.id}?alt=media`)).arrayBuffer();
  return new File([data], file.name, { type: 'application/zip' });
}

// Uploads a backup and keeps the newest `keep` of the ones the app put there; returns its id.
// The fingerprint of what it holds goes along, so other devices can tell what they have.
export async function uploadDriveBackup(name, data, keep, digest) {
  const parent = await folderId();
  const boundary = `cube-${Math.random().toString(36).slice(2)}`;
  const body = new Blob([
    `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n`,
    JSON.stringify({ name, parents: [parent], mimeType: 'application/zip', appProperties: { digest } }),
    `\r\n--${boundary}\r\nContent-Type: application/zip\r\n\r\n`,
    data,
    `\r\n--${boundary}--`,
  ]);
  const { id } = await (await call(UPLOAD, { method: 'POST', headers: { 'Content-Type': `multipart/related; boundary=${boundary}` }, body })).json();
  const all = await listDriveBackups();
  for (const old of all.slice(keep)) await call(`${API}/files/${old.id}`, { method: 'DELETE' }).catch(() => {});
  return id;
}

// Forgets the token when it runs out, so the page shows that syncing waits for a click
let expiry = null;
function watchToken(token) {
  clearTimeout(expiry);
  if (token) expiry = setTimeout(() => drive.set({ token: null }), Math.max(0, token.expires - Date.now() - 60000));
}

async function keepToken(token) {
  drive.set({ token });
  watchToken(token);
  await storage.save('driveToken', token);
}

// Signs in for the first time (or with another account). Must run from a click.
export async function signInToDrive() {
  if (drive.get().helper) await signInWithHelper();
  else await keepToken(await requestToken('select_account'));
  drive.set({ on: true });
  await storage.save('driveOn', true);
  try {
    const about = await json(`${API}/about?fields=user(emailAddress)`);
    drive.set({ email: about.user.emailAddress || '' });
    await storage.save('driveEmail', drive.get().email);
  } catch (err) { /* the address is only shown in Settings */ }
}

// Gets a new token after the old one ran out; Google skips the questions it already asked.
// With the helper this signs in once more and then stays signed in. Must run from a click.
export async function continueDrive() {
  if (drive.get().helper) {
    await signInWithHelper(drive.get().email);
    await helperToken();
  } else {
    await keepToken(await requestToken(''));
  }
}

export async function signOutOfDrive() {
  const { token, helper } = drive.get();
  if (helper) await fetch('/auth/signout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  else if (token && window.google) window.google.accounts.oauth2.revoke(token.value, () => {});
  drive.set({ on: false, email: '', token: null, kept: false });
  await Promise.all([storage.save('driveOn', false), storage.save('driveToken', null), storage.save('driveEmail', ''), storage.save('driveKept', false)]);
}

export async function loadDrive() {
  const [on, email, token, folderId, kept, status] = await Promise.all([
    storage.load('driveOn', false), storage.load('driveEmail', ''), storage.load('driveToken', null), storage.load('driveFolderId', null),
    storage.load('driveKept', false), helperStatus(),
  ]);
  // Offline the helper can't answer, so the last known answer stands
  const helper = status ? status.enabled : kept;
  const stillKept = on && (status ? status.enabled && status.signedIn : kept);
  drive.set({ on, email, folderId, helper, kept: stillKept, token: fresh(token) ? token : null });
  if (status && stillKept !== kept) await storage.save('driveKept', stillKept);
  watchToken(drive.get().token);
}
