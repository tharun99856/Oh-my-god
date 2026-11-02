# Track B methodology, third pass — the inheritance and transformation of divine concepts

*File name stays `TRACK_B_METHOD_v2.md`: code comments, config pointers and the paper's links address it by
that name. The frame described below is v3: twelve dimensions instead of seven, a proposition instead of a
window as the unit, and three separate question-fields instead of one refusal state.*

Status: **methodology**. This document changes how the question will be asked and answered. It is not a
report of an answer, and every number in it is an instrument diagnostic, not a historical finding.
Supersedes `RESEARCH_PROTOCOL.md` §12.4 and the withdrawn conclusion of the paper's divinity section
([paper/main.tex](paper/main.tex) §6.1–6.3; the earlier markdown edition is preserved at
[archive/paper_markdown_v1_3/RESEARCH_PAPER.md](archive/paper_markdown_v1_3/RESEARCH_PAPER.md)).
Artifacts: [config/divinity_ontology.json](config/divinity_ontology.json) (the frame),
[config/ontology_english_rules.json](config/ontology_english_rules.json) (candidate detectors and coverage
states), [config/divinity_lexicon.json](config/divinity_lexicon.json) (lexicon entries and their verification
status), [tools/divinity_ontology.py](tools/divinity_ontology.py) (the instrument),
[tools/migrate_rules_to_v3.py](tools/migrate_rules_to_v3.py) (the seven-to-twelve migration, with the
inventory of every pattern it moved), [tools/audit_exclusivist_matches.py](tools/audit_exclusivist_matches.py)
(the provenance audit), [tools/build_ontology_graph.py](tools/build_ontology_graph.py) (full-corpus graph
layer), [tools/validate_graph_recall.py](tools/validate_graph_recall.py) (the measured recall of that
layer's blocking step), [tools/compare_models.py](tools/compare_models.py) with
[config/model_comparison_v3.json](config/model_comparison_v3.json) (the four-model likelihood machinery of §6),
[tools/prepare_annotation_packet.py](tools/prepare_annotation_packet.py) with
[results/annotation_codebook.csv](results/annotation_codebook.csv) (the blinded coding sheet), and
[tools/score_annotation.py](tools/score_annotation.py) (the scorer that refuses to run on one coder).

---

## 1. Why v1 is withdrawn, stated precisely

Track B exists to test the claim that "God" is one invented concept that spread. v1 built a probe of ten
concept-grammars, ran it over 8,731,101 eligible words, found that no grammar occurred in all 65 works, and
concluded that "the concept of God" has no stable referent in the corpus. Four defects made that conclusion
unavailable, and they are of different kinds.

**1.1 The grammars conflated conceptual dimensions.** `exclusivist_monotheism` folded four independent
questions into one label: how many divinities are counted, whether others may be worshipped, whether others
are real, and in what voice the sentence is spoken. `personal_creator_of_world` folded an ontology claim into
a function claim. `explicit_non_theism_or_skepticism` folded a cardinality value into an interpretation
status. Conflation is not untidiness; it is what generated the errors the audit found (§4).

**1.2 The test did not match the hypothesis.** v1 asked whether one grammar is present *everywhere*. A
historical-inheritance hypothesis does not predict uniform survival of a surface form — it predicts descent
with modification, and the operators of modification (abstraction, demotion, nominalisation, silencing)
positively *remove or relocate* surface markers. Demanding universality is demanding that transmission
produced no change, which is a straw form of the hypothesis. The universality criterion belongs to a
different and much stronger claim — innate availability of a divine concept in every human population — and
that claim is not Track B's.

**1.3 Absence was read as a finding.** The formal defect: v1 inferred "the concept is not present in this
tradition" from "an English surface pattern did not occur in one translation of it". The second proposition
is all the instrument can ever establish. Because all four competing models (§6) predict the same
non-detection pattern, the observation had **no discriminating power at all**; it could not rank the models,
yet it was used to dismiss one of them. v1's own verdict field contained a one-sentence apology for this and
then the paper's headline used the result anyway.

**1.4 Single-coder, undated, monolingual.** All coding was one analyst's lexicon with no second coder;
attestation counts were undated and therefore could not order anything; and the corpus is one English
translation per work, so every "absent" concept was an absent word.

The frame below fixes 1.1 and, by construction, 1.2; §8 fixes 1.3 as a hard inference rule; §7 and §9 fix
1.4 as gates that must be passed before any historical sentence may be written.

---

## 2. The unit of analysis

A **divine-concept state**: the assignment of values on twelve dimensions to **one proposition about an
identified divine referent**, carried inside the *utterance window* that contains it, located in a named
expression (a work, in a language, with three separate dates) and marked with who utters it, what act it
performs, what genre carries it and what the framing text commits to.

v2 coded the window. A window is a bounded run of connected text, and one window routinely carries several
claims: *"I form the light and create darkness; I make peace and create evil"* states four predications with
two different objects. Coding that as one state makes a paragraph into an argument about nothing in particular,
so the instrument now splits each window at coordinating and subordinating connectors
(`PROPOSITION_BREAKS` in [tools/divinity_ontology.py](tools/divinity_ontology.py)), merges fragments too short
to hold a subject and a predicate, and assigns the dimension values to the resulting proposition. The window is
retained as `window_char_start`/`window_char_end` and as the coder's context, because attribution and genre
cannot be read from a clause that has been cut away from its frame.

Every record therefore answers the reviewer's six questions separately: *what entity* (`referent_surface`,
`referent_kind`, `referent_candidates`, `referent_ambiguous`), *which proposition* (`proposition_text` with its
own half-open span), *who states it* (`D7a_speaker_attribution` plus `attribution_basis`, which says whether
that answer was found or defaulted), *what is claimed* (the eight concept dimensions), *whether it is asserted,
questioned, denied or attributed* (`assertion_mode`, derived from `D7b` and `D7d`), and *where and when*
(`work_id`, `passage_id`, `char_start`, `char_end`, `region`, `tradition` and the three date fields).

Three things this still is not. It is not a *tradition* holding a concept (traditions do not hold concepts;
texts attest them, and the difference is what stops frequency counts from becoming ethnography). It is not a
*work* containing a grammar (a work contains many states, sometimes contradictory ones — the Mahābhārata
carries personal-agent, impersonal-principle and no-god states in the same book). It is not an *English word*,
because the word is evidence of a translator's habits.

Record fields and required provenance are defined in
`divinity_ontology.json > coding_record`. The three date fields — `composition_date_claim`,
`earliest_witness_date`, `edition_or_translation_date` — are never collapsed into one. Collapsing them is
how an undated count gets read as chronology. They are `null` in every record of the current run, which is
why `historical_transmission` is `not_yet_assessable` rather than low.

**The segmentation is a machine approximation and is measured as such.** Windows split at punctuation and
connectors, so Hebrew and Old Norse parataxis — clauses joined by nothing at all — survive as one proposition,
and coordinated predicates sharing a subject are sometimes cut in two. The run publishes the failure count
(`propositions_flagged_run_on`), the shape of the distribution (`matched_propositions_per_passage`) and the
known failure modes, and the coding sheet asks each coder whether the machine's unit is one proposition, too
large or too small. That column is a measurement of this design decision rather than an error to be corrected
inside the record.

---

## 3. The twelve dimensions

Orthogonality here means: a value on one dimension does not determine a value on another, and every dimension
answers exactly one question. Values within a dimension are mutually exclusive where the dimension is
single-valued, each dimension carries an explicit `undecidable` residual so that "the text does not commit" is
a recorded state rather than a silent zero, and a single-valued dimension that matches two values on one
proposition publishes `value_conflict` and hands the row to a human instead of choosing by precedence.

v2's table failed that standard in two of its own rows, and this is the correction, not a restatement.

| # | Dimension | The one question it answers | Cardinality |
|---|---|---|---|
| D1 | ontological category | what *kind of thing* is divinity taken to be | set |
| D2a | acknowledged population | how many divine beings does this proposition acknowledge | single |
| D2b | reality of others | what status do *other* divine beings have relative to the one spoken of | single |
| D2c | worship exclusivity | is devotion or rite restricted to this divinity | single |
| D3 | agency | what sort of causal capacity is predicated | set |
| D4 | cosmic function | what *work* is the divinity credited with | set |
| D5 | universe relationship | how the divine stands to the cosmos | set |
| D6 | temporal nature | relation to beginning, end and recurrence | set |
| D7a | speaker attribution | whose utterance does this text print here | single |
| D7b | speech act | what act is performed in this proposition | single |
| D7c | discourse genre | what kind of discourse carries it | single |
| D7d | epistemic commitment | does the framing text commit to it, attribute it, reject it or hold it open | single |

**Why D2 became three.** "How many", "are the others real" and "may they be worshipped" are three
variables that combine freely: the Bhagavad Gītā acknowledges many real beings without exclusive devotion,
Deuteronomy acknowledges gods other worship is forbidden to without denying their existence in its earliest
layer, and a boast of a non-divine claimant acknowledges one and denies the rest. v2 folded all three into one
column, so `sole_existent_others_unreal` and `sole_worshipable_others_acknowledged` were values of a single
variable that was actually three. The migration
([tools/migrate_rules_to_v3.py](tools/migrate_rules_to_v3.py)) moved every old D2 pattern into D2a or D2b,
and routed into D2c only the patterns that also carry devotional language — `worship|serve|bow|incense|
sacrific|no other gods|before me|god but|pray`. That filter dropped 10 of the 16 inherited patterns, because
copying an existence formula into the worship dimension would have manufactured the mirror image of v1's
error; the dropped list is published in the migration report rather than hidden.

**Why D7 became four.** A hymn can contain doctrine, a conditional can contain a reported statement, and an
opponent can make a theological argument. v2's nine labels — doctrine, hymn, myth, argument, command,
conditional, reported speech, boast, apophasis — mixed genre with act with commitment, and its precedence
list resolved the mixture by fiat. Now: *genre* is what carries the text (D7c), *act* is what the utterance
does (D7b), *attribution* is whose voice it is (D7a) and *commitment* is how far the framing text goes with
it (D7d). A confession inside a conditional is `condition` on D7b, `suspended_or_held_open` on D7d, and its
genre is whatever the surrounding discourse is; nothing is decided by precedence except D7b, where marker
collision is genuinely ambiguous and the rule is published.

**D1, D3, D5 and D6 became set-valued** for the reason the reviewer gave: transcendence and immanence
coexist, will and delegated action coexist, eternity and eschatological function coexist. Forcing one choice
there does not make the reading cleaner, it makes the reading a single value the coder was not asked to make.
D1 is set-valued for the same reason in a sharper form: a text can call the divine a person *and* an order
*and* unknowable, and the co-presence of categories is itself a finding.

**The order of evaluation.** The D7 answers are decided from the shape of the proposition before any divine
term is read, because a term match inside a conditional is not a doctrine. Marker patterns and the D7b
precedence rule are in
[config/ontology_english_rules.json](config/ontology_english_rules.json) `> speech_act_markers`.

---

## 4. Worked example: what the frame does to v1's headline result

The audit of every `exclusivist_monotheism` match is
[results/exclusivist_monotheism_audit.json](results/exclusivist_monotheism_audit.json) — 51 matches, each with
its passage, its printed span, its containing section, its original composition, its dependence rule, the
context sentence it was judged from, and the reason for its verdict. v1 reported 46 term hits in 4 works across
4 traditions and read that as "a particular tradition's doctrine, not a pan-human inheritance". Checking each
match against its actual source:

- **None of the 9 Sacred Books of the East hits is an independent witness.** The work is Project Gutenberg
  #12894 — Epiphanius Wilson's 1900 *digest*. Every one of its matches resolves, from the volume's own printed
  contents page and part headings, inside `SELECTIONS FROM THE KORAN`: 8 sit in the reprinted Qur'an
  translation and 1 sits in the volume's editorial matter, under the printed byline `By Thomas Carlyle` — the
  watchman cry "There is no God but God" as Carlyle reports it, which is evidence that the formula circulated,
  not the formula itself. `config/source_dependence.json` *already* carries a rule joining `quran_sale` to
  `sacred_books_east` as `anthology_reuse`. So v1 counted one source twice and reported it as two independent
  attestations across two "traditions", and the census's fourth tradition label (`Multiple`) is an artefact of
  an anthology sitting beside the work it reprints.
- **The corpus misnames its own Qur'an witness.** The title page of `corpus/raw/quran_sale.txt` reads
  `TRANSLATED FROM THE ARABIC BY THE REV. J.M. RODWELL`, so both the work id and the manifest's `cautions`
  string ("George Sale translation") name the wrong translator, and the pair rule's rationale states the
  dependence backwards — the anthology reprints Sale, while the file called `quran_sale` is Rodwell. They are
  still not two independent attestations of the doctrine, but they are two different English renderings of one
  composition, which is why verbatim overlap between them is zero. A method that quotes provenance fields must
  check them against the printed page.
- **Two hits are substring collisions, not doctrines.** 1 Corinthians 6:17 ("he that is joined unto the Lord is
  one spirit") and 1 Nephi 10:19 ("the course of the Lord is one eternal round") both matched
  `the lord is one`. The Book of Mormon's single hit is one of them, so that work stops being attested at all.
- **Three hits regulate worship, not existence.** `no other gods` in Exodus 20:3 and in two Meccan suras
  presupposes gods to be forbidden; denying them worship is not denying that they exist, so these cannot
  witness to the oneness doctrine even though they are scripture the text endorses.
- **Recall, not just precision, was wrong.** Raw Gutenberg text hard-wraps lines — the file stores `there is
  no\r\nGod.` and the patterns used literal single spaces — so matching after whitespace normalisation raises
  the count from 46 to 51 and recovers Isaiah 44:6, Mark 12:29 and four Qur'an confessions. Each of the five is
  published with its wrapped printed span, so the cause is checkable and not asserted.
- **The family's own formula class is much larger than the family.** The audit probes 16 oneness formula
  strings the census never carried — "there is none else", "I am the LORD and there is none else", "none else
  beside", "there is but one god", "one without a second" and others — and finds **79 occurrences, none of them
  caught by the published patterns**. They are deliberately *not* folded into the family: widening a regex
  without match-level adjudication reproduces the error that made the count untrustworthy. They are the
  measured size of the recall gap, and the corrected 51 is a floor, not a ceiling.
- **The same first-person formula appears in a non-divine mouth.** Isaiah 47:8 and 47:10 give Babylon, and
  Zephaniah 2:15 gives the rejoicing city, the words "I am, and none else beside me" / "I am, and there is
  none beside me" — the divine confession form spoken by a claimant the text is condemning. These sit inside
  the 79 missed occurrences, so a widened regex would have counted five formula hits over three denunciations as
  confessions. The identical wording carries opposite doctrinal force depending on who is printed as saying it,
  and no term-matching census can see that.
- **One confession-form match inside the family is a denier's deathbed profession.** The family's own hit at
  `quran_sale:s0535` is Pharaoh drowning — "I believe that there is no God but He…" — which the narrative
  presents as the words of one whose profession is refused. It has the shape of the doctrine and is not a witness
  to it, and v1's census counted it as doctrine.

Net effect on v1's headline: of four "works", one contributes no additional witness at all, one is reduced
to a substring collision, and three matches that were counted as existence claims are worship prohibitions.

**34 matches classified as confessional across two works not marked dependent under the currently configured
source-dependence rules. Independence has not been established because dependence closure remains incomplete.**

The whole match set is partitioned in `results/exclusivist_monotheism_audit.json` under `disposition_table`, and
the rows are generated by rule order and then re-derived by predicate in the same run (`disposition_check`), so
a match counted twice or dropped would fail the run instead of shipping. Every one of the 51 audited matches sits
in exactly one row:

| disposition | matches | works | evidence for the family? |
|---|---|---|---|
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

The first row's 34 is the largest set any independence sentence may be about, and it is still labelled
*not marked dependent* rather than *independent*: `config/source_dependence.json` lists pair rules one at a
time, there is no closure over the corpus or over the external sources each work reprints, and `verbatim_overlap_
with_declared_source` is zero for the Sale/Rodwell pair — two works can be independent printings of one source
while no rule mentions either. The record-level field keeps its v1 name `counts_as_independent_attestation` only
so the schema stays stable; `verdict_counts.matches_by_dependence_marking` states what it means.

Across the 51, 42 are confessional (34 not marked dependent + 8 marked dependent), 2 traditions survive instead
of 4, and 9 are not confessions of sole divinity at all. The claim "oneness is documented in a minority of works
from some textual families" is not *wrong* — exclusivist monotheism really is unevenly distributed — but the
evidence v1 offered cannot carry it, and the direction it was used to point (against common ancestry) is
unsupported for the separate reason in §8.

This is the template for the audit discipline in §5: every match resolved to its containing volume, its
section, its original composition, and its dependence relation, before any count is quoted.

---

## 5. Provenance and source-dependence requirements

No state record is usable until it carries:

1. **Locator** — work, passage, section, character span, in a whitespace-normalised text whose raw offsets are
   preserved so citations stay exact.
2. **`original_textual_source`** — the composition the words belong to (Surah al-Baqara; Deuteronomic source;
   the Kings narrative; a redactor's gloss), not the volume they were printed in. For anthologies this
   requires a section index built from the file's own contents, because an anthology is a container, not a
   source.
3. **`source_dependence_relation`** — resolved against `config/source_dependence.json`, with reprints marked
   `counts_as_independent_attestation: false` at *record* level. Work-level exclusion is insufficient: the
   Wilson volume is independent for its Upanishad selections and dependent for its Qur'an selections.
4. **Editorial-layer separation** — translator prefaces, commentary, chapter titles, verse numbers and
   collector framing are a distinct attestation class (`editorial_or_ethnographic_description`) and may never
   corroborate the doctrine they describe. v1's strongest "four traditions" number included exactly this kind
   of record.
5. **Dependence-graph closure** — where work C reprints B which translates A, the chain must be recorded, not
   just the pair. The present file has 15 pair rules and one family; that is far below what a 65-work corpus
   of nineteenth-century compilations requires, and closing it is a gate (§9), not a refinement.

---

## 6. The hypothesis, restated as four models that can be beaten

The working hypothesis is **inheritance with transformation**: concepts are transmitted and then modified, so
the descendant state need not resemble the ancestor. This is not unfalsifiable, because it does not predict
arbitrary outcomes — it predicts states reachable by named operators along **typed, dated** routes. The
operator vocabulary is in `divinity_ontology.json > transformation_operators`: elevation, demotion,
absorption, abstraction, personification, euhemerisation, negation-inversion, functional transfer, scope
narrowing, scope expansion, differentiation, nominalisation, silencing.

v2's first version of this section stated the four models and then stopped, which left three of the four
claims in the condition set unpriced and the central prediction unmathematicised. The layer now lives in
[config/model_comparison_v3.json](config/model_comparison_v3.json) and is executed by
[tools/compare_models.py](tools/compare_models.py). Its output today is
`status: "not_yet_testable"` with the list of inputs it is missing, published as a result rather than as a
crash. **Nothing here has been tested, and no model has been ranked.** What follows is the specification of
the test and the licence conditions on reporting it.

**6.1 Two edge types, and the confession that M1 conflated them.** Descent through a cultural or population
lineage (*vertical inheritance*) and movement by contact (*horizontal transmission*: borrowing,
back-borrowing, deliberate restoration, revival, translation-mediated transference, coercive religiation,
editorial citation) are different claims with different evidence, and each now has its own edge type and its
own evidence list. The conflation is not hypothetical; it is in the file. `competing_models.M1.predicts`
carries no edge type at all, listing "operator signatures preserved across languages" and "shared arbitrary
non-functional detail travelling with **the contact chain**" as predictions of one ancestral-root model, and
then computing a distance gradient over that undifferentiated relation; and the operator discipline's
condition (c) reads "a contact, transmission **or** dependence relation", one disjunction covering both
kinds. A short-distance contact pair can therefore score like a long-distance descent pair, and M1's
parsimony is inflated by exactly the amount the borrowing edges contribute — which is the thing M3 exists to
compete with. So: `edge_type` is mandatory and exclusive; `descent_or_contact` is an illegal value; an edge
with a documented contact route that could carry the state alone is reported `edge_type_ambiguous` and scored
under both typings or not at all. And a descent claim may not be argued from the similarity it is supposed to
explain — the tool refuses descent evidence whose declared basis is `conceptual_similarity`, because an edge
inferred from its own explanandum makes the hypothesis unfalsifiable by construction.

**6.2 The four models, with their admissions stated.** Each model is now a likelihood, not a mood: it admits
a specified set of edge types and produces a distribution over similarity classes.

| Model | Claims | Edges it may use | Predicts that the others do not | What would make it less likely |
|---|---|---|---|---|
| **M1** one ancestral concept, then transformation | one root state, diversified in descent | vertical from one root; horizontal only as contact borrowing, after the root is fixed | low parsimony against a *single* root; arbitrary non-functional detail travelling with the dated **descent** chain; an operator-signature profile that matches which operators ran, not merely how far | two or more roots surviving in the earliest dated stratum of one lineage; concordance confined to the functional dimension block while the expressive block is free; similarity uncorrelated with typed vertical edge count |
| **M2** multiple independent origins | separate invention per lineage, similarity limited or none | none; similarity read off the background distribution over pairs with `no_known_route` | deep-lineage states sharing nothing but functional pressure; surface similarity confined to known translation reuse | shared arbitrary specifics on a pair with a documented typed edge; similarity tracking edge count rather than pressure |
| **M3** regional inheritance, then mixing | several regional roots, reticulate later contact | vertical within region, horizontal and restoration between regions, each with its own rate | strong within-region signal, weak or conflicting between-region signal; dimension-profile splits on transfer edges (D1_ontological_category inherited while D2a–c are replaced); the same state reached by different operator paths | a tree that fits every region; the reticulation parameter estimating to zero; transfer edges that show no selective transmission |
| **M4** independent development, then convergence | separate origins, convergent elaboration under shared pressures | none; similarity drawn from the declared attractor prior over the dimension blocks | state recurrence uncorrelated with contact distance; recurrence concentrated in `functional_or_pressure_prone`, dispersed in `arbitrary_or_expressive` | similarity correlated with contact or descent distance once provenance is closed; shared arbitrary detail an attractor cannot generate |

M2 and M4 are **baselines**, not candidates for preference: only an inheritance-bearing model (M1, M3) can be
reported as preferred, and only by beating them by the margin in §6.7.

**6.3 The prediction is a distribution, not a decay curve.** M1's fifth prediction — "gradient of
dissimilarity increasing with dated distance from the root" — is withdrawn, because it is the wrong shape.
Inherited concepts are transformed, rediscovered in an archive, borrowed back by the lineage that exported
them, and deliberately restored by reform movements that prefer the older state. What replaces it is a
distribution over similarity class given the pair's date ranges, its typed edge multiset and its contact
status. Each operator *o* fires on each dated edge as a thinned Poisson process with its declared rate
λ_o, and each firing multiplies the retained similarity by its declared retention ρ_o, so
E[ln s] = Σ_o k_o ln ρ_o: the *identity* of the operators sets the rate of change, not the elapsed years.
Horizontal edges carry a declared rate factor (1.2), and a restoration, revival or back-borrowing edge resets
similarity toward the archived witness with probability 0.35 (capped at 0.8). All of these are analyst-set
priors recorded in the config with their reasons; none is a measurement, and the mean edge event rate is
reported with a sensitivity band of [0.1, 0.6] until data can estimate it.

The old monotone prediction is retained as a **nested special case** — equal rates across operators, one
averaged retention (the unweighted geometric mean of the thirteen, 0.564, at the same total rate of 0.310
events per edge), reversals switched off — which is what makes it falsifiable rather than decorative. The mean
is unweighted rather than λ-weighted (which would give 0.618) because the nested case exists to give the old
prediction its best shot, not its softest one. Both are reported
side by side on every run. The derived numbers, recomputable from the config by the tool:

| Pair specification | v3 predicted classes | monotone-decay nested case |
|---|---|---|
| 1 dated vertical edge | identical .733, near .103, partial .091, far .066, unrelated .006 | identical .733, near **.000**, partial .227, far .035, unrelated .004 |
| 8 vertical edges | identical .084, near .094, partial .179, far .306, unrelated .338 | identical .084, near **.000**, partial .208, far .258, unrelated .451 |
| 8 vertical edges **+ 1 restoration edge** | identical **.451** at 6 edges, near .085, partial .136, far .190, unrelated .138 | identical .156, near .000 — the decay case cannot use the restoration at all |

The sharpest single consequence is the column of zeros: a model with one averaged retention **cannot put any
probability on the `near` class** (0.75 ≤ s < 1.0), because a single factor jumps from 1 straight to ρ. Dated
pairs that sit in `near` concordance therefore refute the decay submodel outright and are predicted by the
operator-structured one. That is the cheapest observation that discriminates, and it is the first thing to
look for once dates exist.

Similarity itself is now a defined quantity rather than a rhetorical one: exact match on the single-valued
keys (`D2a_acknowledged_population`, `D2b_reality_of_others`, `D2c_worship_exclusivity`,
`D7a_speaker_attribution`, `D7b_speech_act`, `D7c_discourse_genre`, `D7d_epistemic_commitment`), Jaccard on
the set-valued ones (`D1_ontological_category`, `D3_agency`, `D4_cosmic_function`,
`D5_universe_relationship`, `D6_temporal_nature`), mean over comparable keys, `undecidable` keys skipped and
published as skipped, and **no score below six comparable keys** — no defaulted value, because a defaulted 0.0
would read as evidence for M2 and a defaulted 1.0 as evidence for M1. These are the twelve keys §3 now lists,
row by row: the split has been made, not merely planned, and the seven composite rows of v2 are the antecedents
named in the migration report rather than a table this frame still carries. The split is exactly what makes the
operators separable, since `negation_inversion` preserves D7b and D7c while flipping D7d and D2b, and the old
single D7 could not tell an inverted confession from a confession at all. The three presence fields —
`conceptual_presence`, `doctrinal_endorsement`, `historical_transmission` — replace the old single refusal
state, and a pair identical on all twelve keys but differing on `doctrinal_endorsement` is a different state:
the Babylon boast of §4 and the Isaiah confession share their dimension vector and do not share a fact.

**The twelve keys are two kinds of thing, and the scorer does not average them into one number without
saying so.** D1–D6 say what a proposition claims is the case; D7a–D7d say what kind of speech it is. In a
corpus of English translations the second block is heavily a property of the translator's prose and of genre
convention, so a pair of catechisms can reach a high overall mean while disagreeing on every conceptual key,
and a creation narrative beside a creation hymn can reach a low one while agreeing on D1, D3, D4 and D6. One
mean hides both cases in the same number. `similarity_between` therefore publishes, beside the mean, a mean
for each `reading_blocks` group and a `pattern` naming which block moved:

| Pattern | Block shape | What it does *not* license |
|---|---|---|
| `shared_state_and_shared_speech_situation` | both blocks ≥ 0.5 | an inheritance claim — equally what borrowing, one genre, or two translations of one composition produce |
| `shared_conceptual_state_differently_spoken` | conceptual high, discourse low | descent — it is also two genres quoting one another |
| `shared_genre_without_a_shared_state` | conceptual low, discourse high | any doctrinal agreement; common in a run, it says the instrument is measuring English prose styles |
| `neither_block_shares` | both < 0.5 | an absence claim — 40 of the 93 declared values carry no English detector, so divergence and invisibility read alike |
| `indeterminate_missing_block` | one block has no comparable key | anything at all: reported as missing, never as 0.0 or 1.0 |

The high/low cut is 0.5 — the `partial` boundary already declared in `similarity_classes`, reused rather than
newly chosen, so it is the same number the probability grid uses and not a second threshold tuned for this
table. Both block partitions are analyst-set and published before any pair is scored: `dimension_blocks`
(`arbitrary_or_expressive`, `functional_or_pressure_prone`, `structural`) sorts keys by proneness to
convergent pressure and serves the arbitrary-detail test, while `reading_blocks` separates state from speech.
They are not the same cut and neither is measured. Because the mean is taken over *keys*, blocks carry
unequal weight by their size: 8 of the 12 keys are conceptual, so a pair disagreeing on all four discourse
keys scores 0.666667 while a pair disagreeing on all eight conceptual keys scores 0.333333. That is a
consequence of the declared key list, not a finding, and the pattern column is published precisely so that a
reader sees which block moved instead of inferring it from the mixture.

**6.4 A priced vocabulary, a path limit, and per-operator evidence.** Thirteen unconstrained operators is not
a constraint: at paths of up to three applications the table names 13 + 13² + 13³ = 2,379 labelled routes,
more combinations than this project has datable expression pairs, so almost any two states can be connected
after the fact. The answer is to price the vocabulary. Every operator carries a cost (monotone in evidence
burden and in confoundability), a rate, a retention, a cap on reuses, and the specific evidence items it
requires; parsimony of a candidate derivation is the sum of its operator costs plus 2 per intermediate node no
witness attests.

| Operator | cost | λ per edge | ρ retained | the evidence that must exist before it may be asserted |
|---|---|---|---|---|
| elevation | 3 | .030 | .80 | earlier subordinate rank, later supremacy, ≥2 attributes carried across, a typed edge, one independent witness |
| demotion | 3 | .030 | .70 | higher and lower rank attestations, identity argument that it is the same figure, typed edge, independent witness |
| absorption | 4 | .020 | .55 | both names attested separately, a witness where one carries the other's predicates, a later witness with one name, onomastic argument |
| abstraction | 5 | .015 | .40 | agent attestation, principle attestation, a **bridging re-description**, a documented transmission path, identity of reference argued on D1 not on vocabulary |
| personification | 5 | .015 | .40 | principle prior in the same tradition, agent under the same name, a cult or dedicatory witness that it is addressed, ordering met |
| euhemerisation | 4 | .015 | .50 | divine attestation, human-biography attestation, the genealogy or travel narrative dated, a second hand receiving it |
| negation_inversion | 4 | .015 | .60 | both formulae with locators, the shared syntactic frame shown on the surface text, ordering met, typed edge, independent witness |
| functional_transfer | 4 | .025 | .65 | function with the earlier holder, same predicate with the later holder (not a paraphrase), typed edge, independent witness |
| scope_narrowing | 2 | .040 | .75 | cosmic and bounded attestations, term identity or an original-language check, typed edge |
| scope_expansion | 2 | .040 | .75 | local and cosmic attestations, term identity argument, typed edge |
| differentiation | 4 | .020 | .45 | undivided term, each resulting term, a dated dividing layer, an argument that these are not doublets |
| nominalisation | 3 | .030 | .80 | title-use and name-use **in the source language**; an English rendering is inadmissible |
| silencing | 5 | .015 | .30 | two witnesses of one passage, term present in one and absent in the other with the passages aligned, a dated editorial or censoring layer, a stated motive |

Three consequences are enforced rather than exhorted. (i) A claimed derivation may invoke at most
**three** operator applications, at most **two** if it is to be *reported as preferred* without an attested
intermediate, and at most **one** intermediate node may be unattested — an unattested step is a postulate and
is priced as one. (ii) `scope_narrowing`, `scope_expansion`, `functional_transfer` and `nominalisation` are
marked attractor-confusable and **may not constitute a derivation on their own**, however cheap they are:
independent origin predicts the same moves, so their cheapness is visibility, not discrimination. (iii)
`silencing` may be asserted only where the passage is attested on both sides; it may never be used to explain
a state that is simply missing from an incomplete corpus, because that converts an instrument gap into a
historical event, which §8.1 forbids. Violations return `rejected_derivation` with the constraint named and no
score; a pair with no admissible path is `undecidable_route`, which is not evidence for independent origin.

**6.5 The four conditions are a conjunction.** The rule as first written here ended "Two of the four unmet ⇒
`undecidable`", which is ambiguous: read as a threshold it licenses a claim at three of four, and read as a
warning it says nothing about the case it names. **The decision is that all four conditions are jointly
mandatory** — (a) both states attested with locators, (b) the earlier expression's *composition* range not
postdating the later's, at the §6.6 threshold, (c) a documented route **of the declared edge type**, with that
type's own evidence list, and (d) at least one independent witness outside the translator or edition being
explained. Any single unmet condition yields `undecidable`. The number met is published and confers nothing
below four, there are no waivers, and the four block four different failures (unverifiability, reverse
causation, coincidence, a translator's habit) rather than four grades of the same one.

**6.6 Dates are ranges, and a witness is not a composition.** Every expression in a derivation carries
`date_earliest`, `date_latest`, `dating_basis` (critical edition, manuscript witness, recension comparison,
internal criterion, parallel transmission, archaeological context, colophon, translation of record, specialist
consensus, or undated), `date_confidence`, `survival_or_composition` and a `reference`; §2's three date fields
become ranges under those bases and are never collapsed. **An earlier surviving witness is not evidence of
earlier composition**: a manuscript bounds the *wording* from above and says nothing about when the concept
was held, and a recording or printing date bounds only the printed text — which is the whole state of the
collector-recorded material in the corpus, and is recorded as such in `results/attestation_scaffold.csv`
rather than assumed. Priority claims are therefore computed from composition ranges only; a pair whose
ordering depends on survival dates comes back `ordering_undecidable_survival_only`. Direction is granted only
when P(A precedes B) ≥ 0.95 under a uniform density over each range, computed by exact enumeration of year
pairs, so the number is a consequence of the ranges and not a judgement; below that the pair is
`ordering_undecidable`, contributes to similarity statistics and to no model likelihood. Today the scaffold
holds 65 works, none with a filled composition range and **0 usable for a priority claim**, so this is the
binding constraint on the section, not a detail of it.

**6.7 Preregistration is a hash, and preference needs a margin.** What must be fixed before the run, and
where it is fixed: the operator table's costs, rates, retentions, evidence lists and permitted edge types plus
the path constraints, the dimension blocks and the attractor alpha vector, the margin, the power
simulation's own declared grid, seed, replication count and target probability (the pair floor is an output of
that simulation, not an input to it), the candidate pair list with its record ids, and a proposal ledger entry for every operator assertion
recording `proposed_at`, `observed_at`, `proposed_before_observation` and the note's hash. The mechanism, not
the promise: the config carries `preregistration.mechanism.operator_cost_table_sha256`
(`f972152e42a3dd060b5096d2ed9533fa295c821cf40012cf17d851eca64c64ea`, registered 2026-11-01) over the
canonicalised table, and [tools/compare_models.py](tools/compare_models.py) recomputes it before scoring;
a mismatch returns `not_preregistered` with both hashes published and no score. Editing a cost in place
invalidates the hash, so re-registration means a new date, a new hash, a retained copy of the old table, and
every derivation claimed under the old table re-run and reported under both. An operator proposed after seeing
the pair it explains is recorded, not deleted, and demoted to `post_hoc_exploratory`: excluded from reported
derivations and from every likelihood, reportable only if tested on a pair not yet observed, with the count of
such assertions published next to the result.

Preference is then a margin, declared once —
`four_way_decision_rule.stage_1_symmetric_competition.margin_log10_bayes_factor`, 2.0, read by both stages and
never re-typed — and it is a **two-stage rule**, because the two questions this section used to merge are not
one question.

**Stage 1 asks which model describes the pair set.** All four models score the identical pairs with the
identical likelihood function, and the decisive quantity is the leader's log10 Bayes factor **over the
runner-up**. It is deliberately not a factor against M2: a rule written as "inheritance beats the null" makes
M2 the denominator, M4 decorative and an M1-versus-M3 choice untestable, which is exactly the asymmetry the
first version of this section had. `no_decisive_winner` is a declared outcome and a published result, not a run
that failed to produce an answer.

**Stage 2 asks whether a historical sentence is licensed.** An inheritance-bearing model (M1 or M3) must beat
the no-edge, no-operator baseline M2 by the same declared margin, with M4 reported separately and never
counted as a demonstrated derivation. Both stages are emitted on every run and neither implies the other: the
fixture set in [tests/test_model_comparison.py](tests/test_model_comparison.py) has M1 and M3 predicting the
same profile, so stage 1 separates them by exactly **0.0** log10 units while stage 2 puts both of them
**226.988839** log10 units over M2. One headline status would have had to be either an overstatement or a
silence; two published stages are neither.

**The evidence floor is simulated, not asserted.** A winner is emitted only when the pair set clears two
floors published by `python tools/compare_models.py --power` into
[results/model_power_simulation.json](results/model_power_simulation.json): the smallest pair count on the
declared grid at which stage 1 names the generating model decisively in at least 0.8 of replications **for each
of the four models as the truth** — currently **220 pairs**, with M1 the binding truth — and the 5th-percentile
Kish effective count of that binding cell, currently **29.051621**. The earlier "at least 20 dated route-typed
pairs" was an analyst's number with no derivation behind it. It stays in the config as
`historical_floor_in_config`, the tool reports it as superseded wherever a gate refuses, and a run of the
simulation that derives no floor refuses every pair set rather than quietly falling back to 20.

**The holdout folds by cluster, not by pair.** Each pair declares its `work`, `witness` and optionally
`lineage` labels; a test fold is held out by cluster label on the published seed (20261031), and every pair
touching a held-out cluster is a test pair, so no work contributes evidence to the model choice and confirmation
at the same time. The run publishes the two checks that matter — no pair in both folds, no held-out cluster
present in the discovery fold — along with `discovery_clusters_spanning_folds`, the residual leakage a work
shared across traditions cannot avoid, and an `isolated_test` fold of test pairs whose endpoints are both held
out. The margin must hold on the whole set **and** on the cluster holdout. Dependence is then counted rather
than assumed: Kish's effective sample size, with each pair assigned to the more widely shared of its two
endpoint works, makes 220 pairs drawn from a single work **one** observation, and the gate says so in the
refusal.

The severity is deliberate in both stages: a priced thirteen-operator vocabulary will fit almost anything, so
the fit has to be far better than the null before a reader is told the word "inherited". Failure at stage 1
returns `no_decisive_winner`; failure at stage 2 returns `not_preferred_over_independent_origin` with both
log-likelihoods and the achieved factor, and that is the outcome this layer expects for most pairs it will ever
be given.

**6.8 What this section still does not do.** It does not rank the models; it states the ranking's conditions
and computes them when the inputs exist. The four remain live, the config's own status field says the layer is
a specification of a test rather than a result, and the tool's published output today is
`not_yet_testable` with the missing inputs named — dated composition ranges, typed route evidence, the second
coder, the dependence closure, a pair set. Two disciplines from before still hold and are now enforceable: the
models are compared by which predicts the observed distribution of **dated, edge-typed** states best, not by
plausibility; and no absence, no non-detection and no undecidable cell may be spent as evidence about the
past. v1 announced a winner in a vocabulary census; v2 announces the test, priced, hashed and refused until
the data arrives.

---

## 7. Multilingual attestation, and the honest state of it

**What this instrument is: a multilingual-*ready* research framework, not a multilingual or
language-independent instrument.** Every detector that ran in the current run is an English translation-text
pattern, `expression_language` is `English (translation)` on all 47,641 records, and the frame's own
`multilingual_status` field says source-language detection is not operational. Nothing in this section should
be read as claiming that a tradition's own wording was examined; the records are evidence about English
translation vocabulary, and the design below is the plan for what would have to be built to say more.

Detection is *defined* per **state**, not per English word. The lexicon is written so that it can carry, for
each value, entries in every language in which the value is claimed expressible, with expression, script, ISO
code, transliteration, gloss, source text, attestation range, date basis and reference; on that design a state
would be attested in a work if *any* entry for it matched in *any* language the work's sources are written in.
No entry has yet met the condition attached to that clause — see §7.1 — so the clause is currently inert.

Three rules make this usable rather than decorative.

**7.1 Unverified entries generate candidates, never counts.** `verification_status` is
`unverified_secondary_literature` on all 32 entries that
[config/divinity_lexicon.json](config/divinity_lexicon.json) currently holds, because no entry has been read in
the source language or checked against a critical edition with page and line. The instrument therefore refuses
to score them. This is a gap in the instrument, not a finding about the past, and the file says so in its own
`status` field.

**7.2 Transliteration presence is an orthographic accident.** Values whose terms were transliterated rather
than translated (Brahman, Dao, Elohim, deva, yazata, manitou, avatar) are the best-detected in the whole
frame — for no reason except that a Victorian editor left the word alone. The frame publishes this as a bias,
not a distribution: a tradition whose terms were translated away looks conceptless.

**7.3 Translation decisions are data.** Every value entry carries a `caution` naming the decision embedded in
the English: `ʾĕlōhîm` is morphologically plural and the KJV prints "God"; Deut 6:4's `eḥad` is contested
between "one" and "alone"; `kami` is rendered "god"; the Dead Sea reading of Deuteronomy 32:8 differs from the
text the KJV translates. So no Hebrew or Greek plurality claim may be coded from an English Bible. The
English text is a *witness to a translation*, and `edition_or_translation_date` records which.

---

## 8. The revised inference rules — this is the section that replaces v1's conclusion

**8.1 Non-detection is not detection of absence.** For a tradition *t* and state *s*:
`¬detected(s, t)` licenses exactly one report — "not detected by this instrument in these sources". It never
licenses `not_attested_in_available_sources`, which requires an exhaustive search of an instrumented value
over a corpus known to represent *t*. Where the search was not exhaustive, the state is
`undecidable_from_available_sources`. The three states are never merged, and the third is expected to be the
majority.

**8.2 No conclusion about ancestry may be drawn from a distribution that all models predict.** Before any
count is used to favour or disfavour a model, the count must be shown to differ under the models — a stated
prediction, then the observation. v1's "no grammar is present in all 65 works" is predicted by M1 (because
transformation relocates markers), by M2, by M3 and by M4; it therefore ranks nothing.

**8.3 Absence carries a power requirement.** An `not_attested_in_available_sources` report is admissible only
with a stated detection probability for the value in that source class. If the instrument's recall for a
value is below an agreed floor, absence may not be reported at all for that value. Recall is measured
against §9.2's gold standard; until then, every absence is `undecidable`.

**8.4 What would count against M1.** Specific, not general: (i) the same arbitrary, non-functional detail
absent from the earliest stratum of a family that had no contact route to the proposed root; (ii) a state
distribution better predicted by ecological or cognitive distance than by descent, with the comparison
preregistered; (iii) a documented transformation requiring a contact route that demonstrably did not exist;
(iv) apparent shared states dissolving under provenance analysis into shared *translation* — which §4 shows
is a live risk, not a hypothetical one.

**8.5 What would *not* count against M1**, and this is the correction v1 needed: the absence of any
English-language grammar from every work; the diversity of divine concepts; the presence of traditions with
impersonal ultimates; the presence of non-theism; the failure of a lexical similarity search; and the fact
that the closest analogue to the "one concept" hypothesis turns out to be a doctrine of particular
traditions.

**8.6 Truth and origin stay separated.** Proposition C (that no such beings exist) remains permanently out of
scope for any textual method, in both directions. The revised conclusion also removes the reverse temptation:
evidence of inheritance is not evidence that a concept refers to anything real.

**8.7 The conclusion Track B is licensed to write today** is exactly this: *the instruments now exist to ask
the question without begging it; the question is open; four models remain live; the binding constraints are
annotation reliability, dated attestation and dependence closure — not the absence of a result.*

---

## 9. Annotation, evaluation and the gates

### 9.1 Independent human annotation

Machine records are candidates. The annotation layer must be independent of the detector that produced them.

- **Sampling**: stratified over dimension values (rare values oversampled), over works and over speech acts, so
  precision per value is estimable rather than assumed. Target ≥ 3,000 **propositions** for the first
  reliability set, sized to estimate κ with a usable interval for the rare values, then expand. All three
  layers are now enforced in the sampler: dimension value, work, and `D7b_speech_act` are drawn as separate
  strata, so precision is estimable per value and per work rather than per value only.
- **Blinding**: coders see the proposition, the window that carries it, the locator, and nothing about the
  detector's assignment or expected value. Order randomised and recorded; the randomisation seed is published.
  The plan also publishes the one leak it cannot close — the locator names the work, so a coder with domain
  knowledge can guess what the proposition is about.
- **Two coders per proposition, independently.** Disagreement is *data*, adjudicated with the reason recorded,
  not silently resolved by a third opinion that overwrites the first two.
- **The `undecidable` rate is itself a measured quantity.** A coder who never selects `undecidable` is not
  reading; that appears here and nowhere else.
- **What exists now**: [tools/prepare_annotation_packet.py](tools/prepare_annotation_packet.py) writes a blinded
  packet of **6,199 propositions** (74,388 judgments per coder): **4,699 machine-flagged candidates** over **48
  dimension-value strata**, with **65 works** and **8 speech acts** enforced as separate stratification layers
  and **11 rare strata taken as a whole-population census**, plus **1,500 no-record probe rows** (seed 20261101,
  published). The coder view, the answer key and a published codebook
  ([results/annotation_codebook.csv](results/annotation_codebook.csv)) are separate files so the key cannot leak
  into a coding sheet. All three codable states are sampled — `candidate`,
  `candidate_requires_human_disambiguation` and `not_yet_instrumented` — because a packet drawn only from rows
  the instrument is already sure of would measure the instrument's agreement with itself. The coding columns are
  the twelve dimensions (the set-valued ones take a semicolon list) plus `referent_terms`,
  `unit_is_a_single_proposition` — the coder's verdict on whether the machine cut the right unit — and the two
  separate questions `concept_represented` and `doctrine_endorsed_by_text`. Propositions whose machine
  assignment is not unique on a single-valued dimension are flagged in the key rather than silently given one
  winner; 3 such propositions are in the packet (10 records in the run carry a `value_conflict` list), and the
  coder — not the sampler — decides which value the proposition carries; 9 packet propositions are flagged
  overlong.
- **The packet can now measure recall, which it provably could not before.** The three candidate strata all
  draw from propositions that already carry a machine record, so they bound precision and say nothing about
  misses: a sample of hits contains no misses, and no pairing figure is the detector's recall — the superseded
  banding scored 0.023214 measured on the deterministic 1,632-passage subset and 0.023475 corpus-wide, and the
  exact index that replaced it scores 1.0 against the relation it defines without telling you anything about the
  40 declared values it has no pattern for. So the builder enumerates the detector's own proposition universe over the eligible passages —
  **1,028,478 segments**, of which **36,775** carry a record and **991,703** carry none — and draws two
  disjoint simple random samples from the no-record part: **944,451 cue-negative** segments (900 drawn,
  π = 0.000952934562, w = 1,049.39) and **47,252 cue-positive** segments (600 drawn, π = 0.012697875222,
  w = 78.7533). Each drawn row carries its exact inclusion probability and weight into the answer key.
  Two strata rather than one because misses concentrate where the text names a divinity: a single uniform draw
  would spend nearly all its rows where nothing is, and the cued region would go unmeasured; stratifying and
  weighting keeps the pooled estimate design-unbiased over the whole no-record population. The cue list
  ([config/recall_probe_cues.json](config/recall_probe_cues.json), 111 cues verified over this corpus by
  [tools/check_recall_cues.py](tools/check_recall_cues.py), 6 ambiguous cues retired with reasons) is a
  *sampling instruction* — `not_a_detector: true` — so a cue never produces an attestation, a value or a
  doctrinal count. Probe rows are indistinguishable from detection rows in the coder view, which is what keeps
  the two kinds of row from being coded to two standards.
- **Two estimands, kept in two blocks.** [tools/score_annotation.py](tools/score_annotation.py) computes
  per-value precision on `machine_candidate` rows only, and detector recall on the probe rows only, as a
  Horvitz–Thompson estimate: `recall_hat(v) = detected_v / (detected_v + Σ w)`, where the weight sum runs over
  probe rows *both* coders independently read as carrying value `v` — one coder's over-reading is never
  projected onto a corpus — and `detected_v` is counted over the whole corpus, not over the packet. A stratum
  that finds no miss reports a one-sided exact binomial bound on its miss share instead of a recall of 1.0, and
  a value the probe never produced gets no estimate rather than a perfect one. The scorer refuses to run on a
  key with no probe rows and on a probe row with no weight.
- **The scorer also refuses** to run on one coder and refuses the same sheet supplied twice.
  The packet is **above** the 3,000-proposition target in size; what it is short of is coders. **No coder has
  coded it**, so it produces no reliability figure. That, and not a number, is the current state
  of this gate: [tools/score_annotation.py](tools/score_annotation.py) refuses to run on one coder and refuses
  the same sheet supplied twice.
- **Reliability**: Cohen κ per single-valued dimension; mean Jaccard per set-valued dimension (D1, D3, D4, D5,
  D6); published with the observed-vs-chance decomposition. v1's `cannot_support` list already identified "no
  second coder" as its own weakest link, and that gate has not been passed since.
- **No reliability claim from one analyst.** The audit verdicts in §4 are single-analyst readings, carry
  `adjudication_provenance: single_analyst_reading`, and are the *input* to a reliability test, not its result.

### 9.2 Semantic precision and recall

Computed **per value, never per grammar**, on all twelve dimensions, so that a failing value cannot hide inside
a neighbour's success. [tools/score_annotation.py](tools/score_annotation.py) is the implementation, and it
imports the cardinalities from the packet tool rather than restating them, so the sheet a coder fills in and
the sheet the scorer reads cannot drift apart.

- precision = (machine candidates a coder also assigns to *s*) / (all machine candidates for *s*)
- recall = (instances of *s* in the gold set that the machine found) / (all gold instances of *s*)
- set-valued dimensions (D1, D3, D4, D5, D6) are scored by mean Jaccard over the two coders' value sets,
  single-valued ones by Cohen κ; forcing a single choice on a set-valued dimension and scoring the forced
  choice as agreement would invent concordance. A value one coder saw and the other did not is reported as
  `seen_by_one_coder_only`, not folded into the machine's precision figure.
- the two questions that replaced the old refusal state are coded and scored as **separate columns with their
  own published vocabularies** — `concept_represented` and `doctrine_endorsed_by_text` — each with its own
  agreement statistic, so a withheld endorsement is a disagreement recorded on one axis rather than a row
  deleted from the other. `conceptual_presence` is what the whole packet answers, because a conditional, a
  question or an opponent's reported speech is still evidence that the proposition is represented in the text;
  `counts_as_affirmative_doctrine` is the derived boolean only a subset can answer. A withheld endorsement on a
  proposition the gold standard reads as asserted doctrine is the false negative v2's block hid by deleting the
  record; in v3 it is a scored error instead, and `machine_only` and `human_only` counts keep precision failures
  and recall failures apart per value.
- per-dimension confusion matrices, plus the `undecidable` selection rate per coder
- **baselines that must be beaten**: whitespace-normalised regex; a per-work majority prior; a word-only
  baseline. If the dimension frame does not beat all three it is decoration and will be reported as such
- **ablation that must reproduce v1's errors**: removing the D7 block (D7a–d) must bring back the Corinthians,
  Book of Mormon and Isaiah-in-an-anthology false positives. If it does not, the instrument is not doing what
  this document claims — that is the falsifiable part of the design.

### 9.3 Gates before any historical sentence may be written

| Gate | Status today | Consequence |
|---|---|---|
| Every value instrumented, or reported `not_yet_instrumented` | partly — 9 of the frame's 93 declared values are published as `not_yet_instrumented`, and only 53 of the 93 carry an English detector pattern at all | those values may never appear in an absence claim |
| Whitespace normalisation | **met** — recovers Isaiah 44:6 and Mark 12:29 | mandatory in every later run |
| Formula-class coverage for each value | not met | recall cannot be claimed until the missed-class probe is empty or explained |
| Anthology/volume-level provenance per record | met for exclusivist monotheism, not met corpus-wide | corpus-wide completion is the next audit task |
| Dependence closure including chains and editor-level reuse | not met | independence claims suspended |
| Second independent coder + κ | **not met** | **binding constraint on all expansion** |
| Gold-standard precision/recall per value | not met | no absence report permitted |
| Dated composition and earliest-witness fields populated | not met | no ordering, no priority, no chronology |
| Original-language entries read first-hand | not met (zero entries) | lexicon remains a search plan |

The gate table is the point of this document. Expansion of corpus, grammar or graph size before the
annotation and dating gates are passed increases the number of unadjudicated candidates and adds no evidence;
v1 demonstrated exactly that failure mode at 8.7 million words, and the v3 run has already multiplied the
unadjudicated candidate count to 47,641 records without moving a single gate in this table.

---

## 10. Scale: full-corpus graphs, and the path to a million records

### 10.1 What changes now

v1's graph drew 60 nodes and 149 edges from a 100-pair truncation
([tools/build_relevance_graph.py:258](tools/build_relevance_graph.py#L258) — `[:100]`), so the published
"picture" was a sampled triage list of a 9,428-candidate search over 34,281 passages. The new layer removes
the truncation — and, as the third bullet below records, removing a truncation is not the same as evaluating
every pair:

- every eligible passage is coded against every dimension value — **23,385 eligible passages × 50 value columns
  = 1,169,250 matrix cells**, exported complete as
  [results/ontology_passage_matrix.csv.gz](results/ontology_passage_matrix.csv.gz). Those 50 columns are the
  dimension-value combinations this run actually produced: of the frame's 93 declared values, 43 never matched
  anywhere and so carry no column at all. Most cells are empty, and both an empty cell and a missing column are
  instrument states, never an absence in a tradition.
- every candidate record with its locators, proposition and window spans, referent fields, three presence
  fields and dependence flags is written — **47,641 records over 36,775 distinct propositions and 34,584
  utterance windows** — to
  [results/ontology_attestations.jsonl.gz](results/ontology_attestations.jsonl.gz)
- cross-passage candidate pairing is produced by an **exact inverted index** over live `dimension=value` states —
  44 indexed features, 30,070 postings — joined work-pair by work-pair, so the relation
  `shares at least one live coded state with` is **enumerated** rather than sampled. The enumeration is
  **22,940,506 distinct cross-work passage pairs**, 31,851,655 counted per shared state instead of per pair,
  over the **14,036** passages carrying live states; that is 23.3% of the naive **98,497,630** pair space, and
  unlike the previous figure it is a coverage number, because the denominator is the same relation the layer
  defines. The index ships as
  [results/ontology_passage_index.json.gz](results/ontology_passage_index.json.gz),
  so a reader holding that one file can regenerate every pair without this code.
  [results/ontology_passage_pairs.jsonl.gz](results/ontology_passage_pairs.jsonl.gz) is a declared **display
  slice** of it — the top 20 pairs of each connected work pair by shared-state count, **41,238** edges — chosen
  so the file is openable, not so the count is bounded; every work pair's complete per-state counts go to
  [results/ontology_workpair_dimensions.csv](results/ontology_workpair_dimensions.csv), and the layer's size in
  `ontology_graph.json` is `pairs`, not `edges`.
  What is still incomplete is not the join but the vocabulary it joins: 40 of the frame's 93 declared values
  carry no English pattern and 9 are `not_yet_instrumented`, so a pair absent from the enumeration either really
  shares no coded state or shares a state the detector cannot see, and the artifact cannot tell which. **A
  missing edge is therefore never a missing relationship or a missing state.** The superseded MinHash build
  (128 hashes, 16 bands × 8 rows, seeded 20261101, bucket cap 400) is measured against the exact enumeration
  rather than remembered: [tools/validate_graph_recall.py](tools/validate_graph_recall.py) reports it recovering
  **538,529** of the 22,940,506 pairs, recall **0.023475** corpus-wide — 4,203,223 pairs lost to the bucket cap
  and 18,198,754 to banding itself, 0.206698 without the cap — and **0.023214** on the deterministic stratified
  subset of 1,632 of the 14,036 live passages (9,600 of 413,552 exactly-sharing pairs; 1,330,896 pairwise
  comparisons; 48,043 lost to the cap, 355,909 to banding, 0.139385 without the cap), the figure earlier drafts
  of this document quoted unqualified. The subset and corpus-wide numbers agree closely, which is what makes the
  subset measurement worth citing; it is still a subset measurement, and `results/graph_recall_validation.json`
  publishes both with their populations named. `candidate_generation` in
  [results/ontology_graph.json](results/ontology_graph.json) now separates `coverage_of_the_relation` (COMPLETE)
  from `coverage_of_anything_beyond_the_relation` (INCOMPLETE) and labels the edge file's `never_read_as`,
  because the single field v2 published — a top-level `sampling: "NONE"` — said one true thing loudly and invited
  the reader to hear two.
- work-pair × shared-state aggregation across *all* enumerated passage pairs, not the top 100 — **2,078 of the
  2,080 possible work pairs** — to
  [results/ontology_workpair_dimensions.csv](results/ontology_workpair_dimensions.csv)
- figures drawn from the complete written counts, with all three assertion states visible: the work × dimension
  state heatmap
  (65 × 12 = 780 cells, `no_candidate` rendered as its own labelled category rather than as blank), the
  assertion-state stack, and the speech-act distribution of the plurality family (`D7b_speech_act` read on the
  D2a–c records), in
  [results/figures/](results/figures), plus one self-contained dashboard regenerated from the published
  artifacts by [tools/render_track_b_state.py](tools/render_track_b_state.py)
- **one disclosure about the heatmap's own column set, and how v3 answers it differently.** Three of the four
  interpretation fields (`D7b_speech_act`, `D7c_discourse_genre`, `D7d_epistemic_commitment`) are decided on
  every term-carrying record rather than produced by matching a term of their own, so
  `ontology_work_states.csv` carries all 65 × 25 of their value rows with `candidate_count = 0`; `D7a` does get
  matched rows. v2 answered this by plotting a substitute quantity — windows the frame read as asserted doctrine
  — on the matched-term legend, which mixed two denominators in one picture. v3 does not: the same table now
  publishes `affirmative_doctrine_count` as its own second column (22,818 records, present in all 65 works), and
  the dashboard draws each interpretation field on its own axes over the population it was actually decided on,
  the 47,641 term-carrying records. The zero is still true about matching and false about interpretation; the fix
  is a separate axis with a stated denominator, not a relabelled column.
- **the transformation layer is emitted empty**, as `unpopulated_by_design`, listing the fields it needs.
  A graph with attractive inheritance edges and no dates is how v1's mistake would have been drawn.

### 10.2 The million-record ambition, and what it actually costs

Ambition is welcome; it must be spent on the gates. Target corpus scale for the next phase, with the honest
note that scale multiplies unadjudicated candidates unless annotation grows with it:

| Layer | Today | Phase target | Why this and not more |
|---|---|---|---|
| works | 65 | 400–1,000 | enough to separate families, not enough to make review impossible |
| eligible words | 8.7 M | 150–250 M | ~30 works of the current size per new language family |
| passages | 34,281 (23,385 eligible) | 800,000–1,200,000 | the requested million-record base |
| state candidates | 47,641 records ≈ 5 × 10⁴ | ~10⁷ | follows from passage count and detector breadth |
| passage-pair candidates | 22,940,506 ≈ 2 × 10⁷ (enumerated exactly) | 10⁹–10¹⁰ | the inverted index joins posting lists, so cost tracks shared states rather than pairs; at 10⁶ passages a brute-force scan is ~5 × 10¹¹ pairs and would not run, which is why the index is per-work-pair blocks |
| **propositions coded by two humans** | **0** (6,199 packeted and uncoded) | **3,000 → 12,000** | **the only row that produces evidence** |

Non-English sources move from transliterated terms to actual source text (Sanskrit, Pali, Hebrew, Greek,
Arabic, Avestan, Chinese, Old Norse, Akkadian and Egyptian where legible corpora exist), which is the only
route to real dated attestations and the only cure for §7.2's orthographic bias.

Compute design at that scale: inverted index on dimension values, which is what the graph layer runs today, so
candidate generation is O(shared states) rather than O(pairs) and needs no sketch at the current corpus; LSH with
band-widths tuned to the observed state-frequency distribution only if the pair enumeration itself outgrows
memory, and then with the bucket cap treated as a measured cost rather than a tuning detail — at this corpus the
cap removed 4,203,223 of the sharing pairs banding could have seen and banding itself removed a further
18,198,754, which is why the exact index replaced it; blocked provenance joins so dependence resolution stays
linear; every stage keyed by input SHA-256 so a run
is certifiable and stale inputs are refused, following the contract in
[tools/validate_results_v2.py](tools/validate_results_v2.py).

Storage expectation: ~10⁷ candidate records at ~400 bytes ≈ 4 GB compressed, plus a ~10⁸-cell sparse matrix
as a compressed columnar export rather than CSV. The figures must stay generated from the *complete*
aggregates; a chart drawn from a sampled subset is the error this section exists to end. "Complete" here means
every record and every generated pair that was written — the one thing this layer can promise — and never that
every pair was evaluated; the recall figure above is the measurement of that difference.

### 10.3 Sequencing, deliberately not corpus-first

1. Corpus-wide provenance audit of every high-stakes value (exclusivist monotheism done; then non-theism,
   impersonal ground, deified mortal, celestial administration).
2. Formula-class completion and recall measurement against a hand-built gold set for two values. Pairing is no
   longer an approximation to measure — the exact index enumerates the relation, and the superseded banding's
   recall is on record at 0.023214 on the deterministic 1,632-passage subset and 0.023475 corpus-wide — while the
   detector's recall is not measured at all, and the two are not the same number. What now exists is the instrument to measure it: the 1,500
   weighted no-record probe rows in the packet, scored by Horvitz–Thompson. The number awaits coders.
3. Two-coder reliability on ≥ 3,000 propositions — the existing 6,199-proposition packet is already that large,
   so this step needs coders and not a bigger sample; publish κ, the Jaccard means, the confusion matrices and
   the weighted recall estimate with its bound.
4. Date population for the works that can actually be dated, with the three fields separate.
5. Dependence closure to chain level; anthology and editor layers separated.
6. *Then* scale to a million passages, and only then populate the transformation layer and compare M1–M4 on
   the preregistered scores.

---

## 11. What this document does not claim

It does not claim the concept of divinity has one origin, has many, or was inherited. It does not claim the
dimension frame is the right one — it claims the frame analytically distinct -- separately definable, not measured orthogonal -- coverage-declared, adjudicable and
multilingual-*ready*, which is not the same as multilingual: every detector that ran is an English
translation-text pattern, and no source-language claim in the lexicon has been verified. It names the tests that
would show it wrong (a second lexicon that changes the results; a
baseline that beats it; an ablation that fails to reproduce v1's errors). It does not claim the corpus is a
sample of anything; it is print material chosen for retrievability. It claims nothing about the existence of
divine beings, which no coding frame addresses.

Its actual claim is narrower than v1's and is the only kind Track B can currently afford: the question of
inheritance and transformation is now askable with instruments whose failures are visible in their own
output, and the reason v1's answer came out looking negative is now understood as a property of v1 rather
than a property of the past.
