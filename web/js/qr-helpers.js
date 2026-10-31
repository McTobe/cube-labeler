// QR code helpers: small forms that write the QR code's content in a form phones act on when
// they scan it (join a network, add a contact, open a map). The first few sit in a row under the
// content field and the rest in its More menu, in this order. More helpers are added here.

const mecard = (s) => s.replace(/([\\;,:"])/g, '\\$1');
const digits = (s) => s.replace(/[^\d+]/g, '');
const icalText = (s) => s.replace(/([\\;,])/g, '\\$1').replace(/\n/g, '\\n');
// 2027-05-01T09:00 (a datetime-local field) -> 20270501T090000, local time
const icalTime = (s) => `${s.replace(/[-:]/g, '').slice(0, 13)}00`;

// "59.3294, 18.0686", or a Google Maps link with @lat,lng or q=lat,lng in it
export function parseLocation(text) {
  const t = text.trim();
  const m = t.match(/@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/)
    || t.match(/[?&](?:q|query|ll)=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/)
    || t.match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return [lat, lng];
}

const SOCIAL = {
  instagram: ['Instagram', (h) => `https://instagram.com/${h}`],
  linkedin: ['LinkedIn', (h) => `https://linkedin.com/in/${h}`],
  x: ['X', (h) => `https://x.com/${h}`],
  youtube: ['YouTube', (h) => `https://youtube.com/@${h}`],
  tiktok: ['TikTok', (h) => `https://tiktok.com/@${h}`],
  github: ['GitHub', (h) => `https://github.com/${h}`],
  facebook: ['Facebook', (h) => `https://facebook.com/${h}`],
};

// Each helper: its fields ({key, label, type, placeholder, required, options}), what the code
// holds for them, and a line on what scanning it does
export const QR_HELPERS = [
  {
    id: 'wifi', name: 'Wi-Fi', icon: 'wifi', title: 'Wi-Fi QR code', button: 'Use this network',
    fields: [
      { key: 'ssid', label: 'Network name', required: true },
      { key: 'security', label: 'Security', type: 'segmented', options: [['WPA', 'WPA/WPA2/WPA3'], ['WEP', 'WEP'], ['nopass', 'None']], value: 'WPA' },
      { key: 'password', label: 'Password', when: (v) => v.security !== 'nopass' },
      { key: 'hidden', label: 'Hidden network', type: 'toggle', value: false },
    ],
    build: (v) => {
      let code = `WIFI:T:${v.security};S:${mecard(v.ssid)};`;
      if (v.security !== 'nopass') code += `P:${mecard(v.password || '')};`;
      if (v.hidden) code += 'H:true;';
      return `${code};`;
    },
    note: 'Phones that scan the code join the network. Anyone who sees the label can read the password.',
  },
  {
    id: 'contact', name: 'Contact', icon: 'user', title: 'Contact card', button: 'Use this contact',
    fields: [
      { key: 'name', label: 'Name', required: true, placeholder: 'Tobe Kejonen' },
      { key: 'phone', label: 'Phone', type: 'tel', placeholder: '+46 70 123 45 67' },
      { key: 'email', label: 'Email', type: 'email' },
      { key: 'org', label: 'Company' },
    ],
    build: (v) => {
      let code = `MECARD:N:${mecard(v.name.trim())};`;
      if (v.phone) code += `TEL:${digits(v.phone)};`;
      if (v.email) code += `EMAIL:${mecard(v.email.trim())};`;
      if (v.org) code += `ORG:${mecard(v.org.trim())};`;
      return `${code};`;
    },
    note: 'Scanning offers to add the contact. Every field makes the code denser, so leave out what the label does not need.',
  },
  {
    id: 'location', name: 'Location', icon: 'pin', title: 'Location', button: 'Use this place',
    fields: [
      { key: 'place', label: 'Coordinates, a Google Maps link or an address', required: true, placeholder: '59.3294, 18.0686', locate: true },
    ],
    build: (v) => {
      const at = parseLocation(v.place);
      if (at) return `https://maps.google.com/?q=${at[0].toFixed(6).replace(/\.?0+$/, '')},${at[1].toFixed(6).replace(/\.?0+$/, '')}`;
      return `https://maps.google.com/?q=${encodeURIComponent(v.place.trim())}`;
    },
    note: 'Scanning opens the spot in a map app. Handy for a shed, a fuse box or a water valve.',
  },
  {
    id: 'phone', name: 'Phone call', icon: 'phone', title: 'Phone call', button: 'Use this number',
    fields: [{ key: 'phone', label: 'Phone number', type: 'tel', required: true, placeholder: '+46 70 123 45 67' }],
    build: (v) => `tel:${digits(v.phone)}`,
    note: 'Scanning offers to call the number. Start with + and the country code so it works from abroad too.',
  },
  {
    id: 'email', name: 'Email', icon: 'mail', title: 'Email', button: 'Use this email',
    fields: [
      { key: 'to', label: 'Email address', type: 'email', required: true },
      { key: 'subject', label: 'Subject', placeholder: 'Reorder M4 screws' },
      { key: 'body', label: 'Message', type: 'textarea' },
    ],
    build: (v) => {
      const params = [['subject', v.subject], ['body', v.body]].filter(([, x]) => x)
        .map(([k, x]) => `${k}=${encodeURIComponent(x)}`).join('&');
      return `mailto:${v.to.trim()}${params ? `?${params}` : ''}`;
    },
    note: 'Scanning opens a new email, ready to send.',
  },
  {
    id: 'sms', name: 'Text message', icon: 'message', title: 'Text message', button: 'Use this message',
    fields: [
      { key: 'phone', label: 'Phone number', type: 'tel', required: true },
      { key: 'text', label: 'Message', type: 'textarea' },
    ],
    build: (v) => `SMSTO:${digits(v.phone)}:${v.text || ''}`,
    note: 'Scanning opens a text message to the number, ready to send.',
  },
  {
    id: 'whatsapp', name: 'WhatsApp', icon: 'message', title: 'WhatsApp message', button: 'Use this chat',
    fields: [
      { key: 'phone', label: 'Phone number with country code', type: 'tel', required: true, placeholder: '+46 70 123 45 67' },
      { key: 'text', label: 'Message', type: 'textarea' },
    ],
    build: (v) => `https://wa.me/${digits(v.phone).replace('+', '')}${v.text ? `?text=${encodeURIComponent(v.text)}` : ''}`,
    note: 'Scanning opens a WhatsApp chat with the number.',
  },
  {
    id: 'event', name: 'Calendar event', icon: 'calendar', title: 'Calendar event', button: 'Use this event',
    fields: [
      { key: 'title', label: 'What', required: true, placeholder: 'Replace the water filter' },
      { key: 'start', label: 'Starts', type: 'datetime-local', required: true },
      { key: 'end', label: 'Ends', type: 'datetime-local' },
      { key: 'where', label: 'Where' },
    ],
    build: (v) => [
      'BEGIN:VEVENT', `SUMMARY:${icalText(v.title.trim())}`, `DTSTART:${icalTime(v.start)}`,
      v.end && `DTEND:${icalTime(v.end)}`, v.where && `LOCATION:${icalText(v.where.trim())}`, 'END:VEVENT',
    ].filter(Boolean).join('\n'),
    note: 'Scanning offers to add the event to the calendar. Some phone cameras show it as text instead, so try it once.',
  },
  {
    id: 'social', name: 'Social profile', icon: 'at', title: 'Social profile', button: 'Use this profile',
    fields: [
      { key: 'site', label: 'Site', type: 'select', options: Object.entries(SOCIAL).map(([k, [n]]) => [k, n]), value: 'instagram' },
      { key: 'handle', label: 'Username', required: true, placeholder: 'thetobek' },
    ],
    build: (v) => SOCIAL[v.site][1](v.handle.trim().replace(/^@/, '')),
    note: 'Scanning opens the profile.',
  },
];

// In the row under the field; the rest go in its More menu
export const QR_ROW = 3;

// What the code holds for a helper's values, or '' while a required field is empty
export function helperCode(helper, values) {
  const missing = helper.fields.some((f) => f.required && (!f.when || f.when(values)) && !String(values[f.key] || '').trim());
  return missing ? '' : helper.build(values);
}

export function helperDefaults(helper) {
  return Object.fromEntries(helper.fields.map((f) => [f.key, f.value ?? '']));
}

// Text that reads like a web address without its https://, which phones show as plain text
export const looksLikeSite = (text) => /^(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(\/\S*)?$/i.test(text.trim());

// How readable a code is at a number of printer dots per square (see qr_fit in cube_web.py).
// A dot is 0.14 mm; the limits are a first guess until test prints say otherwise.
export function fitLevel(dotsPerModule) {
  if (!dotsPerModule) return null;
  if (dotsPerModule >= 1.8) return 'ok';
  if (dotsPerModule >= 1.4) return 'small';
  return 'dense';
}
