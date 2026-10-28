# CLAUDE.md — Boost development guide

Working guide for Claude sessions on the Boost AndroidAPS fork. Consolidates the rules, methodology, and mistakes-with-corrections built up over the work to date. Personal/operational specifics (Drive destination, site registry, device details) live in the private memory, not here — this file is committed to a public repo, so it carries no names, tokens, site URLs, or personal identifiers.

## Hard rules (non-negotiable)

1. **Anonymise before anything goes to GitHub.** Public repo. Scrub names, tokens, site URLs, and locations from files, commit messages, and paths before every commit. Use word boundaries so you don't touch unrelated words (e.g. Crowdin, Romanian strings). Read site details from the private registry, never hardcode them. Run a scan before committing — this has caught real leaks (user names in a doc, a hardcoded token in a script).
2. **No training or online inference in the dose path.** The shipping controller is deterministic. Learned components are pre-trained models applied at inference, or robust statistics computed offline/periodically. Anything that would learn-and-dose in the loop is gated behind shadow-logging first.
3. **Absolute safety floors sit under every statistical decision.** The time-below-range kill-switches (consensus absolutes: TBR<70 >4%, <54 >1%) can only tighten. Statistics rank options; they never override a safety floor. Kill-switches key on absolutes, never on relative doubling.
4. **Nothing that changes dosing ships without the two-test bar**: absolute TBR gates plus relative pricing, and for a real dosing change, a pre-registered within-user trial.

## The identification constraint (shapes all analysis)

There is no glucodynamic simulator, so we cannot generate the counterfactual BG trajectory for a dosing change. A "simulate policy A vs B" backtest is not available.

- **Prediction/detection** questions are validated out-of-sample — clean, no counterfactual.
- **Policy** questions are priced against observed outcomes, with the counterfactual caveat stated, plus within-subject and matched-baseline designs.
- An observational effect size is associational unless a within-user or randomised design backs it.
- The bottleneck is identification, not modelling. Keep models modest.

## Methodology

- **DB-first.** Use the local TimescaleDB (`oref.boost_decisions`) for analyses. Pull from Nightscout only for what the DB lacks, and wire missing fields into the extractor rather than re-pulling. NS pulls: chunk to ~7-day windows and retry with backoff (the site 502s on long windows).
- **Backtest protocol.** Refresh the DB to t=now first. Commit scripts and reports to `backtesting/`; the scratchpad holds intermediates only, not deliverables.
- **Out-of-sample everything.** `GroupKFold` with the *user* as the group to prevent leakage — cross-user generalisation is the honest test, not per-person memorisation. Temporal splits for time-ordered data.
- **Matched baselines before believing an effect size.** Multiple large-looking findings dissolved under a proper baseline. Un-baselined and un-leakage-checked effect sizes are provisional.
- **Validate before building — confidence before commitment.** No spec, shadow, or code is built on a claim until it is *freshly measured* in this session — never cited from memory, never a single lucky split. Building ahead of validation and refuting it a step later is the exact failure this rule exists to stop; it wastes effort and destroys trust.
- **Every effect size carries uncertainty.** Report a bootstrap 95% CI and an explicit "distinguishable from baseline/chance?" verdict. If the interval overlaps the baseline, say **unproven** out loud and do not build on it. A bare point estimate is not a finding.
- **Label the confidence tier** whenever a claim is used: **SOLID** (out-of-sample + CI-backed + survived a challenge) / **PROVISIONAL** (single test, wide or unknown CI) / **SPECULATIVE** (spec or reasoning only; the action is untested). State the tier so the reader never guesses which they're standing on.
- **Small-n honesty.** Per-user samples are tiny; report per-user CIs *and* the pooled cross-user result, and never let one user or one split carry a headline.
- **Within-subject > between-subject.** The population is small (single digits to ~30) and self-selected; cross-user results are mostly hypothesis-generating.
- **Proximate ≠ causal.** Attribution names the mechanism at an event; it doesn't prove causation. Audit by outcome before acting on it.
- **Don't re-litigate settled questions.** `backtesting/RELATIONSHIPS_REGISTER.md` lists what's been tested and discarded. Check it before proposing a lever.
- **Code leads.** Verify against the live code and DB before recommending. Memory and prior notes can be stale; if a memory names a file/field/flag, confirm it still exists. Auto-config not applying an expected value has bitten us more than once.

## Lab vs loop

What doses is deterministic (state machine, multipliers, caps, composed brake-floor, rule-based sleep detector, a deterministic per-user auto-config derivation) plus two pre-trained ML models at inference. **The two models are not both restraining.** `mlHypoRisk` is hypo-directional on all four of its paths: it can trim a dose and cannot add one. `mlMealLikely` is dose-INCREASING on three: above 0.50 it releases the V1 G3 hold that gates the aggressive tiers, it carries weight 0.20 in the V5 meal-signal score whose states multiply the dose 0.3x to 1.8x, and above 0.30 it blocks the sleeping classification that would restrain overnight microboluses. Verified in source 2026-09-02; see `backtesting/reports/2026-09_boost_lgbm_methods.md`. All the Bayesian/inferential machinery is offline decision-support that decides what gets built. See `backtesting/STATISTICAL_METHODS.md`.

## Branch and commit workflow

- **Two separate repositories exist and must not be crossed.** All Boost V5/V6/V7 work lives in the Boost fork on its **vehicle branch** (the V7-shadow line) — that is what APKs are built from and flashed. A second repository holds a separate port tracking upstream AAPS (a different generation); **Boost feature or dosing work never goes there.** Sessions often start in the upstream-port working directory because it is the default cwd — that does not make it the target. Confirm the repo and branch before creating a branch or committing. Local paths/branch names are in the private notes.
- Land Boost changes on the vehicle branch first; don't push straight to dev. If a change belongs on both the vehicle and the experimental line, cherry-pick (`-x`) across and push both so they keep a common base.
- Commit messages end with the required Co-Authored-By and session trailer. Keep them factual.
- After a force-push upstream, sync your local branch to origin before running any analysis against it — a stale local branch has inverted conclusions before.

## Build and deploy

- **Roll-out sequence (feature → flashed APK):** prototype in the Boost fork (not the upstream-port repo) → commit (the app build has a no-uncommitted-changes gate; a dirty tree fails it) → land on the vehicle branch, cherry-pick (`-x`) to the sibling line if it belongs there → validate the Dagger graph (`:app` KSP) → build the signed release APK → verify it (SHA/timestamp, signature, and that the new class is actually in the dex) → rename descriptively and copy to the private Drive folder (per local notes) → flash.
- Verify every APK by timestamp/SHA before shipping it. A silent `BUILD FAILED` (hidden by `-q`) once led to an old APK being copied out as if fresh. Never trust an APK you didn't just watch build.
- Background builds: check the exit status and the output, not just that the command returned.
- Wear/phone flashing can be done over adb wireless debugging (pair port + code, then connect port); watch for background sensor permissions and the doze/battery whitelist, which are what let overnight sensing survive.

## Mistakes made, and the rules that came from them

- **Prototyped a feature in the wrong repository** (a smoothing plugin built in the upstream-port repo instead of the Boost fork's vehicle branch, because that was the session's default cwd) → all Boost work goes in the Boost fork on the vehicle branch; confirm the repo/branch before branching or committing, then cherry-pick if a prototype ended up misplaced.
- **Trusted a stale APK** after `-q` hid a build failure → always verify APK timestamp/SHA, and confirm the *new* class is actually in the dex (`unzip -p apk classes*.dex | strings | grep <Class>`), not just that a file exists.
- **A backgrounded `gradle … | tail` reported exit 0** — that was the pipe's last command (`tail`), not gradle; a `BUILD FAILED` (clean-tree gate) was masked and a stale APK was nearly shipped. → Capture gradle's real exit code (`gradlew … > log 2>&1; echo $?`), don't read it through a pipe.
- **Edited a tracked file while a background build ran** → dirtied the tree and tripped the no-uncommitted-changes gate mid-build. Commit (or hold edits) before starting a build; don't touch the tree until it finishes.
- **Ran `git add -A` while a subagent was writing the same repo** → swept the agent's in-progress files into unrelated commits and left the tree dirty. → Stage explicit paths, never `-A`, when a subagent shares the working copy; or give the agent an isolated worktree.
- **Ran analysis against a stale local branch** 24 commits behind origin after a force-push → sync local to origin first.
- **Repeated mis-diagnosis of a single user** from a contaminated aggregate window → verify era detection (`boostv5_active`), don't trust raw day-count windows.
- **Called V1 "oref"**, wrongly deflating a finding → **V1 is Boost** (the V1 generation is a Boost dosing algorithm); `boostv5_active` marks only the V5/V6-generation slice.
- **Leaked real names and a token into committed files** → the anonymise scan is a mandatory pre-commit gate, not a formality.
- **Over-attributed effect sizes** (a brake "34%" that was 90% correct on audit; a cohort "+13pp" that was mostly selection; a recovery "2×" that was a window-length artefact) → matched baseline first.
- **Wrote in a sensational, over-emphatic register** → plain, balanced, British spelling; state limitations without dwelling on them as virtue.
- **Mis-read an ambiguous instruction** (a "watch on the network" as an HTTP server, not adb wireless debugging) → confirm device and protocol before acting on terse infra notes.
- **Read "no output" as "not present" when a glob was involved** — `ls -d "$HOME/Google Drive"* "$HOME/Library/CloudStorage"/*` matched nothing on the FIRST pattern, and zsh aborts the whole command on a failed glob, so the second path was never looked at. Concluded there was no Drive mount when both accounts were mounted. The same `nomatch` behaviour silently killed a wait-loop earlier in the same session. → Never infer absence from an empty result when a glob could have aborted the command; use `find`, `test -e`, or one path per command.
- **`git add <directory>` swept in 172 files / 97.6 MB** of pre-existing untracked work from other studies (including simulator cohort archives deliberately left uncommitted). Same failure as the `-A` case below, without a subagent involved. → Stage explicit file paths. Always. If a commit's file count surprises you, rebuild it before pushing.
- **Described a mechanism from inference instead of reading it** — asserted the post-rescue guard "ramps with window age" when it is a function of BG alone. → Open the function before characterising it, even when the behaviour seems obvious from the logs.
- **Used one screen across knobs it did not suit** — a drift-to-noise ratio was applied to knobs quantised to three values / 0.1 steps, where both terms are dominated by whether a threshold was crossed; it "showed" they should be frozen. It also applied a symmetric bar to asymmetric changes, i.e. demanded that a *tightening* clear the same evidence bar as an insulin-adding raise. → Check the metric suits the estimand and the decision; tightenings and loosenings do not need the same evidence.
- **Scored a series against the wrong expected sign** — aggression is eased DOWN as time-below-range rises, so scoring its agreement against +1 reported 0.00 and marked correct behaviour as total failure. → State the expected sign of every relationship before computing agreement or correlation.
- **Reported from a degenerate calculation** — a "full offset" bound was identically zero by construction and was quoted before that was noticed. → Sanity-check that a computed bound can actually vary before drawing anything from it.
- **Proposed a filter wider than the quantisation it filters** — a measured 0.16 deadband on a knob rounded to 0.1 would have blocked every single-step change and silently frozen it. → Compare any threshold against the granularity of what it gates.
- **Mechanically replaced a code block and removed its neighbours** — a scripted slice between two anchors deleted an adjacent data class and function along with the target. → After any scripted edit, compile immediately and assert the symbols you did not intend to touch still exist.
- **Repeated a documented trap in a new guise** — treated pre-V6 windows as an "exogenous baseline" when V1 IS Boost, so the whole record is Boost's own output. The rule was already in this file. → When a framing depends on an era boundary, re-read the era facts below rather than trusting the framing.
- **An annotation drifted off its class and silently opened the loop for five days.** `@Singleton` sat directly above `open class OpenAPSBoostPlugin`; a later commit inserted a KDoc, a constant and a helper function *between* them. Kotlin skips comments when binding an annotation, so it reattached to the constant, the engine became unscoped, and — because the V5 plugin injected it as a `Provider` — every cycle ran `determine_basal` on one instance and read `lastAPSResult` back from a freshly-constructed one. Null every time: "NO APS SELECTED OR PROVIDED RESULT", result computed and discarded, no exception, nothing in the log but one GUI string. It compiled and every unit test passed. → **Never insert anything between an annotation and its declaration.** Scope-critical DI wiring needs a test that asserts the annotation is present (`isAnnotationPresent`), and a shared collaborator should be injected as `dagger.Lazy` (caches per injection point) rather than `Provider` (new instance per `get()` when unscoped), so one mistake cannot split a writer from its reader.
- **Read three field logs and reported "loop healthy" each time** — by counting `LoopPlugin.invoke()` calls and never reading the outcome three lines below, where every single cycle ended in `NO APS SELECTED OR PROVIDED RESULT`. → A loop *invocation* is not a loop *result*. Check what was enacted, not what was called; grep the outcome line, and count failures alongside attempts (`invocations` vs `no-result`) so a 100% failure rate cannot look like health.
- **Invented a toolchain regression to explain my own wrong command.** `assembleFullRelease` (top level) builds every module's release variant including library validation tasks; the project's recipe is `:app:assembleFullRelease`, which never invokes them. Having "reproduced" the failure on `dev` and at the last-known-good commit, I concluded the environment had broken — when the last-known-good commit had demonstrably produced a working release APK, which should have told me the variable was my command. I nearly had a project-wide safety validation disabled to work around it. → When a reproduction contradicts a known-good artefact, suspect the harness before the code; and read the recorded build recipe *before* building, not after failing twice.
- **Copied out an APK from a build that had FAILED.** The exit code was 1 and an artefact from an earlier successful run was still on disk. Caught only because the exit code was checked separately. → Delete the output before building, gate the copy on the exit code, and confirm the new artefact's SHA differs from the previous one.
- **Invented shorthand and then leaned on it** ("path over net", "material share") until the reader had to ask what any of it meant. → Define a term on first use or do not coin it; prefer the plain sentence over a named metric.

## Domain facts that are easy to get wrong

- **V1 is Boost.** Not oref. See above.
- The high tail is **high-IOB**; adding insulin into recovering highs or late overnight bounces is the repeated source of lows. The dosing guards exist for this.
- **Online knob-tuning does not beat static per-user auto-config.** Caps and sliders, both directions, all converged on the policy auto-config already ships. Don't rebuild it as an online loop.
- **New dosing switches are auto-config managed** (2026-07-17 convention). Any new opt-in dosing toggle is enabled/disabled per-user by `BoostV5AutoConfig` (add it to `managedBooleanKeys` + `suggestionBoolean` in the plugin, and a derived flag on `V5Suggestion`), not shipped OFF-for-everyone requiring manual discovery. Insulin-adding switches auto-enable only for clearly well-controlled users (strict TBR cut — `WELL_CONTROLLED_MAX_TBR70/SEV54`); the user can still override manually. The seam/live gates stay as the runtime backstop.
- **TING** = time in 3.5–7.8 mmol/L (63–140 mg/dL); report alongside TIR.
- The user doses in **U200** (roughly 2× mass per unit); flag cross-user absolute-unit comparisons.
- The composed brake is ~90% correct — don't loosen it.

## How the user works

- Terse and action-oriented. "off you go", "do both", "go" mean proceed — don't ask for permission on the obvious next step. Reserve questions for genuine forks.
- Tool use is auto-approved; don't prompt for confirmation on routine commands.
- Prefers plain, understated writing over emphasis and salesmanship.
- Is the domain expert and the developer of this fork; corrections from the user override prior analysis.

## Writing style for documents

Protocols, reports and papers are written as though for submission to a journal, in British English,
and read as if a person wrote them rather than a machine. The rules below are not preferences to be
balanced against others; they are how the output is expected to look.

Every document is a new draft, always. A revised protocol, report or article is rewritten as though
it were the first version and contains no trace of what it used to say. Never write "an earlier
version assumed", "that was wrong", "this supersedes", "previously specified" or an amendment log.
State the current position and nothing else.

This holds even when the change came from correcting a real mistake, and it holds most strongly then,
because the temptation to show the working is greatest. The reasoning for a change belongs in the
commit message, where the people who need it will find it, not in the document, where it is noise to
every reader who was not present for the earlier version. A reader of the current draft should be
unable to tell that there was one.

Write continuous prose. A bulleted list is a way of avoiding the work of connecting ideas, and it
belongs in a repository README rather than in a document making an argument. Tables are permitted
where the content is genuinely tabular, such as an arm configuration or a set of measured values,
and nowhere else.

Do not use em dashes or en dashes in prose. A comma, a semicolon, a colon or a full stop will do the
work, and the sentence is usually better for the rewrite. Write numeric ranges with the word "to".

Do not use bold for emphasis. Emphasis in a scientific document comes from where a claim is placed
and how plainly it is stated, not from the typography. Reserve any formatting for headings and for
the occasional defined term.

Avoid the rhetorical triplet. Three parallel clauses in a row is the most recognisable tic of
machine-written prose, and once noticed it is seen everywhere. Two clauses, or four, or a sentence
restructured entirely, will read as human. A genuine list of three things is a matter of fact and is
fine; it is the rhythm used for effect that is not.

State limitations plainly, once, in the place where they belong, and then continue. Do not dwell on
a limitation as though the admission were itself a virtue, and do not restate a caveat that has
already been made. Prefer the understated formulation throughout: "cannot be settled by this study"
rather than "it is critically important to note that this study is fundamentally unable to settle".

The same register applies to commit messages, which are read by the same people.

The mechanical rules above are necessary and not sufficient. A draft can pass every one of them and
still read as machine-written, because the strongest tells are structural rather than typographic.
The following were all present in a piece that passed the dash, bullet, bold and triplet checks and
was rejected on sight.

Rhetorical section headings. Headings that pose a question, promise a revelation or land a phrase
("The thing anyone can check for themselves", "Where it earns its keep") signal an essay performing
its own structure. Name the section after its contents and move on.

The negation-then-correction construction. "It is not more information. It is less waiting." "Not a
different shape, not more detail. One number." Once in a long piece is emphasis. Three times is a
tic, and it is the single most recognisable one.

Sentence fragments for emphasis. A two word sentence following a long one is a rhythm almost nobody
uses in expository prose and every model reaches for.

Signposting and meta-commentary. "What I want to do here is", "let me lay them out plainly", "it is
worth being precise", "I should be clear about". Say the thing rather than announcing that you are
about to say it, and never describe your own writing.

Relentless symmetry. Every paragraph opening with a claim, turning on a concession and closing on a
summary is a template rather than a voice. Vary the shape, and let some paragraphs simply end.

Summarising flourishes. "That is the argument in one chart", "this is the whole problem in one
picture". They tell the reader what to think about something they can already see.

The check that works is to read the draft aloud, to grep for the constructions above, and to count
section headings that could be replaced by a plain noun phrase without loss.


## Key reference docs (in `backtesting/`)

- `RELATIONSHIPS_REGISTER.md` — what's been tested: used, discarded, unproven. Read before proposing a lever.
- `STATISTICAL_METHODS.md` — the methods, and where each sits (lab vs loop).
- `protocols/` — pre-registered analysis plans.
- Per-investigation folders under `backtesting/scripts/` — scripts + reports for each study.
