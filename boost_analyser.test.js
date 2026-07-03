#!/usr/bin/env node
/* Node tests for boost_analyser.html's CORE block (the DOM-free, fetch-free pure functions
   between the CORE / ENDCORE markers). Run:  node boost_analyser.test.js
   Covers the Trio-mode additions: the boostV5[…] reason-tag parser (Trio BoostV5Adapter.reasonTag
   format), the per-record/per-dataset source detector (structured boostV5_* fields → AAPS;
   tag or device "Trio" → Trio; both → mixed), and a full Trio paired-cycle reduction through
   parseCycles → pairDoses → analyse, plus an AAPS regression check that pairing semantics are
   unchanged. Also syntax-compiles the page's full <script> block. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "boost_analyser.html"), "utf8");

// ---- extract + compile the FULL script block (syntax check, no execution) ----
const sm = html.match(/<script>([\s\S]*)<\/script>/);
assert(sm, "script block not found");
new vm.Script(sm[1], { filename: "boost_analyser_inline.js" }); // throws on syntax error

// ---- extract + load the CORE block ----
const cs = html.indexOf("/* ================================ CORE");
const ce = html.indexOf("/* =============================== ENDCORE");
assert(cs > 0 && ce > cs, "CORE markers not found");
const ctx = {};
vm.createContext(ctx);
vm.runInContext(html.slice(cs, ce), ctx, { filename: "analyser_core.js" });
const C = ctx;

let n = 0;
function t(name, fn) { fn(); n++; console.log("  ok  " + name); }
const close = (a, b, eps = 1e-9) => assert(Math.abs(a - b) < eps, `${a} !== ${b}`);
// deep-equal across the vm realm boundary (vm objects have foreign prototypes)
const deq = (a, b) => assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), b);

/* ---------------- parseTrioTag ---------------- */
console.log("parseTrioTag");

t("full tag, both ml values, postEx + asleep, appended mid-reason", () => {
  const r = C.parseTrioTag("IOB: 1.21, COB: 0; Dev: 12; " +
    "boostV5[shadow]: state=OBSERVING score=0.45 wouldSMB=0.30U; ml(hypo=0.12 meal=0.88) postEx asleep");
  deq(r, { mode: "shadow", state: "OBSERVING", score: 0.45, wouldSMB: 0.3,
    mlHypo: 0.12, mlMeal: 0.88, exercise: false, postEx: true, asleep: true });
});

t("n/a ml values, no activity flags", () => {
  const r = C.parseTrioTag("boostV5[shadow]: state=IDLE score=0.00 wouldSMB=0.00U; ml(hypo=n/a meal=n/a)");
  assert.strictEqual(r.mlHypo, null);
  assert.strictEqual(r.mlMeal, null);
  assert.strictEqual(r.state, "IDLE");
  assert(!r.exercise && !r.postEx && !r.asleep);
});

t("exercise flag (mutually exclusive with postEx in the adapter)", () => {
  const r = C.parseTrioTag("boostV5[shadow]: state=RECOVERING score=0.10 wouldSMB=0.05U; ml(hypo=0.30 meal=n/a) exercise");
  assert(r.exercise && !r.postEx && !r.asleep);
  close(r.mlHypo, 0.30);
});

t("off and active modes parse", () => {
  assert.strictEqual(C.parseTrioTag(
    "boostV5[off]: state=IDLE score=0.00 wouldSMB=0.00U; ml(hypo=n/a meal=n/a)").mode, "off");
  assert.strictEqual(C.parseTrioTag(
    "boostV5[active]: state=COMMITTED score=0.92 wouldSMB=1.20U; ml(hypo=0.05 meal=0.97)").mode, "active");
});

t("active-mode harness suffixes after the tag do not bleed into the flags", () => {
  const r = C.parseTrioTag("boostV5[active]: state=CONFIRMED score=0.90 wouldSMB=1.20U; " +
    "ml(hypo=0.10 meal=0.95) asleep V6 suppressed (SLEEPING) — base SMB stands;");
  assert(r.asleep && !r.exercise && !r.postEx);
  close(r.wouldSMB, 1.2);
  const r2 = C.parseTrioTag("boostV5[active]: state=IDLE score=0.00 wouldSMB=0.00U; " +
    "ml(hypo=n/a meal=n/a) nightMode(SMB suppressed)");
  assert(!r2.asleep && !r2.exercise && !r2.postEx);
});

t("non-tag reasons return null", () => {
  assert.strictEqual(C.parseTrioTag("Autosens ratio 1.0; COB 24; Eventual BG 154 >= 100"), null);
  assert.strictEqual(C.parseTrioTag(""), null);
  assert.strictEqual(C.parseTrioTag(null), null);
});

/* ---------------- detector ---------------- */
console.log("detector");

const T0 = Date.UTC(2026, 6, 1, 12, 0, 0); // fixed epoch base
const iso = i => new Date(T0 + i * 300000).toISOString();

function aapsRec(i, extra) {
  return { device: "openaps://Samsung SM-G991B", openaps: { suggested: Object.assign({
    timestamp: iso(i), bg: 120, units: 0.1, variable_sens: 54,
    boostV5_state: "IDLE", boostV5_age: 3, boostV5_score: 0.05, boostV5_budget: 0.5,
    boostV5_finalDose: 0.1, boostV5_gateReduction: "none",
    reason: "shadow: V5 IDLE; V1 dosing"
  }, extra || {}) } };
}
function trioRec(i, tag, units, extra) {
  const sug = Object.assign({ timestamp: iso(i), bg: 130, ISF: 54,
    reason: "Autosens ratio 1.00; COB: 12; Eventual BG 160 >= 100; " + tag }, extra || {});
  if (units !== undefined) sug.units = units;
  return { device: "Trio", openaps: { suggested: sug } };
}
const tag = (mode, state, score, smb, ml, ctx2) =>
  `boostV5[${mode}]: state=${state} score=${score.toFixed(2)} wouldSMB=${smb.toFixed(2)}U; ml(${ml})${ctx2 || ""}`;

t("pure AAPS dataset → aaps", () => {
  const d = C.detectSources([aapsRec(0), aapsRec(1), aapsRec(2)]);
  assert.strictEqual(d.mode, "aaps");
  deq(d.counts, { aaps: 3, trio: 0, unknown: 0 });
});

t("pure Trio dataset (tagged) → trio", () => {
  const d = C.detectSources([
    trioRec(0, tag("shadow", "IDLE", 0, 0, "hypo=n/a meal=n/a")),
    trioRec(1, tag("shadow", "OBSERVING", 0.4, 0.3, "hypo=0.10 meal=0.70"))
  ]);
  assert.strictEqual(d.mode, "trio");
  deq(d.counts, { aaps: 0, trio: 2, unknown: 0 });
});

t("Trio device signature without a tag (Boost off) still classifies trio", () => {
  const rec = { device: "Trio", openaps: { suggested: { timestamp: iso(0), reason: "plain oref reason" } } };
  assert.strictEqual(C.classifyRecordSource(rec), "trio");
});

t("structured fields win over device string; plain oref is unknown", () => {
  assert.strictEqual(C.classifyRecordSource(aapsRec(0)), "aaps");
  const plain = { device: "openaps://phone", openaps: { suggested: { timestamp: iso(0), reason: "no boost here" } } };
  assert.strictEqual(C.classifyRecordSource(plain), "unknown");
  const pumpOnly = { device: "Trio", pump: {} };
  assert.strictEqual(C.classifyRecordSource(pumpOnly), null);
});

t("mixed dataset → mixed", () => {
  const d = C.detectSources([aapsRec(0), trioRec(1, tag("shadow", "IDLE", 0, 0, "hypo=n/a meal=n/a"))]);
  assert.strictEqual(d.mode, "mixed");
});

t("empty / junk dataset → none", () => {
  assert.strictEqual(C.detectSources([]).mode, "none");
  assert.strictEqual(C.detectSources([{ pump: {} }]).mode, "none");
});

/* ---------------- Trio paired-cycle reduction ---------------- */
console.log("trio reduction");

t("parseCycles: tag fields, ISF, missing-units, reconstructed age", () => {
  const ds = [
    trioRec(0, tag("shadow", "IDLE", 0.00, 0.00, "hypo=n/a meal=n/a"))],           // units absent
    cyc = C.parseCycles(ds.concat([
      trioRec(1, tag("shadow", "OBSERVING", 0.45, 0.30, "hypo=0.12 meal=0.88"), 0.10),
      trioRec(2, tag("shadow", "CONFIRMED", 0.85, 1.20, "hypo=0.10 meal=0.95")),   // units absent
      trioRec(3, tag("shadow", "CONFIRMED", 0.80, 0.50, "hypo=0.10 meal=0.95"), 0.20),
      trioRec(4, tag("active", "COMMITTED", 0.90, 0.80, "hypo=0.08 meal=0.97"), 0.80)
    ]));
  assert.strictEqual(cyc.length, 5);
  assert(cyc.every(c => c.src === "trio"));
  deq(cyc.map(c => c.state), ["IDLE", "OBSERVING", "CONFIRMED", "CONFIRMED", "COMMITTED"]);
  deq(cyc.map(c => c.age), [0, 0, 0, 1, 0]);   // reconstructed from state runs
  deq(cyc.map(c => c.fd), [0, 0.3, 1.2, 0.5, 0.8]);
  deq(cyc.map(c => c.active), [false, false, false, false, true]);
  assert.strictEqual(cyc[1].isf, 54);                              // mg/dL passes through
  close(C.trioIsfMgdl(3.0), 3.0 * 18.016);                         // mmol leak guard
  assert.strictEqual(cyc[0].gates, null);                          // AAPS-only telemetry absent, not NaN
  assert.strictEqual(cyc[0].ccap, null);
  close(cyc[1].ml.hypo, 0.12); close(cyc[1].ml.meal, 0.88);
});

t("pairDoses: shadow pairs (absent units = oref 0), Boost-active Trio is unpaired", () => {
  const cyc = C.parseCycles([
    trioRec(0, tag("shadow", "IDLE", 0, 0, "hypo=n/a meal=n/a")),
    trioRec(1, tag("shadow", "OBSERVING", 0.45, 0.30, "hypo=0.12 meal=0.88"), 0.10),
    trioRec(2, tag("active", "COMMITTED", 0.90, 0.80, "hypo=0.08 meal=0.97"), 0.80),
    { device: "Trio", openaps: { suggested: { timestamp: iso(3), reason: "no tag this cycle" } } }
  ]);
  deq(C.pairDoses(cyc[0]), { v1: 0, v6: 0 });
  deq(C.pairDoses(cyc[1]), { v1: 0.10, v6: 0.30 });
  assert.strictEqual(C.pairDoses(cyc[2]), null);   // oref counterfactual not logged on Trio
  assert.strictEqual(C.pairDoses(cyc[3]), null);   // no tag → no V6 telemetry
});

t("analyse: Trio site — labels, totals, states, commit shot, unpaired accounting", () => {
  const ds = [
    trioRec(0, tag("shadow", "IDLE", 0.00, 0.00, "hypo=n/a meal=n/a")),
    trioRec(1, tag("shadow", "OBSERVING", 0.45, 0.30, "hypo=0.12 meal=0.88"), 0.10),
    trioRec(2, tag("shadow", "CONFIRMED", 0.85, 1.20, "hypo=0.10 meal=0.95")),
    trioRec(3, tag("shadow", "CONFIRMED", 0.80, 0.50, "hypo=0.10 meal=0.95"), 0.20),
    trioRec(4, tag("active", "COMMITTED", 0.90, 0.80, "hypo=0.08 meal=0.97"), 0.80)
  ];
  const entries = Array.from({ length: 12 }, (_, i) => ({ date: T0 + i * 300000, sgv: 110 + 4 * i }));
  const m = C.analyse(C.parseCycles(ds), entries, []);
  assert.strictEqual(m.siteMode, "trio");
  deq(m.labels, { v1: "Trio oref", v6: "Boost V6" });
  assert.strictEqual(m.paired, 4);
  assert.strictEqual(m.unpaired, 1);                                // the Boost-active cycle
  assert.strictEqual(m.withV6, 5);
  close(m.totals.v1, 0.30);                                         // 0 + 0.10 + 0 + 0.20
  close(m.totals.v6, 2.00);                                         // 0 + 0.30 + 1.20 + 0.50
  assert.strictEqual(m.stateCount.CONFIRMED, 2);
  assert.strictEqual(m.confirms, 1);                                // reconstructed age===0
  deq(m.commitShots, [1.2]);
  deq(m.gateCount, {});                          // AAPS-only → empty, never NaN
  assert.strictEqual(m.segments.length, 1);
  assert.strictEqual(m.segments[0].src, "trio");
  assert(m.gly && isFinite(m.gly.tir) && isFinite(m.gly.ting));     // entries-based, engine-agnostic
});

t("analyse: mixed site — per-cycle modes, both segments reported", () => {
  const ds = [
    aapsRec(0), aapsRec(1),
    trioRec(2, tag("shadow", "OBSERVING", 0.45, 0.30, "hypo=0.12 meal=0.88"), 0.10),
    trioRec(3, tag("shadow", "IDLE", 0.00, 0.00, "hypo=n/a meal=n/a"))
  ];
  const entries = Array.from({ length: 8 }, (_, i) => ({ date: T0 + i * 300000, sgv: 120 }));
  const m = C.analyse(C.parseCycles(ds), entries, []);
  assert.strictEqual(m.siteMode, "mixed");
  deq(m.labels, { v1: "V1/oref", v6: "Boost V6" });
  deq(m.sources, { aaps: 2, trio: 2, unknown: 0 });
  assert.strictEqual(m.segments.length, 2);
  deq(m.segments.map(s => s.src), ["aaps", "trio"]);
  close(m.totals.v1, 0.1 + 0.1 + 0.1 + 0);                          // AAPS shadow units + trio units
  close(m.totals.v6, 0.1 + 0.1 + 0.3 + 0);
});

/* ---------------- AAPS regression: pairing semantics unchanged ---------------- */
console.log("aaps regression");

t("AAPS shadow + V6-active pairing behave exactly as before", () => {
  const cyc = C.parseCycles([
    aapsRec(0),                                                     // shadow: units are V1's dose
    aapsRec(1, { boostV5_active: true, boostV5_finalDose: 0.6, units: 0.6,
                 reason: "V6-ACTIVE drove SMB; base would=0.25 U" }),
    aapsRec(2, { boostV5_active: true, boostV5_finalDose: 0.4, units: 0.15,
                 reason: "V6 suppressed (cumulative SMB cap 1.00U/1.00U reached);" })
  ]);
  assert(cyc.every(c => c.src === "aaps"));
  deq(C.pairDoses(cyc[0]), { v1: 0.1, v6: 0.1 });
  deq(C.pairDoses(cyc[1]), { v1: 0.25, v6: 0.6 });
  deq(C.pairDoses(cyc[2]), { v1: 0.15, v6: 0.4 });
  const entries = Array.from({ length: 6 }, (_, i) => ({ date: T0 + i * 300000, sgv: 120 }));
  const m = C.analyse(cyc, entries, []);
  assert.strictEqual(m.siteMode, "aaps");
  deq(m.labels, { v1: "V1", v6: "V6" });         // default labels → identical UI text
  assert.strictEqual(m.paired, 3);
  assert.strictEqual(m.unpaired, 0);
});

console.log(`\nall ${n} tests passed`);
