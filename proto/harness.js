// Shared by every prototype: mock cameras and recordings, a fake clock, and a tap log.
// Captions stand in for video. Show them only where the video would be.
(function () {
  const MIN = 6e4, H = 36e5, DAY = 864e5;
  const q = new URLSearchParams(location.search);
  const SEED = +(q.get('seed') || window.PROTO_SEED || 1);
  const V = (SEED - 1) % 3; // which set of planted answers
  const KEY = `proto:${location.pathname}:${q.get('run') || 'default'}`;

  let st = null;
  try { st = JSON.parse(localStorage.getItem(KEY)); } catch {}
  if (!st || st.seed !== SEED) {
    const d = new Date(); d.setHours(9, 40, 0, 0);
    st = { seed: SEED, real0: Date.now(), fake0: d.getTime(), log: [] };
  }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch {} };
  // The clock starts at 9:40 this morning and keeps running across reloads of the same run.
  const now = () => st.fake0 + (Date.now() - st.real0);
  const T0 = st.fake0;
  const MIDNIGHT = new Date(T0).setHours(0, 0, 0, 0);
  // Wall-clock arithmetic, so a DST change doesn't shift planted times.
  const at = (daysAgo, hour) => { const d = new Date(MIDNIGHT); d.setDate(d.getDate() - daysAgo); d.setHours(0, 0, 0, 0); d.setSeconds(hour * 3600); return d.getTime(); };

  const log = (type, detail = {}) => { st.log.push({ t: Date.now(), type, ...detail }); save(); };
  if (typeof document !== 'undefined') {
    log('load', { task: q.get('task'), w: innerWidth, h: innerHeight });
    addEventListener('pointerdown', (e) => {
      const el = e.target.closest?.('button,a,input,select,[role],[data-log]') || e.target;
      const label = (el.getAttribute?.('aria-label') || el.dataset?.log || el.textContent || '').trim().slice(0, 40);
      log('tap', { x: Math.round(e.clientX), y: Math.round(e.clientY), el: el.tagName?.toLowerCase(), label });
    }, true);
  }

  // mulberry32
  let a = SEED * 7919;
  const r = () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const between = (lo, hi) => lo + r() * (hi - lo);
  const pick = (xs) => xs[Math.floor(r() * xs.length)];
  const cap = (s) => s[0].toUpperCase() + s.slice(1);

  const CAMERAS = [
    { id: 'garage', name: 'Garage', hue: 30 },
    { id: 'attic', name: 'Attic', hue: 280 },
    { id: 'backyard', name: 'Backyard', hue: 120 },
    { id: 'doorbell', name: 'Doorbell', hue: 205 },
    { id: 'crawl', name: 'Crawl space', hue: 0 },
    { id: 'gate', name: 'Gate & Shed', hue: 170 },
  ];

  const CLOTHES = ['a blue coat', 'a black hoodie', 'a white T-shirt', 'a brown jacket', 'a striped sweater', 'a navy fleece', 'a grey suit', 'a purple scarf', 'a denim jacket', 'a tan trench coat'];
  const P = () => `Person in ${pick(CLOTHES)}`;
  // rate = clips a day; kinds = [tag, weight, captions]; '' tag = plain motion.
  const BG = {
    garage: { rate: 18, kinds: [
      ['person', 4, [() => `${P()} gets into the car`, () => `${P()} carries grocery bags in from the car`, () => `${P()} takes a bike off the wall rack`, () => `${P()} rummages in the chest freezer`]],
      ['vehicle', 3, ['Car backs out of the garage', 'Car pulls into the garage']],
      ['', 3, ['Garage light switches on', 'Garage door opens', 'Garage door closes']]] },
    attic: { rate: 4, kinds: [
      ['', 8, ['Dust drifts past the lens', 'Sunlight shifts across the rafters', 'Insulation flutters by the vent']],
      ['animal', 1, ['Moth flutters near the lens', 'Squirrel peeks in at the vent']],
      ['person', 1, [() => `${P()} carries a box up into the attic`]]] },
    backyard: { rate: 30, burst: [1.5, '', ['Tree branches sway in the wind', 'Leaves blow across the deck']], kinds: [
      ['animal', 5, ['Squirrel runs along the fence', 'Bird lands on the feeder', 'Cat crosses the lawn', 'Crows hop around the lawn', 'Rabbit nibbles the grass']],
      ['person', 2, [() => `${P()} waters the vegetable beds`, () => `${P()} takes out the recycling`, 'Kids play on the lawn']],
      ['', 3, ['Tree branches sway in the wind', 'Shadow of a cloud passes over the lawn', 'Leaves blow across the deck']]] },
    doorbell: { rate: 40, burst: [0.8, 'person', ['Group of kids walks past on the sidewalk']], kinds: [
      ['person', 6, [() => `${P()} walks past on the sidewalk`, () => `${P()} walks a dog past the house`, () => `Jogger in ${pick(CLOTHES)} runs past`, 'Mail carrier puts letters in the mailbox and leaves']],
      ['vehicle', 3, ['Car drives past', 'Delivery van parks across the street', 'Bus passes']],
      ['', 1, ['Headlights sweep across the porch', 'Leaves blow across the steps']]] },
    crawl: { rate: 1.5, kinds: [
      ['', 1, ['Sump pump cycles on', 'Water drips from a pipe', 'Spider walks across the lens']]] },
    gate: { rate: 28, burst: [0.6, '', ['Gate swings in the wind']], kinds: [
      ['person', 5, [() => `${P()} walks in through the gate`, () => `${P()} walks out through the gate`, () => `${P()} gets tools from the shed`, () => `${P()} takes a bin to the curb`]],
      ['vehicle', 2, ['Car passes behind the fence', 'Truck passes on the street']],
      ['animal', 1, ['Cat walks along the fence', 'Raccoon walks past the shed']],
      ['', 2, ['Wind rattles the trash can lids', 'Headlights sweep across the shed']]] },
  };
  const AMBIENT = {
    garage: ['The garage is quiet; the door is closed', 'Car parked; garage lights off'],
    attic: ['The attic is dark and still'],
    backyard: ['The lawn is empty; trees are still', 'A bird sits on the fence'],
    doorbell: ['The porch is empty; the street is quiet', 'A car drives by in the distance'],
    crawl: ['The crawl space is dark; nothing moving'],
    gate: ['The gate is closed; the shed door is shut', 'The path by the shed is empty'],
  };

  const planted = [], bg = [];
  let nid = 0;
  const clip = (list, cam, start, secs, tag, scenes, extra) => {
    const c = { id: 'c' + nid++, cam, start, end: start + secs * 1000, tags: tag ? [tag] : [],
      scenes: typeof scenes === 'string' ? [[0, scenes]] : scenes, hue: Math.floor(r() * 360), ...extra };
    list.push(c); return c;
  };
  const P_ = (...args) => clip(planted, ...args);
  const text = (t) => (typeof t === 'function' ? t() : t);

  // --- Planted answers. Each seed gets its own, so answers don't carry between prototypes.
  const key = { seed: SEED, tasks: [] };
  const hm = (t) => new Date(t).toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

  // 1. Noise outside, happening now.
  const U1 = [
    { cam: 'backyard', lead: 'Something clatters on the deck', s: [[0, 'A raccoon knocks a planter off the deck rail'], [20, 'The raccoon digs through the spilled soil']], live: 'A raccoon is still on the deck, digging in the spilled planter soil', ans: 'Backyard: a raccoon knocked a planter off the deck rail; still there' },
    { cam: 'gate', lead: 'The side gate rattles', s: [[0, 'A deer pushes against the side gate and rattles it'], [20, 'The deer squeezes through and starts eating the hedge']], live: 'A deer is still in the yard, eating the hedge next to the shed', ans: 'Gate & Shed: a deer pushed through the gate; still eating the hedge' },
    { cam: 'doorbell', lead: 'Bikes clatter on the sidewalk', s: [[0, 'Two cyclists collide on the sidewalk; one bike crashes down'], [20, 'The two riders argue over a bent wheel']], live: 'Two cyclists are still on the sidewalk, arguing over a bent wheel', ans: 'Doorbell: two cyclists collided on the sidewalk; still there arguing' },
  ][V];
  const u1start = T0 - between(2, 4) * MIN;
  for (let i = 3; i >= 1; i--) P_(U1.cam, u1start - i * between(20, 30) * 1000, between(4, 8), '', U1.lead);
  P_(U1.cam, u1start, 40 * 60, U1.cam === 'doorbell' ? 'person' : 'animal', U1.s, { live: U1.live });
  key.tasks.push({ uc: 1, task: 'You just heard a noise outside. What was it, and is it still going on?', answer: U1.ans });

  // 2. Trash cans knocked over overnight.
  const U2 = [
    ['raccoon', [[0, 'A raccoon climbs onto the trash cans by the shed'], [12, 'The cans tip over and the raccoon drags out a bag']]],
    ['black bear', [[0, 'A black bear walks up to the trash cans by the shed'], [12, 'The bear shoves the cans over and paws through the garbage']]],
    ['large brown dog', [[0, 'A large brown dog noses at the trash cans by the shed'], [12, 'The dog jumps up, the cans fall over, and it pulls out a bag']]],
  ][V];
  const u2 = at(0, between(1.5, 3.5));
  P_('gate', u2, 40, 'animal', U2[1]);
  P_('gate', u2 - between(50, 80) * MIN, 12, 'animal', 'A raccoon walks past the trash cans without stopping');
  P_('gate', u2 + between(40, 70) * MIN, 15, '', 'Wind rattles the trash can lids');
  P_('gate', u2 - between(100, 120) * MIN, 10, '', 'Wind rattles the trash can lids');
  P_('gate', u2 + between(90, 110) * MIN, 9, 'animal', 'Cat walks along the fence');
  key.tasks.push({ uc: 2, task: 'Something knocked the trash cans over last night. They are kept by the shed. What happened, and when?', answer: `A ${U2[0]} tipped the cans over, ${hm(u2)} (Gate & Shed)` });

  // 3. Who rang the doorbell this morning.
  const VIS = ['a woman in a green raincoat with a clipboard, short grey hair and glasses',
    'a man in an orange hi-vis vest with a beard, holding a small parcel',
    'a teenager in a blue hoodie with a golden retriever on a leash'];
  const u3 = at(0, between(7.4, 8.9));
  const ring = P_('doorbell', u3, 38, 'person', [[0, 'Someone walks up the front path'], [8, `They ring the doorbell: ${VIS[V]}`], [18, 'Their face is clearly visible as they wait at the door'], [30, 'They tuck a note into the door and walk away']]);
  P_('doorbell', u3 - between(30, 60) * MIN, 14, 'person', `${cap(VIS[(V + 1) % 3])} walks past on the sidewalk`);
  P_('doorbell', u3 + between(20, 40) * MIN, 22, 'person', [[0, `${cap(VIS[(V + 2) % 3])} walks up to the porch`], [10, 'They leave a package by the door without ringing']]);
  key.tasks.push({ uc: 3, task: 'Who rang the doorbell this morning? Describe them.', answer: `${cap(VIS[V])}, ${hm(u3)}` });
  key.tasks.push({ uc: 'keep', task: 'Save the recording of that doorbell ring off the phone.', answer: `download of ${ring.id}` });

  // 4. What's going on in <place> right now.
  const U4 = [
    { cam: 'garage', place: 'the garage', live: ['The garage door is wide open; a red kayak sits on sawhorses', 'The garage door is wide open; a bike lies on the floor beside the red kayak'], ans: 'Garage door wide open, red kayak on sawhorses, nobody there' },
    { cam: 'attic', place: 'the attic', live: ['The attic light is on; a box lies tipped over by the stairs', 'The attic light is on; a moth circles the bulb above the tipped-over box'], ans: 'Attic light on, a box tipped over by the stairs' },
    { cam: 'backyard', place: 'the backyard', live: ['The sprinkler is running across the lawn; two crows hop in the spray', "The sprinkler is running; a kid's soccer ball sits in the flower bed"], ans: 'Sprinkler running on the lawn (crows / soccer ball)' },
  ][V];
  AMBIENT[U4.cam] = U4.live;
  key.tasks.push({ uc: 4, task: `What's going on in ${U4.place} right now?`, answer: U4.ans });

  // 5. Rats in the crawl space, weeks ago.
  const CHEWED = ['the pipe insulation', 'the dryer vent hose', 'a sprinkler line'][V];
  const u5 = at([20, 37, 28][V] + Math.floor(between(0, 4)), between(1, 5));
  P_('crawl', u5, 40, 'animal', [[0, 'A rat runs along a floor joist'], [10, `The rat stops and chews on ${CHEWED}`], [28, 'The rat pulls a strip loose and runs off']]);
  P_('crawl', u5 + Math.floor(between(5, 8)) * DAY + between(-2, 2) * H, 10, 'animal', 'A rat scurries along the beam and disappears');
  P_('crawl', u5 - Math.floor(between(4, 9)) * DAY + 14 * H, 300, 'person', [[0, 'Person with a flashlight crawls in'], [60, 'They check the water heater and leave']]);
  key.tasks.push({ uc: 5, task: `Rats chewed through ${CHEWED} in the crawl space. When did they do that? You only just noticed, so it could have been a month or more ago.`, answer: hm(u5) });

  // 6. When did <person> leave?
  const WHO = [['Jordan', 'a red jacket and a grey backpack', 'a red jacket and carrying a white tote bag'],
    ['Riley', 'a yellow raincoat and carrying a black umbrella', 'a yellow raincoat, pushing a stroller'],
    ['Casey', 'a green beanie and carrying a skateboard', 'a green beanie, walking a small dog']][V];
  const u6 = at(0, [7.6, 8.9, 8.2][V] + between(0, 0.3));
  P_('gate', u6, 16, 'person', [[0, `Person in ${WHO[1]} walks out through the gate`], [9, 'They turn left down the street']]);
  P_('gate', u6 + (u6 < at(0, 8.4) ? 1 : -1) * between(25, 40) * MIN, 14, 'person', `Person in ${WHO[2]} walks out through the gate`);
  P_('gate', at(1, between(7.8, 9)), 15, 'person', `Person in ${WHO[1]} walks out through the gate`);
  P_('gate', at(1, between(17, 19)), 15, 'person', `Person in ${WHO[1]} walks in through the gate`);
  P_('doorbell', at(0, between(6.6, 7.1)), 20, 'person', `Person in ${WHO[1]} picks up a package from the porch and goes back inside`);
  key.tasks.push({ uc: 6, task: `When did ${WHO[0]} leave this morning? ${WHO[0]} was wearing ${WHO[1]}.`, answer: `${hm(u6)} via the gate` });

  // Long recordings: hours, and across midnight / days.
  P_('gate', at(6, 23.15), 2.9 * 3600, '', [[0, 'The gate swings open and shut in the wind'], [3600, 'Still swinging; a bin has rolled onto the path'], [7200, 'The gate is still swinging']]);
  P_('attic', at(12, 13), 6 * 3600, '', [[0, 'The attic light was left on; dust drifts in the beam'], [3 * 3600, 'Light still on; nothing else moving']]);
  P_('crawl', at(5, 22), 55 * 3600, '', [[0, 'The IR light flickers; recording runs continuously'], [24 * 3600, 'Still flickering; nothing moving'], [48 * 3600, 'Still flickering']]);
  P_('backyard', at(2, 16.2), 38 * 60, 'person', [[0, `${P()} mows the lawn`], [20 * 60, 'Still mowing, now along the fence']]);

  // --- Background activity, 45 days back to 3 hours past the start of the run.
  const dur = () => { const x = r(); return x < 0.7 ? between(8, 45) : x < 0.95 ? between(45, 240) : between(240, 1200); };
  const hourWeight = (tag, h) => tag === 'person' || tag === 'vehicle' ? (h >= 7 && h < 22 ? 1 : 0.1) : tag === 'animal' ? (h >= 19 || h < 7 ? 1 : 0.5) : 1;
  const sampleTime = (d0, tag) => { for (;;) { const t = d0 + r() * DAY; if (r() < hourWeight(tag, new Date(t).getHours())) return t; } };
  for (let d = 45; d >= 0; d--) {
    const d0 = at(d, 0);
    for (const cam of CAMERAS) {
      const p = BG[cam.id];
      const total = p.kinds.reduce((s, k) => s + k[1], 0);
      const n = Math.round(p.rate * between(0.6, 1.4));
      for (let i = 0; i < n; i++) {
        let x = r() * total, k = p.kinds[0];
        for (const kk of p.kinds) { if ((x -= kk[1]) < 0) { k = kk; break; } }
        clip(bg, cam.id, sampleTime(d0, k[0]), dur(), k[0], text(pick(k[2])));
      }
      if (p.burst && r() < p.burst[0]) {
        let t = sampleTime(d0, p.burst[1]);
        const cnt = 6 + Math.floor(r() * 10);
        for (let i = 0; i < cnt; i++) { const s = between(4, 20); clip(bg, cam.id, t, s, p.burst[1], text(pick(p.burst[2]))); t += (s + between(3, 40)) * 1000; }
      }
    }
  }

  const byCam = {};
  for (const cam of CAMERAS) {
    const mine = planted.filter((c) => c.cam === cam.id);
    const kept = [...mine];
    let lastEnd = 0;
    for (const c of bg.filter((c) => c.cam === cam.id && c.start < T0 + 3 * H).sort((x, y) => x.start - y.start)) {
      if (c.start < lastEnd + 2000) continue;
      if (mine.some((m) => c.start < m.end + 5000 && c.end > m.start - 5000)) continue;
      kept.push(c); lastEnd = c.end;
    }
    byCam[cam.id] = kept.sort((x, y) => x.start - y.start);
  }

  const clips = (camId, from = -Infinity, to = Infinity) => {
    const t = now();
    return byCam[camId].filter((c) => c.start <= t && c.start < to && c.end > from)
      .map((c) => ({ id: c.id, cam: c.cam, start: c.start, end: Math.min(c.end, t), tags: c.tags, ongoing: c.end > t }));
  };
  const find = (id) => { for (const k in byCam) { const c = byCam[k].find((x) => x.id === id); if (c) return c; } };

  // What the "video" shows: a fixed colour per recording, and a caption that changes over time.
  const frame = (source, sec = 0) => {
    if (source.live) {
      const t = now();
      const cam = CAMERAS.find((c) => c.id === source.live);
      const cur = byCam[cam.id].find((c) => c.start <= t && c.end > t);
      let caption;
      if (cur) caption = cur.live || [...cur.scenes].reverse().find((s) => s[0] <= (t - cur.start) / 1000)[1];
      else { const xs = AMBIENT[cam.id]; caption = xs[Math.floor(t / 30000) % xs.length]; }
      return { color: `hsl(${cam.hue} 30% 22%)`, caption };
    }
    const c = find(source.id);
    return { color: `hsl(${c.hue} 42% 38%)`, caption: [...c.scenes].reverse().find((s) => s[0] <= sec)[1] };
  };

  // Shared in-page calendar: native date pickers don't show up in testers' screenshots.
  const dayPicker = (onPick) => {
    const host = document.getElementById('phone') || document.getElementById('app');
    const today = new Date(now()); today.setHours(0, 0, 0, 0);
    const first = new Date(today); first.setDate(first.getDate() - 45);
    let html = '<div style="background:#fff;color:#111;border-radius:12px;padding:12px;width:300px;font:14px system-ui"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b>Pick a day</b><button data-x aria-label="Close" style="border:0;background:none;font-size:18px;cursor:pointer">✕</button></div><div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;text-align:center">';
    for (const d of 'SMTWTFS') html += `<span style="color:#888;font-size:11px">${d}</span>`;
    for (let i = 0; i < first.getDay(); i++) html += '<span></span>';
    for (const d = new Date(first); d <= today; d.setDate(d.getDate() + 1)) {
      const lbl = d.getDate() === 1 || +d === +first ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : d.getDate();
      html += `<button data-d="${+d}" style="border:0;border-radius:6px;background:${+d === +today ? '#cfe0ff' : '#eef1f5'};padding:7px 0;font-size:12px;cursor:pointer">${lbl}</button>`;
    }
    const box = document.createElement('div');
    box.style.cssText = 'position:absolute;inset:0;z-index:50;background:#0008;display:grid;place-items:center';
    box.innerHTML = html + '</div></div>';
    box.onclick = (e) => { const b = e.target.closest('[data-d]'); if (b) { box.remove(); onPick(+b.dataset.d); } else if (e.target.closest('[data-x]') || e.target === box) box.remove(); };
    host.style.position = 'relative'; host.appendChild(box);
  };

  window.PROTO = { cameras: CAMERAS, now, clips, frame, log, dayPicker, task: q.get('task') };
  if (typeof document === 'undefined') window.PROTO.answerKey = key; // only for bin/answers
})();
