# Corpus, Retrieval and Structural Comparison Test Report — 2 November 2026

## 1. Purpose and scope

This report records what the computational stages of the project actually demonstrate. Three questions are separated deliberately:

1. **Provenance.** Can the corpus be acquired, cleaned, hashed and re-verified byte-for-byte?
2. **Candidate retrieval.** Can lexical similarity find reusable text, and how many of its hits are already-known dependence?
3. **Structural comparison.** Can coded narrative events, participants, motifs, causal links and symbols be compared without producing an ancestry claim?

No stage here estimates the probability of common descent, borrowing, or a global origin. The earlier 42-work snapshot is superseded for analysis and retained only as a frozen baseline (`results/run_summary.json`, `results/model_comparison.json`).

## 2. Corpus snapshot (v2)

| Measure | Value |
|---|---:|
| Works successfully acquired | 65 |
| Region labels | 14 |
| Distinct source roles | 20 |
| Source words | 9,568,271 |
| Raw bytes retained | 56,619,411 |
| Passages segmented | 34,281 |
| Passages excluded by cleaning or length | 10,896 |
| Passages entering retrieval | 23,385 |
| Eligible words | 8,731,101 |

Composition of the retrieval set by region (eligible words): South Asia 3,820,431 (43.8%, 16 works), West Asia and Europe 1,098,929 (12.6%), Europe 966,171 (11.1%), North America 939,428 (10.8%), East Asia 689,283 (7.9%), Southeast Asia 262,291 (3.0%), West Asia 250,110 (2.9%), Sub-Saharan Africa 207,079 (2.4%), South Asia and West Asia 167,258 (1.9%), Oceania 127,301 (1.5%), West Asia and South Asia 95,049 (1.1%), Central and South America 84,624 (1.0%), East Africa and West Asia 20,086 (0.2%), Central America 3,061 (0.0%).

External stability of those 65 files is a separate question from internal freshness, and it is now measured rather than assumed: `python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json` re-downloads every work and compares the bytes with the manifest (the published run is recorded 2026-11-03T12:30Z). 63 of 65 still match; two have drifted. `australian_legendary_tales` (Gutenberg 3833) drifted in place: the live copy is served at the identical 207,276 bytes and differs at two byte positions starting at offset 184,973, where the acquired word-list entry `Eär moonan` now reads `Eaer moonan`. `odyssey` (Gutenberg 1727) is served two bytes shorter, its first difference at offset 664, where the header line `Most recently updated: December 2, 2023` now reads `November 2, 2026`. Because that copy's length changed, the positional comparison reports 685,258 differing offsets for it, which counts the shift rather than the edits — so the tool now aligns the two copies line by line as well and publishes the separate edits it finds, four for `odyssey`: that header date, a numeral restored in the preface (`of 894` becomes `of 1894`), a footnote marker added to a body line (`tune.38` becomes `tune.]38`), and one separator line holding only `/` deleted near the end. Neither drift moves a number in this repository — every artifact is pinned to the hash the manifest recorded, and the suite re-hashes those bytes — but a fresh acquisition no longer reproduces the shipped corpus for those two works, so the manifest, not the live site, is the authority for this study. The drift count is a snapshot rather than a constant: runs on consecutive days returned 1 and 2 drifted works, and a run earlier on the same morning as the published one could not reach a third work at all and reported 62 matches, 2 drifts and 1 fetch failure — which is why the status column keeps `fetch_failed` apart from `drifted`, rather than letting an unreachable server read as a changed text. `tests/test_pipeline.py` refuses a verification artifact whose `manifest_sha256` is not the current manifest's, one whose `tally` is not the status column beneath it recomputed, and prose in `paper/main.tex`, this report or `README.md` that quotes a match count the artifact does not record.

The snapshot is English-translation heavy and still dominated by South Asian print sources. It is a retrieval testbed, not a balanced global sample, and public-domain status in the United States settles neither copyright elsewhere nor Indigenous cultural permissions. Historical ethnographies and secondary retellings are labelled separately from primary translations; 19 works carry the role `historical_ethnography` and 7 `secondary_retelling`.

## 3. Methods

1. Download raw UTF-8 text; record source page, acquisition time, title metadata, byte count and SHA-256 for every work.
2. Strip only Gutenberg start/end boilerplate; keep the raw source unchanged and store clean offsets against raw offsets.
3. Segment into 350-word windows, merge tails shorter than 80 words, then classify passages against cleaning rules that remove front matter, introductions, footnotes, appendices, indices, publisher apparatus and other non-narrative material.
4. Fit TF-IDF over eligible passages only: unigrams and bigrams, English stop words, sublinear term frequency, `max_df=0.85`, `min_df=2`, 120,000-feature cap, float32, L2 normalisation.
5. Retain up to six cross-work neighbours per passage at cosine ≥ 0.15.
6. Label every candidate pair against `config/source_dependence.json` (15 pair rules plus 1 work family) before any ranking is published.
7. Compare against 20,000 random cross-work pairs and 20,000 length-matched pairs; run known-overlap positive controls; run order diagnostics on 256 sampled passages.
8. Run an exploratory bounded-regex motif lexicon (8 categories). Motif hits are retrieval candidates, never annotations.
9. Repeat the run and compare output hashes. Seed `20261031`.

## 4. Retrieval results

| Measure | Result |
|---|---:|
| Candidate cross-work pairs | 9,428 |
| Pairs joining configured dependent works | **8,677 (92.0%)** |
| Pairs not known dependent | 751 |
| Random-pair mean | 0.0121 |
| Random-pair median / p95 / p99 / max | 0.0104 / 0.0293 / 0.0416 / 0.0747 |
| Length-matched mean (mean absolute word-count difference 11.8) | 0.0126 |
| Length-matched p95 / p99 / max | 0.0303 / 0.0426 / 0.1209 |
| Positive control: Qur'an text in two anthology volumes | 0.6000 |
| Positive control: Dhammapada text repeated in *Sacred Books of the East* | 0.6166 |

The 92.0% figure is the headline. At this corpus size, high near-verbatim English overlap is overwhelmingly an artifact of shared editions, quotations, anthologies and retellings. Retrieval therefore works as designed for reuse detection; interpreted as a discovery ranking it mostly re-ranks the printing history of the corpus.

### 4.1 Cleaning ablation

`results/v2_cleaning_ablation.json` refits the same vectorizer over the unfiltered passage set, so the comparison also carries vocabulary and IDF effects and is reported as descriptive.

| Configuration | Candidate pairs |
|---|---:|
| Unfiltered (34,281 passages) | 29,048 |
| Pairs involving rule-excluded apparatus passages | 2,227 |
| Pairs involving sub-threshold short passages | 16,703 |
| Pairs between eligible passages only (unfiltered vectorizer) | 10,689 |
| Published cleaned run (refit vectorizer) | 9,428 |
| Count reduction from unfiltered | 67.5% |

Two numbers must not be conflated. The 67.5% reduction compares the unfiltered run (29,048) with the published cleaned run (9,428); because the two vectorizers are fitted separately, part of that difference is vocabulary, IDF and per-passage neighbour-cap behaviour rather than passage exclusion. Holding the unfiltered fit fixed, restricting to eligible passages leaves 10,689 pairs, which is the closest available estimate of the exclusion effect alone (−63.2%). The runs are not nested, so the split is approximate and is reported as such rather than as a decomposition.

**Cleaning has a measured recall cost.** Seven of the 95 quoted evidence fragments in the annotation set fall on passages the cleaning rules exclude — the Popol Vuh wooden-people events (`pop_e1`–`pop_e5`) and two Ymir body events (`ymir_e1`, `ymir_e5`). The narratives are present in the corpus, but the specific windows the coder cited were classified as apparatus or too short, so the retrieval layer cannot currently reach them. The correct claim is therefore that cleaning substantially reduced retrieval candidates while introducing identified recall failures that still need validation — not that cleaning removed nothing of substance.

### 4.2 Model diagnostics

| Diagnostic | Value |
|---|---:|
| Original vs word-shuffled, unigram+bigram | 0.7125 mean |
| Original vs sentence-shuffled, unigram+bigram | 0.9858 mean |
| Original vs word-shuffled, bigram-only | 0.1071 mean |
| Original vs sentence-shuffled, bigram-only | 0.9649 mean |

Sentence shuffling is almost invisible to the model, so lexical relevance does not encode discourse order, let alone event structure. The mixed model is retained for candidate discovery only.

### 4.3 Exploratory motif keyword counts

serpent 2,296 · storm/lightning 2,033 · flood/destruction 743 · divine weapon 459 · return from death 248 · death/descent 56 · creation from body 16 · water release 4 (passages with any hit: 4,745).

The rare tags are far too thin for distributional inference at 65 works. Low counts measure lexicon recall, not the absence of the narratives.

## 5. Source-context review

Nine leading discovery pairs were reviewed manually (`results/v2_manual_review.json`). The review guides dependence rules; it is not a labelled ground-truth sample and supports no precision or recall claim.

| Score | Pair | Classification | Action |
|---:|---|---|---|
| 0.9544 | *Myths and Legends of China* / *Strange Stories from a Chinese Studio* | secondary retelling of identified tales | excluded |
| 0.5605 | *Mabinogion* / *Celtic Myths* | secondary retelling (Taliesin) | excluded |
| 0.5166 | *Myths of the Cherokee* / *Creek Migration Legends* | formulaic or linguistic material, not an aligned narrative | not read as a parallel |
| 0.4994 | *Myths of Mexico and Peru* / *Myths of the North American Indians* | title-page artifact | retained as a cleaning failure |
| 0.4566 | KJV / *The Chaldean Genesis* | direct biblical quotation | excluded |
| 0.4342 | *Myths of the North American Indians* / *Myths of the Cherokee* | secondary retelling (animal councils) | excluded |
| 0.4225 | *Myths of the North American Indians* / *Myths of the Iroquois* | secondary retelling (skeleton, pipe, flint, mice) | excluded |
| 0.4056 | *Japanese Fairy Tales* / *Myths and Legends of Japan* | shared tale retelling | excluded |
| 0.3930 | *Philippine Folk Tales* / *Tinguian Traditions* | shared collector textual material | excluded |

Two categories recur: reuse of one collector's text inside another book, and non-narrative apparatus (title pages, songs, dialect material). Both are properties of the corpus, not findings about myth.

## 6. Structural comparison engine

`tools/narrative_similarity.py` (engine version 1.1) scores coded narrative versions, not word windows. Inputs are `config/annotated_versions.json` (14 versions, 4 comparison classes, 94 events, 218 participant role assertions, 76 causal links, 38 preregistered motifs asserted 78 times, 87 symbol assertions, 95 machine-verified quoted fragments; 4 versions on fragmentary attestations) and `config/source_dependence.json`.

Preregistered configuration, fixed on 1 November 2026 before any pair was scored and never fitted to an outcome: Needleman–Wunsch with gap `g = 1.0`; event similarity `e(a,b) = (0.50·predicate + 0.30·participant + 0.20·outcome) / (weights of measurable parts)` with predicate credit 1.0 exact / 0.5 same family / 0 otherwise, participant pair credit 1.0 / 0.5 / 0.25 / 0 by role and asserted referent, and outcome lexical overlap; `S_sequence = 1 − D_mn / max(m,n)`; weighted Jaccard motifs restricted to the assessed domain; 200 permutation draws; seed 20261031.

91 unordered version pairs were compared. All 91 receive sequence, causal, role and symbol values; 25 receive a motif value and 66 return `NA` because the pair crosses comparison classes whose motifs the coder never adjudicated. The engine emits **no composite score and no historical field**.

### 6.1 Controls

| Control | Result | Status |
|---|---|---|
| Same narrative, dependent witnesses | 2 pairs; mean `S_sequence` 0.816, min 0.632, max 1.000 | passed |
| Predicted-unrelated negatives | 6 pairs; mean `S_sequence` 0.031, max 0.045 | passed |
| Discrimination violations (negative ≥ dependent witness) | 0 | passed |
| Translation-renaming stability (random aliases on every participant) | max absolute change 0.0 on 91 pairs | passed |
| Motif invariance under event reordering | mean absolute change 0.0 | passed |
| Internal doublet anchor (Mahābhārata Manu fish, book 3 / book 12) | 1.000 on all five components, 9 aligned events, 0 gaps | passed |
| Cross-class motif semantics | `NA`, never 0 | passed |
| Thin motif domains | 25 scored pairs; 3 over a domain of 1, 8 over ≤ 2, 10 at full class domain | reported, not read as agreement |

### 6.2 Order sensitivity — a gate that failed

Permuting one event sequence lowers `S_sequence` by only **0.0186 on average**, below the preregistered floor of 0.02, and 5 of 91 pairs exceed `p ≤ 0.05` against the permutation null. This is recorded as a failed check (`results/narrative_validation.json`, `order_sensitivity.passed = false`) rather than tuned away.

The cause is arithmetic. Mismatch cost is `1 − e(a,b)`, which lies in `[0, 1]` and therefore never exceeds the preregistered gap of 1.0, so gapping both events always costs at least as much as aligning them. Under those settings Needleman–Wunsch behaves like a maximum-weight order-preserving matching: 91 of 91 pairs matched every event of the shorter sequence. Order is still visible — the loss against the crossing relaxation averages 0.0131, is non-zero for 77 of 91 pairs, and reaches 0.101 — but `S_sequence` must be described as an **event-matching score, not a plot-order score**. Lowering the gap would import a free parameter and move the ranking by roughly that amount (see 6.3).

### 6.3 Robustness and cross-measure agreement

| Variant | Mean absolute rank shift | Kendall τ | Pairs |
|---|---:|---:|---:|
| gap 0.5 / 0.75 / **1.0** / 1.25 / 1.5 | 0.291 / 0.262 / **0.001** / 0.231 / 0.284 | 0.106 / 0.200 / **0.998** / 0.344 / 0.190 | 91 |
| same-family predicate credit 0.25 / 0.5 / 0.75 | 0.011 / 0.001 / 0.006 | 0.975 / 0.998 / 0.988 | 91 |
| motif weight cap 0.6 / 0.8 / 1.0 | 0.013 / 0.000 / 0.000 | 0.973 / 1.000 / 1.000 | 25 |
| leave-one-region-out empirical weights (`1/log(2+versions)`) | ≤ 0.017 for all 6 folds | 0.967 – 1.000 | 25 |

The shift is mean |rank displacement| divided by the full ranking range (P−1), so 0 means the variant reproduces the published order and 1 means it reverses it; τ is reported alongside because a shift of 0.29 on a 91-item ranking is only interpretable against the range. The last two rows re-rank the 25 pairs that have an assessed motif domain, since the cap and the empirical weights cannot change a pair whose motif component is `NA` — comparing them against all 91 would have measured nothing.

The ordering is parameter-bound on alignment settings, not on the judgement weights: at the preregistered g = 1.0 the sweep reproduces its own ranking (0.001, τ = 0.998), while every other gap moves it by roughly a quarter to three-tenths of the whole range and τ falls to 0.11–0.34. Across the 78 pairs carrying both measures, Spearman ρ between `S_sequence` and the lexical cosine (a maximum over the passage windows the annotation cites, not a whole-work maximum) is **0.264**. The textbook `p = 0.019` is **not admissible** — the 91 pairs share 14 versions, so 13 of every 14 observations move together — and a quadratic-assignment permutation test on version labels (200 draws, seed 20261031, 12 extremes, p = (1+12)/(1+200)) returns **p = 0.0647**. The published block therefore states `status: exploratory`, records `independence_p_value_status`, and carries the QAP parameters so the value can be recomputed. Worked disagreements: Noah–Gilgamesh scores 0.095 on events against 0.550 on adjudicated motifs (domain 4); Noah–Manu scores 0.243 structurally against 0.0358 lexically; the abridged *Celtic Myths* Taliesin drops three drops of grace, the year and a day and the blind fire-tender, and its motif domain falls from 11 to 5 while the event skeleton still aligns at 0.632.

## 7. Graph layers

`results/v2_relevance_graph.json` (schema 3.0) aggregates the 9,428 passage pairs into 201 work pairs (152 not known dependent, 49 configured dependence) and publishes five layers so that a retrieval artifact cannot be read as a conclusion. The candidate layer is deliberately a sampled triage list, not a complete map:

| Layer | Edges | Meaning |
|---|---:|---|
| `source_dependency` | 60 | work-level premises (translation, quotation, anthology, retelling); not discovered |
| `similarity_candidates` | 149 | `RETRIEVED_AS_CANDIDATE` only: top 100 independent work pairs plus all 49 dependence controls, over 60 work nodes |
| `narrative_structure` | 91 | `COMPARED_WITH`: the alignment produced a component vector for these two coded versions. No composite, no historical field, and explicitly **not** a verdict of resemblance |
| `historical_context` | 0 (65 nodes) | bibliographic and regional context, no relationship edges |
| `adjudicated_historical_relationships` | 0 | empty by design until source criticism produces claims |

An interactive canvas version is regenerated by the same script.

### 7.1 Track B dimension-state graph — the full-corpus layer

`tools/build_ontology_graph.py` replaces the sampled triage above for the divinity question. Its first release
blocked candidate pairs with MinHash banding, wrote every pair the banding produced, and called that complete
because nothing was discarded after generation; `tools/validate_graph_recall.py` measured the blocking step and
found it recovered 2.3% of the pairs it claimed to enumerate. The layer now ships the thing the sketch was
approximating: an **exact inverted index** over live `dimension=value` states, joined posting-list by posting-list
work-pair by work-pair. The index is also published — `results/ontology_passage_index.json.gz`, 44 features and
30,070 postings — so the complete pair set is reconstructible by a reader who has the file and no code.

`results/ontology_graph.json` carries a `candidate_generation` block whose `method` is `exact_inverted_index_join`
and whose `approximation` says NONE for the join, and it separates the two different completeness questions that
the earlier artifact conflated: `coverage_of_the_relation` is COMPLETE (every cross-work pair sharing a live coded
state is enumerated), while `coverage_of_anything_beyond_the_relation` is INCOMPLETE, because 40 of the frame's 93
declared values carry no English pattern and 9 are `not_yet_instrumented`. Those two are indistinguishable from
inside the artifact, so **a missing edge is never a missing relationship or a missing state**.

| Layer | Size | Meaning |
|---|---:|---|
| `1_source_dependency` | 60 edges | configured reprint, quotation and retelling premises; not discovered |
| `2_dimension_state_attestation` | 65 works × 12 dimensions = 780 matrix cells (`ontology_work_states.csv` itself is the finer per-work × per-value inventory: 65 × 93 = 6,045 rows) | per-work state inventory, rendered as a matrix |
| `3_passage_pair_shared_states` | **22,940,506 pairs enumerated, 41,238 edges displayed** | two passages in different works share at least one live dimension state; **not** similarity of doctrine. The enumeration is exact; the edge file is a declared display slice, top 20 pairs per connected work pair by shared-state count, and the complete per-work-pair counts live in `ontology_workpair_dimensions.csv` |
| `4_inheritance_and_transformation` | **0 edges, `unpopulated_by_design`** | needs dated expressions and contact routes; the fields it requires are printed in the artifact |
| `5_coverage_and_absence` | 9 values not yet instrumented | which values the detector cannot see, so a gap reads as an instrument gap |

The passage × value matrix is 23,385 rows × 50 value columns = **1,169,250 cells**, the 50 columns being exactly
the dimension-value combinations the run produced at least once — 43 of the frame's 93 declared values never
matched and have no column, so a missing column is an instrument state and not an absence. The attestation table
is **47,641 records** over 36,775 distinct propositions and 34,584 utterance windows. Of the 2,080 possible work
pairs, **2,078** are connected by at least one sharing pair, and the 22,940,506 distinct pairs are 23.3% of the
98,497,630 naive pair space over the 14,036 passages carrying live states; counted per feature instead of per pair
the same enumeration is 31,851,655, the difference being pairs that share more than one state.

What that replaced is measured rather than asserted. `tools/validate_graph_recall.py` now reports the superseded
banding **corpus-wide**, against the exact enumeration as its denominator: 538,529 of the 22,940,506 pairs
recovered, a recall of **0.023475**, with 4,203,223 pairs lost to the 400-row bucket cap and 18,198,754 lost to
banding itself, and 0.206698 if the cap were removed. It also keeps the original deterministic-subset measurement,
in which the banding recovered 9,600 of 413,552 exactly-sharing pairs inside a stratified subset of 1,632 of the
14,036 live passages (1,330,896 pairwise comparisons) — a recall of **0.023214**, with 48,043 lost to the cap and
355,909 to banding, and 0.139385 without the cap. The two figures agree closely, which is what makes the older
subset-only number trustworthy; **0.023214 is nonetheless a subset measurement and is quoted as one wherever it
appears.** Both runs are also checked for precision: every candidate of both the capped and the uncapped run
shared a live state (538,529 of 538,529, and 4,741,752 of 4,741,752), so banding's only defect was coverage, not
noise. Three figures are drawn from those complete counts, not from a sample: the work × dimension heatmap (all 65
rows, `no_candidate` rendered as its own category), the assertion-state stack per dimension, and the speech-act
distribution of the plurality family. Two runs of the builder over identical input now write byte-identical
artifacts: the gzip streams carry `mtime=0` and no stored filename (`tools/deterministic_gzip.py`), which a test
checks in the header bytes rather than by re-running the pipeline.

**Two locator defects found by the instrument's own test suite.** `tests/test_divinity_ontology.py` was written
against the published coordinates rather than the code, and the first run failed two assertions that no count
would have shown:

- a record's `char_start`/`char_end` were the *window* bounds, and `window_char_start` held the match start —
  two fields with the same name pointing at different things. The packet groups rows to code, so
  on the old semantics it was grouping by match position: the same sentence was coded several times, and the
  window a coder saw did not belong to the span that was published. The instrument now emits `char_start`/
  `char_end` for the matched expression, `window_char_start`/`window_char_end` for the utterance window and
  `proposition_char_start`/`proposition_char_end` for the proposition actually being coded, all half-open and in
  raw coordinates. The packet is therefore **6,199 propositions** — 4,699 machine-flagged claims plus 1,500
  propositions the detector produced no record for, one coding target per claim, with the window
  carried beside it as context — and 3 of them carry two different machine values on the same single-valued
  dimension (10 records in the run carry a `value_conflict` list), which the key flags instead of assigning a
  winner; 9 packet propositions are flagged overlong.
- `normalise()`'s raw-offset map was longer than the normalised text it described: the final segment extended
  `range(cursor, cursor + len(text))` instead of `range(cursor, len(text))`, so indices past the true end of a
  run resolved to positions the reader cannot slice. Fixed, with a test that walks the map and asserts it is
  exactly as long as the text and reproduces the normalised string.

Neither defect moved a published count in the run where it was found — the totals were identical before and
after the fix. Both would have made the coordinates a coder is asked to trust wrong, which is the kind of error
that survives a review of totals. The v3 counts did move afterwards, and for stated reasons: the unit changed
from window to proposition (47,641 records, 36,775 propositions, 34,584 windows), the composite D2 and D7 columns
were split into D2a–c and D7a–d, and the refusal state was deleted rather than re-tuned, so the run reports
47,122 `candidate`, 140 `candidate_requires_human_disambiguation` and 379 `not_yet_instrumented` with no refusal
row at all.

**The packet could not measure recall, so it now samples the propositions the detector missed.** The three
candidate strata all draw from propositions that already carry a machine record, which means they can bound
precision and cannot say anything about misses — a sample of hits contains no misses — and the graph layer's
pairing recall (0.023214 measured on the deterministic 1,632-passage subset, 0.023475 corpus-wide, both now
superseded by the exact index) was never the detector's recall. `tools/prepare_annotation_packet.py` now enumerates the detector's
own proposition universe over the eligible passages (**1,028,478** segments, **36,334** of them carrying an asserted
candidate and **992,144** carrying nothing the detector asserted) and draws two disjoint simple random samples from
the no-record part: **900** of the 944,833 cue-negative segments (π = 0.000952549286, w = 1,049.8144) and **600** of the 47,311
cue-positive ones (π = 0.012682040118, w = 78.8517). Each probe row carries its exact inclusion probability and
weight into the answer key, and the cue list that decides which stratum a segment falls in
(`config/recall_probe_cues.json`, 111 cues, each counted over the eligible passages by
`tools/check_recall_cues.py`, with 6 ambiguous cues retired and their reasons recorded) is marked
`not_a_detector: true`: a cue decides where to look and never what to record. Two strata rather than one because
misses concentrate where the text names a divinity; a single uniform draw would spend almost every row where
nothing is, and the dense part would go unmeasured. Probe rows are indistinguishable from detection rows in the
coder view, so neither kind can be coded to a different standard.

The frame is drawn on `assertion_state: candidate`, and only that state. **441** propositions carry a machine
record and still carry no detection: **379** `not_yet_instrumented` records and **140**
`candidate_requires_human_disambiguation` records — **519** records in all — name values the detector either
declares it has no instrument for or declined to choose. The first build of the probe counted all of them as
hits, which did two damaging things at once: it gave five values a nonzero numerator and a published recall for
an instrument that was never written, and it removed their propositions from the very frame a miss is measured
in. They are still sampled, in the candidate strata, because a human read of them is how such a value gets
validated; they are simply not detections. `tools/score_annotation.py` keeps the two
estimands apart: per-value precision is computed on `machine_candidate` rows only, and recall is a
Horvitz–Thompson estimate whose numerator is `detected_v` multiplied by the share of flagged propositions both
coders actually kept — a false positive cannot be a true positive — over a denominator that adds the probe rows
*both* coders independently read as carrying value `v`, weighted by 1/π and divided by the share of the drawn
stratum that was realised. The uncorrected figure is published beside it as an upper bound. A stratum that finds
no miss returns a one-sided exact binomial bound on its miss share, not a recall of
1.0, and a value the probe never produced returns no estimate. A blank draw counts as uncovered, not as coded
and empty, so a half-coded stratum widens the miss estimate instead of shrinking it. The scorer refuses a key
with no probe rows, a probe row with no weight, and a stratum whose rows report two different populations.
`tests/test_annotation_recall.py` (37 tests) pins the arithmetic, the refusals, the
two-estimand separation, the detection frame, and the accumulation bug that made `undecidable_selection_rate` report only the last
row it read. **No human has coded the packet, so no recall figure exists yet either** — the instrument to measure
it does, which is the whole of the change.

### 7.2 The instrument measured against its own chance line

`tools/scan_dimension_anomalies.py` turns the state coder on itself and publishes
`results/dimension_anomalies.json`. Every dimension is measured twice — once with the statistic the frame
declares (exact match on a single-valued key, Jaccard on a set-valued one) and once as set overlap — over two
pair populations: the carrier graph (every pair of works that both carry the key) and the scored graph (the
1,237 of 2,080 pairs that `compare_models.similarity_between` agrees to score, at ≥ 6 comparable keys, covering
52 of the 65 works). Each measurement is then compared to a chance line produced by a per-dimension
configuration model: 200 seeded draws (seed 20261102) in which each synthetic work takes exactly as many values
as the real work it replaces, weighted by that dimension's observed prevalence, and the synthetic pairs are
scored with the same statistic over the same pairs. On the carrier graph that is every pair of the works carrying
the key; on the scored graph it is exactly the edge set the observed mean was measured over, per dimension, which
is the difference between a conservative baseline and a baseline from a different population -- the artifact
publishes both lines and the gap (`pair_graph.chance_line_conditioning`). A permutation control is not used and
cannot be: the mean over a complete graph is invariant to permuting which work owns which set, so a label-shuffled
control returns the observed number and calls it a null. That is also why the co-occurrence-preserving control
asked for in two earlier review rounds is published as an impossibility rather than run as an experiment.

What the corpus reports about the instrument:

| Finding | Number |
| --- | --- |
| Declared dimensions that fire on no work | 3 of 12 — `D7b_speech_act`, `D7c_discourse_genre`, `D7d_epistemic_commitment` (0 of 65 works) |
| Dimensions inside the 0.05 chance band on the scored graph | `D2a` (+0.021), `D2b` (+0.030), `D6` (+0.048), `D7a` (+0.006) under both statistics |
| `D7a` observed vs its own base rate | 0.510 vs 0.504; under the endorsement frame the excess is −0.006, i.e. no direction |
| Live single-valued cells where exact match has no defined answer | 89 of 157 works (0.567) carry >1 value on a key declared single-valued |
| Largest movement of a dimension's mean between the two graphs | `D4_cosmic_function` +0.0988 — larger than the chance band itself |
| Largest movement of a *chance line* from conditioning it on the pairs | `0.00982` (`D6_temporal_nature`, set-overlap reading) against a band of `0.05`; `2` of the `18` band verdicts cross and `0` adjacency verdicts do |
| Block ordering the corpus gives, raw | functional 0.636 > arbitrary 0.542 > structural 0.365, so the declared `structural > arbitrary` adjacency is reversed by −0.177 |
| Same blocks, chance-corrected | functional +0.118, arbitrary +0.058, structural +0.041 — a −0.017 gap, inside the registered 0.05 separability, hence a tie |
| Pairs where the arbitrary block out-agrees the functional block | 550 of 1,237 |
| Dependence among the top 15 pairs by excess agreement | 15 of 15 flagged (`mahabharata_v3`/`mahabharata_v4`, `cherokee_myths`/`chinese_folklore`, ...) |
| The band's own false-positive rate, scored graph | `0.000` on 10 of the 18 measurements, up to `0.555` on `D2c_worship_exclusivity`, whose null scatter (sd `0.0845`) is wider than the band judging it; `D4_cosmic_function` wanders by `0.0045` |
| A noise-only corpus of this size, as a family | at least one measurement outside the band in `0.760` of draws; mean `1.015` measurements and `0.795` dimensions |
| Where the band and its own scatter disagree | `D2a` (+0.021), `D2b` (+0.030) and `D6` (+0.048) sit inside the band yet clear chance (`p = 0.004975`, `p = 0.044776`, `p = 0.004975`); `D2c` (+0.148) is flagged and clears too (`p = 0.024876`), so the single measurement where the band and its own null contradicted each other has stopped contradicting |
| Declared-rule dimensions surviving `0.05/9 = 0.005556` | 6 of 9 (`D1`, `D2a`, `D3`, `D4`, `D5`, `D6`), every one at the `1/201 = 0.004975` floor, and the same six on both graphs |

The gate consequence is the reason this section exists. `attractor_block_profile_test` — the test of M4's one
non-null prediction — ran on raw similarity and returned the registered falsification hook
`block_ordering_contradicts_declared_propensity` on a corpus whose block means move from −0.177 to −0.017
depending on whether base rates are subtracted. The gate now runs both scales: raw says CONTRADICTS, the
matched chance-corrected reading says `block_profile_did_not_resolve_the_declared_separability`, and because the
two straddle the disqualification line the published status is
`block_profile_verdict_depends_on_the_similarity_scale` and nothing is disqualified. The chance table's SHA-256
travels into the verdict, so a gate that depends on which artifact is on disk names the artifact it read.
`results/model_power_simulation.json` is byte-identical after the change (SHA-256 `d25c0706…`), because the
power generator's synthetic pairs carry no per-key block profile and reach stage 1 by the totals path.

The band itself is now measured, because a count of dimensions outside an uncalibrated distance is not a
count of discoveries. `chance_band_diagnostics` in the same artifact re-draws each of the 18 scored
measurements 200 times, records each draw's leave-one-out excess — that replicate subtracted from the mean
of the other 199, so no draw is judged against a line it helped draw, which is the published deviation from
the chance line scaled by `200/199` — and reports the fraction of noise draws landing outside ±0.05. That
fraction is not a constant. It is `0.000` for 10 of the 18 measurements and `0.555` for
`D2c_worship_exclusivity`, whose own null is wider than the band; for 8 of the 9 declared-rule measurements
the band is wider than the 95th percentile of its own noise, so it under-flags them, and for `D2c` it is far
too narrow, so it over-flags that one. Reading the same draws as a two-sided Monte Carlo `p` disagrees with
the band on three dimensions — `D2a`, `D2b` and `D6` inside the band yet resolved — while `D2c`, which the band
flags, is resolved by its own null at `p = 0.024876` (`5` draws in `201`), and six of nine survive a Bonferroni
cut at `0.05/9 = 0.005556`. All six sit at `1/201 = 0.004975`, the
floor this many draws can express: that is a bound, not a measurement of how far below 0.05 they are. The
family figure is the one a reader should compare a flagged count against, because noise alone puts at least
one measurement outside in `0.760` of draws while the corpus flags 5 declared-rule dimensions (10 of its 18
measurements). What this does not do: it is not a test
at a declared α, it corrects nothing about the dependence between dimensions — the null draws each dimension
independently, exactly the assumption the chance line already makes — and it does not re-tune the 0.05. The
band is kept as the descriptive statistic it was declared to be, now with its own error rate published
beside it, and the paper's anomaly section reports the count of flagged dimensions against that noise line
rather than against zero.

`tests/test_dimension_anomalies.py` (51 tests) runs the chance draw in subprocesses under four
`PYTHONHASHSEED` values and requires identical bytes — an earlier version of this scan drifted in the fourth
decimal because it iterated a set-derived sequence; re-runs `scan()` and requires the committed artifact; checks
that every published mean is labelled with the statistic and population that produced it; requires the scan and
the M4 gate to agree on the chance-corrected block means; pins the corpus facts above; and re-derives the paper's
`tab:chance` rows and every prose figure in its anomaly section from the artifact, so a number copied out of a
scan into prose is checked the same way a test count is. The band tests re-derive the calibration rather than
trusting it: the per-measurement rates must sum to the family mean they are meant to explain (the identity
that caught the first version, which tallied booleans as a set and reported 1.0 for every dimension), the
leave-one-out excess must be centred on zero by construction, no published `p` may sit below the `1/(reps+1)`
floor or off the lattice of counts over 201, the six Bonferroni survivors are recomputed from the published
`p` values instead of copied, and the diagnostics' own flags must agree with the `excess_within_declared_chance_band`
column of the dimension table they describe.

### 7.3 The two-coder pilot kit: a handout that exists, and a measurement that still does not

Every agreement figure this project lacks has the same cause: one person wrote the frame and one person applied
it. The fix is not another tool but two readers who have not spoken to each other filling the same sheet, and
that ask is only specific once the slice, the value lists and the instructions exist as files someone could be
sent. `tools/make_pilot_packet.py` now cuts them, and the selection is recorded as arithmetic rather than as a
choice.

**The slice.** 300 rows out of the packet's 6,199, allocated across the packet's three existing sampling roles by
largest remainder proportional to those roles, with ties broken by role name, and a simple random sample without
replacement drawn inside each stratum from the stratum's tokens sorted lexicographically before the generator
sees them (seed 20261102). Sorting first is what makes the draw reproducible on a machine whose hash seed is not
fixed: `tests/test_pilot_kit.py` re-runs the builder under four `PYTHONHASHSEED` values and requires byte-identical
output, and the same test re-renders the whole slice at the published seed and compares against the committed
files.

| stratum | rows in packet | pilot rows | design weight |
| --- | --- | --- | --- |
| `machine_candidate` | 4699 | 227 | 20.7004 |
| `no_candidate_uncued` | 900 | 44 | 20.4545 |
| `no_candidate_cue_positive` | 600 | 29 | 20.6897 |
| **total** | **6199** | **300** | |

The weights are near-uniform because proportional allocation makes them so, and the test asserts that all three
strata survive the cut (`a slice that drops a stratum is a different design`) and that the three token sets are
disjoint. The sheet keeps the packet's row order — the packet builder already shuffled, and a second shuffle
would be a second thing to reproduce — so row order carries no stratum information.

**The blinding.** The sheet is cut from `results/annotation_packet_coder_view.csv`; the answer key is read only to
learn which stratum each token belongs to, and no key field is written into the sheet. The builder asserts the
coder view it emits has every coding cell empty, because a sheet with machine answers in it cannot be coded blind,
and it deliberately does **not** print per-stratum counts in the coder handout: how many rows the machine flagged,
and how many it flagged nothing for, is information that changes how hard a reader looks. The counts go in
`results/pilot_slice.json`, which a coder is asked not to read before finishing.

**The handouts are generated, never typed.** `results/pilot_packet_coder_view.csv` (29 columns, 300 rows,
SHA-256 `59a1d00c…`, 98,413 bytes), `annotation/PILOT_CODEBOOK.md` (`6b1e7854…`, 13,033 bytes) and
`annotation/CODER_INSTRUCTIONS.md` (`515eb69e…`, 4,340 bytes) are all rendered from the packet, the key and
`results/annotation_codebook.csv`, and `python tools/make_pilot_packet.py --check` re-renders them in memory and
exits non-zero on any drift, naming the files that differ. The derivation publishes the SHA-256 and byte count of
those three and of nothing else — a JSON file cannot contain its own hash, so claiming to publish its own would be
claiming something no reader could verify. The codebook renders the frame's **93** dimension values and **14**
fixed-question answers as two separate counts; an earlier draft summed them into "107 values", which conflated a
dimension value with an answer to the endorsement question, and a test now fails if the two are ever added.

One row asks 15 answers (12 dimensions plus the unit, representation and endorsement questions), so the pilot asks
4,500 of them against 74,388 per coder for the full packet. That ratio is the whole argument for the slice being a
pilot: it is sized to find out whether the frame can be filled in by someone who did not design it, and how long
that takes.

**The scorer is written to be less capable than the full-packet scorer.** `tools/score_annotation.py --pilot`
refuses `--key` and `--attestations` outright, so a slice that was never allocated across the value strata cannot
produce a precision or recall figure even by accident; a test walks the emitted JSON recursively and fails if any
key is named `recall` or `precision`. It also refuses a missing slice file, two sheets whose token sets are not
exactly the published 300 (coding the interesting half of a random sample measures the interesting half), a value
name that is not on the codebook list, a required column left empty by either coder, one person coding twice
under two `coder_id`s, and a run that does not name its own `--out` — the last because a developer run against
synthetic sheets must not overwrite the canonical reliability file with figures no human produced. It scores each
column with the statistic the frame declares for it — Cohen's kappa where the column is single-valued, mean
Jaccard where it is a set — and reports the two-blank-row count apart instead of averaging it into a Jaccard of
1.0, which is the human-side copy of the trap §7.2 found on the machine side: a dimension nobody used reports
`neither_reader_used_this_column` with a null mean, not perfect agreement.

**What is measured, and what is not.** `tests/test_pilot_kit.py` is 33 tests: the slice's reproducibility, the
handouts' generation, the scorer's refusals, and a class that re-derives every figure the paper's pilot subsection
prints from `results/pilot_slice.json`, including the four table rows above and the paper's own "nobody has
returned a sheet" sentence against `coders_who_have_returned_sheets: []`. `results/pilot_slice.json` states
`status: pilot_prepared_not_coded` and lists four things the slice cannot support: a precision estimate for any
single value, a recall estimate, an inter-coder reliability coefficient for the corpus, and — until two sheets
come back — any figure at all. Nothing in this section is an agreement statistic. The kit is the honest form of an
ask that has not yet been answered.

### 8.1 Match-level audit of the exclusivist-monotheism family

`tools/audit_exclusivist_matches.py` audits §8's most load-bearing family match by match, importing the probe's
own patterns rather than copying them, and `tests/test_exclusivist_audit.py` enforces that the audit
reproduces the probe before correcting it, that every published span lands on its term, that the missed-formula
classes stay out of the family, and that the artifact is fresh against both scripts. Headline numbers, all from
`results/exclusivist_monotheism_audit.json`:

| Quantity | Published by §8 | After the audit |
|---|---:|---:|
| matches (raw text) | 46 | 46 — reproduced exactly, `audit_as_is_matches_identical: true` |
| matches (whitespace-normalised) | — | **51** (+5, each with its wrapped printed span) |
| works attested | 4 | **2** |
| traditions attested | 4 | **2** |
| confessional matches in works not marked dependent | 46 | **34** |
| anthology matches contributing an additional witness | 9 | **0** |
| substring collisions counted as doctrine | — | 2 |
| worship prohibitions counted as existence claims | — | 3 |
| oneness formula classes the family does not carry | — | 16 classes, **79 occurrences, none caught** |
| confession forms in a non-divine claimant's mouth | — | 5 formula hits over 3 distinct verses (Isaiah 47:8, 47:10, Zephaniah 2:15) |

The 34 is not an independence claim. The audit states it as:
**34 matches classified as confessional across two works not marked dependent under the currently configured
source-dependence rules. Independence has not been established because dependence closure remains incomplete.**
That sentence is generated from the partition (`tools/audit_exclusivist_matches.py`
`independence_statement()`), not typed. All 51 audited matches fall in exactly one row of
`disposition_table`, and `disposition_check` re-derives each row by predicate in the same run — mutual
exclusivity, coverage of the whole match set, and the confessional split (34 + 8 = 42) are enforced
arithmetically, and a match no rule claims stops the build:

| disposition | matches | works | evidence for the family? |
|---|---:|---|---|
| `confessional_in_a_work_not_marked_dependent` | 34 | kjv_bible 4 + quran_sale 30 | yes (as candidate) |
| `confessional_in_a_work_marked_dependent` | 8 | sacred_books_east 8 | no |
| `monolatrous_prohibition_presupposing_other_gods` | 3 | kjv_bible 1 + quran_sale 2 | no |
| `conditional_or_hypothetical` | 2 | quran_sale 2 | no |
| `reported_speech_of_denial` | 1 | quran_sale 1 | no |
| `divine_formula_in_non_divine_mouth` | 0 | — | no |
| `editorial_description_of_formula` | 1 | sacred_books_east 1 | no |
| `non_doctrinal_substring_collision` | 2 | book_of_mormon 1 + kjv_bible 1 | no |
| `unresolved_needs_second_coder` | 0 | — | no |
| **total** | **51** | | |

The field `counts_as_independent_attestation` keeps its v1 name so the record schema stays stable; what it
records is the absence of a declared pair rule, published under
`verdict_counts.matches_by_dependence_marking` with its own meaning note. `tests/test_exclusivist_audit.py`
(27 tests) pins the partition arithmetic, the exact headline string, that only the first row counts as family
evidence, and that every verdict the matches carry is covered by a rule.

The audit also corrects provenance in the corpus's own metadata: `corpus/raw/quran_sale.txt` prints
`TRANSLATED FROM THE ARABIC BY THE REV. J.M. RODWELL`, so the work id and the acquisition manifest's `cautions`
string both name the wrong translator, and the configured `anthology_reuse` rationale states the dependence
backwards. `divinity_terms.work_attributes` is not edited to match — the finding is published, because silently
renaming a witness would break every locator that cites it. Every verdict carries
`adjudication_provenance: single_analyst_reading, not independently verified`, the unresolved list is empty, and
the limitations block records that an empty unresolved list on a source-critical pass is itself a reason to
re-code.

`RESEMBLES` is emitted nowhere in this build. The builder attaches a `resemblance_promotion_criterion` to the structural layer — witnesses independently attested rather than merely unmarked, a shared comparison class, every nonzero component on an assessed domain, and survival under the parameter sweeps — and stamps every structural edge with `explicitly_not: ["RESEMBLES", …]`. `validate_results_v2.py` asserts both that no structural edge is labelled `RESEMBLES` and that the promotion criterion is present, so a future edit that promotes a comparison into a verdict without a reviewed decision fails the build rather than shipping.

## 8. Concept-of-divinity probe (Track B, first pass)

`tools/divinity_terms.py` tests the *precondition* of the project's motive claim — that "god" names one concept across the traditions compared — by matching ten analyst-authored divine-concept grammars against the eligible passages of the same corpus the retriever uses. No score is produced; every match carries `passage_id` plus a character span.

| Grammar | Term hits | Works (of 65) | Traditions | Regions |
|---|---:|---:|---:|---:|
| plural or council deities | 4,120 | 50 | 26 | 13 |
| supreme-being attributes | 802 | 35 | 17 | 10 |
| personal creator of world | 728 | 41 | 24 | 13 |
| impersonal ground | 1,071 | 26 | 11 | 9 |
| explicit non-theism or skepticism | 116 | 20 | 10 | 7 |
| saving descent | 351 | 21 | 14 | 10 |
| spirit immanent in things | 137 | 18 | 14 | 8 |
| exclusivist monotheism | 46 | 4 | 4 | 4 |
| deified human or ancestor | 42 | 14 | 9 | 6 |
| celestial bureaucracy | 4 | 3 | 2 | 2 |

Corpus: 65 works, 8,731,101 eligible words, 37 tradition labels, 14 regional labels. **No grammar is attested in every work**; individual works carry between 1 and 8 grammars (10 works carry exactly one), and 4 works match none of the ten vocabularies at all. That is a descriptive fact about this vocabulary census. It is **not** the result this report originally drew from it ("the motive claim therefore has no single referent in this corpus"), and that inference is withdrawn: the census measures the English words one generation of translators had to hand, and non-detection in such a corpus is predicted equally by inherited-and-transformed, by independent-origin, by regional-mixing and by convergent models, so it cannot rank them. Section 6.2 of the paper ("The vocabulary census and the withdrawal of its inference", [paper/main.tex](paper/main.tex)) and §1 and §8 of [TRACK_B_METHOD_v2.md](TRACK_B_METHOD_v2.md) carry the withdrawal.

The sharpest number in the table was the one that cut against the motive: the doctrine that divinity is literally *one* ("no god but", "beside me there is no God", "the Lord our God is one") appearing in 46 passages from **four** works — kjv_bible, quran_sale, book_of_mormon, sacred_books_east. That row is the one the audit in §8.1 corrected, match by match, so the table above is the *pre-audit* census and must not be quoted without it. **The audited figure is 34 confessional matches in 2 independent works** (kjv_bible, quran_sale): all 9 sacred_books_east hits sit inside that anthology's reprinted Qur'an and its Carlyle essay, contributing nothing independent; the Book of Mormon's only hit is one of the two substring collisions, the other being 1 Corinthians 6:17, and 3 further matches are worship prohibitions that presuppose the gods they forbid; and whitespace normalisation raises the raw count from 46 to 51, recovering Isaiah 44:6 and Mark 12:29, which the line-wraps had hidden. Monotheism is unevenly distributed in this corpus — that survives. "One tradition's confession, not a pan-human kernel" does not.

**A defect found by inspection, not by a test.** The first version of the non-theism family matched `there is no god` and `unbelief` inside the shahada and inside intra-Abrahamic polemic, so it reported 262 "skepticism" records of which the large majority affirmed God rather than denied gods. That is the same class of error the audit found in the cleaning claim: a pattern doing the work of a judgement. It is fixed by (a) dropping `unbelief`, which names disbelief *within* a theistic frame, and (b) an exclusion rule keyed to the text *following* the match (`\A\s*but`), which removes 41 monotheistic-formula matches. An earlier draft used a ±60-character window for that rule and wrongly discarded genuine conditionals in the *Iliad* and separate sentences in the Book of Mormon; the tightened window is published in the artefact with every excluded match retained, so the judgement is auditable rather than silent.

**Limits binding on every downstream use**, recorded in the artefact's `cannot_support` block: absence of an English term is not absence of a concept (one translation per work, monolingual corpus); the probe cannot address belief, ritual or doctrine-holding; attestation counts are undated so grammars cannot be ordered historically; the lexicon is one analyst's authorship with no second coder; and no vocabulary census bears on the existence or non-existence of supernatural beings.

`tests/test_divinity_terms.py` (9 tests) enforces the locators rather than the counts: every published match must land on the term it reports at the cited character span inside an eligible passage, region and tradition must come from the manifest, the monotheism/non-theism split must stay separate, exclusions must be published rather than dropped, the verdict must not claim universality, and a rebuild must reproduce the published bytes.

## 9. Validation and reproducibility

- `python -m pytest tests -q` → **455 passed, plus 7 subtests** (45 pipeline tests, 43 structural-engine tests,
  19 schema tests, 9 divinity-probe tests, 27 exclusivist-audit tests, 33 state-coder tests,
  13 graph-recall tests, 116 model-comparison tests, 51 anomaly-scan tests, 37 annotation-recall tests,
  33 pilot-kit tests, 9
  typesetting tests, 8 documented-count tests, 12 documented-hashes tests). The figure is no longer re-measured by hand at all: `tests/test_documented_counts.py`
  runs the collector and the two subtest-bearing tests in subprocesses and fails if the number in this document,
  the number in `paper/main.tex`, the number in `ARCHITECTURE.md` or the per-suite breakdown disagrees with what
  the collector says. That gate exists because the previous draft of this file said 239 tests while its own
  per-suite breakdown summed to 244 — two typed numbers, both stale, arguing with each other in one document.
  Between that draft and this one the model-comparison layer gained its two-stage rule, cluster holdout,
  effective-sample gate and power simulation (+28), the typesetting suite grew from 5 to 9 once a real LaTeX
  engine was installed and then to its current size when the stated page count became a checked claim, and the
  documented-count suite was added, and grew to its present seven checks when the line count this file quotes from
  the TeX validator became a claim of the same kind as the test counts. Most recently the instrument acquired its
  own anomaly scan (§7.2) as a 28-test suite, which is 40 now that the chance band is measured against its own
  null, and the model-comparison suite reached 113 when the M4 block-profile
  gate gained a tie class and a second, chance-corrected reading of the same pairs; it is 116 now because the
  refusal itself was put on trial, and must publish that gate when a pair set is supplied instead of printing a
  missing-input list and saying nothing about the one claim the corpus can score. It grew by 33 more with the
  two-coder pilot kit (§7.3), whose tests own the slice's reproducibility, the handouts' generation and the pilot
  scorer's refusals. The schema suite validates `schema.sql` structurally without a server: primary keys, FK arity and ordering, deferred `ALTER TABLE` targets, enum vocabularies, layered-graph semantics, the score whitelist confined to descriptive `[0,1]` measures, and graded rather than numeric evidence.
- `python tools/validate_annotations.py --write-to results/annotation_validation.json` → status `passed`: 14 versions, 94 events, 218 participant role assertions, 76 causal links, a 38-motif registry asserted 78 times, 87 symbol assertions, 66 legal predicates, 10 full and 4 partial attestations, 95 quote fragments verified against cited corpus text, 0 errors. Without `--write-to` the validator prints and publishes nothing, so the artifact carries the SHA-256 of the annotation store and the passage file it read and `tests/test_narrative_similarity.py` can tell a stale report from a passing one. Seven warnings report evidence passages excluded by cleaning rules (Popol Vuh wooden-people events, Ymir body events) — a cleaning-recall observation, not an annotation defect.
- `python tools/validate_results_v2.py` → status `passed`: 65 raw hashes, byte-exact clean slices, all 34,281 passage offsets and word counts, all dependence labels, all graph endpoints, orientations and `edge_kind` stamps, plus layer-by-layer verification including `narrative_pairs_sha256` and `candidate_pairs_sha256` freshness. It also enforces the vocabulary boundaries an audit flagged: every structural edge must be `COMPARED_WITH` with `RESEMBLES` in its own `explicitly_not` list and an un-promoted `resemblance_admission`, the layer must publish that promotion criterion, no layer may contain a `RESEMBLES` edge, and the builder is forbidden to fill in the reviewer-decision fields. It refuses to certify a graph built from stale inputs, and now refuses one whose semantics were edited after the fact.
- Determinism was re-tested in this session rather than asserted: re-running `tools/run_similarity_v2.py` reproduced `results/v2_candidate_pairs.jsonl` byte-for-byte (SHA-256 `a690dcf9…`), with `corpus/derived/passages_v2.jsonl` unchanged at `9398b166…`. Only the timestamp field in `v2_run_summary.json` differs between runs, so the graph is rebuilt and its recorded input hashes re-checked after any rerun; the validators refuse a stale graph. Environment: Python 3.13.6, numpy 2.3.5, scipy 1.17.1, scikit-learn 1.9.0. Line endings are now pinned rather than inherited: 24 text-mode writes across 11 tools used `open(..., "w")` or `write_text(...)` with no `newline` argument, which on Windows translated every emitted `\n` into `\r\n`. The published artifacts are the bytes that translation produced and `.gitattributes` stores them without conversion, so the recorded SHA-256 values describe CRLF files; on Linux the same commands would have written LF, changing the bytes of roughly two dozen artifacts and making every downstream freshness assertion report a stale input --- a reproducibility failure caused by the operating system rather than the data. Each writer now names the endings its published artifact already carries (CRLF where the published file is CRLF, `newline=""` where it is LF), corpus readers keep `newline=""` so the raw and clean offsets stay byte-exact, and `tests/test_pipeline.py::ToolWritePolicyTests` fails on any future text-mode write that leaves the choice to the platform. The pin records the status quo rather than moving a hash: after the change, re-running `tools/validate_annotations.py --write-to` reproduced the published `results/annotation_validation.json` byte-for-byte.
- Published hashes: v2 run — passages `9398b166…`, acquisition manifest `2bdfa81f…`, source dependence `dc1cd84b…`, motif lexicon `8107160f…`, retrieval code `5201547e…`. Structural run — annotations `472f9087…`, engine code `a52a8673…`, seed 20261031, 200 permutation draws. Published graph — narrative pair set `645d8d30…`, candidate set `a690dcf9…`. Each of these is recomputed by `tools/validate_results_v2.py`, by the freshness test in `tests/test_narrative_similarity.py`, and by `tests/test_documented_hashes.py`, which reads every abbreviated digest printed in the six project documents and fails if one no longer matches the artifact it abbreviates, so a document quoting a stale hash is contradicted by the suite rather than by a reader. The two code digests moved because those tools' own sources changed when their output streams were pinned to a declared line ending, and the manifest digest moved because the rebuild stamped a new `generated_at_utc` and wrote the `partial_run` field the v2 retriever now emits -- which is why this one is re-pinned on every rebuild rather than settled once: an acquisition manifest is a receipt, and a receipt of a run on a later date has different bytes; a digest of a *tool* is a digest of its bytes, so this line is the record of a rebuild, not of a measurement.

Two defects found by this suite are recorded in `config/annotated_versions.json` under `protocol_revisions`. A traceback direction error in the alignment code emitted invalid match lists and mislabelled which events were paired while leaving every published score correct, so it was invisible in the numbers until tested against a brute-force monotone enumeration. Separately, identical events were capped at 0.8 whenever an outcome yielded no lexical terms, conflating coding completeness with narrative difference; measurable parts are now renormalised. Neither correction changed a published pilot value (all 94 events carry coded outcomes and participants), and the run summary records that explicitly.

A third defect, in the divinity probe rather than the engine, was found by reading its output rather than by a test: the non-theism family had been counting the shahada as evidence of skepticism. It is documented in Section 8 together with the rule that now excludes it and the 41 excluded matches, which the artefact publishes instead of discarding. The pattern is the same in all three cases — the numbers stayed internally consistent while the thing being measured was wrong — which is why inspection of examples is part of this project's verification and not a substitute for it.

## 10. What passes, what does not

**Passes:** provenance and re-verification; cleaning and apparatus exclusion; dependence filtering; reuse detection against positive controls; candidate retrieval; structural component separation; dependent-witness discrimination; renaming invariance; motif `NA` semantics; graph semantics with an empty adjudication layer; test coverage of the schema and results.

**Does not pass as evidence:** any historical relationship. No `DESCENDS_FROM` or `BORROWS_FROM` edge exists, and no `RESEMBLES` edge exists either — the structural layer publishes comparisons, and the promotion to a resemblance verdict requires a reviewer decision this build cannot make. The order-sensitivity gate failed and is reported as failed. The structural–lexical association is exploratory: ρ = 0.264 with a quadratic-assignment p = 0.0647 over 200 draws, which is not a significant result and not even a stable one, since its own permutation p-value would move with more draws. Structural results rest on single-analyst coding of 14 versions, so no inter-coder reliability estimate exists and the coding manual's predicate families, motif definitions and comparison classes were authored by the person who applied them. Quote verification proves a fragment occurs in the cited passage; it does not prove the coding is correct. Random and length-matched pairs are limited sampling models, not historical nulls. Absence of a configured dependence rule does not prove independence, and `witnesses_not_marked_dependent` is therefore not a measure of independence. Cleaning's effect on recall is unmeasured in the positive direction: the rules removed two-thirds of the candidate pairs and also removed seven passages that the annotation cites as evidence. **The original vocabulary census cannot establish whether divine concepts share an origin. The v3 instrument provides a more granular, proposition-level representation of machine-detected claims, but its records remain unadjudicated. It therefore adds analytical capacity, not yet independently validated historical findings.** The census reads one English translation per work, so it cannot show that any tradition lacks a concept, cannot date which grammar came first, and cannot say anything about the existence or non-existence of anything; and because it counted a term rather than a proposition, the inference it was given — that "god" is not one concept in this corpus — is withdrawn, since non-detection of an English pattern in a one-translation corpus is predicted by every competing model and ranks none of them. The v3 state layer's 47,641 records are machine candidates with `verification_status: machine_candidate_unadjudicated` on every one, its doctrinal tally rests on a machine field no coder has checked, and its pair enumeration is exact only for the relation `shares a live coded state` — a relation the instrument can define for 53 of its own 93 declared values. So the absence of an edge between two passages is not evidence that they share no state, and no absence in this layer may be reported as a finding. (The superseded MinHash build, whose recall was 0.023475 corpus-wide and 0.023214 on the deterministic 1,632-passage subset cited in §7.1, is no longer the reason for that rule; the incomplete detector vocabulary is.) Measured against a chance line drawn from its own value frequencies the instrument adds three more reasons (§7.2): `D7b_speech_act`, `D7c_discourse_genre` and `D7d_epistemic_commitment` fire on no work at all, `D7a_speaker_attribution` clears its own base rate by only +0.009 (+0.008 as set overlap, −0.006 under the endorsement frame), and the declared block ordering reverses by −0.177 on raw similarity while the same means tie at −0.020 once each dimension's base rate is subtracted — so neither the firing nor the silence of the registered M4 falsification hook is evidence about these traditions.

## 11. Next gates

1. Independent second-coder annotation of the same 14 versions from the cited passages, plus a reliability estimate; no version currently reaches the `independently_annotated` review state.
2. Adjudicated historical claims, one at a time, with dated witnesses, a stated route and reviewed counterevidence, entering only the fifth graph layer.
3. Multilingual and original-language retrieval, since the current filtering partly measures nineteenth-century publishing history.
4. Corpus balancing by independent narrative lineages rather than work count, with community protocols for Indigenous and living-tradition material.
5. A calibrated inference layer only after 1–4; nothing in the present pipeline is authorised to produce one.
6. Re-run the version-label permutation test with enough draws to resolve the correlation it currently cannot. p is computed as (1 + extremes)/(1 + draws), so 200 draws report a tail proportion of 12/200 = 0.060 whose own 95% Monte-Carlo interval is roughly 0.027–0.093; the test cannot distinguish "just below 0.05" from "comfortably above it", which is why the result is labelled exploratory rather than non-significant. More draws narrow the estimate without changing its interpretation, and until they do, no `RESEMBLES` promotion is admissible for any pair.
7. A recall measurement for cleaning, i.e. a labelled set of narrative passages known to be legitimate, so that "the rules removed 67.5% of candidates" can be reported alongside what they removed in error.
8. Track B (concept of divinity) was revised on 1 November 2026: the ten conflated grammars are superseded first by a seven-dimension frame and now, in v3, by the **twelve analytically distinct dimensions** of `config/divinity_ontology.json` — D1, the three-way split of plurality into D2a–c, D3–D6, and the four-way split of interpretation into D7a–d — coded one **proposition** at a time instead of one window. The probe's negative verdict about common ancestry is **withdrawn** — non-detection of an English pattern in a one-translation corpus is predicted by every competing model and therefore ranks none of them. What Track B still needs before any historical sentence is authorised: dated original-language attestations filled by specialists (`results/attestation_scaffold.csv` creates the fields and records that they are empty; `date_earliest`, `date_latest` and `dating_basis` are null in every record of the current run), a blinded second coding of the 6,199-proposition `results/annotation_packet_coder_view.csv` (4,699 flagged candidates plus 1,500 weighted no-record probes), which exists and has never been coded, scored by `tools/score_annotation.py`, and since 2 November 2026 also as a 300-proposition pilot slice whose sheet, codebook and instructions are generated files with published hashes (`tools/make_pilot_packet.py`, §7.3) that no reader has returned yet — and dependence closure to chain and editor level. The four competing models now have a likelihood layer (`tools/compare_models.py` with `config/model_comparison_v3.json`, 116 tests) whose decision rule is two published stages — a symmetric four-way competition judged by the leader over the runner-up, with `no_decisive_winner` reachable, and the separate inheritance-licence question — with a cluster holdout and pair/effective-sample floors derived by `--power` rather than asserted, and it publishes `not_yet_testable` with the inputs it is missing in `results/track_b_verdict.json`, alongside the one M4 claim this corpus can score — the block-profile gate over its 1237 scored pairs, whose chance table's digest travels inside the same file; no model has been ranked. See `TRACK_B_METHOD_v2.md` and `RESEARCH_PROTOCOL.md` §12.4.

9. A decision the anomaly scan forces but cannot make: either write detectors for `D7b`/`D7c`/`D7d` or retire them from the declared frame, and re-register which scale `attractor_block_profile_test` is authorised to read. Today the test reports `block_profile_verdict_depends_on_the_similarity_scale` and disqualifies nothing, which is honest but not a rule — the registered `minimum_block_spread` of 0.05 was written against raw similarity, while the corpus's own base rates are large enough that the same adjacency is a reversal on one scale and a tie on the other. Whichever scale is chosen has to be chosen before the next coding round, not after it.

## 12. Before and after the revision

The frozen 42-work baseline (`results/run_summary.json`, `results/model_comparison.json`) is kept unchanged, so the changes below are measurable rather than asserted.

| Aspect | Baseline (v1) | Revised (v2 + engine 1.1) | Effect |
|---|---|---|---|
| Works / eligible passages | 42 works, 21,580 fixed windows | 65 works, 23,385 eligible of 34,281 passages | apparatus and short passages excluded *before* indexing |
| Apparatus handling | none | cleaning rules + `tools/cleaning_ablation.py` | 29,048 → 9,428 candidate pairs (−67.5%) |
| Dependence | labels in a review file only | 15 pair rules + 1 work family applied to every pair | 8,677 of 9,428 (92.0%) identified as known reuse |
| Null baseline | 18,963 random pairs, mean 0.0141 | 20,000 random + 20,000 length-matched, mean 0.0121 / 0.0126 | length confound removed |
| Edge semantics | graph edge called `RESEMBLES` | `RETRIEVED_AS_CANDIDATE` (lexical), `COMPARED_WITH` (structural), five layers, empty adjudication layer, zero `RESEMBLES` | neither a retrieval hit nor an alignment output can be read as resemblance, let alone ancestry |
| Independence vocabulary | pairs unmarked by a dependence rule described as independent | field renamed `witnesses_not_marked_dependent`, with `independence_basis` stating that no rule is not a judgement | absence of evidence stops being recorded as evidence of absence |
| Significance testing | textbook Spearman `p = 0.019` on 78 pairs | quadratic-assignment permutation on version labels (200 draws, 12 extremes) → `p = 0.0647`, published as `status: exploratory` with `independence_p_value_status` | the correlated-unit problem is stated in the artefact, not discovered by a reader |
| Sensitivity reporting | bare "mean rank shift 0.29" | scale declared in every row (displacement ÷ (P−1)), Kendall τ alongside, and the reference-set size per variant | the number becomes interpretable, and the binding parameter family is identifiable |
| Similarity measure | `S_desc = 100(0.40…0.15…)` composite specified | five separate components, `NA` domains, no composite | component disagreement becomes visible (Noah–Gilgamesh 0.095 events vs 0.550 motifs) |
| Order claim | word-shuffle 0.6740 shown as a caveat | event alignment + preregistered permutation floor | order sensitivity measured and **fails** (0.0186 < 0.02); cause identified |
| Schema | `expression.based_on_expression_id` self-reference, percent-scale `score` | `expression_dependency`, `work_family`, `comparison_class`, `evidence_assessment`; score whitelisted to the five descriptive `S_*` measures in `[0,1]`; separate `retrieval_score`, `retrieval_aggregate` and `statistical_test` tables; `event.passage_id` `NOT NULL` with a composite FK through `narrative_attestation` | a retrieval score or a permutation p-value can no longer be stored where a similarity would be read, and an event citation cannot point at a passage outside its own version |
| Motive claim | assumed that "god" names one concept worldwide, so its recurrence would indicate one invention | v1 census of ten concept grammars, every match located; then an audit of every exclusivist-monotheism match and a twelve-dimension, proposition-level replacement of the frame | the assumption is under-specified, and v1's negative verdict about common ancestry is **withdrawn**: the audit showed the anthology volume's 9 hits were Qur'an reprints already counted under `quran_sale` and 2 more were substring collisions, while whitespace normalisation recovered 5 missed formulas including Isaiah 44:6 |
| Verification | 6 unit tests, hash and offset checks | 455 tests + annotation validator + result/layer validator + freshness assertions + every documented artifact digest recomputed + a real LaTeX compile | found two code defects, one measurement defect, one documentation defect and two locator defects (§7.1) |

The revision's net research conclusion is narrower than the baseline's, which is the point: the baseline ranked "strongest parallels" that turned out to be editorial commentary quoting 1 Samuel, index pages, and shared editions. The revised pipeline reports those as dependence, refuses to score what it cannot measure, and publishes a failed preregistered gate instead of adjusting the gate.

## 13. Reproduction

```bash
python -m pytest tests -q
python tools/acquire_corpus.py
python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json
python tools/build_passages_v2.py
python tools/run_similarity_v2.py
python tools/cleaning_ablation.py
python tools/validate_annotations.py --write-to results/annotation_validation.json
python tools/narrative_similarity.py --lexical
python tools/build_relevance_graph.py
python tools/validate_results_v2.py
python tools/divinity_terms.py
python tools/audit_exclusivist_matches.py
python tools/divinity_ontology.py
python tools/build_ontology_graph.py
python tools/validate_graph_recall.py
python tools/build_attestation_scaffold.py
python tools/check_recall_cues.py
python tools/prepare_annotation_packet.py
python tools/make_pilot_packet.py
python tools/render_track_b_state.py
python tools/scan_dimension_anomalies.py --write
python tools/compare_models.py --corpus-pairs --write-to results/track_b_verdict.json
python tools/compare_models.py --power
python tools/validate_tex.py
python tools/validate_tex.py --self-test
python tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json
```

Two tracked artifacts are deliberately outside that list. The commands above rebuild the
v2 pipeline and everything the paper quotes; the frozen 42-work v1 baseline is rebuilt only
by `python tools/run_similarity.py` (writing `results/run_summary.json`,
`results/candidate_pairs.jsonl`, `results/motif_candidates.jsonl`,
`results/top_pairs_for_review.csv`) and `python tools/compare_models.py --legacy-lexical`
(writing `results/model_comparison.json`), and neither is run by the reproduction sequence
because §12 exists to show the before-and-after difference against an unchanged baseline.
`results/v2_manual_review.json` is in neither group: it records a human reading of nine
discovery pairs, no tool writes it, and running the list above cannot regenerate it.

Outputs, command by command. `tools/acquire_corpus.py` writes `corpus/acquisition_manifest.json` and the
gitignored `corpus/raw/` text; `tools/verify_corpus_live.py --write-to` writes
`results/corpus_live_verification.json`, the one step that reads the network instead of the local corpus: it
re-downloads all 65 works and records per work whether the bytes still match the manifest, so external
stability is published rather than assumed; `tools/build_passages_v2.py` writes the gitignored
`corpus/derived/passages_v2.jsonl` and `corpus/derived/passages_v2_summary.json`;
`tools/run_similarity_v2.py` writes `results/v2_run_summary.json`, `results/v2_candidate_pairs.jsonl`,
`results/v2_discovery_pairs.jsonl`, `results/v2_motif_candidates.jsonl`, `results/v2_top_pairs_for_review.csv`;
`tools/cleaning_ablation.py` writes `results/v2_cleaning_ablation.json` and
`results/v2_unfiltered_candidate_pairs.jsonl`; `tools/validate_annotations.py --write-to` writes
`results/annotation_validation.json`; `tools/narrative_similarity.py --lexical` writes
`results/narrative_component_pairs.jsonl`, `results/narrative_component_pairs.csv`,
`results/narrative_validation.json`, `results/narrative_run_summary.json` and the token cache
`results/narrative_lexical_baseline.json`; `tools/build_relevance_graph.py` writes
`results/v2_relevance_graph.json`, `results/v2_work_relevance.csv` and
`results/v2_priority_cross_region_motifs.csv`; `tools/divinity_terms.py` writes `results/divinity_terms.json`;
`tools/audit_exclusivist_matches.py` writes `results/exclusivist_monotheism_audit.json` and
`results/exclusivist_monotheism_audit.csv`; `tools/divinity_ontology.py` writes
`results/ontology_attestations.jsonl.gz`, `results/ontology_passage_matrix.csv.gz`,
`results/ontology_work_states.csv` and `results/ontology_run_summary.json`; `tools/build_ontology_graph.py`
writes `results/ontology_graph.json`, `results/ontology_passage_index.json.gz`,
`results/ontology_passage_pairs.jsonl.gz`, `results/ontology_workpair_dimensions.csv`,
`results/figures/assertion_states_by_dimension.svg`, `results/figures/speech_act_of_plurality_claims.svg` and
`results/figures/work_by_dimension_states.svg`; `tools/validate_graph_recall.py` writes
`results/graph_recall_validation.json`; `tools/build_attestation_scaffold.py` writes
`results/attestation_scaffold.csv` and `results/attestation_scaffold_summary.json`;
`tools/check_recall_cues.py` writes `config/recall_probe_cues.json`; `tools/prepare_annotation_packet.py`
writes `results/annotation_packet_coder_view.csv`, `results/annotation_packet_key.jsonl`,
`results/annotation_sampling_plan.json` and `results/annotation_codebook.csv`; `tools/make_pilot_packet.py`
writes `results/pilot_slice.json` and `results/pilot_packet_coder_view.csv`; `tools/render_track_b_state.py`
writes `results/track_b_state.html`; `tools/scan_dimension_anomalies.py --write` writes
`results/dimension_anomalies.json`; `tools/compare_models.py --corpus-pairs --write-to` writes
`results/track_b_verdict.json`, the verdict the methodology quotes -- a refusal to rank, and the M4
block-profile gate over the corpus's own 1237 scored pairs, with the SHA-256 of the chance table it read
embedded beside it; and
`tools/compare_models.py --power` writes `results/model_power_simulation.json`; `tools/compare_published_fingerprints.py --write-to` writes `results/fingerprint_diff.json`, the report that says which bytes moved when the whole list was re-run. `tests/test_pipeline.py` reads this paragraph back and fails if a file
appears in `results/` without being named here, or is named here without appearing in the source of a command
printed above; it checks that the command knows the name, not the direction of the write, which is what the
prose claims.
 `tools/compare_models.py` prints to stdout unless `--write-to` names a file, except that `--corpus-pairs` writes `results/track_b_verdict.json` by default, because the reading that flag computes is a published measurement and a measurement that exists only on a terminal is not published; the sequence also names the path, so the flag's default and the document agree. That verdict is where the digest of the chance table it read is kept, which is the second reason the sequence has to run the scan with `--write` first: a gate that reads a chance table no command wrote is a gate whose number cannot be traced to an artifact. `tools/compare_models.py --power` runs the declared grid and writes `results/model_power_simulation.json`, which is the file the pair and effective-sample gates are read from, and a run with any override stamps itself `SMOKE RUN` instead of overwriting the published artifact cleanly. `tools/score_annotation.py` is deliberately absent from this list, because it needs two coded sheets that do not exist yet and refuses to run without them, without a packet that carries no-record probe rows, and without a weight on every probe row. `tools/validate_tex.py` writes nothing at all: it prints a line-numbered structural report on `paper/main.tex` (environment nesting, per-row cell counts against the column spec, escapes, label and citation cross-checks, and whether every `\texttt{\_}` artifact name carries a breakpoint) and exits non-zero on any problem. Its `--self-test` mode exists because an unverified verifier is decoration: it injects ten defect classes — a short table row, an unclosed environment, a mismatched `\end`, a dropped brace, a dangling `\ref`, an orphaned `\bibitem`, an unbreakable typewriter underscore, and unescaped `_`, `#` and `$` — one at a time into an in-memory copy of the source and requires the matching check to fire, then re-runs the clean copy and requires zero problems. Current status: all ten fire, clean copy passes with 0 problems over 2253 lines. The earlier claim in this document that no LaTeX engine is installed was true when it was written and is not true now: MiKTeX 25.12 is installed in this environment (off `PATH`, at `C:/Users/tharu/AppData/Local/Programs/MiKTeX/miktex/bin/x64`), `paper/main.pdf` is compiled here, and `tests/test_tex_typesetting.py` runs that compiler as part of the suite, failing on any overfull box, undefined reference or length change between passes. The page count is therefore a measured property of this file rather than an expectation about it.

Re-running the list end to end was measured rather than asserted. On 3 November 2026 the 26 commands above ran
from the pytest step to this report's own. The 25 pipeline steps all exited zero in 2,873.3 s, the heaviest
being segmentation at 800.3 s, the live re-download at 679.6 s, the state coder at 381.8 s, the similarity
engine at 322.9 s and the cleaning ablation at 220.6 s; the whole list, suite included, took 3,203.2 s. The
suite step exited 1, and it is worth saying what for, because it is the failure this section exists to catch:
seven assertions in `tests/test_documented_counts.py` and `tests/test_tex_typesetting.py` refused figures the
documents were still carrying from before this round: the collector counts 455 where the prose said 441,
`tests/test_dimension_anomalies.py` collects 51 where §7.2 said 40, `tests/test_pipeline.py` collects 45 where
the breakdown said 43, `tests/test_documented_hashes.py` collects 12 where it said 11, `tools/validate_tex.py`
prints 2,253 lines where this report quoted 2,228, and the paper that claimed 42 pages now sets to 43.
No artifact was involved and no measurement moved: the suite had grown, and the prose had not followed. Each
figure was re-pinned from the collector or the compiler rather than retyped, and the step now exits 0 with
**455 passed, plus 7 subtests**. After the run `tools/compare_published_fingerprints.py --write-to` classified
the result against the commit the paper was built on: 63 files compared -- 50 artifacts byte-identical, 7 changed in stamps only, 0 removed,
0 unclassifiable, 3 added and 3 whose measured content moved. The three added are new
artifact sets from this round, not moved measurements: `results/annotation_validation.json`,
`results/corpus_live_verification.json` and `results/track_b_verdict.json`. Those three measured changes are
named because a claim that nothing moved would be false, and each has a different reason.
`results/dimension_anomalies.json` grew from 118,588 to 163,915 bytes for two reasons at once: it gained the
`chance_band_diagnostics` section §7.2 describes, which is new measured content by design, and its scored-graph
chance lines moved because they are now drawn over the 1,237 pairs the observed mean was measured on instead
of over every pair of the works carrying the dimension. The second is a correction, not a drift, so its size
is published rather than described: no chance line moves by more than `0.00982` against a band of `0.05`, and
2 of the 18 scored band verdicts change, both `D6_temporal_nature`. `tools/scan_dimension_anomalies.py` also
keeps the per-replicate means it used to average away, and `tests/test_dimension_anomalies.py` requires the
retained means to average back to the published line.
`results/track_b_state.html` now prints the corrected no-record universe and probe weights of §8 (992,144
propositions, `π=0.000952549286` and `π=0.012682040118`): the committed page was stale against the committed
`results/annotation_sampling_plan.json`, which already said 992,144 while the page still rendered 991,703, so
this is a documentation defect the rebuild corrected rather than a measurement that moved, and the
byte-for-byte re-render assertion in `tests/test_divinity_ontology.py` is what keeps the two from parting
again. `results/ontology_run_summary.json` separates the propositions the over-length rule ran on (59) from
the records it flagged on them (97), which is the double-count §8 records as fixed. Moving no other
measurement is what determinism means here; it is not evidence that the instruments measure what they claim,
and `results/fingerprint_diff.json` says so in its own `what_this_does_not_establish` field.
