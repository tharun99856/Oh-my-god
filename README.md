# Oh my god: measuring divine-concept claims across 65 English translations

This repository contains a computational study of how texts talk about divinity, not a
study of whether any religion is true. It builds three instruments over a 65-work corpus of
English translations (scripture, myth and folklore, mostly Project Gutenberg editions) and
publishes every count they produce:

1. a TF-IDF **lexical retriever** that finds candidate passage pairs across works;
2. a **structural comparison engine** that aligns coded narrative versions event by event and
   reports five separate components, never a composite;
3. a **divine-concept state coder** that segments matched passages into propositions and
   records, for each proposition, twelve analytically distinct dimensions (plurality,
   exclusivity, transcendence, temporal nature, referent, gender, and four interpretation
   fields about speech act, genre and epistemic commitment).

The headline result is a negative one and is stated as such in the paper: the instrument
finds a great many surface resemblances, most of them traceable to shared editions,
editorial apparatus or one text quoting another, and the evidence needed to support a
historical-inference claim (dated witnesses, documented transmission routes, independent
second coding) does not exist yet. No number in the paper is typed by hand.

## Layout

| Path | What it is |
|---|---|
| `paper/main.tex` | the paper; `paper/main.pdf` is built from it here |
| `tools/` | every instrument, validator and figure writer |
| `config/` | ontologies, lexicons, dependence rules, coded versions, sampling plan |
| `results/` | published artifacts, each with the SHA-256 of the inputs that produced it |
| `tests/` | the suite that re-derives the paper's figures from those artifacts |
| `corpus/` | acquired texts and the acquisition manifest (see below) |
| `annotation/` | coder-facing handouts for the pilot |
| `audit_checks/` | the two one-off analyses whose figures `AUDIT_REPORT.md` §2 quotes, shipped so that a
reader can re-run them instead of taking the report's word for it |
| `ARCHITECTURE.md`, `RESEARCH_PROTOCOL.md`, `TRACK_B_METHOD_v2.md`, `TEST_REPORT.md` | design, protocol, method, and what the tests actually found |
| `AUDIT_REPORT.md` | the final audit: every confirmed defect with its fix, every analysis actually executed, what was deleted, and the blockers that stand between this repository and a submission |

## Set up

Python 3.13 (the suite is measured on 3.13.6) and:

```bash
python -m pip install -r requirements.txt
```

A LaTeX engine is optional. If none is installed, `tests/test_tex_typesetting.py` skips the
whole class rather than passing; everything else runs.

## Run the tests

```bash
python -m pytest tests -q
```

This is the check that the published numbers still follow from the shipped code and
artifacts. Many tests re-run an instrument and compare bytes, so a stale artifact fails
loudly instead of quietly agreeing with an old draft.

**A clean clone is not the same as this working tree.** `corpus/raw/` and
`corpus/derived/` are gitignored: only `corpus/acquisition_manifest.json` is versioned.
Twelve tests therefore report explicit skips (`corpus/derived/passages_v2.jsonl is
gitignored ...`) because they re-read source text or re-hash it; measured in a clone of the
shipped commit, that is 443 passed, 12 skipped and 7 subtests, where this tree passes all
455. Everything that can be verified from the shipped artifacts does run; the skipped checks
are the locator and byte-reproduction ones that need the corpus itself.

The corpus has a second reproducibility problem that no local hash can see: the publisher
edits its files in place. `python tools/verify_corpus_live.py` re-downloads all 65 works and
compares them with the manifest, and the published
`results/corpus_live_verification.json` records 63 matches and 2 drifts —
`australian_legendary_tales` is served at the same byte length with two bytes changed in a
word list, and `odyssey` differs at four lines: that `Most recently updated` header date, a numeral
restored in the preface (`of 894` → `of 1894`), a footnote marker added to a body line, and one separator
line holding only a slash removed near the end. Read by byte offset the second file looks like a
685,258-position change; aligned line by line, which is what the artifact publishes, it is four edits and
two bytes of length. A positional byte count on a file whose length changed counts the shift, not the
edits.
Every number here is pinned to the hashes the manifest recorded, so neither drift changes
a measurement; they do mean a re-acquisition from the live web no longer reproduces those
two files, which is why the manifest is the authority and not the site.

## Reproduce from scratch

Fetch the corpus (network required), then rebuild every stage in order. The full command
sequence, with which command writes which artifact, is section 13 of `TEST_REPORT.md`, and
`tests/test_pipeline.py` checks that the inventory in that section is complete:

```bash
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

This is the command list from `TEST_REPORT.md` section 13 with the corpus steps first;
`tools/compare_models.py` with no flag prints its verdict to stdout and writes nothing, while
`--corpus-pairs` scores the M4 block-profile gate on the corpus's own pair set and writes the verdict by
default; the sequence passes `--write-to` anyway, because that verdict embeds the SHA-256 of the chance table
it read and a reader cannot check an embedded hash that exists only on a terminal -- which is also why the
scan runs with `--write`, so the table the gate reads is the one this sequence published. The last command
digests every artifact twice -- as bytes, and with the fields that record *that* a run happened stripped out --
so "did re-running the pipeline change a measurement?" is answered by a file rather than by a claim.

`tools/run_similarity.py` and `tools/compare_models.py --legacy-lexical` rebuild the frozen
42-work v1 baseline that the paper measures itself against; they are deliberately outside the
sequence above so that baseline stays unchanged. `tools/score_annotation.py` refuses to run,
by design, until two people have independently coded the blinded packet.

## Build the paper

```bash
python tools/validate_tex.py            # structural check, exits non-zero on any problem
python tools/validate_tex.py --self-test # proves the checker itself can fail
pdflatex paper/main.tex && pdflatex paper/main.tex
```

## What this repository does not claim

* No inter-coder agreement, `kappa`, precision or recall figure exists, because no human has
  coded the packet yet. `results/annotation_reliability.json` is absent, not hidden.
* Unverified lexicon entries generate candidates; they never count as attestations.
* The inheritance layer of the state graph ships empty, because dates are unfilled.
* Absence of similarity is not used to disconfirm common ancestry.
* No composite score is produced by the structural engine, and no historical relationship is
  inferred from descriptive similarity.
