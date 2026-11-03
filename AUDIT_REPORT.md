# Final audit report

**What this document is.** The record of an audit pass over this repository taken as a submission would be
read: `paper/main.tex`, the 32 tools in `tools/`, the 455-test suite in `tests/`, the 63 published artifacts
`tools/compare_published_fingerprints.py` compares (50 under `results/`, 12 under `config/`, and the acquisition
manifest), and the six project documents. It says what was found wrong, what was changed,
what was executed rather than asserted, what was deleted, and what still stops this work being published as a
claim about the ancestry of religious narratives. It does not restate the methodology; it points at it.

**The standard applied.** Every quantitative sentence in the paper and the methodology was traced to the
artifact and the command that writes it. Where the trace existed, the number is now re-derived by a test.
Where the trace did not exist, either the measurement was published as an artifact and then quoted, or the
sentence was weakened to what the evidence supports. No number was changed to obtain a favourable result, and
no result was suppressed because it was negative: the two headline outcomes of this round are that the paper's
central historical question is **not answerable with this evidence** and that the instrument's own decision
band is **the wrong size for most of the panel it is applied to**.

---

## 1. Confirmed defects, and what each one would have cost a reader

| # | Defect | Where | What it cost | Fix |
| --- | --- | --- | --- | --- |
| 1 | The M4 verdict published nothing about the one M4 claim this corpus can score, so the block means quoted in the methodology were transcribed by hand from a terminal run | `tools/compare_models.py:2056` (`refusal`), `:2184` (`run`), `:2343` (default target) | A reviewer could not check the numbers the falsification discussion rests on | `refusal()` now embeds `m4_block_profile_gate`; `--corpus-pairs` writes `results/track_b_verdict.json` (12,566 B, status `not_yet_testable`) and the gate reading inside it |
| 2 | `--corpus-pairs` produced a 915 KB `missing_inputs` list: ~7,400 copies of the same "no dates" complaint, one per pair | `tools/compare_models.py:2210` | The published verdict was unreadable and buried the actual refusal (the derivation record) | A similarity-graph pair set is no longer asked for date fields; the pair-set name is published once. Regression test in `tests/test_model_comparison.py` |
| 3 | The chance-table SHA-256 printed in `TRACK_B_METHOD_v2.md` (§6.8) went stale the moment the scan gained a new section (`244a7fa8…` → `68585ec5…`) | `TRACK_B_METHOD_v2.md:545` | The methodology cited a digest of a file that was no longer on disk | Digest corrected; `tests/test_documented_hashes.py` recomputes every abbreviated digest printed in the six documents and fails on the next occurrence. The value has moved twice more since (`68585ec5…` → `5a54f92f…`, defect 11), which is the check behaving as designed: a digest quoted in prose is a claim about the bytes currently on disk, not a permanent name |
| 4 | The committed `results/track_b_state.html` disagreed with the committed `results/annotation_sampling_plan.json`: the page rendered a 991,703-proposition universe and two superseded inclusion probabilities while the artifact behind it said 992,144, `π=0.000952549286`, `π=0.012682040118` | `results/track_b_state.html`, `tools/render_track_b_state.py` | A shipped figure page quoting numbers that no longer exist anywhere in the repository | Rebuilt through the published sequence; `tests/test_divinity_ontology.py:568` re-renders the page into a temp dir and compares bytes, then forbids the superseded numbers |
| 5 | 24 text-mode writes across 11 tools left `\n` → `\r\n` translation to the platform, while `.gitattributes` stores bytes without conversion and the published hashes are of those bytes | `tools/*.py`, `tests/test_pipeline.py::ToolWritePolicyTests` | On Linux the same published commands would rewrite ~two dozen artifacts with different bytes, so every downstream freshness assertion would report a stale input — a reproducibility failure caused by the operating system | Each writer now names the line ending its published artifact carries; corpus readers keep `newline=""` so offsets stay byte-exact; a future undecided write fails the suite |
| 6 | The state coder's over-length accounting conflated two different counts: 97 records flagged against 59 propositions actually run on | `tools/divinity_ontology.py`, `results/ontology_run_summary.json` | A double-counted measurement presented as a sample size | Both quantities published as separate fields (`propositions_flagged_run_on`, `records_on_flagged_propositions`); the fingerprint diff classifies it as a measured change, with the cause named |
| 7 | The 0.05 chance band was set by the analyst, never calibrated, and a count of dimensions outside it was reported as if it were a count of discoveries | `tools/scan_dimension_anomalies.py:488` | The instrument's own error rate was invisible; the word "flagged" carried a meaning the band cannot bear | `chance_band_diagnostics` added (per-measurement false-positive rate, family rate, leave-one-out scatter, two-sided Monte Carlo `p`, Bonferroni survivors); paper §anomalies finding (7) reports the corpus's 5 flagged dimensions against the noise-only expectation of 0.80 dimensions rather than against zero |
| 8 | Three artifact digests quoted in `TEST_REPORT.md` §9 were stale, with no statement of why | `TEST_REPORT.md` §9 | A reader could not tell stale hashes from a changed measurement | Digests corrected to `2bdfa81f…`, `5201547e…`, `a52a8673…` and the cause published: two are tool digests that moved because those tools' sources changed, one is a stamp (`generated_at_utc` plus a new `partial_run` field) that has since moved a second time for the same reason, with `tools/compare_published_fingerprints.py` classifying the manifest's changed fields as stamps-only |
| 9 | §13's published sequence did not produce the artifacts the documents quote: the scan ran without `--write`, and the verdict existed only on stdout | `TEST_REPORT.md` §13, `README.md` | The chance table whose SHA-256 is embedded in the verdict was a file no published command wrote | Sequence corrected (`scan_dimension_anomalies.py --write`, `compare_models.py --corpus-pairs --write-to …`), and `tests/test_pipeline.py` compares the README copy with §13 line for line |
| 10 | The suite counts and the validator line count were carried between drafts by hand (historically 239 in one place and 244 in another, in the same document) | `tests/test_documented_counts.py` | Two stale numbers arguing with each other, which is what the reviewer flagged as "reported, not verified" | The collector is run in a subprocess and every printed total — abstract, data-availability breakdown, per-suite figures, §9, ARCHITECTURE, RESEARCH_PROTOCOL, the validator's line count — is checked against it |
| 11 | The scored graph's chance line was drawn over every pair of the works that carry a dimension, while the observed mean it is subtracted from was measured over the 1,237 pairs the comparison layer accepts — two different pair populations, so the published excess was not the quantity `RESEARCH_PROTOCOL.md` §12.4 declares ("the same pair graph and with the same statistic") | `tools/scan_dimension_anomalies.py` (`chance_agreement`, `chance_replicate_means`, `dimension_rows`) | Every scored-graph excess in the paper, the falsification gate that reads that table, and a published finding about how fragile the choice of pair set is | Each null replicate is now scored over the same edge set as the mean it feeds (`edges_by_key`, per dimension and per reading); `edges=None` still reproduces the complete-graph draw bit-for-bit, and the artifact publishes both lines plus a per-measurement `conditioning_gap`. Measured, not asserted: no chance line moves by more than `0.00982` against a band of `0.05`, `2` of the `18` scored band verdicts cross (both `D6_temporal_nature`, `+0.057079` → `+0.047630`), `0` adjacency verdicts change, the same six dimensions survive Bonferroni, and the M4 tie moves `-0.020395` → `-0.017394` with its status unchanged |
| 12 | A Python chained comparison inside the field that reports how much defect 11 matters (`measured[...] != abs(...) < CHANCE_BAND`) said `6` of `18` verdicts move where the arithmetic says `2` | `tools/scan_dimension_anomalies.py::chance_line_conditioning` | The one number whose job was to size the correction overstated the instrument's fragility by three times, and it was in the artifact the paper quotes | Explicit parentheses, and `tests/test_dimension_anomalies.py` recomputes the flag from the two published excesses rather than trusting it. Found by re-deriving the field outside the tool, not by a failing test |
| 13 | The paper and §12.4 named a "tighter null that preserves which values co-occur inside a work" as the remedy for the null's independence assumption. The audit ran it: it is unusable, not merely unwritten | `tools/scan_dimension_anomalies.py` (`null_model.why_not_a_co_occurrence_preserving_permutation`) | A published limitation pointed at a repair that cannot do the job, so a reader would have spent the effort to discover it themselves | Resampling whole observed value sets across works has an expectation exactly equal to the observed complete-graph mean for every live dimension — the permutation null is invariant to which work owns which set — so the excess it produces is `0.000` by construction. The impossibility is now published in place of the promise, and the remaining tightening named is a maximum-entropy model over value pairs, which this scan does not fit |

Nothing in that list is a stylistic preference. Items 1-4, 6-7 and 11 would each have led a careful reviewer to
a different number than the one the paper prints.

Two defects found earlier and recorded here because they are load-bearing for the audit's conclusion: the
recall estimator's numerator, precision correction and coverage (fixed in `tools/validate_graph_recall.py`
and re-validated), and the non-theism family counting the shahada as evidence of skepticism — the second was
found by reading the detector's output, not by a test, which is why example inspection is now part of §7's
routine rather than an afterthought.

## 2. Analyses executed, with their outputs

Every item below was run in this session and its output inspected; the first four are re-run by the suite.

- **Full suite.** `python -m pytest tests -q` → **455 passed, plus 7 parameterised subtests**
  (45 pipeline, 43 structural-engine, 19 schema, 9 divinity-census, 27 exclusivist-audit, 33 state-coder,
  13 graph-recall, 116 model-comparison, 51 anomaly-scan, 37 annotation-recall, 33 pilot-kit, 9 typesetting,
  8 documented-counts, 12 documented-hashes). Inside the anomaly suite, the 10 tests in
  `ChanceBandIsMeasuredAgainstItsOwnNull` own the band calibration and the 9 in
  `ChanceLineConditionsOnTheScoredPairs` own the pair conditioning, including the proof that permuting whole
  value sets has the observation as its expectation. Every total in this row is the collector's: a suite
  number typed by hand is defect 10, and this document is the one place the checker cannot see, so the
  figure here is copied from `tests/test_documented_counts.py`'s own output rather than remembered.
- **The published reproduction sequence, timed end to end.** 26 commands (`TEST_REPORT.md` §13). The 25
  pipeline steps all exited zero in 2,873.3 s; the whole list, suite step included, took 3,203.2 s. The
  heaviest steps are passage segmentation (800.3 s), the live re-download of all 65 works (679.6 s), the
  state coder (381.8 s) and the similarity engine (322.9 s). The suite step exited 1, and on what is worth
  recording: seven assertions refused document figures this round had invalidated — a collector total of 455
  against 441 in prose among them — which is defect 10 firing as designed, not a measurement failing. Each
  was re-pinned from the collector or the compiler, and the step exits 0 now. The per-step table is in the
  appendix.
- **Rebuild classification.** `tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json`
  against the commit the audit started from (`78b2ed7`): 63 files compared — **50 byte-identical, 7
  stamps-only, 0 removed, 0 unclassifiable, 3 added, 3 measurement-changed**. The three added are artifacts
  this audit created (`annotation_validation.json`, `corpus_live_verification.json`, `track_b_verdict.json`),
  not moved measurements. The three measured changes are named in §13 with their reasons rather than folded
  into a claim that nothing moved: `dimension_anomalies.json` (118,588 → 163,915 bytes) gained the band
  diagnostics *and* had its scored-graph chance lines re-drawn over the pairs the observed mean was measured
  on — defect 11, which moves no line by more than `0.00982` and changes 2 of the 18 scored band verdicts;
  `track_b_state.html` stopped rendering a proposition universe its own source artifact had superseded
  (defect 4); and `ontology_run_summary.json` separates the 59 propositions the over-length rule ran on from
  the 97 records it flagged on them (defect 6).
- **The instrument against its own null.** 200 seeded draws per measurement, both statistics, both pair
  populations, with the scored graph's line drawn over the same 1,237 pairs as the mean it subtracts (defect 11):
  the band's false-positive rate runs from `0.000` (10 of 18 measurements) to `0.555`
  (`D2c_worship_exclusivity`, whose null scatter is `sd 0.0845` — wider than the band judging it, against
  `0.0045` for `D4_cosmic_function`); for 8 of the 9 declared-rule measurements the band is wider than the
  95th percentile of its own noise. As a family, noise alone puts at least one measurement outside in `0.760`
  of draws (mean `1.015` measurements, `0.795` dimensions). The Monte Carlo reading disagrees with the band on
  three dimensions — `D2a` (+0.021), `D2b` (+0.030) and `D6` (+0.048) inside the band yet resolved at
  `p ≤ 0.05` — while `D2c`, which the band flags, is now resolved too at `p = 0.024876` (`5` draws in `201`), so
  the one measurement where the two readings argued has stopped arguing. Six of nine survive Bonferroni at
  `0.05/9 = 0.005556`, all six at the `1/201 = 0.004975` floor, which is a bound rather than a measurement.
- **The conditioned baseline checked against two implementations that did not share code with it.** The
  published line for each of the nine live dimensions was re-derived by an independently written draw-without-
  replacement (an exponential-race priority sampler over the same marginals and the same edge set, 20,000
  replicates): every line agrees with the published one to within two standard errors of the combined estimate,
  largest `|z| = 1.90` (`D2a`), largest absolute difference `0.0016` — smaller than the conditioning gap the
  correction exists to measure. The edge-conditioned sampler is also pinned by an exact enumeration of a
  four-work case, where the conditioned and complete-graph expectations provably differ; that one is in the
  suite, and the 20,000-replicate race ships as `audit_checks/verify_conditioned_chance_line.py` — re-run
  from that path after the scratch copy was deleted, printing the same `1.90`, the same `0.0016`, and the same
  two verdicts that change.
- **M4's block-profile gate on the corpus's own 1,237 scored pairs.** Raw similarity reverses the declared
  `structural > arbitrary` adjacency by `-0.177458`; subtracting each dimension's own chance line leaves
  `-0.017394`, inside the registered separability of 0.05. The two readings straddle the disqualification
  line, so the published status is `block_profile_verdict_depends_on_the_similarity_scale`: the committed
  falsification hook does not fire, and M4 is not confirmed either. Re-running the gate against the corrected
  chance table (`results/track_b_verdict.json`, which embeds that table's SHA-256) moved the tie and nothing
  else: the three block means are `0.117963` functional, `0.041092` structural, `0.058486` arbitrary, and
  `results/model_power_simulation.json` is byte-identical.
- **Live corpus re-verification.** `tools/verify_corpus_live.py` re-downloads all 65 works: **63 match the
  manifest byte for byte, 2 have drifted.** `australian_legendary_tales` (id 3833) is served at the same length
  with two bytes changed — `E?r moonan` → `Eaer moonan` in a word list, one line. `odyssey` (id 1727) differs at
  685,258 byte positions and 2 bytes of length, which realigns to **four** line-level edits: the publisher's
  "Most recently updated" stamp (December 2, 2023 → November 2, 2026), `edition of 894` → `edition of 1894`,
  `tune.38` → `tune.]38`, and one separator line holding only `/` deleted near the end. The earlier release of
  this tool reported the Odyssey drift as a 685,258-edit change because it counted byte offsets rather than
  lines; the tool now publishes both counts, and `results/corpus_live_verification.json` records the drift
  instead of silently adopting it. No published measurement reads the live site, so no number moved.
- **Typesetting.** A real MiKTeX 25.12 `pdflatex` compile in a clean temp directory: **43 pages** — one more
  than the 42 this document quoted before the audit's anomaly prose was added — no overfull box, no undefined
  reference, page count stable between passes; `tools/validate_tex.py` reports 0 problems over 2253 lines and
  `--self-test` requires all ten injected defect classes to fire (they do).
  The page count and that line count are claims the suite re-measures, not assertions in prose.
- **Clean clone.** `git clone` of the repository into a separate directory and `python -m pytest tests -q`
  there: reported in §5 below, because the honest sentence is that a clean clone is not this working tree.
- **Scan cost.** Keeping the per-replicate means rather than averaging them away, and then drawing each
  scored-graph line over its own edge set instead of once over the carriers, moved the scan from 8 s to 21.2 s
  (measured on a stdout-only run of `tools/scan_dimension_anomalies.py` in this session). That is the price of
  publishing the scatter and the pair set instead of only a mean.

## 3. Claims that were weakened, and claims that were never made

The audit's most common finding was not a wrong number but a sentence that assumed a licence the evidence does
not grant. What changed:

- **No transmission or descent claim anywhere.** The graph's inheritance layer ships empty because zero dated
  attestations are filled; `RESEMBLES` edges are forbidden and the promotion criterion is published. The paper
  states that dependence is flagged per pair and never filtered, because the pairs that look like transmission
  are the pairs that are the same book (15 of the top 15 by excess agreement are flagged dependent).
- **Absence-based disconfirmation of common ancestry is not used** and is recorded as a rule, not a habit: no
  number here can show that two traditions are unrelated.
- **"Multilingual" became "multilingual-ready."** The classification is detector output over English
  translations of print material; nothing in the instruments has been run in another language.
- **Every excess over chance is an upper bound.** The null preserves each work's own number of values and each
  dimension's prevalence; it does not preserve correlations between values inside a work. That is stated in the
  paper's anomaly section rather than assumed. What the audit added is the half of the specification the paper
  used to leave implicit: the null is drawn over **the same pair set** as the mean it is subtracted from, because
  a baseline from another population is not a conservative version of the right one, it is a different quantity
  (defect 11).
- **A promised null that cannot exist is reported as impossible, not as future work.** The co-occurrence-
  preserving control named in two earlier rounds of review turns out to be degenerate: a permutation of whole
  value sets between works rearranges the observation rather than modelling chance, so its excess is `0.000` by
  construction. `tests/test_dimension_anomalies.py` proves the identity on a five-work panel for both
  statistics, and `results/dimension_anomalies.json` publishes the argument under `null_model` next to the null
  it replaces.
- **The M4 comparison is symmetric.** Four models, two stages, the licence bound by
  `min(log10 BF over M2, log10 BF over M4)`, and the tie/refusal statuses published with the numbers rather
  than resolved by whichever reading is kinder.
- **The pilot reports no agreement statistic, because none exists.** Two readers have not coded the packet.
  `tools/score_annotation.py` refuses to run without two sheets, a no-record probe and a weight on every row,
  and the scorer is deliberately given less power than the packet it reads. No κ, precision or recall figure
  was invented to fill that gap at any point in this audit.

## 4. Repository cleanup

Deleted (confirmed unnecessary, all of them regenerated by the tools that own them): duplicate top-level paper
drafts and repeated result dumps found in the earlier pass, the scratch files this audit used to inspect
artifacts and to rewrite prose (`tmp_*.py`, `tmp_*.json`, `tmp_*.log`, `tmp_*.out`, `tmp_html_diff.txt`), the
rebuild and clean-clone logs whose tables are now printed in this document, and the stale fingerprint snapshot
taken before the rebuild. Nothing under `results/` or `config/` was deleted.

Promoted rather than deleted, because §2 quotes what they measured: `audit_checks/verify_conditioned_chance_line.py`
(the independently coded chance line, whose `|z|` figures appear above) and `audit_checks/time_reproduction_sequence.py`
(the timed harness behind the appendix table). A one-off analysis whose script is deleted is a claim; the same
analysis with its script shipped is a check.

Kept deliberately, because each is evidence or a regeneration input rather than debris:
`config/pre_v3_backup/` (the instrument's previous vocabulary, needed to show what the split changed),
`results/v2_manual_review.json` (a human reading of nine pairs that no tool can regenerate), the frozen v1
baseline artifacts (`results/run_summary.json`, `results/candidate_pairs.jsonl`,
`results/motif_candidates.jsonl`, `results/top_pairs_for_review.csv`, `results/model_comparison.json`), which
§12 exists to compare against, and `corpus/acquisition_manifest.json` while `corpus/raw/` and
`corpus/derived/` stay gitignored for size and licence reasons.

Orphans cannot accumulate: `tests/test_pipeline.py` fails if a file appears in `results/` without being named
in the §13 inventory, if the README's copy of the sequence differs from §13, or if the paper's
data-availability table omits a shipped artifact.

## 5. Environmental limits on the verification

- A clean clone lacks `corpus/raw/` and `corpus/derived/`, so the locator and byte-reproduction checks skip
  with an explicit reason rather than passing vacuously. Everything re-derivable from the shipped artifacts
  runs there. (Count reported in the commit message and in `README.md`, which names the same limitation.)
- Network access is required for `tools/acquire_corpus.py` and `tools/verify_corpus_live.py`; both were run
  here. Offline, the suite still passes because the artifacts are the inputs.
- A LaTeX engine is optional; without one `tests/test_tex_typesetting.py` reports a skip and the page-count
  claim in the paper is unverified on that machine. With MiKTeX installed it is measured.
- `python tools/score_annotation.py` cannot be run at all until two independent coders produce sheets. This
  is a missing input, not a failure, and it is the reason the paper's central measurement is still absent.

## 6. Plain-language explanation of the research

**What it asks.** Whether the striking resemblances between creation and flood narratives across world
traditions can be studied as a *testable* historical question — one where a machine-readable record of what a
text asserts could, in principle, support a claim about ancestry, and where the absence of such support is
visible rather than argued away.

**How it tries to answer.** Three instruments over a corpus of 65 works in English translation. A lexical
retriever finds candidate pairs. A structural engine compares event sequences, participants and outcomes. The
main one, a divine-concept state coder, reads each passage and records a small vector of declared answers to
twelve questions about what the text says gods are, how many there are, whether others are acknowledged,
whether the universe is contingent, and what kind of speech act carries the claim. Similarity is then computed
per dimension between every pair of works — 2,080 work pairs, of which the comparison layer agrees to score
1,237 — and, crucially, compared against a chance line: a seeded null in which every synthetic work keeps the
same number of values, drawn from the same prevalence, but carries no structure. Four competing models
(independent origin, shared inheritance, cultural convergence, and an attractor model) are then scored on the
same pair sets, and a verdict requires clearing evidence floors that were themselves simulated rather than
declared.

**What it found.** The instruments work, and the historical question is not answerable yet. Concretely: three
of the twelve dimensions fire on no work at all, so the frame is partly untested; the chance-corrected block
profile that the attractor model's one falsifiable prediction depends on reverses on raw similarity and turns
into a tie once base rates are subtracted, so the registered refutation did not fire and neither did
confirmation; the analyst-set 0.05 band used to call an excess "anomalous" turns out to have a false-positive
rate between `0.000` and `0.555` across the panel, so the five dimensions it flags are reported against a noise
expectation instead of against zero; one apparent discovery of this round — that which pairs you choose to
compare decides which concepts look anomalous — was an error in the instrument's own baseline, and with the
baseline drawn on the right pairs no verdict depends on the pair population at all; and the pairs that most look
like borrowing are reprints of the same book.
The one thing that would move this from description to history — two independent coders agreeing on the same
packet — does not exist yet, and the repository now ships the handout, the scorer, the refusals and the
weights that a second coder would need, so that the missing measurement can be produced by someone else.

**What remains unresolved.** Whether anyone should read these dimensions as evidence of descent. Not answerable
until (a) human coding establishes that the detector measures what the frame says it measures, (b) dated
attestations fill the inheritance layer, and (c) the classification is checked beyond English translations.

## 7. Publication-readiness assessment

**Assessment: publishable as a methods and instrumentation paper; not publishable as a result in comparative
religion or the anthropology of religion.** The contribution that survives review is a falsifiable,
reproducible framework plus a set of negative and self-reflective findings about what such an instrument can
and cannot say: a chance model for value agreement, drawn on the pair set it subtracts from, a gate that reports
scale-dependence instead of picking a side, a family-wide calibration of its own decision band, a published
proof that the obvious co-occurrence-preserving control cannot work, and a refusal architecture in which every
missing input is named rather than papered over. The contribution that is *not* supported is any claim about the
ancestry of the narratives. The paper says so; the audit did not find a way to say it louder without changing
the evidence.

**Blockers, in the order they can be cleared.**

1. **No inter-coder reliability.** One person wrote the frame and one person applied it. *Clears when* two
   independent coders return the pilot sheets and `tools/score_annotation.py` runs; the agreement statistic,
   the detector's precision and recall against human coding, and the stratum weights are already published so
   that the result is computable the moment the sheets exist.
2. **No dated attestation layer.** `results/attestation_scaffold_summary.json` carries the structure for all 65
   works and 0 of them are `works_usable_for_priority_claims_today`: 22 works have an edition or translation
   date filled and 43 have nothing, and an edition date constrains when the English wording existed, not when
   the concept was held. The composition and earliest-witness columns are empty for every work, so the
   inheritance layer is empty by construction. *Clears when* those columns are filled by specialists and
   audited; until then no `DESCENDS_FROM`/`BORROWS_FROM` edge may be asserted and none is.
3. **Detector output, not reading.** The classification is rule- and lexicon-driven over English translations
   of print material selected for retrievability. *Clears when* the human coding in (1) is compared against
   detector output per dimension and the un-attested lexicon entries are either attested or removed from the
   candidate path.
4. **The null assumes independence between values inside a work.** Every published excess is therefore an
   upper bound on attributable structure. This audit ran the repair the earlier rounds named — resampling whole
   observed value sets between works — and it is unusable: for a mean taken over every pair of a set of works a
   permutation is a rearrangement of the observation, so the excess that null produces is `0.000` by construction
   for all nine live dimensions. *Does not clear by resampling.* What is left is a fitted model rather than a
   control — a maximum-entropy distribution over value pairs that reproduces each work's marginals and its
   within-work co-occurrence — which would have to be preregistered before any excess it produces could be
   quoted. The paper and `results/dimension_anomalies.json` now say this instead of promising a permutation.
5. **Corpus composition.** 65 works, one language family of sources, publisher-edited in place (one file
   already drifted). No conclusion here depends on the corpus being representative, and the paper says it is
   not one. *Reviewer-facing limitation* rather than a blocker.

**Not blockers.** The three dead dimensions, the reversed raw block ordering, the tie after chance correction,
the band's false-positive spread, the dependence-flagged top pairs, and the empty adjudication layer are
results. They are reported with their numbers and they are what the audit was for.

## Appendix: the timed rebuild

The sequence was timed by a harness that read the 26-command list out of `TEST_REPORT.md` §13 rather than
retyping it, ran each command with `cwd` at the repository root, and recorded exit status and wall-clock
seconds. The harness ships as `audit_checks/time_reproduction_sequence.py` and writes its logs to a
temporary directory unless told otherwise, so timing a build never dirties the tree; the two log files from
this run are scratch and were deleted, and the table below is what they measured, on 3 November 2026, on the
machine that builds this paper.

| # | Command | Exit | Seconds |
| --- | --- | --- | --- |
| 1 | `python -m pytest tests -q` | 1 | 329.9 |
| 2 | `python tools/acquire_corpus.py` | 0 | 10.9 |
| 3 | `python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json` | 0 | 679.6 |
| 4 | `python tools/build_passages_v2.py` | 0 | 800.3 |
| 5 | `python tools/run_similarity_v2.py` | 0 | 322.9 |
| 6 | `python tools/cleaning_ablation.py` | 0 | 220.6 |
| 7 | `python tools/validate_annotations.py --write-to results/annotation_validation.json` | 0 | 1.3 |
| 8 | `python tools/narrative_similarity.py --lexical` | 0 | 36.9 |
| 9 | `python tools/build_relevance_graph.py` | 0 | 5.0 |
| 10 | `python tools/validate_results_v2.py` | 0 | 10.5 |
| 11 | `python tools/divinity_terms.py` | 0 | 42.4 |
| 12 | `python tools/audit_exclusivist_matches.py` | 0 | 84.2 |
| 13 | `python tools/divinity_ontology.py` | 0 | 381.8 |
| 14 | `python tools/build_ontology_graph.py` | 0 | 14.8 |
| 15 | `python tools/validate_graph_recall.py` | 0 | 46.5 |
| 16 | `python tools/build_attestation_scaffold.py` | 0 | 0.5 |
| 17 | `python tools/check_recall_cues.py` | 0 | 52.5 |
| 18 | `python tools/prepare_annotation_packet.py` | 0 | 82.8 |
| 19 | `python tools/make_pilot_packet.py` | 0 | 0.8 |
| 20 | `python tools/render_track_b_state.py` | 0 | 2.5 |
| 21 | `python tools/scan_dimension_anomalies.py --write` | 0 | 28.7 |
| 22 | `python tools/compare_models.py --corpus-pairs --write-to results/track_b_verdict.json` | 0 | 0.8 |
| 23 | `python tools/compare_models.py --power` | 0 | 40.6 |
| 24 | `python tools/validate_tex.py` | 0 | 0.4 |
| 25 | `python tools/validate_tex.py --self-test` | 0 | 0.8 |
| 26 | `python tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json` | 0 | 5.2 |
| — | **Total, 26 commands** | — | **3,203.2** |

Two readings of this table matter for a reviewer planning a reproduction. First, the 3,203.2 s is one wall
clock on one machine with the corpus already on disk; the four heaviest steps account for 2,184.6 s of it,
and one of those four (step 3) is the only step that reads a network. Second, the suite step is not a fixed
cost either: the same 455 tests measured 329.9 s in this run and 170.8 s when re-run minutes later on warm
caches, so neither figure is a property of the code. Step 1's exit status is the run's most useful result,
and §2 records what it refused.
