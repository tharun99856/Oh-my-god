# Provenance and ingestion architecture — v1

## 1. Authority boundaries

- **PostgreSQL** is the authoritative store for identities, metadata, annotations, claims, evidence, rights, and analysis manifests.
- **Object storage** holds immutable source assets, OCR output, and analysis snapshots. Every object has a SHA-256 hash.
- **Neo4j** is a regenerable read model for exploration, not an independent source of historical truth.
- **Search indexes** support discovery only. Embedding similarity never becomes an ancestry edge automatically.
- **Python** runs deterministic ingestion, validation, scoring, and graph export jobs.

## 2. Data flow

```text
source registration → rights/access review → immutable acquisition
→ OCR/transcription → passage location → source verification
→ independent annotation → adjudication → frozen analysis snapshot
→ scoring/model comparison → graph/search projection → evidence-first display
```

No downstream stage can silently edit an earlier artifact. Corrections create versions linked by `supersedes_id` or an equivalent audit record.

## 3. Ingestion contract

Each registered source receives a persistent ID and, as applicable:

- work, expression, witness, and repository identifiers;
- original title, creator, language, script, tradition, and place;
- composition, attestation, collection, and publication date ranges;
- edition, translator, and translation-dependence metadata;
- stable URI, repository identifier, citation, and exact passage locators;
- copyright, license, access class, community protocol, and permitted uses;
- original file hash, acquisition time, extraction method, and software version.

A crawler may register metadata but may not bypass access controls or ingest restricted text into public indexes. Thousands of documents are not acquired before the sampling frame and rights policy exist.

## 4. Immutable processing

1. Preserve the acquired object unchanged; store its hash and media type.
2. Store OCR/transcription as a separate versioned artifact with page or region coordinates and extraction confidence.
3. Link passages to stable source locators, not only character offsets in a generated text file.
4. Preserve original script, transliteration system, translations, restorations, and damaged-text markers.
5. Require human source verification before confirmatory annotation.
6. Keep AI extraction proposals distinguishable from accepted human-reviewed values.

Extraction confidence, annotation certainty, and historical-evidence strength are separate fields.

## 5. Core record model

```text
Work → Expression ↔ Witness → Asset
           │                     │
           └── Passage ──────────┘
                  │
             Attestation → NarrativeVersion
                              ├─ Event ↔ Participant/Entity
                              ├─ Concept coding (motif/theme/symbol/object)
                              └─ NarrativeRelationship → Claim ↔ EvidenceItem

AnalysisRun → Score → ScoreComponent
```

The important distinction is `NarrativeVersion` versus `NarrativeRelationship`: the former contains source-bound observations; the latter contains a revisable inference.

## 6. Claims and graph projection

The exported graph is stratified into five layers with different evidential status, so that a retrieval artifact can never be read as a conclusion: `source_dependency` (work-level premises, excluded from independent discovery), `similarity_candidates` (`RETRIEVED_AS_CANDIDATE`, lexical only), `narrative_structure` (`COMPARED_WITH`: the engine reports the component vector an alignment produced, which is not yet a verdict that the narratives resemble one another), `historical_context` (bibliographic and regional context, no relationship edges until supplied by source criticism), and `adjudicated_historical_relationships`. Only the last layer may hold `DESCENDS_FROM`, `BORROWS_FROM`, or `INFLUENCES`, and each such edge resolves to a claim containing status, rationale, creator, reviewer, and supporting and contradicting evidence, plus chronological and counterevidence review. Candidate and descriptive layers cite an analysis run and components; they assert no historical relationship. `RESEMBLES` is a promoted label the builder can emit only when a pair passes a recorded admission rule — independently attested rather than merely unmarked witnesses, a shared comparison class, every nonzero component on an assessed domain, and survival under the parameter sweeps — and `validate_results_v2.py` fails the build if a `RESEMBLES` edge appears without that decision, so the current publication carries zero of them.

Graph export uses stable PostgreSQL IDs and a dated snapshot. Neo4j constraints enforce unique IDs, but graph-only edits are prohibited. Disputed and superseded relationships remain queryable. Public exports filter restricted evidence before graph generation, not merely in the interface.

## 7. Analysis reproducibility

An analysis manifest freezes input IDs and hashes, code and vocabulary versions, configuration, software/model versions, random seed, and output hash. Scores retain component values and alignment payloads so a user can inspect why two versions were considered similar.

Positive, negative, matched, and cross-category controls run through the same pipeline. Exploratory and confirmatory snapshots are separate. Failed or null results remain in the release.

## 8. Multilingual verification

This section is a design specification, not a status report: no stage in the present repository searches
original-script text (§11), and every Track B record in the current run carries `expression_language` =
`English (translation)` because every detector that ran is an English translation-text pattern. The frame is
multilingual-**ready**, not multilingual.

Search uses original-script text, transliteration, translations, names, and controlled concepts. Consequential passages receive original-language review and, where feasible, comparison of independent translations. Translation disagreements create alternative codings rather than a hidden single choice.

OCR and embeddings propose; passages and qualified review decide.

## 9. Access and audit

Use least-privilege service accounts, separate restricted object prefixes and indexes, encrypted transport and storage, and audit logs for restricted assets. Public API responses expose only permitted excerpts and metadata. Backups inherit the same restrictions.

AI agents receive only the minimum source material required for a task. They cannot alter rights, approve their own historical claims, or publish edges.

## 10. Initial implementation boundary

Phase 1 needs PostgreSQL, immutable local or S3-compatible storage, a small ingestion CLI, annotation exports, deterministic scoring, and a snapshot graph exporter. A public web application, distributed processing, and a custom language model are deferred until the pilot passes its methodological gates.

## 11. Implementation status (1 November 2026)

The repository is a file-backed implementation of sections 2–7, not a deployed instance of sections 8–10. What exists and what does not must stay visible:

| Described here | Present now | Not present |
|---|---|---|
| Immutable acquisition, hashing, offsets | `tools/acquire_corpus.py`, `corpus/`, 65 raw hashes re-verified | object storage, OCR pipelines, media-type registry |
| Stable record model | `schema.sql`, validated structurally by `tests/test_schema.py` | a running PostgreSQL instance (no server or client available in this environment), Neo4j projection |
| Passage location and cleaning | `tools/build_passages_v2.py`, cleaning rules, `tools/narrative_v2.py` | narrative segmentation by story/hymn/parvan rather than windows |
| Candidate retrieval and dependence filtering | `tools/run_similarity_v2.py`, `config/source_dependence.json`, `tools/cleaning_ablation.py` | multilingual or embedding retrieval, original-script search |
| Structural scoring | `tools/narrative_similarity.py` (engine 1.1), `config/annotated_versions.json`, 14 single-analyst versions | independent second-coder annotation, inter-coder reliability, adjudication |
| Graph projection and display | `tools/build_relevance_graph.py` five-layer JSON and canvas (truncated to 100 work pairs); `tools/build_ontology_graph.py` full-corpus layer: an **exact inverted index** over live `dimension=value` states, joined work-pair by work-pair, enumerating all **22,940,506** distinct cross-work sharing pairs over 14,036 live passages (44 indexed features, 30,070 postings) with complete per-work-pair counts in `ontology_workpair_dimensions.csv` and the index itself shipped as `results/ontology_passage_index.json.gz`; `ontology_passage_pairs.jsonl.gz` is a declared **display slice** (41,238 edges: the top 20 pairs per connected work pair by shared-state count), not the pair set; `tools/validate_graph_recall.py` measures what the **superseded** MinHash banding lost — 0.023475 corpus-wide (538,529 of 22,940,506) and 0.023214 on the deterministic 1,632-passage subset — so the replacement is a measured before/after rather than a claim; SVG figures from untruncated counts; `tools/render_track_b_state.py` renders the same artifacts (run summary, graph, recall validation, audit, packet plan) into one inline dashboard, reading every number from the files so the picture cannot drift from the run; gzipped artifacts are written with `mtime=0` and no stored filename (`tools/deterministic_gzip.py`) so a re-run hashes identically | rights-filtered public export, adjudicated historical edges (the transformation layer is emitted empty by design); completeness about concepts rather than about coded states — the enumeration is exact for the relation `shares a live coded state` and silent about the 40 of 93 declared values that carry no English pattern, so **a missing edge is never a missing relationship** |
| Concept-of-divinity census (Track B) | v1 `tools/divinity_terms.py` retained as the record of what was claimed; superseded by `tools/divinity_ontology.py` (instrument v3) with `config/divinity_ontology.json` (twelve analytically distinct dimensions — D1, D2a–c, D3–D6, D7a–d — coded proposition by proposition, declared distinct rather than measured orthogonal), `config/ontology_english_rules.json` (English detectors plus per-value coverage states; the 93 declared values are counted once, in the single coverage table at RESEARCH_PROTOCOL.md §12.4, and are not restated here because five partial counts of that one set were what the reviewer flagged), `tools/migrate_rules_to_v3.py` (the seven-to-twelve pattern migration and its published drop list), `config/divinity_lexicon.json` (32 entries across 16 languages, every one `unverified_secondary_literature`; the frame is multilingual-**ready**, not multilingual — `expression_language` is `English (translation)` on all 47,641 records), `tools/prepare_annotation_packet.py` and `tools/score_annotation.py` (blinded two-coder packet of 6,199 propositions — 4,699 machine-flagged candidates plus 1,500 weighted no-record probe rows, because a sample of hits cannot contain a miss — with a published codebook, κ per single-valued dimension and mean Jaccard per set-valued one, per-value precision on candidate rows and a Horvitz–Thompson recall estimate on probe rows; the scorer refuses one coder, the same sheet twice, a key with no probe rows and a probe row with no weight; `tools/make_pilot_packet.py` cuts the **300-row pilot** the two coders are actually sent — largest-remainder allocation across the packet's three roles (227 / 44 / 29) and a simple random draw over tokens sorted before the generator sees them, so the seed pins the bytes and `PYTHONHASHSEED` cannot move them — and renders the blank sheet, `annotation/PILOT_CODEBOOK.md` and `annotation/CODER_INSTRUCTIONS.md` from the packet, the key and the codebook, with `--check` re-rendering all three and failing on drift and `results/pilot_slice.json` publishing their hashes, the four things the slice cannot support, and `coders_who_have_returned_sheets: []`; `tools/score_annotation.py --pilot` scores two returned sheets and refuses `--key` and `--attestations`, so a slice that was never allocated across value strata cannot print a precision or recall figure even by accident, `config/recall_probe_cues.json` (111 corpus-verified cues, `not_a_detector: true`) and `tools/check_recall_cues.py` supply and verify the sampling instruction), `tools/compare_models.py` with `config/model_comparison_v3.json` (the four-model likelihood layer of TRACK_B_METHOD_v2.md §6: mandatory edge typing, priced operators, path caps, a **two-stage** decision rule — stage 1 scores all four models symmetrically on one pair set and demands the leader's log10 Bayes factor over the **runner-up**, with `no_decisive_winner` a reachable published outcome; stage 2 keeps the separate inheritance-licence question, and its margin is now `min(log10 BF over M2, log10 BF over M4)` because a licence measured only against independent origin left convergence reported and never competed, with the binding baseline published per model; M4's attractor alpha vector is itself confronted with the dimension-block concordance ordering it declares, read on **two scales** — raw mean similarity and mean excess over a per-dimension chance line drawn from this corpus's own marginals on the same pair graph — with a third adjacency class for a gap inside the registered 0.05 separability, so a flat or contradicted `block_profile` disqualifies M4 from being named the stage-1 leader while a profile that contradicts on one scale and ties on the other issues `block_profile_verdict_depends_on_the_similarity_scale` and disqualifies nothing, and the chance artifact's SHA-256 is published inside the verdict; that chance line comes from `tools/scan_dimension_anomalies.py`, which publishes `results/dimension_anomalies.json` (every dimension on two statistics and two pair populations, the dead dimensions, the cells where a declared-single key carries several values, and a per-pair excess ranking with the dependence flag) — a holdout folded by work/witness/lineage **cluster** rather than by pair, Kish effective-sample accounting, pair and effective-sample floors derived by `python tools/compare_models.py --power` and published as `results/model_power_simulation.json` (220 pairs, 29.051621 effective samples, M1 binding) in place of the superseded analyst-set "20", preregistration by SHA-256 — printing `not_yet_testable` today), `tools/build_attestation_scaffold.py` (three separate date fields per work), `tools/audit_exclusivist_matches.py` (per-match source provenance) | dated original-language attestations filled by specialists, an independent second coding and its reliability estimate, dependence closure to chain and editor level — until those exist no historical priority or absence claim is authorised |
| Reproducibility | seeds, SHA-256 manifests, freshness assertions in `tools/validate_results_v2.py`, 455 tests plus 7 parameterised subtests, `tools/validate_tex.py` structural checks with a ten-class injected-defect self-test, a real MiKTeX compile of `paper/main.tex` inside `tests/test_tex_typesetting.py` (overfull boxes, undefined references and pass-to-pass length changes fail the suite), and `tests/test_dimension_anomalies.py`, which re-runs the seeded chance draw under four hash seeds, reproduces `results/dimension_anomalies.json` from the corpus, and re-derives every figure the paper's anomaly section quotes, and `tests/test_pilot_kit.py`, which reproduces the pilot slice byte-for-byte under four hash seeds, fails if the generated handouts drift from `--check`, and pins every refusal the pilot scorer makes | calibrated historical inference, which no current stage is authorised to produce |

Rights, community protocols and access classes are recorded as fields and reviewed per source, but the corpus is English-translation print material selected for retrieval testing; the review states in `schema.sql` (`candidate` through `analysis_ready`) are the mechanism by which later stages are supposed to gate one another, and only the first states are currently populated.
