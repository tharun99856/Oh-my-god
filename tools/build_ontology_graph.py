#!/usr/bin/env python3
"""Full-corpus ontology graphs for the v3 instrument: every passage, every value, no top-N truncation.

The v2 relevance graph capped itself at 100 work pairs (build_relevance_graph.py:258),
which made a 34,281-passage corpus look like a 200-row table. This tool emits the
complete layers instead: an exact passage-pair candidate set, an aggregated
work-by-dimension state matrix, and SVG figures drawn from those full counts.

One honesty correction for v3, and then a second one for v3.1. The first release of this layer blocked
candidates with MinHash banding, wrote every pair the banding produced, and called that complete because
nothing was discarded after generation. `tools/validate_graph_recall.py` measured the blocking step and
found it recovered 2.32% of the exact sharing pairs on a deterministic subset — the pair set was a small
sample of the relation it claimed to enumerate. v3.1 replaces the sketch with the thing it was
approximating: an exact inverted index over `dimension=value` states, joined posting-list by posting-list,
so the relation `shares at least one live coded state with` is enumerated completely and its counts are
published whole. The edge file is a declared display slice of that enumeration
(`EDGES_DISPLAY_PER_WORK_PAIR` pairs per work pair, chosen by shared-state count); the exact count is
published in `scale`, and the complete relation is reconstructible from
`results/ontology_passage_index.json.gz`, which is the index itself.

What remains incomplete is not the join. A passage pair with no shared live state may still share a
concept this instrument cannot see: 40 of the 93 declared values carry no English pattern and 9 are
published as `not_yet_instrumented`, and the detector's own recall is what the annotation packet exists to
measure. A missing edge is therefore never a missing relationship.

Layer 4 (transformation) is deliberately empty. Asserting an inheritance edge needs
dated composition, dated witness and a documented contact route; the dates are not
filled, so the layer publishes what is missing rather than a plausible-looking tree.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy.sparse as sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_gzip import gzip_text_writer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ATTEST = ROOT / "results/ontology_attestations.jsonl.gz"
SUMMARY = ROOT / "results/ontology_run_summary.json"
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"
DEPENDENCE = ROOT / "config/source_dependence.json"
RULES = ROOT / "config/ontology_english_rules.json"
ONTOLOGY = ROOT / "config/divinity_ontology.json"
OUT_GRAPH = ROOT / "results/ontology_graph.json"
OUT_EDGES = ROOT / "results/ontology_passage_pairs.jsonl.gz"
OUT_INDEX = ROOT / "results/ontology_passage_index.json.gz"
OUT_WORKPAIRS = ROOT / "results/ontology_workpair_dimensions.csv"
OUT_MATRIX = ROOT / "results/ontology_passage_matrix.csv.gz"
OUT_RECALL = ROOT / "results/graph_recall_validation.json"
FIGURES = ROOT / "results/figures"

# The exact inverted index is the blocking step now, so these are not production parameters: they are
# the superseded MinHash build's parameters, kept because tools/validate_graph_recall.py measures what
# that build lost against the exact enumeration. 128 hashes banded 16x8, buckets over BUCKET_CAP rows
# discarded outright -- a real coverage cut, and the reason the old edge file was 2.32% of the relation.
NUM_HASHES, BAND_SIZE, NUM_BANDS = 128, 8, 16
BUCKET_CAP = 400
MERSENNE_PRIME = (1 << 61) - 1
SEED = 20261101

# Display-only cap for the edge file: this many pairs per connected work pair, chosen by shared-state
# count then by passage id, so the slice is readable and reproducible. It is a cap on what is
# *displayed*, never on what is counted -- every work pair's complete counts go to the CSV and to
# `scale`, and the index that regenerates all of them ships beside them.
EDGES_DISPLAY_PER_WORK_PAIR = 20


def load_attestations():
    records = []
    with gzip.open(ATTEST, "rt", encoding="utf-8") as handle:
        for line in handle:
            records.append(json.loads(line))
    return records


def matrix_shape():
    """Rows and value-columns of the published passage matrix, read from the artifact itself.

    `divinity_ontology.py` writes one row per eligible passage and one column per dimension value,
    so the cell count is the size of the evidence surface the instrument covers. It is reported as
    cells, not as findings: most cells are empty, and an empty cell is an instrument state, never an
    absence in a tradition.
    """
    if not OUT_MATRIX.exists():
        return 0, 0
    with gzip.open(OUT_MATRIX, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        columns = len(next(reader)) - 2
        rows = sum(1 for _ in reader)
    return rows, columns


def features_of(records):
    """Passage -> set of live dimension-value states.

    In the v3 schema live means `assertion_state == "candidate"`. The two refusal states are not live:
    `candidate_requires_human_disambiguation` has no adjudicated value yet, and `not_yet_instrumented`
    records that the detector cannot see the value at all. A pair shares an edge when both passages carry
    at least one live state in common — that is co-occurrence of coded states, not a similarity claim.
    """
    per_passage = defaultdict(set)
    for record in records:
        if record["assertion_state"] != "candidate":
            continue
        per_passage[(record["work_id"], record["passage_id"])].add(f"{record['dimension']}={record['value']}")
    return per_passage


def minhash_signatures(per_passage, vocabulary):
    index = {feature: position for position, feature in enumerate(sorted(vocabulary))}
    rng = np.random.default_rng(SEED)
    multipliers = rng.integers(1, MERSENNE_PRIME, size=(len(index), NUM_HASHES), dtype=np.uint64)
    increments = rng.integers(0, MERSENNE_PRIME, size=(len(index), NUM_HASHES), dtype=np.uint64)
    keys, signatures = [], np.full((len(per_passage), NUM_HASHES), MERSENNE_PRIME, dtype=np.uint64)
    for row, ((work, passage), features) in enumerate(sorted(per_passage.items())):
        keys.append((work, passage))
        positions = [index[f] for f in features if f in index]
        if not positions:
            continue
        hashes = (multipliers[positions] + increments[positions]) % np.uint64(MERSENNE_PRIME)
        signatures[row] = hashes.min(axis=0)
    return keys, signatures


def band_candidates(keys, signatures, bucket_cap=BUCKET_CAP):
    """Stream bucket pairs; returns every cross-work candidate pair exactly once.

    `bucket_cap` is exposed as a parameter (default BUCKET_CAP, the production behaviour) so that
    tools/validate_graph_recall.py can measure the cap's coverage loss against the same banding
    instead of reimplementing it. A cap of None never discards a bucket.
    """
    seen, pairs = set(), []
    for band in range(NUM_BANDS):
        buckets = defaultdict(list)
        start = band * BAND_SIZE
        for row in range(len(keys)):
            buckets[tuple(signatures[row, start:start + BAND_SIZE].tolist())].append(row)
        for rows in buckets.values():
            if len(rows) < 2:
                continue
            if bucket_cap is not None and len(rows) > bucket_cap:
                continue
            for position, left in enumerate(rows):
                for right in rows[position + 1:]:
                    if keys[left][0] == keys[right][0]:
                        continue
                    identity = (keys[left][1], keys[right][1])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    pairs.append((keys[left], keys[right]))
    return pairs


def jaccard(left_features, right_features):
    union = len(left_features | right_features)
    return len(left_features & right_features) / union if union else 0.0


def inverted_index(per_passage):
    """feature -> sorted passage keys carrying it as a live candidate record.

    This is the whole blocking step now: a pair is a candidate exactly when the two passages appear in
    one posting list together. No sketch, no band, no bucket cap, so the sharing-pair relation is
    enumerated rather than sampled. The index ships beside the graph because the complete pair set is
    the join of these lists and a reader holding the file needs neither this machine nor an approximation
    to regenerate every pair.
    """
    postings = defaultdict(list)
    for key, features in per_passage.items():
        for feature in features:
            postings[feature].append(key)
    return {feature: sorted(keys) for feature, keys in sorted(postings.items())}


def write_index(index):
    """Ship the exact index, so the complete pair set is reconstructible without this machine."""
    payload = {"artifact": "exact inverted index over live dimension=value states",
               "relation": "a passage pair is a candidate exactly when the two passages share a posting here",
               "approximation": "none: this is the join, not a sketch of it",
               "cross_work_only": "the published layer-3 rule drops same-work pairs; the postings themselves "
                                  "are not filtered by work",
               "features": {feature: [[work, passage] for work, passage in keys]
                            for feature, keys in index.items()}}
    with gzip_text_writer(OUT_INDEX) as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def exact_sharing_layer(per_passage, index, display_per_work_pair=EDGES_DISPLAY_PER_WORK_PAIR):
    """Join the index work-pair by work-pair: complete counts, declared display slice.

    Each work pair gets its own sparse product over the features the two works both carry. Entry (i, j)
    of `A @ B.T` is the number of live states the two passages share, so the product's support is that
    work pair's exact distinct-pair set, its sum is the pair-by-feature multiplicity, and a column sum
    is the distinct-pair count for one feature -- because incidence is binary per feature, a pair can
    share a given state only once. Blocks are bounded by two works' passage counts rather than by the
    corpus, which is what makes the exact enumeration affordable.
    """
    keys = sorted(per_passage)
    row_of = {key: position for position, key in enumerate(keys)}
    features = sorted(index)
    column_of = {feature: position for position, feature in enumerate(features)}
    rows, columns = [], []
    for key, key_features in per_passage.items():
        for feature in key_features:
            rows.append(row_of[key])
            columns.append(column_of[feature])
    incidence = sparse.csr_matrix((np.ones(len(rows), dtype=np.int8), (rows, columns)),
                                  shape=(len(keys), len(features)))
    key_of_row = {row: key for key, row in row_of.items()}
    blocks = {}
    for work in sorted({key[0] for key in keys}):
        positions = np.array([row_of[key] for key in keys if key[0] == work], dtype=np.int64)
        block = incidence[positions]
        counts = Counter(int(column) for column in block.indices)
        blocks[work] = (positions, np.array(sorted(counts), dtype=np.int64), counts)
    works = sorted(blocks)
    pair_counts = {}
    feature_pair_counts = Counter()
    display_edges = []
    for position, left_work in enumerate(works):
        left_rows, left_features, left_counts = blocks[left_work]
        for right_work in works[position + 1:]:
            right_rows, right_features, right_counts = blocks[right_work]
            shared = np.array(sorted(set(left_features.tolist()) & set(right_features.tolist())),
                              dtype=np.int64)
            if not shared.size:
                pair_counts[(left_work, right_work)] = (0, 0, {})
                continue
            # A pair shares a given feature at most once (incidence is binary), so the distinct-pair
            # count for one feature in this work pair is a product of the two works' posting sizes --
            # exact, and cheaper than reading columns back off the product.
            per_feature = {features[column]: left_counts[int(column)] * right_counts[int(column)]
                           for column in shared}
            product = (incidence[np.ix_(left_rows, shared)] @ incidence[np.ix_(right_rows, shared)].T)
            pair_counts[(left_work, right_work)] = (int(product.nnz), int(sum(per_feature.values())),
                                                    per_feature)
            feature_pair_counts.update(per_feature)
            if display_per_work_pair is None:
                continue
            coordinates = product.tocoo()
            order = np.lexsort((right_rows[coordinates.col], left_rows[coordinates.row],
                                -coordinates.data.astype(np.int64)))
            for chosen in order[:display_per_work_pair]:
                # coordinates are block-local: row i of the block is left_rows[i] of the full
                # incidence matrix, and column j is right_rows[j].
                display_edges.append((key_of_row[int(left_rows[coordinates.row[chosen]])],
                                      key_of_row[int(right_rows[coordinates.col[chosen]])],
                                      int(coordinates.data[chosen])))
    return {"pair_counts": pair_counts, "feature_pair_counts": dict(feature_pair_counts),
            "display_edges": sorted(display_edges), "postings": len(rows),
            "features_in_index": len(features), "passages_in_index": len(keys)}


def dependence_map():
    rules = json.loads(DEPENDENCE.read_text(encoding="utf-8"))
    pairs = {}
    for rule in rules["pair_rules"]:
        pairs[frozenset((rule["left_work"], rule["right_work"]))] = rule["relationship"]
    for family in rules["work_families"]:
        members = family["work_ids"]
        for position, left in enumerate(members):
            for right in members[position + 1:]:
                pairs.setdefault(frozenset((left, right)), "family:" + family["family_id"])
    return pairs


def colour(value, palette):
    return palette.get(value, "#3b3f46")


def svg_heatmap(rows, columns, matrix, path, title, note, palette, cell=13):
    """A dependency-free SVG heatmap, so the figure is reproducible from data alone."""
    left, top = 250, 74
    width = left + len(columns) * cell + 30
    height = top + len(rows) * cell + 96
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif">',
             f'<rect width="{width}" height="{height}" fill="#14171b"/>',
             f'<text x="18" y="30" fill="#e8eaed" font-size="16" font-weight="600">{title}</text>',
             f'<text x="18" y="52" fill="#9aa0a6" font-size="11">{note}</text>']
    for column, label in enumerate(columns):
        parts.append(f'<text x="{left + column * cell + cell // 2}" y="{top - 8}" fill="#9aa0a6" '
                     f'font-size="9" text-anchor="middle" transform="rotate(-90 '
                     f'{left + column * cell + cell // 2} {top - 8})">{label}</text>')
    for row_index, row_label in enumerate(rows):
        parts.append(f'<text x="{left - 8}" y="{top + row_index * cell + 10}" fill="#c7cdd3" '
                     f'font-size="10" text-anchor="end">{row_label}</text>')
        for column_index, column_label in enumerate(columns):
            value = matrix.get((row_label, column_label), "")
            fill = colour(str(value), palette) if value != "" else "#1d2126"
            parts.append(f'<rect x="{left + column_index * cell}" y="{top + row_index * cell}" '
                         f'width="{cell - 1}" height="{cell - 1}" fill="{fill}">'
                         f'<title>{row_label} / {column_label}: {value if value != "" else "no data"}</title></rect>')
    legend_x = left
    for offset, (label, hex_value) in enumerate(palette.items()):
        parts.append(f'<rect x="{legend_x + offset * 170}" y="{height - 52}" width="11" height="11" fill="{hex_value}"/>')
        parts.append(f'<text x="{legend_x + offset * 170 + 16}" y="{height - 42}" fill="#9aa0a6" font-size="10">{label}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8", newline="")


def stacked_bars(groups, counts, path, title, note, palette):
    width, height, left, top, bar = 900, 90 + 46 * len(groups), 250, 70, 380
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="system-ui, sans-serif">',
             f'<rect width="{width}" height="{height}" fill="#14171b"/>',
             f'<text x="18" y="30" fill="#e8eaed" font-size="16" font-weight="600">{title}</text>',
             f'<text x="18" y="52" fill="#9aa0a6" font-size="11">{note}</text>']
    maxima = {key: max(sum(v.values()) for v in counts.values()) or 1 for key in groups}
    for index, group in enumerate(groups):
        row_y = top + index * 46
        parts.append(f'<text x="{left - 10}" y="{row_y + 14}" fill="#c7cdd3" font-size="11" text-anchor="end">{group}</text>')
        x = left
        scale = bar / max(1, sum(counts[group].values()))
        for label, value in sorted(counts[group].items(), key=lambda item: -item[1]):
            width_px = max(1, value * scale)
            parts.append(f'<rect x="{x}" y="{row_y}" width="{width_px:.1f}" height="18" fill="{colour(label, palette)}">'
                         f'<title>{group} / {label}: {value}</title></rect>')
            x += width_px
        parts.append(f'<text x="{x + 8}" y="{row_y + 14}" fill="#9aa0a6" font-size="10">'
                     f'{sum(counts[group].values())} records</text>')
    legend_x = left
    for offset, (label, hex_value) in enumerate(palette.items()):
        parts.append(f'<rect x="{legend_x + offset * 170}" y="{height - 34}" width="11" height="11" fill="{hex_value}"/>')
        parts.append(f'<text x="{legend_x + offset * 170 + 16}" y="{height - 24}" fill="#9aa0a6" font-size="10">{label}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8", newline="")


def coverage_inventory(rules, ontology, records):
    """ONE table of what the instrument can and cannot see, so five partial counts stop circulating.

    Five different numbers describe the same 93 declared values -- 93 declared, 53 with a surface pattern, 50
    observed, 43 without a matrix column, 40 without a pattern, 9 `not_yet_instrumented` -- and they are not a
    partition, so subtracting them from each other produces a remainder that means nothing. This function
    publishes the sets and their overlaps instead of the differences, and it computes them from the rules file,
    the ontology and the run's own records rather than from prose.

    Two things fall out that a hand-typed table would have got wrong. Seven of the nine `not_yet_instrumented`
    values do carry a surface pattern: the pattern exists, and what is missing is a way to establish an absence
    or a non-relation from it. And most of the values with no pattern are not gaps at all: the D7a-d
    interpretation values and the nine `undecidable` residuals are produced by rules that read the window, so
    "no pattern" is the wrong instrument for them, not an absent detector.
    """
    declared = {f"{dimension}={value}" for dimension, specs in ontology["dimensions"].items()
                for value in specs["values"]}
    patterned, coverage_state = set(), {}
    for dimension, specs in rules["dimensions"].items():
        for value, spec in specs.get("values", {}).items():
            if not isinstance(spec, dict):
                continue
            # the rules file's field is `coverage`; a reader of `coverage_state` silently gets nothing, and
            # an empty gap list is worse than no list because it reads as "no gaps"
            coverage_state[f"{dimension}={value}"] = spec.get("coverage", "unlabelled")
            if spec.get("patterns"):
                patterned.add(f"{dimension}={value}")
    not_yet = {key for key, state in coverage_state.items() if state == "not_yet_instrumented"}
    observed = {f"{record['dimension']}={record['value']}" for record in records}
    no_pattern = declared - patterned
    derived = sorted(key for key in no_pattern
                     if key.split("=")[0].startswith("D7") or key.endswith("=undecidable"))
    return {
        "declared_values": len(declared),
        "with_a_surface_pattern": len(patterned),
        "without_a_surface_pattern": len(no_pattern),
        "observed_at_least_once": len(observed),
        "with_no_matrix_column": len(declared) - len(observed),
        "coverage_state_labels": dict(sorted(Counter(coverage_state.get(key, "absent_from_rules")
                                                     for key in declared).items())),
        "flagged_not_yet_instrumented": len(not_yet),
        "overlaps": {
            "not_yet_instrumented_that_still_have_a_pattern": sorted(not_yet & patterned),
            "why_a_pattern_can_still_be_unusable": "these are absence and non-relation values -- others not "
                                                   "addressed, no devotional language, non-agential, outside "
                                                   "time. A surface pattern cannot establish that something is "
                                                   "not being said, so the detector is missing a method, not a "
                                                   "regex",
            "not_yet_instrumented_with_no_pattern": sorted(not_yet - patterned),
            "no_pattern_and_not_flagged": len(no_pattern - not_yet),
            "of_which_produced_by_rules_not_patterns": len(derived),
            "why_those_are_not_gaps": "the D7a-d interpretation values and the nine `undecidable` residuals are "
                                      "assigned by reading the window, not by matching a term, so counting them "
                                      "as uninstrumented because they have no pattern is a category error",
            "patterned_but_never_matched": sorted(patterned - observed),
        },
        "reading_the_table": "these rows are nested sets, not a partition: 93 = 53 patterned + 40 unpatterned, "
                             "and separately 93 = 50 observed + 43 unobserved, and 9 of the 93 are labelled "
                             "not_yet_instrumented, 7 of them inside the patterned 53. The remainder a reader "
                             "gets by writing 93 - 53 - 9 is 31 and it is not a count of anything; the set that "
                             f"is real is {len(no_pattern - not_yet)} values with no pattern and no "
                             "not_yet_instrumented label, and almost all of those are rule-derived fields. An "
                             "empty cell, a missing column and a missing edge each say something about this "
                             "instrument and nothing about a tradition",
        "values": {"not_yet_instrumented": sorted(not_yet),
                   "patterned_but_never_matched": sorted(patterned - observed),
                   "derived_rather_than_matched": derived},
    }


def candidate_generation_block(exact_pairs):
    """How candidate pairs are produced, stated honestly.

    Two claims need keeping apart. The *join* is exact: every cross-work pair whose passages share a live
    `dimension=value` state is enumerated, counted whole, and reconstructible from the shipped index. The
    *relation* is not the world: a pair with no shared live state may still share a concept this instrument
    cannot see, because 40 of the 93 declared values carry no English pattern and 9 are published as
    `not_yet_instrumented`, and the detector's own recall is what the annotation packet exists to measure.
    So the answer to "is the candidate set complete?" is yes for the relation as defined and no for any
    richer notion of similarity -- and a missing edge is never a missing relationship.

    The superseded MinHash build is retained here as a measured before/after, not as a live code path.
    """
    block = {
        "method": "exact_inverted_index_join",
        "index": "feature -> sorted passage keys; a cross-work pair is a candidate exactly when the two "
                 "passages appear in one posting list together",
        "approximation": "NONE in the join. No sketch, no band, no bucket cap, no top-N truncation: every "
                         "pair the relation defines is enumerated, and the per-work-pair counts published in "
                         "ontology_workpair_dimensions.csv and in `scale` are complete counts of it.",
        "coverage_of_the_relation": f"COMPLETE. {exact_pairs} distinct cross-work pairs share at least one "
                                   "live coded state and every one of them is in the enumeration, so a pair "
                                   "absent from it genuinely shares no live coded state in this instrument's "
                                   "output.",
        "coverage_of_anything_beyond_the_relation": "INCOMPLETE, and this is the limit that matters. The "
            "relation is built from live candidate records only, so a pair is missing from it for either of "
            "two reasons: the concepts really do not co-occur in the coded states, or the instrument has no "
            "English pattern for the state in question. Those are indistinguishable from the artifact's "
            "inside. Read a missing edge as a missing relationship or a missing state and you have made the "
            "inference the v1 census withdrew. `coverage_inventory` decomposes the detector gap itself: 40 of "
            "the 93 declared values have no surface pattern and 9 carry the `not_yet_instrumented` label, but "
            "the sets overlap and most of the unpatterned values are rule-derived fields rather than blind "
            "spots, so the honest statement is that the gap is real, uneven and not equal to 40.",
        "display_slice": {
            "edge_file": "results/ontology_passage_pairs.jsonl.gz",
            "rule": f"the top {EDGES_DISPLAY_PER_WORK_PAIR} pairs of each connected work pair, ranked by "
                    "shared-state count then by passage id",
            "what_it_is": "readability, not a sample of the relation. Every work pair keeps its complete "
                          "counts in the CSV and in `scale`, and the whole pair set regenerates from "
                          "results/ontology_passage_index.json.gz.",
            "never_read_as": "a bound on the pair count, or as evidence that unsampled pairs do not share a "
                             "state.",
        },
    }
    if OUT_RECALL.exists():
        measurement = json.loads(OUT_RECALL.read_text(encoding="utf-8"))
        results = measurement["results"]
        wide = measurement.get("corpus_wide")
        block["superseded_minhash_recall_measured"] = {
            "source_artifact": "results/graph_recall_validation.json",
            "status": "the figures below describe the v3 build's blocking step, which this build no longer "
                      "uses; they are kept because they are the measured cost of the approximation that was "
                      "replaced, and because tools/validate_graph_recall.py still runs them against the exact "
                      "enumeration",
            "corpus_wide": wide,
            "subset": {
                "measured_on": results["subset_definition"],
                "exact_sharing_pairs_in_subset": results["exact_sharing_pairs"],
                "recovered_by_lsh": results["recovered_by_lsh"],
                "recall": results["recall"],
                "pairs_lost_to_bucket_cap": results["lost_to_bucket_cap"],
                "pairs_lost_to_banding": results["lost_to_banding"],
                "always_qualify": "this recall is a subset measurement; quote it with the passage count and "
                                  "the exact-pair count of the subset, never as a corpus figure",
            },
            "parameters": {"num_hashes": NUM_HASHES, "bands": NUM_BANDS, "rows_per_band": BAND_SIZE,
                           "seed": SEED, "bucket_cap": BUCKET_CAP},
            "statement": "recall of the superseded LSH blocking step, measured by exact comparison with this "
                         "module's own minhash_signatures and band_candidates, over the whole live-state "
                         "population (corpus_wide) and over a deterministic stratified subset (subset). The "
                         "two agree closely, which is what makes the older subset-only figure trustworthy.",
        }
        if wide:
            block["superseded_minhash_recall_measured"]["before_and_after"] = (
                f"banding enumerated {wide['recovered_by_lsh']} of the {wide['exact_distinct_cross_work_pairs']} "
                f"cross-work sharing pairs ({wide['recall']:.6f}); this build enumerates all "
                f"{exact_pairs} of them, because the index is the join rather than a sketch of it")
    else:
        block["superseded_minhash_recall_measured"] = None
        block["superseded_minhash_recall_missing"] = ("results/graph_recall_validation.json has not been "
                                                     "produced; run tools/validate_graph_recall.py to measure "
                                                     "what the superseded banding step lost. The join itself "
                                                     "needs no such measurement -- it is exact by construction "
                                                     "-- but the before/after figure is unmeasured until then.")
    return block


def build():
    records = load_attestations()
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    passage_meta = {}
    for line in PASSAGES.read_text(encoding="utf-8").splitlines():
        passage = json.loads(line)
        passage_meta[passage["passage_id"]] = passage
    per_passage = features_of(records)
    index = inverted_index(per_passage)
    write_index(index)
    layer = exact_sharing_layer(per_passage, index)
    dependence = dependence_map()

    workpair_dimensions = {pair: dict(sorted(features.items()))
                           for pair, (_, _, features) in sorted(layer["pair_counts"].items()) if features}
    written = 0
    with gzip_text_writer(OUT_EDGES) as handle:
        for (left_work, left_passage), (right_work, right_passage), _ in layer["display_edges"]:
            left_features, right_features = per_passage[(left_work, left_passage)], per_passage[(right_work, right_passage)]
            score = jaccard(left_features, right_features)
            shared = sorted(left_features & right_features)
            if not shared:
                continue
            edge = {"left_passage_id": left_passage, "right_passage_id": right_passage,
                    "left_work_id": left_work, "right_work_id": right_work,
                    "shared_states": shared, "state_jaccard": round(score, 6),
                    "dependence_relationship": dependence.get(frozenset((left_work, right_work)), ""),
                    "counts_as_independent": frozenset((left_work, right_work)) not in dependence,
                    "edge_kind": "SHARED_DIMENSION_STATE_CANDIDATE",
                    "edge_is_from": "exact inverted index over live dimension=value states",
                    "display_slice": f"top {EDGES_DISPLAY_PER_WORK_PAIR} pairs of its work pair by shared "
                                     "state count; the work pair's complete count is in "
                                     "ontology_workpair_dimensions.csv and the full relation regenerates "
                                     "from ontology_passage_index.json.gz"}
            handle.write(json.dumps(edge, ensure_ascii=False) + "\n")
            written += 1

    works = sorted({record["work_id"] for record in records})
    dimensions = sorted(ontology["dimensions"])
    # v3 assertion states, ranked by how far the instrument got: a live candidate outranks a record
    # awaiting human disambiguation, which outranks a record whose value is not instrumented. The v2
    # state `blocked_by_speech_act` no longer exists and keys off nothing here.
    v3_state_rank = {"not_yet_instrumented": 1, "candidate_requires_human_disambiguation": 2, "candidate": 3}
    state_matrix = {(work, dimension): "no_candidate" for work in works for dimension in dimensions}
    state_rank_seen = {}
    for record in records:
        key = (record["work_id"], record["dimension"])
        rank = v3_state_rank.get(record["assertion_state"], 0)
        if rank > state_rank_seen.get(key, 0):
            state_rank_seen[key] = rank
            state_matrix[key] = record["assertion_state"]

    with OUT_WORKPAIRS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["left_work", "right_work", "dimension_state", "shared_passage_pairs",
                         "counts_as_independent"])
        for (left, right), features in sorted(workpair_dimensions.items()):
            for feature, count in sorted(features.items()):
                writer.writerow([left, right, feature, count,
                                 "no" if frozenset((left, right)) in dependence else "yes"])

    FIGURES.mkdir(parents=True, exist_ok=True)
    palette = {"candidate": "#3ddc97", "candidate_requires_human_disambiguation": "#5aa9e6",
               "not_yet_instrumented": "#8b8f95", "no_candidate": "#4a5560", "": "#1d2126"}
    svg_heatmap(works, dimensions, state_matrix,
                FIGURES / "work_by_dimension_states.svg",
                "Every work against every dimension: where a state was found, where it awaits a human, where it looked",
                f"green = at least one live candidate record · blue = only records needing human disambiguation · "
                f"slate = only not-yet-instrumented records · grey = no record · all {len(works)} works, "
                f"all {len(dimensions)} dimensions; this matrix is a complete count of records, not a sample",
                palette)

    by_dimension = defaultdict(Counter)
    for record in records:
        by_dimension[record["dimension"]][record["assertion_state"]] += 1
    ordered = [d for d in dimensions if by_dimension[d]]
    stacked_bars(ordered, by_dimension, FIGURES / "assertion_states_by_dimension.svg",
                 "Candidate records by assertion state, per dimension",
                 "the frame's own refusal rate is a result of the design, not noise inside it",
                 {"candidate": "#3ddc97", "candidate_requires_human_disambiguation": "#5aa9e6",
                  "not_yet_instrumented": "#8b8f95"})

    # v3 splits D7 into four fields on every record; the voice distribution of the plurality family
    # (D2a/D2b/D2c) is read from D7b_speech_act. The v2 `D7_speech_act` field and `D2_plurality`
    # dimension are gone, so keying off either would silently draw an empty chart.
    d7_counts = Counter(record["D7b_speech_act"] for record in records
                        if record["dimension"].startswith("D2"))
    ranked_d7 = d7_counts.most_common(12)
    stacked_bars([label for label, _ in ranked_d7],
                 {label: {"speech act": value} for label, value in ranked_d7},
                 FIGURES / "speech_act_of_plurality_claims.svg",
                 "Which voice the windows carrying plurality claims are actually in (v3 D7b_speech_act)",
                 "v1 counted the term and inferred the doctrine; this is the distribution that inference hid",
                 {"speech act": "#5aa9e6"})

    matrix_rows, matrix_columns = matrix_shape()
    exact_pairs = sum(distinct for distinct, _, _ in layer["pair_counts"].values())
    exact_multiplicity = sum(multiplicity for _, multiplicity, _ in layer["pair_counts"].values())
    connected_work_pairs = {pair for pair, (distinct, _, _) in layer["pair_counts"].items() if distinct}
    coverage = coverage_inventory(rules, ontology, records)
    graph = {
        "schema_version": "1.2",
        "instrument": "divinity-ontology v3.1 graph layer",
        "coverage_inventory": coverage,
        "interpretation": "passage-level shared-state candidates and work-level state inventories. No edge is a "
                          "historical claim; edge kinds are candidate-generation labels only. A pair shares an "
                          "edge when both passages carry at least one live dimension=value state; that is a "
                          "co-occurrence of coded states, not a similarity. The relation is now enumerated "
                          "exactly, so a pair absent from it genuinely carries no state in common in this "
                          "instrument's output -- which is still not a claim about the concepts, because 40 of "
                          "the 93 declared values have no surface pattern and 9 are labelled "
                          "not_yet_instrumented. See `coverage_inventory` for what those sets really are: most "
                          "of the unpatterned values are rule-derived fields, not missing detectors, and seven "
                          "of the nine labelled values do have a pattern.",
        "candidate_generation": candidate_generation_block(exact_pairs),
        "nodes": [{"id": work, "region": next((r["region"] for r in records if r["work_id"] == work), ""),
                   "tradition": next((r["tradition"] for r in records if r["work_id"] == work), ""),
                   "candidate_records": sum(1 for r in records if r["work_id"] == work),
                   "live_candidate_records": sum(1 for r in records if r["work_id"] == work and r["assertion_state"] == "candidate")}
                  for work in works],
        "edges": [{"id": f"{left}--{right}", "left_work": left, "right_work": right,
                   "shared_passage_pairs": multiplicity,
                   "distinct_shared_state_pairs": distinct,
                   "edge_kind": "SHARED_DIMENSION_STATE_CANDIDATE",
                   "counts_as_independent": frozenset((left, right)) not in dependence}
                  for (left, right), (distinct, multiplicity, _) in sorted(layer["pair_counts"].items())
                  if (left, right) in connected_work_pairs],
        "layers": [
            {"name": "1_source_dependency", "status": "populated",
             "edge_meaning": "documented reprint, retelling or shared-translation relationships",
             "explicitly_not": "not evidence of conceptual agreement",
             "edges": len(dependence)},
            {"name": "2_dimension_state_attestation", "status": "populated",
             "edge_meaning": "none: this layer is an inventory of states per work, rendered as a matrix not as edges",
             "explicitly_not": "not a claim that any tradition holds the coded state; records are unadjudicated candidates",
             "nodes": len(works)},
            {"name": "3_passage_pair_shared_states", "status": "populated",
             "edge_meaning": "two passages from different works share at least one live dimension state",
             "explicitly_not": "not similarity of doctrine; shared English wording and shared translation habits are the "
                               "dominant cause at this scale and must be reviewed before any use",
             "enumeration": "exact inverted index join; no blocking approximation remains in this layer",
             "pairs": exact_pairs,
             "edges": written,
             "edges_are": f"a display slice: the top {EDGES_DISPLAY_PER_WORK_PAIR} pairs of each connected "
                          "work pair by shared-state count. The `pairs` value above, not this one, is the "
                          "layer's size."},
            {"name": "4_inheritance_and_transformation", "status": "unpopulated_by_design",
             "edge_meaning": "would carry OPERATOR-tagged edges between dated expressions",
             "explicitly_not": "empty because composition dates, earliest-witness dates and contact routes are not yet "
                               "recorded as data; filling it before then would be the error the v1 conclusion made",
             "required_fields": ontology["transformation_operators"]["discipline"],
             "edges": 0},
            {"name": "5_coverage_and_absence", "status": "populated",
             "edge_meaning": "which dimension values are instrumented at all, so a gap reads as an instrument gap",
             "explicitly_not": "not a statement about the traditions",
             "values_not_yet_instrumented": coverage["values"]["not_yet_instrumented"],
             "inventory": "see the top-level `coverage_inventory`, which is the one table of these sets",
             "edges": 0},
        ],
        "scale": {
            "attestation_records": len(records),
            "passages_with_live_states": len(per_passage),
            "passage_matrix_rows": matrix_rows,
            "passage_matrix_value_columns": matrix_columns,
            "passage_matrix_cells": matrix_rows * matrix_columns,
            "index_features": layer["features_in_index"],
            "index_postings": layer["postings"],
            "exact_distinct_cross_work_pairs": exact_pairs,
            "exact_pair_multiplicity_by_feature": exact_multiplicity,
            "work_pairs_connected": len(connected_work_pairs),
            "work_pairs_possible": len(works) * (len(works) - 1) // 2,
            "passage_pair_edges_displayed": written,
            "passage_pair_edges_written": written,
            "display_cap_per_work_pair": EDGES_DISPLAY_PER_WORK_PAIR,
            "edge_file_is_display_slice": written < exact_pairs,
            "work_pair_edges": len(workpair_dimensions),
            "work_state_matrix_cells": len(works) * len(dimensions),
            "source_dependency_edges": len(dependence),
            "naive_passage_pair_space": len(per_passage) * (len(per_passage) - 1) // 2,
            "note": "these are the counts of what the instrument looked at, not of what it established. The "
                    "pair count is now exact for the relation the layer defines -- every cross-work pair "
                    "sharing at least one live coded state -- where the previous build shipped a MinHash "
                    "banding sample measured at 2.32% of that set. The edge file is a display slice under a "
                    "declared per-work-pair cap; the complete relation regenerates from "
                    "results/ontology_passage_index.json.gz, and every count here is over the whole "
                    "enumeration, not over the displayed rows.",
        },
        "reproducibility": {"attestations_sha256": hashlib.sha256(ATTEST.read_bytes()).hexdigest(),
                            "passages_sha256": hashlib.sha256(PASSAGES.read_bytes()).hexdigest(),
                            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            "index_sha256": hashlib.sha256(OUT_INDEX.read_bytes()).hexdigest(),
                            "graph_recall_validation_sha256": (
                                hashlib.sha256(OUT_RECALL.read_bytes()).hexdigest() if OUT_RECALL.exists() else None),
                            "deterministic": "the join reads posting lists in sorted order and the display "
                                             "slice is chosen by shared-state count then passage id, so two "
                                             "runs write byte-identical files. The gzip streams are written "
                                             "with mtime=0 and no stored filename, because the header's "
                                             "creation time made the files differ run to run while every "
                                             "count stayed equal. tests/test_graph_recall.py re-runs this "
                                             "build and compares the four artifact hashes.",
                            "superseded_lsh_parameters": {"seed": SEED, "num_hashes": NUM_HASHES,
                                                          "bands": NUM_BANDS, "rows_per_band": BAND_SIZE,
                                                          "bucket_cap": BUCKET_CAP,
                                                          "why_still_here": "tools/validate_graph_recall.py "
                                                                            "measures what this blocking step "
                                                                            "lost against the exact enumeration"},
                            "candidate_pair_semantics": "co-occurrence of live dimension=value states across "
                                                        "works, never similarity or a historical claim"},
    }
    OUT_GRAPH.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    return {"passages_with_live_states": len(per_passage),
            "index_features": layer["features_in_index"], "index_postings": layer["postings"],
            "exact_distinct_cross_work_pairs": exact_pairs,
            "exact_pair_multiplicity_by_feature": exact_multiplicity,
            "work_pairs_connected": len(connected_work_pairs),
            "work_pairs_possible": len(works) * (len(works) - 1) // 2,
            "edges_displayed": written, "edges_written": written,
            "display_cap_per_work_pair": EDGES_DISPLAY_PER_WORK_PAIR,
            "work_pairs_with_shared_states": len(workpair_dimensions),
            "records": len(records),
            "index_file_mb": round(OUT_INDEX.stat().st_size / 1e6, 1),
            "edges_file_mb": round(OUT_EDGES.stat().st_size / 1e6, 1),
            "passage_matrix_cells": matrix_rows * matrix_columns,
            "work_state_matrix_cells": len(works) * len(dimensions)}


def main():
    print(json.dumps(build(), indent=2))
    print(f"wrote {OUT_GRAPH.name}, {OUT_EDGES.name}, {OUT_INDEX.name}, {OUT_WORKPAIRS.name}, {FIGURES.name}/*.svg")


if __name__ == "__main__":
    main()
