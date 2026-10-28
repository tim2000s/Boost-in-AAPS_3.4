// The same invariants as units_test.js, but run inside the real simulator in headless Chrome.
//
// This exists because jsdom does not implement the value sanitisation a range input performs: given
// a value that is not on a step it keeps it, where a browser snaps it to the nearest one. That
// difference is exactly where a units layer goes wrong, so the checks that depend on it are
// repeated here rather than trusted from jsdom.
//
// It is injected into the page and its result read back out of the DOM, so no automation library is
// needed beyond Chrome's --dump-dom.
const fs = require('fs');
const path = require('path');

const src = process.argv[2];
const out = process.argv[3];

const PROBE = `
<div id="unit-probe-result" style="display:none"></div>
<script>
(function () {
  const MMOL = 18.0182;
  const rows = [];
  let fails = 0;
  const check = (ok, msg) => { if (!ok) { fails++; rows.push('FAIL ' + msg); } };
  const ids = BG_SLIDERS.map(sd => sd.id);
  const snap = () => Object.fromEntries(ids.map(id => [id, getBgSliderMgdl(id)]));

  // 1. the display setting never enters the maths
  const fixed = getInputs();
  const a = JSON.stringify(calcAll(fixed));
  setUnit('mmol');
  const b = JSON.stringify(calcAll(fixed));
  check(a === b, 'calcAll on identical inputs differs between display settings');
  setUnit('mgdl');

  // 2. every displayed value sits on a round number of its step
  setUnit('mmol');
  BG_SLIDERS.forEach(sd => {
    const el = document.getElementById('s-' + sd.id);
    const v = parseFloat(el.value), lo = parseFloat(el.min);
    const offGrid = Math.abs((v - lo) / sd.stepMmol - Math.round((v - lo) / sd.stepMmol));
    check(offGrid < 1e-6, sd.id + ' shows ' + el.value + ', which is not on its step grid from ' + el.min);
    // the grid itself should be round numbers, not an arbitrary offset
    const loOffGrid = Math.abs(lo / sd.stepMmol - Math.round(lo / sd.stepMmol));
    check(loOffGrid < 1e-6, sd.id + ' minimum ' + el.min + ' is not a multiple of its step ' + sd.stepMmol);
  });

  // 3. the whole mg/dL range stays reachable despite the snapping
  BG_SLIDERS.forEach(sd => {
    const el = document.getElementById('s-' + sd.id);
    el.value = el.max;
    check(Math.abs(getBgSliderMgdl(sd.id) - sd.max) < 0.01,
      sd.id + ' cannot reach its maximum ' + sd.max + ': tops out at ' + getBgSliderMgdl(sd.id).toFixed(2));
    el.value = el.min;
    check(Math.abs(getBgSliderMgdl(sd.id) - sd.min) < 0.01,
      sd.id + ' cannot reach its minimum ' + sd.min + ': bottoms out at ' + getBgSliderMgdl(sd.id).toFixed(2));
  });
  setUnit('mgdl');

  // 4. switching repeatedly settles rather than walking away
  // One switch quantises to the displayed grid, which is unavoidable and visible to the reader.
  // What must not happen is that each further switch moves it again.
  const start = snap();
  setUnit('mmol'); setUnit('mgdl');
  const after1 = snap();
  for (let i = 0; i < 20; i++) { setUnit('mmol'); setUnit('mgdl'); }
  const after21 = snap();
  ids.forEach(id => {
    const sd = BG_SLIDERS.find(x => x.id === id);
    const step = sd.stepMmol * MMOL;
    check(Math.abs(start[id] - after1[id]) <= step / 2 + 1e-6,
      id + ' moved more than half a step on the first switch: ' + start[id] + ' -> ' + after1[id]);
    check(Math.abs(after1[id] - after21[id]) < 1e-6,
      id + ' kept moving over twenty more switches: ' + after1[id] + ' -> ' + after21[id]);
  });

  // 5. a Nightscout mg/dL write lands on the right value while showing mmol
  setUnit('mmol');
  [['bg', 200], ['bg', 350], ['bg', 40], ['profIsf', 45], ['target', 100]].forEach(([id, v]) => {
    setSlider(id, v, 0, 1000);
    const sd = BG_SLIDERS.find(x => x.id === id);
    const got = getBgSliderMgdl(id);
    check(Math.abs(got - v) <= sd.stepMmol * MMOL / 2 + 1e-6,
      'setSlider(' + id + ', ' + v + ') read back as ' + got.toFixed(2));
  });
  setUnit('mgdl');

  rows.unshift(fails === 0 ? 'PASS — all checks in Chrome' : fails + ' check(s) FAILED in Chrome');
  document.getElementById('unit-probe-result').textContent = rows.join('\\n');
})();
</` + `script>
`;

let html = fs.readFileSync(src, 'utf8');
// after the page's own scripts have run
html = html.replace('</body>', PROBE + '</body>');
fs.writeFileSync(out, html);
console.log(out);
