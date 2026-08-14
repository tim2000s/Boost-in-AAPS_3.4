#!/usr/bin/env node
// Runs every check against boost_simulator.html.
//
//   npm install && npm test
//
// Three harnesses, because no single one covers the ground:
//
//   units_test.js   jsdom. Fast, and can call into the page's functions directly. Cannot be trusted
//                   on range inputs: jsdom keeps an off-step value where a browser snaps it.
//   chrome_check.js the same invariants inside headless Chrome, where the snapping is real. This is
//                   the one that found the display grid being off-centre.
//   regress.js      drives the current file and the previous commit's over the same inputs and
//                   requires identical results in mg/dL, since most readers never touch the toggle.
//
// Chrome is skipped with a warning if it is not installed, rather than failing the run.
const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const SIM = path.join(ROOT, 'boost_simulator.html');
const HERE = __dirname;

const CHROME = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].find(p => fs.existsSync(p));

let failed = 0;
const run = (label, fn) => {
  process.stdout.write(`${label}\n`);
  try { fn(); } catch (e) { failed++; process.stdout.write(`  ${e.message.trim()}\n`); }
};

run('units_test (jsdom)', () => {
  process.stdout.write(execFileSync('node', [path.join(HERE, 'units_test.js'), SIM],
    { encoding: 'utf8' }));
});

run('regress (mg/dL unchanged from HEAD)', () => {
  const orig = path.join(os.tmpdir(), 'boost_simulator_head.html');
  fs.writeFileSync(orig, execFileSync('git', ['-C', ROOT, 'show', 'HEAD:boost_simulator.html'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }));
  process.stdout.write(execFileSync('node', [path.join(HERE, 'regress.js'), orig, SIM],
    { encoding: 'utf8' }));
});

run('chrome_check (real range-input snapping)', () => {
  if (!CHROME) { process.stdout.write('  SKIPPED — no Chrome or Chromium found\n'); return; }
  const probe = path.join(os.tmpdir(), 'boost_simulator_probe.html');
  execFileSync('node', [path.join(HERE, 'chrome_check.js'), SIM, probe], { encoding: 'utf8' });
  const r = spawnSync(CHROME, ['--headless', '--disable-gpu', '--dump-dom',
    '--virtual-time-budget=6000', 'file://' + probe], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const m = /id="unit-probe-result"[^>]*>([\s\S]*?)<\/div>/.exec(r.stdout || '');
  if (!m) throw new Error('the probe did not report, so the page most likely threw before it ran');
  const text = m[1].replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();
  process.stdout.write('  ' + text.split('\n').join('\n  ') + '\n');
  if (!text.startsWith('PASS')) throw new Error('Chrome checks failed');
});

process.stdout.write(failed === 0 ? '\nall harnesses passed\n' : `\n${failed} harness(es) failed\n`);
process.exit(failed === 0 ? 0 : 1);
