// Camera card for Home Assistant: recent recordings from our Reolink NVR as a scrolling list, with
// one-tap playback, live view, and a camera grid. Data comes from the family-infra Reolink override
// (/api/reolink/recordings, /still, /play). Ported from proto/charlie3.html.
const VERSION = 'v1-dev';
const MIN = 6e4, DAYMS = 864e5, CHUNK = 30; // days per older-recordings fetch (~0.8 s for a month)
const PALETTE = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9']; // dataviz validator: passes on dark
const I = {
  person: '<circle cx="12" cy="7" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/>',
  vehicle: '<path d="M3 16v-4l2.5-5h13l2.5 5v4z"/><circle cx="7.5" cy="16.5" r="1.8"/><circle cx="16.5" cy="16.5" r="1.8"/>',
  animal: '<circle cx="6.5" cy="10" r="1.8"/><circle cx="10" cy="5.5" r="1.8"/><circle cx="14" cy="5.5" r="1.8"/><circle cx="17.5" cy="10" r="1.8"/><path d="M8 18c0-3 2-6 4-6s4 3 4 6c0 2-2 2-4 2s-4 0-4-2z"/>',
  motion: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  play: '<path d="M7 4.5v15l12.5-7.5z"/>',
  pause: '<path d="M6.5 4.5h4v15h-4zM13.5 4.5h4v15h-4z"/>',
  prev: '<path d="M5 5h2.5v14H5zM20 5v14L9 12z"/>',
  next: '<path d="M16.5 5H19v14h-2.5zM4 5v14l11-7z"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  doorbell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  unknown: '<circle cx="12" cy="12" r="8"/><path d="M9.8 9.5a2.3 2.3 0 1 1 3.2 2.1c-.6.3-1 .8-1 1.4v.5M12 16.5v.01"/>',
};
const FILLED = new Set(['play', 'pause', 'prev', 'next']);
const svg = (k, cls = '') => `<svg class="${FILLED.has(k) ? 'f ' : ''}${cls}" viewBox="0 0 24 24">${I[k]}</svg>`;

const STYLE = `
:host{display:block;--pg:var(--ha-card-background,var(--card-background-color,#1c1c1e));--cell:color-mix(in srgb,var(--txt) 8%,transparent);--cell2:color-mix(in srgb,var(--txt) 15%,transparent);--sep:var(--divider-color,#38383a);--txt:var(--primary-text-color,#f2f2f7);--mut:var(--secondary-text-color,#8e8e93);--acc:var(--primary-color,#0a84ff);--red:#ff453a}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
[hidden]{display:none!important}
button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
button:disabled{opacity:.3;cursor:default}
svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
svg.f{fill:currentColor;stroke:none}
#app{position:relative;height:calc(100dvh - var(--header-height,56px) - env(safe-area-inset-top,0px));max-width:600px;margin:0 auto;border-radius:var(--ha-card-border-radius,12px);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color,#0002));box-shadow:var(--ha-card-box-shadow,none);display:flex;flex-direction:column;overflow:hidden;background:var(--pg);color:var(--txt);font:15px/1.3 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
#player{height:min(84vw,506px,45%);flex:none;display:flex;flex-direction:column;background:#000}
#grid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,1fr);gap:2px;height:100%}
.tile{position:relative;overflow:hidden;text-align:left;background:var(--cell)}
.tile img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.tile .nm{position:absolute;left:8px;top:6px;font-size:12px;font-weight:600;color:#fff;text-shadow:0 1px 2px #000}
.tile .lv{position:absolute;right:6px;top:6px;font-size:9.5px;font-weight:700;letter-spacing:.06em;color:#fffc;background:#0006;border-radius:3px;padding:1px 4px}
#single{display:flex;flex-direction:column;height:100%}
#video{position:relative;flex:1;min-height:0;display:grid;place-items:center;overflow:hidden;background:#000}
#video video,#video #live,#video #liveimg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
#cap{position:relative;max-width:84%;text-align:center;font-size:15px;color:var(--mut)}
.vtop{position:absolute;z-index:1;color:#fff;left:10px;right:10px;top:8px;display:flex;justify-content:space-between;gap:8px;white-space:nowrap;font-size:12px;font-weight:600;text-shadow:0 1px 2px #000;pointer-events:none}
#vcam{min-width:0;overflow:hidden;text-overflow:ellipsis}
.badge{color:#fff;background:var(--red);border-radius:4px;padding:1px 6px;font-size:11px;letter-spacing:.04em}
#ctl{flex:none;display:flex;flex-direction:column;padding:2px 10px 4px;background:var(--pg)}
.pill{height:30px;min-width:44px;padding:0 10px;border-radius:15px;background:var(--cell2);font-size:13px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;gap:4px}
.pill.red{background:var(--red);color:#fff}
.r2{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}
.r2 span{min-width:44px}.r2 span:last-child{text-align:right}
#seek{flex:1;height:24px;accent-color:var(--txt);margin:0}
.r3{display:flex;align-items:center;gap:2px}.r3 .sp{flex:1}
.r3 button:not(.pill){width:46px;height:36px;display:grid;place-items:center;border-radius:20px;font-size:13px;font-weight:600}
.r3 button:active,.pill:active,.row:active{background:var(--cell2)}
#bplay svg{width:28px;height:28px}
.chips{flex:none;display:flex;gap:5px;padding:6px 10px;overflow-x:auto;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:none;height:30px;padding:0 8px;border-radius:15px;background:var(--cell);font-size:12px;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.chip[aria-pressed=true]{background:var(--txt);color:var(--pg);font-weight:600}
.cd{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
#filters{padding-top:0;border-bottom:.5px solid var(--sep)}
#filters .sp{flex:1;min-width:0}
#cams .chip{padding:0 6px}
.chip svg{width:15px;height:15px}
#filters .chip{padding:0 12px}
#bdate{position:relative}
#date{position:absolute;inset:0;opacity:0;width:100%}
#feed{flex:1;overflow-y:auto;overflow-anchor:none;overscroll-behavior:contain;padding-bottom:calc(16px + env(safe-area-inset-bottom,0px))}
.dh{position:sticky;top:0;z-index:2;background:var(--pg);padding:8px 16px 6px}
.dh .tt{display:flex;justify-content:space-between;align-items:baseline;font-weight:700;font-size:16px}
.dh .tt span{font-weight:400;font-size:12px;color:var(--mut)}
.rib{position:relative;height:16px;margin-top:6px;border-radius:3px;background:var(--cell);overflow:hidden;cursor:pointer}
.rib i{position:absolute;top:0;bottom:0;min-width:2px;border-radius:1px}
.rib .fut{position:absolute;top:0;bottom:0;right:0;opacity:.5;background:repeating-linear-gradient(135deg,transparent 0 3px,var(--sep) 3px 5px)}
.hl{display:flex;justify-content:space-between;font-size:10px;color:var(--mut);margin-top:2px}
.row{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:7px 16px;min-height:56px}
.row.on{background:#0a84ff26;box-shadow:inset 3px 0 var(--acc)}
.row.flash{animation:fl 1.2s}
@keyframes fl{0%,40%{background:var(--cell2)}}
.sw{position:relative;width:71px;height:40px;border-radius:6px;flex:none;overflow:hidden;background:var(--cell)}
.sw img{width:100%;height:100%;object-fit:cover;display:block}
.sw.stack{overflow:visible;box-shadow:4px -4px 0 -1px var(--sep),8px -8px 0 -2px var(--cell2);margin-right:6px}
.sw.stack img{border-radius:6px}
.sw b{color:#fff;position:absolute;right:3px;bottom:2px;font-size:10px;font-weight:600;background:#0009;border-radius:3px;padding:0 3px;font-variant-numeric:tabular-nums}
.tx{flex:1;min-width:0}
.t1{display:flex;align-items:center;gap:5px;font-weight:600;font-size:15px}
.t1 svg{width:15px;height:15px;color:var(--mut)}
.t1 .cn{font-weight:400;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t2{font-size:13px;color:var(--mut);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chev{color:var(--mut);transition:transform .2s}
.burst.open .chev{transform:rotate(90deg)}
.kids{background:var(--cell2)}
.kids .row{padding-left:28px;min-height:48px}
.kids .sw{width:59px;height:33px}
.untg{margin-top:6px;font-size:12.5px;color:var(--acc);padding:4px 0}
.quiet{padding:10px 16px;font-size:13px;color:var(--mut);text-align:center;border-top:.5px solid var(--sep);border-bottom:.5px solid var(--sep);margin:6px 0}
.end{padding:20px;text-align:center;font-size:12px;color:var(--mut)}
#toast{position:absolute;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0px));transform:translate(-50%,20px);opacity:0;transition:.25s;background:#2c2c2ef2;color:#fff;padding:10px 16px;border-radius:14px;font-size:14px;white-space:nowrap;pointer-events:none;z-index:9}
#toast.show{opacity:1;transform:translate(-50%,0)}
`;

const HTML = `
<div id="app">
  <section id="player">
    <div id="grid"></div>
    <div id="single" hidden>
      <div id="video">
        <div class="vtop"><span id="vcam"></span><span id="vbadge"></span></div>
        <video id="vid" playsinline muted hidden></video>
        <img id="liveimg" alt="" hidden>
        <div id="cap"></div>
      </div>
      <div id="ctl">
        <div class="r2"><span id="tel"></span><input type="range" id="seek" aria-label="Seek" min="0" step="0.1"><span id="ttot"></span></div>
        <div class="r3">
          <button id="bprev" aria-label="Previous clip"></button>
          <button id="bback" aria-label="Skip back"></button>
          <button id="bplay" aria-label="Play/pause"></button>
          <button id="bfwd" aria-label="Skip forward"></button>
          <button id="bnext" aria-label="Next clip"></button>
          <span class="sp"></span>
          <button class="pill" id="bspeed" aria-label="Playback speed">1×</button>
          <button class="pill red" id="blive" aria-label="Go live">Live</button>
          <button class="pill" id="bgrid" aria-label="All cameras"></button>
        </div>
      </div>
    </div>
  </section>
  <nav id="cams" class="chips"></nav>
  <div id="filters" class="chips">
    <button class="chip" data-tag="" aria-pressed="true">All</button>
    <button class="chip" data-tag="person">People</button>
    <button class="chip" data-tag="vehicle">Cars</button>
    <button class="chip" data-tag="animal">Animals</button>
    <button class="chip" data-tag="doorbell" aria-label="Rang the doorbell">Rang</button>
    <span class="sp"></span>
    <button class="chip" id="bdate" aria-label="Jump to a day"><input type="date" id="date" aria-label="Jump to a day"></button>
  </div>
  <main id="feed"><div id="more"></div></main>
  <div id="toast"></div>
</div>`;

// ---- time helpers (the phone's local time; the NVR is in the same timezone)
const dayStart = (i) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - i); return d.getTime(); };
const dayIndex = (t) => { const d = new Date(t); d.setHours(0, 0, 0, 0); return Math.round((dayStart(0) - d.getTime()) / DAYMS); };
const iso = (t) => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const fmt = (o) => new Intl.DateTimeFormat('en-US', o).format; // one formatter each: toLocale* builds one per call
const hm = fmt({ hour: 'numeric', minute: '2-digit' }), hms = fmt({ hour: 'numeric', minute: '2-digit', second: '2-digit' });
const wkS = fmt({ weekday: 'short' }), wkL = fmt({ weekday: 'long', month: 'short', day: 'numeric' }), md = fmt({ month: 'short', day: 'numeric' });
const dayName = (i, short) => i === 0 ? 'Today' : i === 1 ? 'Yesterday' : (short ? wkS : wkL)(dayStart(i));
const when = (t) => { const i = dayIndex(t); return (i < 7 ? dayName(i, true) : md(t)) + ' ' + hm(t); };
const errText = (e) => e?.body?.message || e?.message || e?.error || e?.status_code || String(e);
const ago = (t) => { const m = (Date.now() - t) / MIN; return m < 1 ? 'just now' : m < 60 ? `${Math.floor(m)} min ago` : m < 360 ? `${Math.floor(m / 60)} hr ago` : ''; };
const clock = (s) => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = String(s % 60).padStart(2, '0'); return h ? `${h}:${String(m).padStart(2, '0')}:${x}` : `${m}:${x}`; };
const short = (s) => s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.floor(s / 3600)}h ${Math.round(s / 60) % 60}m`;
const len = (c) => (c.end - c.start) / 1000;
const KN = { doorbell: 'Rang the bell', person: 'Person', vehicle: 'Vehicle', animal: 'Animal' };
const ordered = (tags) => ['doorbell', 'person', 'vehicle', 'animal'].filter((t) => tags.includes(t));
const kind = (tags, sched) => [sched && 'Scheduled', ...ordered(tags).map((t) => KN[t])].filter(Boolean).join(' · ') || 'Motion';
const icons = (c) => (c.sched ? svg('clock') : '') + (c.tags.length ? ordered(c.tags).map((t) => svg(t)).join('') : c.sched ? '' : svg('motion'));
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => `&#${ch.charCodeAt(0)};`);

class CameraCard extends HTMLElement {
  setConfig(config) { this._config = config || {}; }
  getCardSize() { return 12; }
  set hass(h) {
    this._hass = h;
    if (!this._started) { this._started = true; mount(this, this._config); }
  }
  get hass() { return this._hass; }
  connectedCallback() { this._timers?.start(); }
  disconnectedCallback() { this._timers?.stop(); }
}

function mount(host, config) {
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>${STYLE}</style>${HTML}`;
  const $ = (s) => root.querySelector(s);
  const api = (path) => Promise.race([host.hass.callApi('GET', path), new Promise((_, no) => setTimeout(() => no(new Error('timed out')), 15000))]);
  const S = { cams: [], recs: new Map(), byId: new Map(), hiddenSched: [], loaded: -1, oldest: 0, sched: false, cam: 'all', tag: '', view: { mode: 'grid' }, speed: 1, all: [], next: 0, quiet: null, open: new Set(), seeking: false, playSeq: 0, gen: 0 };
  const cam = {};
  const camDot = (ch) => PALETTE[S.cams.findIndex((c) => c.ch === ch) % PALETTE.length];

  // ---- data
  const toRec = (r) => ({ id: r.id, cam: r.ch, start: Date.parse(r.start), end: Date.parse(r.end), tags: [...r.tags].sort(), untagged: r.untagged });
  async function fetchDays(newest, oldest) { // day indexes, inclusive
    const j = await api(`reolink/recordings?from=${iso(dayStart(oldest))}&to=${iso(dayStart(newest))}`);
    return j;
  }
  async function loadOlder() { // the next CHUNK days past what's loaded
    const from = S.loaded + 1, to = Math.min(S.loaded + CHUNK, S.days);
    const j = await fetchDays(from, to);
    for (const r of j.recordings) S.recs.set(r.id, toRec(r));
    S.loaded = to;
    filter();
  }
  function filter() {
    const ids = new Set(S.cam === 'all' ? S.cams.map((c) => c.ch) : [S.cam]);
    const events = merge([...S.recs.values()].filter((c) => ids.has(c.cam)).sort((a, b) => a.start - b.start));
    S.byId = new Map(events.map((e) => [e.key, e]));
    const plain = (e) => e.sched && !e.tags.length;
    S.hiddenSched = !S.tag && !S.sched ? events.filter(plain) : [];
    S.all = events.filter((e) => S.tag ? e.tags.includes(S.tag) : S.sched || !plain(e));
  }
  // The integration hands out recordings in 5-minute slices; the NVR's own files are what count.
  // A motion file is one event: merge its slices and their tags. An always-save file (about an hour,
  // opened on the hour) splits wherever the tags change, so a sighting inside it is its own row.
  function merge(slices) {
    const span = new Map();
    for (const c of slices) {
      const k = `${c.cam}|${c.id.split('|')[4]}`, x = span.get(k);
      span.set(k, x ? [Math.min(x[0], c.start), Math.max(x[1], c.end)] : [c.start, c.end]);
    }
    const isSched = (k) => { const [a, b] = span.get(k), past = (a / 1000) % 3600; return b - a >= 20 * MIN || past <= 15 || past >= 3585; };
    const out = [], last = {};
    for (const c of slices) {
      const e = last[c.cam], f = c.id.split('|'), fk = `${c.cam}|${f[4]}`, sched = isSched(fk);
      if (e && len(c) < 10 && c.start <= e.end + 2000) continue; // a seconds-long stub at a file change: part of e
      if (e && e.fk === fk && c.start - e.end <= 2000 && (!sched || c.tags.join() === e.tags.join())) {
        if (c.end > e.end) { e.end = c.end; e.id = e.id.replace(/[^|]+$/, f[6]); }
        if (!sched) e.tags = [...new Set([...e.tags, ...c.tags])].sort();
      } else {
        if (e && e.end - e.start < 10000 && c.start <= e.end + 2000) e.drop = true; // ... or just before it
        out.push(last[c.cam] = { ...c, fk, sched, key: `${c.cam}:${c.start}` });
      }
    }
    return out.filter((e) => !e.drop);
  }
  // Short clips on one camera less than a minute apart collapse into one burst row.
  function dayUnits(i) {
    const a = dayStart(i), b = dayStart(i - 1);
    const inDay = S.all.filter((c) => c.start >= a && c.start < b);
    const runs = [], last = {};
    for (const c of inDay) {
      const r = last[c.cam], p = r && r[r.length - 1];
      if (p && len(p) < 120 && len(c) < 120 && c.start - p.end < MIN) r.push(c);
      else runs.push(last[c.cam] = [c]);
    }
    const units = runs.flatMap((r) => r.length >= 3 ? [r] : r.map((c) => [c]));
    units.sort((x, y) => y[y.length - 1].start - x[x.length - 1].start);
    return { a, inDay, units };
  }

  // ---- stills: fetched with the user's token, a few at a time, only for rows on screen
  const stillQ = [], stillUrls = new Map();
  let stillBusy = 0;
  const stillIO = new IntersectionObserver((es) => {
    for (const e of es) {
      const el = e.target;
      if (e.isIntersecting) { stillIO.unobserve(el); stillQ.push(el); }
    }
    pumpStills();
  }, { root: root.querySelector('#feed'), rootMargin: '300px' });
  async function pumpStills() {
    while (stillBusy < 4 && stillQ.length) {
      const el = stillQ.pop(); // newest request first: what the user scrolled to last
      if (!el.isConnected) continue;
      const key = el.dataset.still;
      stillBusy++;
      (async () => {
        try {
          let url = stillUrls.get(key);
          if (url) { stillUrls.delete(key); stillUrls.set(key, url); } // most recently used last
          else {
            const r = await host.hass.fetchWithAuth(`/api/reolink/still/${key}`);
            if (!r.ok) throw new Error(r.status);
            url = URL.createObjectURL(await r.blob());
            stillUrls.set(key, url);
            if (stillUrls.size > 300) { const [k, u] = stillUrls.entries().next().value; stillUrls.delete(k); URL.revokeObjectURL(u); }
          }
          el.insertAdjacentHTML('afterbegin', `<img alt="" src="${url}">`);
        } catch { /* leave the grey box */ } finally { stillBusy--; pumpStills(); }
      })();
    }
  }
  const stillKey = (c) => `${c.cam}/${Math.floor(c.start / 1000) + Math.min(3, Math.floor(len(c) / 2))}`;

  // ---- feed rendering
  const feed = $('#feed'), more = $('#more');
  const stillHTML = (c, badge, cls = '') => `<span class="sw ${cls}" data-still="${stillKey(c)}"><b>${badge}</b></span>`;
  function rowHTML(c) {
    const camName = S.cam === 'all' ? `<span class="cn"><span class="cd" style="background:${camDot(c.cam)}"></span>${esc(cam[c.cam].short)}</span>` : '';
    const sub = [len(c) >= 300 ? `${hm(c.start)}–${hm(c.end)}` : hm(c.start), ago(c.start)].filter(Boolean).join(' · ');
    return `<button class="row" data-play="${c.key}" data-t="${c.start}" aria-label="${kind(c.tags, c.sched)} ${esc(cam[c.cam].name)} ${hm(c.start)}">
      ${stillHTML(c, short(len(c)))}
      <span class="tx"><span class="t1">${icons(c)}${kind(c.tags, c.sched)}${camName}</span><span class="t2">${sub}</span></span></button>`;
  }
  function burstHTML(r) {
    const first = r[0], lastC = r[r.length - 1], key = first.id;
    const tags = [...new Set(r.flatMap((c) => c.tags))];
    const open = S.open.has(key);
    return `<div class="burst${open ? ' open' : ''}" data-key="${esc(key)}">
      <button class="row grp" data-burst="${esc(key)}" data-t="${lastC.start}" aria-label="Burst of ${r.length} clips">
        ${stillHTML(lastC, r.length, 'stack')}
        <span class="tx"><span class="t1">${tags.length ? ordered(tags).map((t) => svg(t)).join('') : svg('motion')}${r.length} clips${S.cam === 'all' ? `<span class="cn">${esc(cam[first.cam].short)}</span>` : ''}</span>
        <span class="t2">${hm(first.start)}–${hm(lastC.end)} · ${kind(tags, r.every((c) => c.sched))}</span></span>
        ${svg('chev', 'chev')}</button>
      <div class="kids" ${open ? '' : 'hidden'}>${r.slice().reverse().map((c) => rowHTML(c)).join('')}</div></div>`;
  }
  function ribbonHTML(d, i) {
    const bars = d.inDay.map((c) => {
      const l = Math.max(0, (c.start - d.a) / DAYMS * 100), r = Math.min(100, (c.end - d.a) / DAYMS * 100);
      return `<i style="left:${l}%;width:${Math.max(0, r - l)}%;background:${S.cam === 'all' ? camDot(c.cam) : 'var(--acc)'}"></i>`;
    }).join('');
    const fut = i === 0 ? `<span class="fut" style="left:${(Date.now() - d.a) / DAYMS * 100}%"></span>` : '';
    return `<div class="rib" data-a="${d.a}" aria-label="Day timeline">${bars}${fut}</div><div class="hl"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>12a</span></div>`;
  }
  const hiddenOn = (i) => S.hiddenSched.filter((c) => c.start >= dayStart(i) && c.start < dayStart(i - 1)).length;
  function daySection(i, d = dayUnits(i)) {
    const el = document.createElement('section');
    el.dataset.day = i;
    const n = d.inDay.length, hid = hiddenOn(i);
    const untg = !S.tag && (hid || S.sched) ? `<button class="untg" data-untagged>${S.sched ? 'Hide scheduled recordings' : `+ ${hid} scheduled`}</button>` : '';
    el.innerHTML = `<div class="dh"><div class="tt">${dayName(i)}<span>${n ? `${n} clip${n > 1 ? 's' : ''}` : i ? 'No clips' : 'No activity yet'}</span></div>${ribbonHTML(d, i)}${untg}</div>`
      + d.units.map((u) => u.length > 1 ? burstHTML(u) : rowHTML(u[0])).join('');
    el.querySelectorAll('[data-still]').forEach((s) => stillIO.observe(s));
    return el;
  }
  function flushQuiet() {
    if (!S.quiet) return;
    const q = S.quiet, el = document.createElement('div');
    el.className = 'quiet'; el.dataset.from = q.from; el.dataset.to = q.to;
    const nm = (i) => new Date(dayStart(i)).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    el.textContent = `Nothing ${S.tag ? 'matching ' : ''}${q.from === q.to ? 'on ' + nm(q.from) : `from ${nm(q.to)} to ${nm(q.from)}`}`;
    if (q.untg) { const b = document.createElement('button'); b.className = 'untg'; b.dataset.untagged = ''; b.dataset.day = q.from; b.textContent = `+ ${q.untg} scheduled`; el.append(document.createElement('br'), b); }
    feed.insertBefore(el, more); S.quiet = null;
  }
  // One render at a time. rebuild() bumps gen, so a render waiting on the network gives up.
  let rendering = null;
  function renderMore(upTo = 0) {
    rendering ||= doRender(upTo, S.gen).then((failed) => {
      rendering = null;
      const recheck = () => { moreIO.unobserve(more); moreIO.observe(more); }; // still near the bottom?
      failed ? setTimeout(recheck, 5000) : recheck();
    });
    return rendering;
  }
  async function doRender(upTo, gen) {
      try {
        let n = 0;
        while (S.next <= S.days && (n < 30 || S.next <= upTo)) {
          if (S.next > S.loaded) {
            more.className = 'end'; more.textContent = 'Loading…';
            await loadOlder();
            if (gen !== S.gen) return;
          }
          const i = S.next++, d = dayUnits(i);
          if (i > 0 && !d.units.length) { const u = hiddenOn(i); S.quiet ? (S.quiet.to = i, S.quiet.untg += u) : (S.quiet = { from: i, to: i, untg: u }); continue; }
          flushQuiet();
          feed.insertBefore(daySection(i, d), more);
          n += d.units.length + 2;
        }
        more.className = ''; more.textContent = '';
        if (S.next > S.days) {
          flushQuiet(); more.className = 'end';
          more.textContent = `That's everything: the NVR keeps recordings back to ${md(S.oldest)}`;
        }
        markPlaying();
      } catch (e) {
        more.className = 'end'; more.textContent = `Couldn't load older recordings (${errText(e)}). Retrying…`;
        return true;
      }
  }
  async function rebuild(keepDay) {
    S.gen++;
    await rendering;
    filter();
    feed.querySelectorAll('section,.quiet').forEach((e) => e.remove());
    S.next = 0; S.quiet = null;
    feed.scrollTop = 0;
    await renderTo(keepDay || 0);
    if (keepDay) jumpToDay(keepDay);
  }
  async function renderTo(i) { // keep going until day i is on screen, even behind a render in flight
    do await renderMore(i); while (S.next <= Math.min(i, S.days) && !more.textContent.startsWith("Couldn't"));
  }
  async function refreshToday() {
    const j = await api(`reolink/recordings?from=${iso(dayStart(0))}`);
    const sig = j.recordings.map((r) => r.id).join() + '|' + Math.floor(Date.now() / (5 * MIN));
    if (sig === S.todaySig) return;
    S.todaySig = sig;
    const t0 = dayStart(0);
    for (const [k, c] of S.recs) if (c.start >= t0) S.recs.delete(k);
    for (const r of j.recordings) S.recs.set(r.id, toRec(r));
    filter();
    const old = feed.querySelector('section[data-day="0"]');
    if (!old) return;
    old.querySelectorAll('[data-still]').forEach((x) => stillIO.unobserve(x));
    const h = old.offsetHeight, nu = daySection(0);
    old.replaceWith(nu);
    if (feed.scrollTop > 0) feed.scrollTop += nu.offsetHeight - h;
    markPlaying();
  }
  const moreIO = new IntersectionObserver((es) => { if (es[0].isIntersecting && S.next <= S.days) renderMore(); }, { root: feed, rootMargin: '600px' });

  function markPlaying(scroll) {
    feed.querySelectorAll('.row.on').forEach((e) => e.classList.remove('on'));
    if (S.view.mode !== 'clip') return;
    let el = feed.querySelector(`.row[data-play="${S.view.clip.key}"]`);
    if (!el) return;
    if (el.closest('.kids')?.hidden) el = el.closest('.burst').querySelector('.grp');
    el.classList.add('on');
    if (scroll) {
      const top = feedTop(el), pad = 76; // below the sticky day header
      if (top - pad < feed.scrollTop) feed.scrollTo({ top: top - pad, behavior: 'smooth' });
      else if (top + el.offsetHeight > feed.scrollTop + feed.clientHeight) feed.scrollTo({ top: top + el.offsetHeight - feed.clientHeight + 8, behavior: 'smooth' });
    }
  }
  const feedTop = (el) => el.getBoundingClientRect().top - feed.getBoundingClientRect().top + feed.scrollTop;
  function scrollToRow(el) {
    feed.scrollTo({ top: feedTop(el) - (feed.clientHeight - el.offsetHeight) / 2, behavior: 'smooth' });
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
  }
  function jumpToDay(i) {
    const el = feed.querySelector(`section[data-day="${i}"]`)
      || [...feed.querySelectorAll('.quiet')].find((q) => +q.dataset.to <= i && i <= +q.dataset.from || +q.dataset.from <= i && i <= +q.dataset.to);
    if (el) { feed.scrollTop = feedTop(el); if (el.classList.contains('quiet')) scrollToRow(el); }
  }

  feed.addEventListener('click', (e) => {
    const rib = e.target.closest('.rib');
    if (rib) {
      const r = rib.getBoundingClientRect(), t = +rib.dataset.a + (e.clientX - r.left) / r.width * DAYMS;
      const rows = [...rib.closest('section').querySelectorAll('.row:not(.kids .row)')];
      if (rows.length) scrollToRow(rows.reduce((b, x) => Math.abs(x.dataset.t - t) < Math.abs(b.dataset.t - t) ? x : b));
      return;
    }
    const u = e.target.closest('[data-untagged]');
    if (u) { // stay on the day the user tapped, rather than jumping to the top
      S.sched = !S.sched;
      rebuild(+(u.dataset.day ?? u.closest('section')?.dataset.day ?? 0));
      return;
    }
    const b = e.target.closest('[data-burst]');
    if (b) {
      const w = b.closest('.burst'), k = w.dataset.key, kids = w.querySelector('.kids');
      kids.hidden = !kids.hidden; w.classList.toggle('open', !kids.hidden);
      kids.hidden ? S.open.delete(k) : S.open.add(k);
      markPlaying(); return;
    }
    const p = e.target.closest('[data-play]');
    if (p) playClip(S.byId.get(p.dataset.play));
  });

  // ---- player
  const grid = $('#grid'), single = $('#single'), vid = $('#vid'), liveImg = $('#liveimg'), seekEl = $('#seek');
  $('#bgrid').innerHTML = svg('grid');
  $('#bprev').innerHTML = svg('prev');
  $('#bnext').innerHTML = svg('next');
  const picture = (ch) => { const e = cam[ch].entity; return e && host.hass.states[e]?.attributes.entity_picture; };

  async function playClip(c) {
    if (!c) return;
    const my = ++S.playSeq;
    S.view = { mode: 'clip', clip: c, t: 0, status: 'Loading…' };
    vid.removeAttribute('src'); vid.load();
    draw(); markPlaying(true);
    try {
      const { url } = await api('reolink/play?id=' + encodeURIComponent(c.id));
      if (my !== S.playSeq) return;
      vid.src = url;
      vid.playbackRate = S.speed;
      await vid.play();
    } catch (e) {
      if (my !== S.playSeq) return;
      S.view.status = "Couldn't load this recording";
      toast(`Couldn't load this recording (${errText(e)})`);
    }
    draw();
  }
  function goLive(ch) { ++S.playSeq; vid.pause(); vid.removeAttribute('src'); vid.load(); S.view = { mode: 'live', cam: ch }; draw(); markPlaying(); }
  function showGrid() { ++S.playSeq; vid.pause(); vid.removeAttribute('src'); vid.load(); S.view = { mode: 'grid' }; draw(); markPlaying(); }
  function step(dir) {
    const v = S.view;
    if (v.mode === 'live') { const mine = S.all.filter((c) => c.cam === v.cam); return playClip(mine[mine.length - 1]); }
    const st = v.clip.start;
    const c = dir > 0 ? S.all.find((x) => x.start > st) : S.all.findLast((x) => x.start < st);
    if (c) playClip(c);
  }
  const skipBy = () => len(S.view.clip) > 600 ? 300 : 10;
  // A long event is still downloading from the NVR (~1 min per hour of video): only what's
  // arrived can be seeked to.
  function seek(t) {
    const r = vid.seekable, max = r.length ? r.end(r.length - 1) : 0;
    if (t > max + 1) toast(`Still loading: ${clock(max)} of ${clock(len(S.view.clip))} so far`);
    vid.currentTime = Math.min(Math.max(0, t), max);
    draw();
  }

  vid.addEventListener('timeupdate', () => { if (S.view.mode === 'clip') { S.view.t = vid.currentTime; draw(); } });
  for (const ev of ['playing', 'pause', 'ended', 'waiting']) vid.addEventListener(ev, () => { if (S.view.mode === 'clip') { S.view.status = ev === 'waiting' ? 'Loading…' : ''; draw(); } });
  vid.addEventListener('error', () => { if (S.view.mode === 'clip' && vid.getAttribute('src')) { S.view.status = "Couldn't play this recording"; draw(); } });
  $('#bplay').onclick = () => { if (S.view.mode !== 'clip') return; vid.paused ? vid.play() : vid.pause(); };
  $('#bback').onclick = () => seek(vid.currentTime - skipBy());
  $('#bfwd').onclick = () => seek(vid.currentTime + skipBy());
  $('#bprev').onclick = () => { if (S.view.mode === 'clip' && vid.currentTime > 3) seek(0); else step(-1); };
  $('#bnext').onclick = () => step(1);
  $('#blive').onclick = () => goLive(S.view.clip.cam);
  $('#bgrid').onclick = showGrid;
  $('#bspeed').onclick = () => { S.speed = { 1: 2, 2: 4, 4: 1 }[S.speed]; vid.playbackRate = S.speed; draw(); };
  seekEl.addEventListener('input', () => { S.seeking = true; seek(+seekEl.value); });
  seekEl.addEventListener('change', () => { S.seeking = false; });
  $('#video').addEventListener('click', () => $('#bplay').click());

  const setText = (el, s) => { if (el.textContent !== s) el.textContent = s; };
  function draw() {
    const v = S.view;
    grid.hidden = v.mode !== 'grid'; single.hidden = v.mode === 'grid';
    if (v.mode === 'grid') return drawGrid();
    const isClip = v.mode === 'clip', c = v.clip, ch = isClip ? c.cam : v.cam;
    vid.hidden = !isClip;
    liveImg.hidden = isClip;
    if (!isClip && liveImg.dataset.cam !== String(ch)) { liveImg.dataset.cam = ch; liveImg.removeAttribute('src'); delete liveImg.dataset.busy; loadPic(liveImg, picture(ch)); }
    setText($('#cap'), isClip ? (v.status || '') : picture(ch) ? '' : 'No live view for this camera');
    setText($('#vcam'), isClip ? `${cam[ch].name} · ${kind(c.tags, c.sched)} · ${when(c.start)}` : cam[ch].name);
    $('#vbadge').className = isClip ? '' : 'badge';
    setText($('#vbadge'), isClip ? hms(c.start + v.t * 1000) : 'LIVE');
    $('#bspeed').hidden = $('#blive').hidden = !isClip;
    $('#bgrid').hidden = isClip || S.cam !== 'all';
    setText($('#bspeed'), S.speed + '×');
    const L = isClip ? len(c) : 1;
    seekEl.disabled = !isClip; seekEl.max = L;
    if (!S.seeking) seekEl.value = isClip ? v.t : 1;
    setText($('#tel'), isClip ? clock(v.t) : '');
    setText($('#ttot'), isClip ? clock(L) : 'Live');
    const playing = isClip && !vid.paused;
    if ($('#bplay').dataset.s !== String(playing)) { $('#bplay').dataset.s = playing; $('#bplay').innerHTML = svg(playing ? 'pause' : 'play'); }
    $('#bplay').disabled = !isClip;
    const sk = isClip ? skipBy() : 10, u = sk >= 60 ? `${sk / 60}m` : `${sk}s`;
    setText($('#bback'), '−' + u); setText($('#bfwd'), '+' + u);
    $('#bback').disabled = $('#bfwd').disabled = !isClip;
    $('#bprev').setAttribute('aria-label', isClip ? 'Previous clip' : 'Latest recording');
    $('#bnext').disabled = !isClip;
  }
  function drawGrid() { for (const t of grid.children) { const img = t.querySelector('img'); if (!img.getAttribute('src')) loadPic(img, picture(+t.dataset.cam)); } }
  // Camera pictures: entity_picture is a fresh snapshot each fetch; its token rotates every 5 min.
  function loadPic(img, p) {
    if (!p || Date.now() - (img.dataset.busy || 0) < 10000) return;
    img.dataset.busy = Date.now();
    img.src = p + (p.includes('?') ? '&' : '?') + 't=' + Date.now();
  }
  const done = (e) => { if (e.target.tagName === 'IMG') delete e.target.dataset.busy; };
  for (const ev of ['load', 'error']) { grid.addEventListener(ev, done, true); liveImg.addEventListener(ev, done); }
  function tickPictures() {
    if (S.view.mode === 'grid') for (const t of grid.children) loadPic(t.querySelector('img'), picture(+t.dataset.cam));
    if (S.view.mode === 'live') loadPic(liveImg, picture(S.view.cam));
  }

  // ---- cameras & filters
  const camsEl = $('#cams');
  function selectCam(ch) {
    const changed = ch !== S.cam;
    S.cam = ch;
    camsEl.querySelectorAll('.chip').forEach((b) => b.setAttribute('aria-pressed', b.dataset.cam === String(ch)));
    if (changed) rebuild();
    if (ch === 'all') showGrid(); else goLive(ch);
  }
  camsEl.addEventListener('click', (e) => { const b = e.target.closest('[data-cam]'); if (b) selectCam(b.dataset.cam === 'all' ? 'all' : +b.dataset.cam); });
  grid.addEventListener('click', (e) => { const t = e.target.closest('[data-cam]'); if (t) selectCam(+t.dataset.cam); });
  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-tag]'); if (!b) return;
    S.tag = b.dataset.tag;
    $('#filters').querySelectorAll('[data-tag]').forEach((x) => x.setAttribute('aria-pressed', x === b));
    rebuild();
  });
  const dateEl = $('#date'), bdate = $('#bdate');
  bdate.insertAdjacentHTML('afterbegin', svg('cal'));
  root.querySelector('#filters [data-tag=doorbell]').insertAdjacentHTML('afterbegin', svg('doorbell'));
  dateEl.addEventListener('change', async () => {
    if (!dateEl.value) return;
    const [y, m, d] = dateEl.value.split('-').map(Number);
    const i = Math.min(S.days, Math.max(0, dayIndex(new Date(y, m - 1, d).getTime())));
    await renderTo(i);
    jumpToDay(i);
  });

  let toastT;
  function toast(s) { const t = $('#toast'); t.textContent = s; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2400); }

  // ---- start: today first, then the cameras and how far back the NVR goes
  (async () => {
    $('#cap').textContent = '';
    more.className = 'end'; more.textContent = 'Loading…';
    let j;
    try { j = await fetchDays(0, 0); } catch (e) { more.textContent = `Couldn't reach the cameras (${errText(e)}).`; return; }
    const ents = host.hass.entities || {}, devs = host.hass.devices || {};
    for (const c of j.cameras) {
      const name = c.name;
      const found = Object.keys(host.hass.states).filter((e) => e.startsWith('camera.') && ents[e]?.platform === 'reolink' && devs[ents[e]?.device_id]?.name === name);
      cam[c.ch] = {
        name, short: config.names?.[c.ch] ?? name.replace(' and ', ' & ').replace(/ space$/, ''),
        entity: config.entities?.[c.ch] ?? (found.find((e) => e.endsWith('_fluent')) || found[0]),
      };
    }
    S.cams = j.cameras;
    const oldest = Math.min(...j.cameras.map((c) => c.oldest ? new Date(c.oldest + 'T00:00').getTime() : Date.now()));
    S.oldest = oldest; S.days = dayIndex(oldest); S.t0 = dayStart(0);
    for (const r of j.recordings) S.recs.set(r.id, toRec(r));
    S.loaded = 0;
    camsEl.innerHTML = `<button class="chip" data-cam="all" aria-pressed="true">All</button>`
      + S.cams.map((c) => `<button class="chip" data-cam="${c.ch}" aria-label="${esc(cam[c.ch].name)}" style="box-shadow:inset 0 -3px ${camDot(c.ch)}">${esc(cam[c.ch].short)}</button>`).join('');
    grid.innerHTML = S.cams.map((c) => `<button class="tile" data-cam="${c.ch}" aria-label="${esc(cam[c.ch].name)} live"><img alt=""><span class="nm">${esc(cam[c.ch].name)}</span><span class="lv">LIVE</span></button>`).join('');
    dateEl.min = iso(oldest); dateEl.max = iso(Date.now());
    moreIO.observe(more);
    await rebuild();
    draw();
    let ticks = 0, timer = null;
    const tick = () => {
      if (document.hidden) return;
      tickPictures();
      if (dayStart(0) !== S.t0) { // midnight: yesterday is index 1 now
        S.t0 = dayStart(0); S.days = dayIndex(S.oldest); S.loaded++; S.todaySig = null; dateEl.max = iso(Date.now());
        rebuild().then(refreshToday).catch(() => {});
      } else if (++ticks % 15 === 0) refreshToday().catch(() => {}); // every 30 s
    };
    host._timers = { start() { timer ??= setInterval(tick, 2000); }, stop() { clearInterval(timer); timer = null; } };
    if (host.isConnected) host._timers.start();
  })();
}

customElements.define('camera-card', CameraCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: 'camera-card', name: 'Camera card', description: 'Recordings and live view for the Reolink NVR' });
console.info(`camera-card ${VERSION}`);
