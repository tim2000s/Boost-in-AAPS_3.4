// Exercise the simulator's unit toggle in a headless DOM.
//
// Two separate claims are under test and they need different tolerances.
//
// The first is exact: the display setting must not enter the maths at all. That is checked by
// running calcAll over one fixed set of mg/dL inputs under both settings and requiring the results
// to be bit-identical.
//
// The second is not exact and cannot be: a mmol slider shows a coarser grid than a mg/dL one, so a
// value written in one unit and read back in the other lands on the nearest displayable step. What
// is checked there is that the error stays within that step rather than accumulating.
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2];
const MMOL = 18.0182;

// jsdom has no canvas. The stub has to be in place before the page's scripts run, since the last
// thing the page does on load is draw.
const stubCanvas = w => {
  w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
    get: (t, k) => {
      if (k === 'measureText') return () => ({ width: 10 });
      if (k === 'createLinearGradient' || k === 'createRadialGradient') {
        return () => ({ addColorStop() {} });
      }
      if (k === 'canvas') return { width: 600, height: 300, style: {} };
      return typeof k === 'string' ? () => {} : undefined;
    },
    set: () => true,
  });
};

const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://example.invalid/',
  beforeParse: stubCanvas,
});
const w = dom.window;

let fails = 0;
const check = (ok, msg) => { if (!ok) { fails++; console.log('  FAIL ' + msg); } };

const BG_IDS = ['profIsf', 'bg', 'delta', 'shortAvgDelta', 'longAvgDelta', 'target', 'recentLowBg',
  'normTarget', 'bgCap', 'nightOffset', 'tempTargetBg'];
const flat = o => JSON.stringify(o);

// BG_SLIDERS is a top-level const, so it lives in the script's lexical scope rather than on window.
// eval reaches it from the page's own global scope.
const STEPS = w.eval('Object.fromEntries(BG_SLIDERS.map(sd => [sd.id, sd.stepMmol]))');

// ── 1. the maths never sees the display setting ──────────────────────────────
// One fixed input object, evaluated under both settings. Any difference here would mean a unit
// conversion had leaked into the calculation, which is the failure the whole design exists to rule
// out. This one is exact.
const fixed = w.getInputs();
const mgdlResult = flat(w.calcAll(fixed));
w.setUnit('mmol');
const mmolResult = flat(w.calcAll(fixed));
check(mgdlResult === mmolResult, 'calcAll on identical inputs differs between display settings');
w.setUnit('mgdl');

// ── 2. a round trip stays within the display grid ────────────────────────────
const snap = () => Object.fromEntries(BG_IDS.map(id => [id, w.getBgSliderMgdl(id)]));
const start = snap();
w.setUnit('mmol');
const shown = snap();
w.setUnit('mgdl');
const back = snap();
BG_IDS.forEach(id => {
  check(Math.abs(start[id] - back[id]) < 1e-9,
    `${id} did not return to its starting value: ${start[id]} -> ${back[id]}`);
  // Half of the step the control offers, which is the finest the display can represent.
  check(Math.abs(start[id] - shown[id]) <= STEPS[id] / 2 * MMOL + 1e-6,
    `${id} reads back as ${shown[id].toFixed(3)} mg/dL while shown in mmol, from ${start[id]}`);
});

// Repeating the switch must not compound the error.
const before = snap();
for (let i = 0; i < 20; i++) w.setUnit(i % 2 ? 'mgdl' : 'mmol');
w.setUnit('mgdl');
BG_IDS.forEach(id => check(Math.abs(before[id] - w.getBgSliderMgdl(id)) < 1e-9,
  `${id} drifted over twenty switches: ${before[id]} -> ${w.getBgSliderMgdl(id)}`));

// ── 3. the display is actually converted ─────────────────────────────────────
w.setUnit('mmol');
const bgEl = w.document.getElementById('s-bg');
// Half a step, since the value is written onto the 0.1 mmol grid the control offers.
check(Math.abs(parseFloat(bgEl.value) - 140 / MMOL) <= 0.05 + 1e-9,
  `BG slider shows ${bgEl.value} in mmol, expected about 7.8`);
check(parseFloat(bgEl.max) < 20, `BG slider max is ${bgEl.max} in mmol, expected about 19.4`);
check(w.document.getElementById('v-bg').textContent.includes('mmol/L'),
  'BG readout: ' + w.document.getElementById('v-bg').textContent);
check(w.document.getElementById('hints-bg').textContent.includes('mmol/L'),
  'BG hint: ' + w.document.getElementById('hints-bg').textContent);
check(w.document.getElementById('hints-recentLowBg').textContent.includes('(recent hypo)'),
  'descriptive hint note lost: ' + w.document.getElementById('hints-recentLowBg').textContent);
check(w.document.getElementById('hints-delta').textContent.includes('(rising)'),
  'delta hint note lost: ' + w.document.getElementById('hints-delta').textContent);
check(w.document.querySelector('.isf-unit-label').textContent === 'mmol/L per U',
  'ISF panel unit label: ' + w.document.querySelector('.isf-unit-label').textContent);
check(w.document.getElementById('unit-btn-mmol').classList.contains('active'),
  'mmol button not marked active');

// ── 4. nothing is left showing the other unit ────────────────────────────────
const live = [...w.document.querySelectorAll('.ctrl-val, .ctrl-hints, .isf-cell-unit')];
const stale = live.filter(e => /mg\/dL|mg\/U/.test(e.textContent))
  .map(e => (e.id || '(no id)') + ': ' + e.textContent.trim());
check(stale.length === 0, 'still showing mg/dL while set to mmol:\n      ' + stale.join('\n      '));

// ── 5. the Nightscout import writes mg/dL correctly while showing mmol ───────
w.setSlider('bg', 200, 40, 350);
const HALF_STEP = 0.05 * MMOL;   // half of the 0.1 mmol grid, about 0.9 mg/dL
check(Math.abs(w.getBgSliderMgdl('bg') - 200) <= HALF_STEP + 1e-6,
  `setSlider(200) read back as ${w.getBgSliderMgdl('bg')}`);
check(Math.abs(parseFloat(w.document.getElementById('s-bg').value) - 200 / MMOL) <= 0.05 + 1e-9,
  `setSlider(200) displays ${w.document.getElementById('s-bg').value}, expected about 11.1`);
w.setSlider('bg', 999, 40, 350);   // clamping must happen in mg/dL, not in display units
check(Math.abs(w.getBgSliderMgdl('bg') - 350) <= HALF_STEP + 1e-6,
  `setSlider(999) clamped to ${w.getBgSliderMgdl('bg')}, expected about 350`);
w.setSlider('profIsf', 45, 10, 200);
check(Math.abs(w.getBgSliderMgdl('profIsf') - 45) <= 0.025 * MMOL + 1e-6,
  `ISF setSlider(45) read back as ${w.getBgSliderMgdl('profIsf')}`);
// A non-BG slider must be untouched by any of this.
w.setSlider('cr', 12, 3, 30);
check(parseFloat(w.document.getElementById('s-cr').value) === 12,
  `carb ratio was converted when it should not be: ${w.document.getElementById('s-cr').value}`);

// ── 6. moving a slider in mmol reaches the maths as mg/dL ────────────────────
const el = w.document.getElementById('s-bg');
el.value = '10.0';
check(Math.abs(w.getBgSliderMgdl('bg') - 180.182) < 0.01,
  `10.0 mmol read as ${w.getBgSliderMgdl('bg')} mg/dL, expected 180.18`);
w.setUnit('mgdl');
check(Math.abs(parseFloat(el.value) - 180.182) < 0.01,
  `after switching back the slider shows ${el.value}, expected 180.18`);

// ── 7. the delta sliders are usable in mmol ──────────────────────────────────
// The range is -10 to +15 mg/dL, which is under 1.4 mmol end to end. A step that leaves only a
// handful of positions would make the control useless in mmol even though it converts correctly.
w.setUnit('mmol');
const dEl = w.document.getElementById('s-delta');
const positions = (parseFloat(dEl.max) - parseFloat(dEl.min)) / parseFloat(dEl.step);
check(positions >= 20, `delta slider has only ${positions.toFixed(0)} positions in mmol`);
w.setUnit('mgdl');

console.log(fails === 0 ? 'PASS — all unit checks' : `${fails} check(s) FAILED`);
process.exit(fails === 0 ? 0 : 1);
