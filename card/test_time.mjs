// Checks the card's house-time helpers: `node card/test_time.mjs`. Costs nothing.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('camera-card.js', import.meta.url), 'utf8');
const helpers = src.slice(src.indexOf('// ---- time helpers'), src.indexOf('const errText'));
const load = (house, phone) => {
  process.env.TZ = phone; // node re-reads this on assignment
  return new Function('MIN', 'DAYMS', `${helpers}; TZ = ${JSON.stringify(house)}; return { wall, dayStart, dayIndex, iso, fromIso, hm, zone, at, dayName };`)(6e4, 864e5);
};
const Z = (s) => Date.parse(s);
const realNow = Date.now;
Date.now = () => Z('2026-11-22T02:30:00Z'); // 6:30 PM Saturday Nov 21 at the house

// A phone in Tokyo sees the house's evening, on the house's day, labelled.
let h = load('America/Los_Angeles', 'Asia/Tokyo');
const clip = Z('2026-11-22T02:04:00Z');
assert.equal(h.at(clip), '6:04 PM PST');
assert.equal(h.at(clip, clip + 6e5), '6:04 PM–6:14 PM PST');
assert.equal(h.iso(clip), '2026-11-21');
assert.equal(h.dayIndex(clip), 0);
assert.equal(h.dayStart(0), Z('2026-11-21T08:00:00Z'));
assert.equal(h.dayStart(1), Z('2026-11-20T08:00:00Z'));
assert.equal(h.dayIndex(Z('2026-11-21T07:59:00Z')), 1); // 11:59 PM Friday at the house
assert.equal(h.dayName(2), 'Thursday, Nov 19');
assert.equal(h.zone(Z('2026-07-01T20:00:00Z')), ' PDT'); // named for the clip's date, not today's

// Days start at house midnight on both sides of a clock change.
assert.equal(h.fromIso('2026-03-08'), Z('2026-03-08T08:00:00Z'));
assert.equal(h.fromIso('2026-03-09'), Z('2026-03-09T07:00:00Z'));
assert.equal(h.fromIso('2026-11-01'), Z('2026-11-01T07:00:00Z'));
assert.equal(h.fromIso('2026-11-02'), Z('2026-11-02T08:00:00Z'));

// At home, and anywhere the clocks agree, nothing is added.
assert.equal(load('America/Los_Angeles', 'America/Los_Angeles').at(clip), '6:04 PM');
assert.equal(load('America/Los_Angeles', 'America/Vancouver').at(clip), '6:04 PM');

// A house east of the phone, on a half-hour zone.
h = load('Asia/Kolkata', 'America/Los_Angeles');
assert.equal(h.hm(clip), '7:34 AM');
assert.equal(h.iso(clip), '2026-11-22');
assert.equal(h.wall(Z('2026-11-22T02:30:07Z')) / 1000 % 3600, 7); // 8:00:07 there: seconds past the hour

Date.now = realNow;
console.log('house time: ok');
