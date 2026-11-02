# Global Narrative Interconnection Project

## Research protocol — version 1.3

**Status:** Phase 1 research design; conclusions are not presupposed  
**Primary object of study:** attested narrative versions, not religions as undifferentiated wholes  
**Decision rule:** evidence determines the conclusion; absence of evidence is recorded as uncertainty, not converted into proof of either origin or independence

**Revisions in 1.1 (1 November 2026), after the first implementation pass:** §7.2 now specifies a component vector instead of a weighted composite, because the implemented engine showed the components disagreeing and a mean would have hidden that; §8.1 adds the `RETRIEVED_AS_CANDIDATE` stratum and treats `SOURCE_DEPENDENCE` as a work-level premise rather than a discovered relation. Both changes were made to match what the code in this repository actually produces, not to improve the expected result.

**Revisions in 1.2 (1 November 2026), with the Track B instrument rebuild:** §12.4's unit of analysis became the proposition-level divine-concept state on twelve analytically distinct dimensions; the withdrawn negative inference was removed from the disconfirmation list; the four-model comparison was specified rather than assumed.

**Revisions in 1.3 (2 November 2026), after the second reviewer audit:** §12.4 is now a summary that points at the detailed documents instead of restating them at greater length, because the two copies had begun to drift; the coverage figures for the 93 declared values are given once, in one table, with their overlaps explained, since five different counts of the same set were circulating; "orthogonal" is replaced by "analytically distinct" wherever it described an unmeasured property; `witnesses_not_marked_dependent` no longer supports any sentence about independence; the withdrawn census inference is removed from the remaining places it survived; and §12.4's graph figures are the exact-index enumeration, not the superseded banding sample. The Track B decision rule is now **two published stages**: a symmetric four-way competition whose decisive quantity is the leader over the runner-up, with `no_decisive_winner` reachable, followed by the separate inheritance-licence question; the holdout folds by work, witness and lineage cluster instead of by pair; and both the pair floor and the effective-sample floor come from `python tools/compare_models.py --power` rather than from an analyst's number, which retires the "at least 20 dated route-typed pairs" this protocol previously asserted.

---

## 1. Purpose and scope

The project investigates why narrative versions resemble one another and what, if anything, can be reconstructed about their history. It tests common descent, direct or indirect borrowing, independent invention, and mixtures of these mechanisms. It does not test theological claims.

The research universe includes written, oral, inscribed, archaeological, and iconographic evidence from all regions and periods. “Global” is a sampling commitment, not a claim that every tradition is already represented. Living traditions are included only under applicable community protocols and permissions.

### 1.1 Definitions

- **Work:** an abstract textual or oral work, such as a named epic.
- **Expression:** a language- and version-specific realization of a work, including a recension, edition, or translation.
- **Witness:** a manuscript, inscription, recording, field note, or other carrier attesting an expression.
- **Passage:** a precisely located portion of an expression or witness.
- **Narrative version:** the bounded sequence of events attested by one or more identified passages. Variants remain separate records.
- **Narrative family:** a proposed set of historically related versions. This is a conclusion under test, never an ingestion label treated as fact.
- **Motif:** an explicitly coded recurring element. A source-native description and an analyst’s comparative code are stored separately.
- **Tradition:** a historically situated research grouping associated with communities, languages, places, and periods. Traditions are not assumed to be isolated or internally uniform.
- **Attestation date:** when a surviving witness or record was produced.
- **Composition date:** an evidence-based estimate for an expression’s composition.
- **Estimated narrative age:** a separate, normally more uncertain inference. Recording a story recently does not prove that it is recent; nor does it prove that it is ancient.

### 1.2 Permitted outcomes

Every comparison may conclude:

1. evidence supports common descent;
2. evidence supports borrowing or adaptation;
3. evidence supports a mixed history;
4. independent invention is the best-supported explanation;
5. resemblance exists but historical relationship is unresolved;
6. the proposed resemblance is not supported after source verification.

No comparison is required to produce an ancestral story.

---

## 2. Questions, hypotheses, and predictions

### 2.1 Local hypotheses

For each preregistered comparison set, evaluate:

- **H1 — common descent:** shared features were inherited from an ancestral narrative tradition.
- **H2 — independent invention:** shared features arose independently under recurring cognitive, ecological, social, or narrative constraints.
- **H3 — transmission:** one tradition directly or indirectly contributed material to another.
- **H4 — mixed history:** inheritance, transmission, loss, and innovation acted together.
- **H5 — multiple families:** the sample contains different historical groupings rather than one family.

These are not mutually exclusive across an entire dataset. A mechanism established for one narrative cannot be generalized to all narratives without further evidence.

### 2.2 Global single-origin hypothesis

A useful single-origin hypothesis must make risky, testable predictions. Merely observing universal themes does not do so. At minimum, a global common-origin model would need to predict some combination of:

- non-arbitrary shared sequences or innovations, not just widespread motifs;
- a distribution better explained by one historical tree or network than by multiple families, contact, and convergence;
- systematic correspondences surviving controls for known language families and historical contact;
- chronological compatibility among the relevant attestations and proposed transmission history;
- recoverable ancestral features whose loss and transformation patterns are consistent across independent regional panels.

A universal tree with no differential predictions is not accepted merely because it can be drawn.

### 2.3 Falsifying or limiting claims

The single-origin model loses support if preregistered tests repeatedly show that:

- multiple-family and contact models explain held-out distributions better;
- apparent shared features are generic, independently frequent, or produced by coding choices;
- proposed ancestral sequences disappear under alternative annotations or translations;
- chronology or historically documented transmission contradicts the model;
- results are driven by a few overrepresented literary corpora or copied witnesses;
- purported ancestral features cannot be recovered above null baselines.

Failure to support a universal origin does not prove that no remote connection ever existed. It establishes a limit on what current evidence and methods can responsibly claim.

---

## 3. Research governance and reproducibility

### 3.1 Preregistration

Before examining relationship outcomes for a pilot or expansion batch, freeze:

- research question and candidate selection rule;
- inclusion and exclusion criteria;
- primary sources and admissible translations;
- coding manual and motif vocabulary version;
- positive, negative, and matched control sets;
- scoring implementation and configuration;
- statistical tests, exclusions, corrections, and stopping rules;
- evidence thresholds for each permitted conclusion.

Later changes are versioned amendments with reasons. They never overwrite the original analysis plan.

### 3.2 Data and analysis releases

Each analysis run records:

- immutable input snapshot and content hashes;
- schema and vocabulary versions;
- code commit or archived source;
- software and model versions;
- parameters and random seeds;
- annotator and reviewer identifiers;
- machine-readable results and human-readable interpretation.

AI-generated text is an annotation or research aid. It is never independent historical evidence.

### 3.3 Review states

Records move through explicit states:

`candidate → located → rights_checked → transcribed → source_verified → independently_annotated → adjudicated → analysis_ready`

Only `analysis_ready` records enter confirmatory analyses. Exploratory results are labeled and kept separate.

---

## 4. Sampling and global coverage

### 4.1 Stratified sampling

Sample across the following axes rather than selecting only famous parallels:

- region and subregion;
- language family and isolate status;
- attestation period and recording period;
- oral, textual, inscriptional, archaeological, and iconographic transmission;
- narrative category;
- dominant and locally transmitted traditions;
- source quality and accessibility.

Oversampling well-preserved Eurasian literate traditions must be disclosed and corrected where possible. An unattested motif is coded `unknown`, not `absent`, unless the corpus and observation conditions justify absence.

### 4.2 Independence of evidence

Copies of one manuscript, quotations of one scholar, translations dependent on one earlier translation, and variants collected from the same informant network are not independent observations. Witness stemmata, translation dependence, collector, and source lineage are recorded and used to cluster dependent data.

### 4.3 Control panels

Every confirmatory study includes:

- **positive controls:** relationships independently supported by direct textual or historical evidence;
- **negative controls:** pairs selected before outcome analysis with no proposed historical relationship;
- **matched controls:** pairs comparable in period, region, genre, motif prevalence, and source type;
- **cross-category controls:** narrative categories not used to design the target comparison.

A method that assigns equally strong historical support to positive and negative controls is not ready for expansion.

---

## 5. Evidence and source verification

### 5.1 Evidence hierarchy

The hierarchy guides review effort; it does not make any source infallible:

1. primary witnesses, inscriptions, recordings, and archaeological context;
2. critical editions, original-language texts, and transparent scholarly translations;
3. peer-reviewed historical, linguistic, anthropological, and archaeological scholarship;
4. community-authorized ethnographic documentation and oral histories;
5. academic reference works;
6. general secondary summaries for discovery only.

A late primary record may be direct evidence of a performance or text at its recording date while remaining weak evidence for an earlier date.

### 5.2 Minimum evidence record

Every material claim links to an evidence item containing:

- bibliographic identity and stable identifier or URL;
- expression, edition, translation, and witness where applicable;
- exact passage, page, folio, tablet, line, timestamp, or figure locator;
- original-language excerpt or faithful transcription when rights permit;
- translation and translator;
- relevant historical and cultural context;
- analyst observation, kept distinct from quoted evidence;
- support, contradiction, or contextual relevance to the claim;
- counterevidence and unresolved questions;
- reviewer and verification status.

A URL without a locator is insufficient for a confirmatory claim. AI summaries, encyclopedias, and search snippets may lead to sources but cannot substitute for them.

### 5.3 Dating rules

- Store dates as ranges with calendar, uncertainty, and dating rationale.
- Never replace a range with an undocumented midpoint.
- Keep composition, manuscript, performance, collection, publication, and inferred narrative dates separate.
- Do not infer priority merely from the earliest surviving manuscript.
- Borrowing requires chronological feasibility; common descent requires a defensible genealogy, not merely an early date in one branch.

### 5.4 Indigenous and restricted knowledge

Record community, collector, consent or authorization scope, access conditions, seasonal or gender restrictions where applicable, and permitted forms of storage, analysis, quotation, and display. Public availability does not cancel cultural restrictions. Restricted content is not reproduced in open datasets or public visualizations.

---

## 6. Narrative decomposition standard

### 6.1 Segmentation

Annotators identify a narrative version from explicit boundaries in a source: hymn, episode, performance, inscribed scene, or a justified passage range. Include frame narrative and narratorial context when relevant. Do not merge separate episodes merely because they feature the same character.

Each version receives a persistent identifier. Every variant, translation, and later retelling remains linked but distinct.

### 6.2 Required layers

1. **Source layer:** exact passages and witness information.
2. **Native-description layer:** source wording, indigenous categories, names, and immediate context.
3. **Event layer:** ordered actions, states, speech events, transitions, and outcomes, each linked to text spans.
4. **Participant layer:** entities, local roles, genealogical relations, objects, and locations.
5. **Comparative-code layer:** motifs, themes, symbols, and cross-cultural roles with vocabulary versions.
6. **Interpretive layer:** proposed relations, transformations, reconstructions, and counterarguments.

Layers 1–4 describe the attested version. Layer 5 is analytical coding. Layer 6 is inference. They cannot overwrite one another.

### 6.3 Event representation

Each event records:

- local ordinal and optional larger episode;
- action predicate in analyst vocabulary;
- source text span and literal gloss where needed;
- agents, patients, instruments, recipients, witnesses, and locations;
- explicit versus inferred participants;
- temporal and causal links, marked as source-explicit or analyst-inferred;
- narrative outcome and any restoration, creation, destruction, release, or transformation;
- annotator certainty and review status.

Alternative segmentations are preserved. Event order is not inferred solely from a modern summary.

### 6.4 Motif and role coding

- Use established indices such as Thompson’s Motif-Index and ATU as discovery aids where applicable, not as complete global ontologies.
- Record the exact index edition and code definition.
- Add local terms and definitions for concepts those systems do not represent well.
- Distinguish an entity’s identity from a temporary narrative role.
- Do not equate two deities because both are associated with storms, or two adversaries because both are serpentine.
- Permit multiple codes and disputed codes with rationale.
- Maintain a versioned codebook with inclusion examples, exclusion examples, and near-neighbor distinctions.

### 6.5 Annotation reliability

At least two annotators independently code a preregistered subset, with source and relationship hypotheses masked where feasible. Report agreement at event, participant, and motif levels using an appropriate chance-corrected statistic such as Krippendorff’s alpha, plus raw disagreements. Resolve disagreements through source review and document adjudication; do not silently average them.

Low reliability triggers codebook revision and re-annotation, not more elaborate statistics.

---

## 7. Comparison and scoring

### 7.1 Separate outputs

Every comparison reports separately:

1. **descriptive similarity:** how alike the coded versions are;
2. **linguistic evidence:** whether systematic historical relationships exist;
3. **transmission evidence:** direct, circumstantial, contradictory, and feasibility evidence;
4. **ancestral inference:** model comparison with uncertainty;
5. **data quality:** completeness, reliability, and source limitations.

A high descriptive score never supplies missing historical evidence.

### 7.2 Descriptive similarity

Descriptive similarity is reported as a **component vector**, not a single number. The originally specified index was:

\[
S_{desc}=100(0.40S_{structure}+0.25S_{motif}+0.20S_{role}+0.15S_{symbol})
\]

Each component lies in `[0,1]`. Weights are provisional design choices, not natural constants. A weighted mean is not admissible as a primary output: it would require unavailable components to be imputed or silently renormalised, and it would average quantities measured on different domains. In the implemented engine the components disagree routinely — a pair may score 0.095 on aligned events and 0.550 on adjudicated motifs — which is exactly the information a historical argument needs, so `S_desc` is retained here only as a documented, unused formulation. No score has any interpretation as a probability.

- **Motif and symbol similarity:** weighted Jaccard overlap restricted to the assessed domain, i.e. motifs both versions adjudicated against their comparison-class checklist. Weights are computed from a preregistered reference sample using inverse motif frequency, with a cap to prevent rare miscodings dominating. Report unweighted overlap, the domain size, and thin-domain flags alongside it.
- **Role similarity:** normalized maximum-weight matching between participants using the coder's asserted referent identity and source-attested roles, not names or broad divine labels alone, normalised by the larger participant set.
- **Structure similarity:** normalized alignment of event sequences and causal links. The alignment cost, permitted gaps, and treatment of alternative segmentations are fixed before scoring, and the alignment settings are reported as parameters because the ranking is bound to them.
- **Causal similarity:** agreement of explicit and inferred event links, computed only where both versions carry links.

Publish all component values and the aligned elements. If a component cannot be measured on both sides — including a motif the coder never adjudicated, or a pair drawn from different comparison classes — report `NA` and do not silently renormalize or impute.

### 7.3 Candidate retrieval

Multilingual embeddings, lexical search, and motif search may nominate candidates. Embedding cosine is not historical evidence and is not included in `S_desc`. Retrieval performance is evaluated on a labeled discovery set; candidates still require source-level annotation.

### 7.4 Historical evidence assessment

Record evidence for each mechanism rather than collapsing it into an arbitrary weighted percentage:

- exact verbal correspondences and shared errors;
- systematic sound correspondences and inherited formulaic language;
- chronological feasibility;
- documented contact and plausible route;
- directionality and intermediate versions;
- distribution relative to linguistic phylogeny;
- uniquely shared innovations versus widespread motifs;
- contradictory order, function, outcome, and chronology;
- dependence among sources and witnesses.

Use calibrated likelihood ratios or an explicit probabilistic graphical model only when training data justify their parameters. Otherwise use an ordinal assessment—`strong`, `moderate`, `weak`, `mixed`, `none identified`—for each evidence line. “Unresolved” is preferable to a numerically precise but uncalibrated probability.

### 7.5 Robustness

Report:

- sensitivity to reasonable weight choices and alignment parameters;
- results with and without low-quality or late attestations;
- alternative motif codings and translations;
- leave-one-tradition-out and leave-one-witness-lineage-out analyses;
- null-model and multiple-comparison-adjusted results.

Rank movement between a published ordering and a perturbed one must state its own scale — mean absolute displacement divided by the full ranking range, so that 0 is "the variant reproduces the published order" and 1 is "the variant reverses it" — and must be reported alongside Kendall \(	au\) over the pairs present in both orderings. An unlabelled number such as "0.29 rank shift" cannot be interpreted, and a ranking that moves substantially under one parameter family while holding under another is parameter-bound: state which family binds, and do not publish that ordering as a settled similarity claim. A sweep is not a robustness test if the reference set silently changes; report how many pairs each variant ordering actually shares with the reference.

---

## 8. Historical inference and ancestral reconstruction

### 8.1 Relationship prerequisites

Graph edges are stratified, and each stratum has its own evidential requirement. A `RETRIEVED_AS_CANDIDATE` edge states only that two passages were paired by a named retrieval model above a stated threshold; it requires an analysis run and no interpretation at all. A `COMPARED_WITH` edge states that the structural instrument produced a component vector for two coded versions; it is an output, not a verdict, and it records which components were assessable rather than a single blended value. A `RESEMBLES` edge is a *promotion* over `COMPARED_WITH` and requires a recorded admission decision against a published criterion — witnesses independently attested rather than merely unmarked, a shared comparison class, every nonzero component sitting on an assessed domain, and survival under the parameter sweeps. A `DESCENDS_FROM`, `BORROWS_FROM`, or `INFLUENCES` edge additionally requires a claim record, evidence links, directionality, chronological assessment, counterevidence, status, and reviewer. Disputed and superseded claims remain visible. A build that emits `RESEMBLES` without that decision, or that labels a comparison as a verdict, fails validation.

`SOURCE_DEPENDENCE` is not a discovered relationship and is not part of the version-level vocabulary. It is a work-level premise recorded separately — shared translation, quotation, anthology, compilation, or retelling — used to exclude pairs from independent discovery. A pair with no configured dependence rule is "not known dependent", which is not the same as proved independent.

Geographical proximity or trade contact demonstrates opportunity, not the fact of transmission. Linguistic relatedness makes inheritance plausible for some material but does not prove that a particular narrative was inherited.

### 8.2 Reconstruction procedure

For each proposed family:

1. define the versions and why they were selected;
2. establish attestation, composition, language, and witness context;
3. model copied or otherwise dependent witnesses;
4. align events, participants, formulae, and outcomes;
5. identify shared retentions, shared innovations, losses, and later additions;
6. compare common descent, borrowing, independent invention, and mixed models;
7. test chronological and geographical feasibility;
8. construct more than one ancestral model where evidence permits;
9. challenge each model with negative controls and contradictory versions;
10. publish what cannot be reconstructed.

### 8.3 Reconstruction grammar

Every proposed ancestral element receives one label:

- **attested:** directly present in a cited surviving version;
- **comparatively reconstructed:** inferred by an explicit model from related versions;
- **conjectural:** supplied to make a model coherent but not independently supported;
- **unrecoverable:** evidence is insufficient.

An ancestral narrative is published as an evidence table or structured hypothesis, not as fluent invented prose. Majority voting across descendants is insufficient, especially where borrowing or unequal witness survival is possible.

---

## 9. Multilingual and historical-source workflow

1. Identify the original language, script, expression, witness, and relevant recension.
2. Acquire an authoritative facsimile or critical text where lawful and feasible.
3. Preserve original script; add transliteration only with a named system.
4. Segment by the source’s own tablets, hymns, chapters, lines, folios, or recording timestamps.
5. Use at least one scholarly translation and inspect a second independent translation for consequential passages.
6. Have a language-qualified reviewer verify disputed names, key predicates, negation, modality, and metaphors.
7. Record translation choices that alter motif or event coding.
8. Check whether translations depend on one another.
9. Separate textual restoration and damaged passages from securely attested wording.
10. Link every analytical claim to original and translation passages.

OCR confidence measures extraction quality only. It is not a measure of historical authenticity or relationship confidence.

---

## 10. Statistical falsification strategy

### 10.1 Null models

Null models must preserve features that otherwise manufacture significance:

- motif prevalence and co-occurrence;
- tradition and language-family clustering;
- source type, genre, period, and corpus size;
- dependent witnesses and translations;
- event-count differences.

Use stratified or block permutations and network null models appropriate to the comparison. Unconstrained random pairings across the whole corpus are not an adequate baseline.

### 10.2 Tests

Preregister test statistics such as aligned-sequence enrichment, shared-innovation concentration, phylogenetic signal, or held-out predictive performance. Report effect sizes and uncertainty, not only p-values. Use family-wise correction for confirmatory families or false-discovery-rate control for explicitly exploratory searches. Account for selection conducted before the formal test.

**The permutation unit must match the unit of dependence.** Pair-level observations are not independent draws: with 14 versions coded, each version contributes 13 pairs, and a correlation over 78 such pairs has 14 effective units of variation, not 78. A textbook \(p\)-value computed as if the pairs were independent understates uncertainty and is inadmissible. Report the association with a permutation test that resamples the labels of the dependent entity — a quadratic-assignment procedure that holds the pair structure fixed and permutes version labels — with the draw count, seed, extreme-draw count and the exact formula \((1 + \text{extremes}) / (1 + \text{draws})\) published so the value can be recomputed, and mark the result exploratory unless it clears a threshold fixed in advance. Where a permutation \(p\) is not admissible evidence of significance, say so in the same field rather than letting a bare number speak.

### 10.3 Model comparison

Compare at least:

- independent-origin/no-link baseline;
- single-tree common-descent model;
- multiple-tree or regional-family model;
- contact/network model;
- hybrid tree-plus-contact model.

Where possible, fit on one panel and evaluate on held-out traditions. A visually persuasive graph is not model validation. Prefer parsimonious models unless added historical structure materially improves held-out performance.

### 10.4 Adversarial review

For each strong proposed connection, assign a reviewer to argue the best borrowing, convergence, coding-artifact, and source-dependence alternatives. Publish the strongest counterargument and what evidence would change the conclusion.

---

## 11. Collaborative AI and human review

### 11.1 Responsibilities

**Research partner:** source discovery, historical context, literature review, linguistic assessment, hypotheses, counterarguments, and reconstruction proposals.  
**Implementation partner:** ingestion, metadata, database and graph pipelines, annotation tooling, reproducible computations, null models, and visualization.  
**Language or regional reviewers:** resolve source and cultural questions that generalist AI cannot settle.  
**Human research lead:** approves protocol changes, rights decisions, and publication claims.

Roles may exchange tasks, but the proposer and verifier of a consequential historical claim should not be the same unattended process.

### 11.2 Exchange contract

Partners exchange versioned records containing:

- stable object and claim identifiers;
- exact source locators and evidence links;
- observation versus inference labels;
- methods, parameters, and confidence;
- counterevidence and unresolved questions;
- reviewer and review state.

No partner silently changes identifiers, code definitions, weights, or established decisions. Changes require a decision record with reason, affected records, migration, and approval.

### 11.3 Disagreement

Disagreements are first-class records. Each side states its claim and evidence; adjudication cites sources rather than authority or eloquence. Unresolved alternatives remain attached to the relationship and appear in exports.

---

## 12. Pilot study

The pilot tests the workflow before global expansion. It has one principal panel and two cross-category panels.

### Panel A — combat with a serpentine or primordial adversary

Candidate versions: Indra–Vritra, Hittite Storm God–Illuyanka, Zeus–Typhon, Marduk–Tiamat, Thor–Jörmungandr, and Perun–Veles.

These are **candidates for comparison, not presumed members of one family**. The panel deliberately includes different outcomes and evidence quality. In particular, it must test water release, creation from an adversary, and eschatological mutual destruction as potentially different structures rather than treating “god fights monster” as a sufficient shared sequence. Perun–Veles tests how the framework handles reconstruction without a directly attested pagan narrative.

### Panel B — flood, destruction, and renewal

Use Mesopotamian and Hebrew material to test known regional transmission questions, plus a geographically distant late-recorded version to test dating and contact alternatives. Do not treat all floods as one story type.

### Panel C — creation through bodily division

Use Purusha, Ymir, and Pangu material to compare detailed event alignments against generic creation motifs. Examine whether the correspondence concerns actors, ordered acts, body-to-cosmos mappings, or only a broad theme.

### 12.1 Pilot acceptance gates

The pilot is complete only when:

- every included version has a primary-passage record and a documented translation;
- every material observation has an exact locator;
- composition, attestation, and inferred age are separated;
- all six principal candidates include counterevidence and an unresolved-questions field;
- at least two independent codings exist for a preregistered subset;
- positive, negative, and matched controls are scored with the same pipeline;
- all scores are reproducible from a frozen input and configuration;
- no historical confidence is inferred from descriptive similarity alone;
- at least one candidate relationship may remain unresolved without blocking completion.

### 12.2 Expansion gate

Expand only if source coverage and annotation reliability are adequate, controls behave differently in the expected direction, and sensitivity analyses do not reverse substantive conclusions. Otherwise revise the method and repeat the pilot.

### 12.3 Gate status after the first implementation pass (1 November 2026)

Recorded as observed, including the gates that failed.

| Gate | Status | Evidence |
|---|---|---|
| Every included version traces to a primary passage record with a documented translation | **met** | 14 versions, all cited to `corpus/derived/passages_v2.jsonl` offsets |
| Every material observation has an exact locator | **met** | 95 quoted fragments machine-verified against cited text (`tools/validate_annotations.py`) |
| Composition, attestation and inferred age separated | **partly** | separated in schema and discussed in prose for individual cases (e.g. the *Popol Vuh*'s recording history); per-version composition and attestation ranges are not yet recorded as data fields |
| Counterevidence and unresolved-questions fields for the principal candidates | **met qualitatively** | paper §5.1–§5.3; no claim records yet in the database sense |
| Two independent codings for a preregistered subset | **not met** | all 14 versions coded by one analyst; no reliability estimate exists |
| Positive, negative and matched controls in the same pipeline | **met** | dependent witnesses, 6 predicted-unrelated negatives, length-matched lexical pairs |
| Scores reproducible from a frozen input and configuration | **met** | seed 20261031, recorded SHA-256 inputs, byte-identical rerun of the candidate set |
| No historical confidence inferred from descriptive similarity alone | **met and enforced** | no composite, no `DESCENDS_FROM`/`BORROWS_FROM` edge, empty adjudication layer, zero `RESEMBLES` edges, 282 tests |
| Preregistered order-sensitivity floor | **failed** | mean `S_sequence` drop 0.0186 against a 0.02 floor; cause identified as the gap-cost ceiling, reported rather than tuned |
| Controls behave in the expected direction | **partly** | dependent witnesses outrank all negatives; famous cross-tradition parallels do **not** rank high, which the model reports rather than explains away |
| Sensitivity analyses do not reverse substantive conclusions | **not met for alignment parameters** | on the scale above, the gap sweep moves the published ranking by 0.231–0.291 (Kendall τ 0.11–0.34) while the preregistered g = 1.0 reproduces itself at 0.001 (τ = 0.998); predicate-credit, motif-cap and leave-one-region-out shifts are ≤ 0.017 (τ ≥ 0.973) |

Consequence: the expansion gate is **not** satisfied. Annotation reliability is the binding constraint, so the next work is a second independent coding and a reliability estimate, not corpus growth. The order-sensitivity failure also forbids describing `S_sequence` as a plot-order measure in any downstream document. The structural–lexical association is recorded as exploratory (ρ = 0.264; quadratic-assignment two-tailed p = 0.065 over 200 draws): its textbook p-value was computed on an independence the design does not have, and it must not be cited as evidence that structure and wording are dissociated until a properly powered test establishes it.

### 12.4 Track B — the concept of divinity (scope declared before work begins)

The project’s motive claim is that “God” is a single invented concept that spread. Section 6.1 of the paper ([paper/main.tex](paper/main.tex)) separates it into three propositions; this section fixes what Track B may and may not do about them.

**In scope.** Proposition A, that divine narratives descend from a limited number of ancestral formulations, is tested by the existing instruments. Proposition B, that the divine *concept* has a single origin, is a legitimate question and Track B is its designated home. Proposition C, that no supernatural being exists, is permanently out of scope for any textual method: an idea’s history does not settle its truth-value, in either direction. Recording that exclusion in advance is the safeguard against a project that quietly converts “this was narrated by humans” into “this is therefore false”.

**Unit of analysis (revised 1 November 2026; rebuilt the same day).** The divine-concept *state*: an assignment of values on **twelve analytically distinct dimensions** — declared distinct by construction, not measured orthogonal — D1 ontological category, D2a acknowledged population, D2b reality of the others, D2c worship exclusivity, D3 agency, D4 cosmic function, D5 universe relationship, D6 temporal nature, and the four-part interpretation block D7a speaker attribution, D7b speech act, D7c discourse genre, D7d epistemic commitment — to **one proposition about an identified divine referent**, located in a named expression with three separate date fields and carrying its utterance window as context (`proposition_text`, `proposition_char_start`, `proposition_char_end`, `proposition_overlong`, `window_char_start`, `window_char_end`). Five dimensions (D1, D3, D4, D5, D6) are set-valued and seven (D2a–c, D7a–d) are single-valued; every one carries an `undecidable` residual, and a single-valued dimension that matches twice publishes a `value_conflict` instead of choosing by precedence. The v2 frame coded the *window* and had one composite plurality column and one composite interpretation column; the composite was three variables in the first case and four in the second, which is why they were split. The earlier formulation, a list of ten to twelve “grammars” (creator-of-world, plurality-with-council, impersonal ground, conferred divinity, bureaucratic heaven, saving descent, denied divinity, and any grammar a second coder adds), is withdrawn as the unit of analysis, because each grammar folded several independent questions into one label and that conflation is what produced the errors the exclusivist-monotheism audit documents: a cardinality claim merged with an exclusivity claim merged with a truth-claim about other gods merged with a speech act. The dimension definitions, cardinalities, residual `undecidable` values and per-value coverage states are in [config/divinity_ontology.json](config/divinity_ontology.json) and [config/ontology_english_rules.json](config/ontology_english_rules.json); the reasoning is [TRACK_B_METHOD_v2.md](TRACK_B_METHOD_v2.md) §2 and §3.

What did not change, and remains the point of the revision: the state is attested in a named *expression* — a specific work, in a specific language, at a specific attested date — not in a tradition as such. Traditions do not hold concepts; texts attest them, and the distinction is what keeps frequency counts from becoming ethnography.

**Preregistered observations that would favour a single conceptual origin.**

1. A shared arbitrary, non-functional element of the concept — not “a high god exists” but a specific predicative structure, such as creation by a single uttered word plus a rest or division sequence — appearing in the earliest attested expression of ≥ 3 families with documented contact or inheritance between them, dated in an order consistent with transmission.
2. Concept vocabulary that travels with its morphology (a loanword for “god”, “creator” or “soul” borrowed together with its predicative grammar), which is hard to produce by convergence.
3. The distribution mapping onto language-family phylogeny better than onto ecological or subsistence variables, under the §10.1 nulls.
4. Narrative-structure comparisons of the kind this pilot runs, where the high-scoring pairs are the ones independent source criticism already places in one lineage, and low-scoring pairs are the ones it places in different lineages.

**Preregistered observations that would count against it.**

1. Non-overlapping concept grammars in the earliest strata of families with no contact route — **and note the condition that makes this observation admissible**: the non-overlap must be established in dated original-language attestations with the value's detection recall measured, not inferred from the absence of an English surface pattern in one translation. Without those three conditions the correct report is `undecidable_from_available_sources`, and the observation counts against nothing. This revision exists because the divinity-terms probe was read as supplying this observation when it could only supply a vocabulary distribution.
2. Traditions with documented, ancient, non-theistic or divinity-pluralistic doctrinal vocabularies (Jaina and Buddhist doxographies, Chinese bureaucratic heaven, animist grammar of personhood) in which the creator grammar is absent rather than lost — absent in the earliest attestation, not merely absent in one translation.
3. A single-origin model that requires every divergence to be explained as loss while every similarity counts as inheritance; that asymmetry is the unfalsifiability warned about in §2.3 and is disqualifying.
4. The apparent universality disappearing when apparatus, genre and translator vocabulary are controlled, as §5.6–§5.7 of the paper report for retrieval similarity (§5.6 “Relevance formulation and graph semantics”, §5.7 “Cleaned global corpus and dependence filtering” in [paper/main.tex](paper/main.tex)).
5. A within-tradition spread of divine-concept vocabularies larger than the between-tradition spread: if “god” means something very different inside one tradition across its own history, there is no stable cross-traditional kernel to have originated once. **Item 5 is itself now limited**: a large within-tradition spread is also what inheritance-with-transformation predicts, since a tradition's own history is where abstraction, demotion and nominalisation happen. It discriminates only if the spread's direction matches an operator path along a dated route, which is a §6 test of the new methodology rather than a §12.4 disconfirmer.

**What today’s probe is.** `tools/divinity_terms.py` v1 is a vocabulary census of ten analyst-authored grammars over the English corpus, published with locators and with its excluded matches. It measures translators’ available English vocabulary and is admitted only as a *description*; it is no longer admitted as a precondition test that could disconfirm anything, because the precondition it claimed to test — that one grammar recur everywhere — is a universality condition that inheritance-with-transformation does not predict and that its absence cannot discriminate among the four models. Its `cannot_support` block is binding on any downstream use: it does not establish absence of a concept, does not order grammars historically, does not address belief, and does not address Proposition C. `tools/divinity_ontology.py` replaces it as the Track B instrument; v1 is retained as the record of what was claimed and on what basis, and its published `verdict` string is superseded by the audit and by [TRACK_B_METHOD_v2.md](TRACK_B_METHOD_v2.md) §4 and §8.

**State of the replacement instrument as of this revision — a summary.** The numbers below are read from
`results/ontology_run_summary.json`, `results/ontology_graph.json` and
`results/graph_recall_validation.json`; the full account is
[TRACK_B_METHOD_v2.md](TRACK_B_METHOD_v2.md) §3, §5 and §7 and
[TEST_REPORT.md](TEST_REPORT.md) §7.1 and §8, and this section deliberately no longer restates them at the same
length, because the two copies had begun to drift apart and the drift was itself a finding.

`tools/divinity_ontology.py` (v3) has run over the whole eligible corpus: **47,641 candidate records** over
36,775 distinct propositions and 34,584 utterance windows, in 23,385 eligible passages and 8,731,101 eligible
words across 65 works — 47,122 open candidates, 140 needing human disambiguation, 379 falling on values the
detector cannot see, and no fourth state. Every record carries three separate answers
(`conceptual_presence`, `doctrinal_endorsement`, `historical_transmission`) plus the derived boolean
`counts_as_affirmative_doctrine`; `historical_transmission` is `not_yet_assessable` on all 47,641 because
`date_earliest`, `date_latest` and `dating_basis` are null in every record. The graph layer enumerates
**22,940,506** distinct cross-work passage pairs that share at least one live coded state, exactly, by inverted
index — 2,078 of the 2,080 possible work pairs connected — with **41,238** of them displayed as a labelled slice
in the edge file and the index itself shipped so the enumeration is reconstructible. It emits the
inheritance-and-transformation layer empty, `unpopulated_by_design`. The blinded two-coder packet is **6,199
propositions**: 4,699 machine-flagged candidates plus **1,500 weighted no-record probe rows**, because a sample
of hits contains no misses and no pairing-recall figure is the detector's recall. **No coder has coded it**, so
no annotation κ, precision or recall figure exists anywhere in this repository. The exclusivist-monotheism audit
is complete and reduced v1's headline from 46 matches in 4 works: **34 matches classified as confessional across
two works not marked dependent under the currently configured source-dependence rules. Independence has not been
established because dependence closure remains incomplete.** All 51 audited matches sit in exactly one row of the
mutually exclusive `disposition_table` in `results/exclusivist_monotheism_audit.json`.

**The coverage of the instrument's own detectors, stated once.** Five different counts describe the same 93
declared values, and they are nested sets rather than a partition, so the differences between them are not
quantities of anything. Every number in this table is read from `results/ontology_graph.json` →
`coverage_inventory`, which `tools/build_ontology_graph.py` computes and `tests/test_divinity_ontology.py`
re-derives from the rules file; the paper quotes the same object and `tests/test_tex_typesetting.py` pins its
figures against it. The prose that used to restate these numbers in four places is what drifted.

| Set | Count | What it actually is |
|---|---:|---|
| declared values, all twelve dimensions | **93** | the frame's own vocabulary, from `config/divinity_ontology.json` |
| carry at least one English surface pattern | **53** | term- or phrase-matched values |
| carry no English surface pattern | **40** | 2 of them also labelled `not_yet_instrumented`, and **all 38 of the remainder are produced by rules rather than by patterns** — the 30 values of the `D7a–d` interpretation block, plus the 8 `undecidable` residuals of D1–D6 (the `D7a–d` residuals are among those 30); calling these detector gaps is a category error, they are derived fields |
| labelled `not_yet_instrumented` | **9** | **7 of the 9 do have a pattern** — `non_agential`, `outside_time`, `unknowable_or_conceptless`, `no_function_attributed`, `scale_not_claimed`, `world_in_divine_not_exhausting`, `from_lost_past` — and they are absence and non-relation values where the missing thing is a method for establishing that something is *not* being said, not a regex; the other 2 (`others_not_addressed`, `no_devotional_language`) have no pattern either |
| observed at least once in this run | **50** | hence the 50 value-columns of the passage matrix |
| with no matrix column | **43** | 93 − 50. Of these, 3 have a pattern and never matched (`world_in_divine_not_exhausting`, `outside_time`, `retreated_or_absent`); the rest are unpatterned or `not_yet_instrumented` |
| coverage-state labels over all 93 | 83 `instrumented`, 1 `partially_instrumented`, 9 `not_yet_instrumented` | the labels live on the rules file's `coverage` field, per value |

Reading the rows against each other: 93 = 53 + 40 on one axis and 93 = 50 + 43 on another, and the 9 labelled
values sit inside the 53 on the first axis, not outside it. **The "31" you get by writing 93 − 53 − 9 is not a
count of anything** — it double-removes the 7 labelled values that do have patterns; the set that exists is the
38 unpatterned-and-unlabelled values, and every one of them is a rule-derived field. An empty cell, a missing
column and a missing edge each say something about this instrument and nothing about a tradition.

**The four models are compared, not assumed.** Track B now holds four live possibilities open and preregisters what would separate them: (M1) one ancestral concept followed by transformation; (M2) multiple independent origins; (M3) regional inheritance followed by cultural mixing; (M4) independent development followed by convergence. Each is stated with the predictions the others do not make, and the discriminating scores are parsimony, contact-distance correlation, the arbitrary-detail test, dimension-profile partition, and dated-first-attestation ordering. The layer is implemented rather than described — `config/model_comparison_v3.json` read by `tools/compare_models.py`, 91 tests — and its full specification, including what it still cannot do, is [TRACK_B_METHOD_v2.md](TRACK_B_METHOD_v2.md) §6; the sentences that follow are the register of binding rules, not a second specification. Its binding rules: vertical inheritance and horizontal transmission are **mandatory, exclusive edge types** and `descent_or_contact` is an illegal value; the prediction is an operator-rate **distribution over similarity classes**, not a monotone time-decay curve, and the decay form survives only as a nested special case; the thirteen operators are priced (cost, rate, retention, reuse cap, per-operator evidence list) and a derivation may invoke at most **three** applications, at most **two** to be reported as preferred, with at most **one** unattested intermediate node; the four evidence conditions are **jointly mandatory** — any single unmet condition yields `undecidable`, and the v2 wording “two of the four unmet” is resolved as a conjunction, not a threshold; dates are ranges, an earlier surviving witness is never evidence of earlier composition, and direction needs P(A precedes B) ≥ 0.95; the cost table is preregistered by SHA-256 and a mismatch returns `not_preregistered`. The decision rule is **two published stages rather than one verdict**: stage 1 scores all four models symmetrically on one pair set and demands a **log10 Bayes factor ≥ 2.0 for the leader over the runner-up** — over the runner-up, not over M2, because a rule written as “inheritance beats the null” makes M2 the denominator and M4 decorative — with `no_decisive_winner` reachable and printed as a result, while stage 2 keeps the separate licence question, the same declared margin against the no-edge baseline, and neither stage implies the other. A winner is emitted only above a pair floor and an **effective independent sample** floor that the layer derives by simulation instead of asserting: the previous “at least 20 dated route-typed pairs on a held-out half” is a superseded analyst-set number, the holdout is by **cluster** (work, witness, lineage) rather than by pair, and pairs sharing a work are counted as one observation, not two. Run today it prints `status: "not_yet_testable"` with the inputs it is missing. **No model has been ranked, and nothing in this layer has been tested.**

**What Track B requires before it may publish a historical conclusion.**

1. Original-language and dated expressions per dimension value, not one English translation per work; the current corpus cannot support priority claims, and the current instrument cannot say anything except about English translation vocabulary — it is a multilingual-**ready** framework, not a multilingual or language-independent one, and `expression_language` is `English (translation)` on all 47,641 records.
2. A second analyst-authored lexicon, independently built, with inter-annotator agreement on value assignment across the twelve dimensions (κ per single-valued dimension, mean Jaccard per set-valued one); a census whose categories are authored by its only coder is a description of one reading.
3. Anthropological and historical-literacy sources for the concept’s institutional life (cult, ritual, office, self-referential use), since a vocabulary census cannot see any of that.
4. Community and specialist review for living-tradition material, per §5.4, before its concepts are used as distribution data.
5. The gate in §12.2 applied to concept claims as well: no `DESCENDS_FROM` for a concept until a dated attestation chain and reviewed counterevidence exist in the fifth graph layer.

Until those exist, Track B’s permitted output is a descriptive inventory of coded states with their coverage states, their three assertion states and their separated presence, endorsement and transmission answers, the audit record of what each source actually is, and the list of observations that would move the question — and it explicitly excludes any sentence that treats non-detection in English as evidence about ancestry in either direction. That exclusion is the substantive revision: §12.4 formerly licensed the negative inference, and the paper’s census section — §6.2 “The vocabulary census and the withdrawal of its inference” in [paper/main.tex](paper/main.tex), §6.1 of the earlier markdown edition — published its result as the answer to the motive claim. Both are withdrawn.

---

## 13. Phased execution plan

Durations are planning estimates. Quality gates, not calendar dates, authorize expansion.

### Phase 0 — protocol and governance

**Outputs:** this protocol, decision log template, rights policy, codebook v1, pilot preregistration.  
**Measures:** all terms defined; hypotheses and stopping rules frozen; restricted-data workflow approved.

### Phase 1 — provenance infrastructure and evidence pilot

**Outputs:** PostgreSQL schema, immutable source register, passage-level evidence records, three pilot panels, initial annotated dataset.  
**Measures:** 100% of included versions trace to primary passages; 100% of historical claims have evidence and counterevidence fields; all restricted assets have access classifications; no unsupported ancestry edges are published.

### Phase 2 — reliability and computational validation

**Outputs:** independent annotations, adjudication report, scoring implementation, null models, control results, sensitivity report.  
**Measures:** agreement reported by layer; analysis reruns from a clean snapshot; control performance and failure cases published.

### Phase 3 — regional expansion

**Outputs:** balanced regional batches, multilingual review log, searchable evidence repository, versioned graph export.  
**Measures:** sampling coverage reported by region, language, period, and source type; copied witnesses clustered; unresolved and negative results retained.

### Phase 4 — reconstruction and falsification

**Outputs:** competing family reconstructions, model comparisons, transmission maps with uncertainty, single-origin falsification report.  
**Measures:** every reconstructed element labeled; alternative models and held-out performance reported; unrecoverable elements explicitly listed.

### Phase 5 — public research platform

**Outputs:** narrative atlas, evidence-first graph, searchable provenance, reproducible analysis downloads, culturally appropriate public views.  
**Measures:** selecting any edge exposes its evidence and disputes; no public display violates access restrictions; exports reproduce published results.

---

## 14. Reporting standard

Every research report includes:

1. question and preregistered hypotheses;
2. sampling and exclusions;
3. source and dating table;
4. annotation and reliability methods;
5. descriptive similarities with components;
6. historical evidence for and against each mechanism;
7. null models, corrections, and sensitivity analyses;
8. competing reconstructions or an explanation of why none is justified;
9. limitations, missing evidence, and unresolved questions;
10. machine-readable citations and analysis snapshot.

The project succeeds by producing defensible distinctions—including negative and unresolved results—not by maximizing the number of connections.
