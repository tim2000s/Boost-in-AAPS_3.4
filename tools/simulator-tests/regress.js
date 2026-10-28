// The mg/dL view must be unchanged by the port. Both files are driven over the same grid of inputs
// and their outputs compared exactly; any difference is a regression for the readers who never
// touch the toggle.
const fs = require('fs'); const { JSDOM } = require('jsdom');
const stub = w => { w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
  get: (t,k)=> k==='measureText'?()=>({width:10}):(k==='createLinearGradient'||k==='createRadialGradient')?()=>({addColorStop(){}}):k==='canvas'?{width:600,height:300,style:{}}:typeof k==='string'?()=>{}:undefined,
  set: ()=>true }); };
const load = f => new JSDOM(fs.readFileSync(f,'utf8'),
  {runScripts:'dangerously', pretendToBeVisual:true, url:'https://example.invalid/', beforeParse:stub}).window;
const A = load(process.argv[2]), B = load(process.argv[3]);

const GRID = [
  {bg:60,delta:-6,iob:2}, {bg:90,delta:0,iob:0}, {bg:140,delta:2,iob:0.5},
  {bg:180,delta:8,iob:1}, {bg:250,delta:12,iob:3}, {bg:340,delta:-2,iob:0.2},
];
let diffs = 0, n = 0;
for (const g of GRID) {
  for (const state of ['IDLE','OBSERVING','CONFIRMED','COMMITTED']) {
    for (const tdd of [25, 40, 70]) {
      const run = w => {
        const inp = w.getInputs();
        Object.assign(inp, g, {tdd, v6PriorState: state});
        return JSON.stringify(w.calcAll(inp));
      };
      const a = run(A), b = run(B);
      n++;
      if (a !== b) { diffs++; if (diffs <= 3) console.log(`  DIFF bg=${g.bg} ${state} tdd=${tdd}\n    was ${a}\n    now ${b}`); }
    }
  }
}
console.log(diffs === 0 ? `PASS — ${n} input combinations identical in mg/dL` : `${diffs}/${n} DIFFER`);
process.exit(diffs === 0 ? 0 : 1);
