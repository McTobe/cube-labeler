// The QR code helpers (js/qr-helpers.js) write content phones act on. Run with: node tests/test_qr_helpers.mjs
import assert from 'node:assert/strict';
import { QR_HELPERS, helperCode, helperDefaults, parseLocation, looksLikeSite, fitLevel } from '../js/qr-helpers.js';

const make = (id, values) => {
  const h = QR_HELPERS.find((x) => x.id === id);
  return helperCode(h, { ...helperDefaults(h), ...values });
};

assert.equal(make('wifi', { ssid: 'Shed;1', password: 'a:b' }), 'WIFI:T:WPA;S:Shed\\;1;P:a\\:b;;');
assert.equal(make('wifi', { ssid: 'Open', security: 'nopass' }), 'WIFI:T:nopass;S:Open;;');
assert.equal(make('wifi', {}), '');  // the network name is needed
assert.equal(make('contact', { name: 'Tobe', phone: '+46 70-123' }), 'MECARD:N:Tobe;TEL:+4670123;;');
assert.equal(make('phone', { phone: '+46 (70) 123 45' }), 'tel:+467012345');
assert.equal(make('email', { to: 'a@b.se', subject: 'Reorder M4' }), 'mailto:a@b.se?subject=Reorder%20M4');
assert.equal(make('sms', { phone: '0701', text: 'Hi' }), 'SMSTO:0701:Hi');
assert.equal(make('whatsapp', { phone: '+46 70 1', text: 'Hej då' }), 'https://wa.me/46701?text=Hej%20d%C3%A5');
assert.equal(make('social', { site: 'github', handle: '@McTobe' }), 'https://github.com/McTobe');
assert.equal(make('event', { title: 'Filter, new', start: '2027-05-01T09:00' }),
  'BEGIN:VEVENT\nSUMMARY:Filter\\, new\nDTSTART:20270501T090000\nEND:VEVENT');

assert.deepEqual(parseLocation('59.3294, 18.0686'), [59.3294, 18.0686]);
assert.deepEqual(parseLocation('https://www.google.com/maps/@59.3294,18.0686,15z'), [59.3294, 18.0686]);
assert.deepEqual(parseLocation('https://maps.google.com/?q=-33.9,151.2'), [-33.9, 151.2]);
assert.equal(parseLocation('Storgatan 1, Stockholm'), null);
assert.equal(make('location', { place: '59.329440, 18.068610' }), 'https://maps.google.com/?q=59.32944,18.06861');
assert.equal(make('location', { place: 'Storgatan 1' }), 'https://maps.google.com/?q=Storgatan%201');

assert.ok(looksLikeSite('example.com'));
assert.ok(looksLikeSite('www.tobezone.com/workshop'));
assert.ok(!looksLikeSite('https://example.com'));
assert.ok(!looksLikeSite('M4 screws'));

assert.equal(fitLevel(2.4), 'ok');
assert.equal(fitLevel(1.6), 'small');
assert.equal(fitLevel(1.1), 'dense');
assert.equal(fitLevel(0), null);

console.log('qr helpers: ok');
