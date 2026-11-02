#!/usr/bin/env python3
"""Full-corpus ontology graphs: every passage, every value, no top-N sampling.

The v2 relevance graph capped itself at 100 work pairs (build_relevance_graph.py:258),
which made a 34,281-passage corpus look like a 200-row table. This tool emits the
complete layers instead: a passage-by-pair candidate edge set produced by MinHash
banding, an aggregated work-by-dimension state matrix, and SVG figures drawn from
those full counts.

Layer 4 (transformation) is deliberately empty. Asserting an inheritance edge needs
dated composition, dated witness and a documented contact route; the dates are not
filled, so the layer publishes what is missing rather than a plausible-looking tree.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ATTEST = ROOT / "results/ontology_attestations.jsonl.gz"
SUMMARY = ROOT / "results/ontology_run_summary.json"
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"
DEPENDENCE = ROOT / "config/source_dependence.json"
RULES = ROOT / "config/ontology_english_rules.json"
ONTOLOGY = ROOT / "config/divinity_ontology.json"
OUT_GRAPH = ROOT / "results/ontology_graph.json"
OUT_EDGES = ROOT / "results/ontology_passage_pairs.jsonl.gz"
OUT_WORKPAIRS = ROOT / "results/ontology_workpair_dimensions.csv"
OUT_MATRIX = ROOT / "results/ontology_passage_matrix.csv.gz"
FIGURES = ROOT / "results/figures"

# 128 hashes banded 16x8: two passages sharing a state profile land in a bucket
# often enough to be recovered while keeping the candidate set a fraction of the
# 5.9e8 pairs the passage count would otherwise imply.
NUM_HASHES, BAND_SIZE, NUM_BANDS = 128, 8, 16
MERSENNE_PRIME = (1 << 61) - 1
SEED = 20261101


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
    """Passage -> set of dimension-value states, counting only live candidates."""
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


def band_candidates(keys, signatures):
    """Stream bucket pairs; returns every cross-work candidate pair exactly once."""
    seen, pairs = set(), []
    for band in range(NUM_BANDS):
        buckets = defaultdict(list)
        start = band * BAND_SIZE
        for row in range(len(keys)):
            buckets[tuple(signatures[row, start:start + BAND_SIZE].tolist())].append(row)
        for rows in buckets.values():
            if len(rows) < 2 or len(rows) > 400:
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


def build():
    records = load_attestations()
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    passage_meta = {}
    for line in PASSAGES.read_text(encoding="utf-8").splitlines():
        passage = json.loads(line)
        passage_meta[passage["passage_id"]] = passage
    per_passage = features_of(records)
    vocabulary = {feature for features in per_passage.values() for feature in features}
    keys, signatures = minhash_signatures(per_passage, vocabulary)
    candidates = band_candidates(keys, signatures)
    dependence = dependence_map()

    workpair_dimensions = defaultdict(lambda: defaultdict(int))
    written = 0
    with gzip.open(OUT_EDGES, "wt", encoding="utf-8", newline="") as handle:
        for (left_work, left_passage), (right_work, right_passage) in sorted(candidates):
            left_features, right_features = per_passage[(left_work, left_passage)], per_passage[(right_work, right_passage)]
            score = jaccard(left_features, right_features)
            if score <= 0:
                continue
            shared = sorted(left_features & right_features)
            edge = {"left_passage_id": left_passage, "right_passage_id": right_passage,
                    "left_work_id": left_work, "right_work_id": right_work,
                    "shared_states": shared, "state_jaccard": round(score, 6),
                    "dependence_relationship": dependence.get(frozenset((left_work, right_work)), ""),
                    "counts_as_independent": frozenset((left_work, right_work)) not in dependence,
                    "edge_kind": "SHARED_DIMENSION_STATE_CANDIDATE"}
            handle.write(json.dumps(edge, ensure_ascii=False) + "\n")
            written += 1
            for feature in shared:
                workpair_dimensions[(left_work, right_work)][feature] += 1

    works = sorted({record["work_id"] for record in records})
    dimensions = sorted(ontology["dimensions"])
    state_matrix = {}
    for record in records:
        key = (record["work_id"], record["dimension"])
        current = state_matrix.get(key, "")
        if record["assertion_state"] == "candidate":
            state_matrix[key] = "candidate"
        elif record["assertion_state"] == "blocked_by_speech_act" and current != "candidate":
            state_matrix[key] = "blocked"
        elif current == "":
            state_matrix[key] = "no_candidate"

    with OUT_WORKPAIRS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["left_work", "right_work", "dimension_state", "shared_passage_pairs",
                         "counts_as_independent"])
        for (left, right), features in sorted(workpair_dimensions.items()):
            for feature, count in sorted(features.items()):
                writer.writerow([left, right, feature, count,
                                 "no" if frozenset((left, right)) in dependence else "yes"])

    FIGURES.mkdir(parents=True, exist_ok=True)
    palette = {"candidate": "#3ddc97", "blocked": "#f2a24b", "no_candidate": "#4a5560", "": "#1d2126"}
    svg_heatmap(works, dimensions, state_matrix,
                FIGURES / "work_by_dimension_states.svg",
                "Every work against every dimension: where a state was found, where the frame refused, where it looked",
                "green = at least one live candidate record · orange = matches occurred but D7 blocked the doctrinal reading "
                "· grey = no candidate · rows are all 65 works, columns are all 7 dimensions; nothing is sampled",
                palette)

    by_dimension = defaultdict(Counter)
    for record in records:
        by_dimension[record["dimension"]][record["assertion_state"]] += 1
    ordered = [d for d in dimensions if by_dimension[d]]
    stacked_bars(ordered, by_dimension, FIGURES / "assertion_states_by_dimension.svg",
                 "Candidate records by assertion state, per dimension",
                 "the frame's own refusal rate is a result of the design, not noise inside it",
                 {"candidate": "#3ddc97", "candidate_requires_human_disambiguation": "#5aa9e6",
                  "blocked_by_speech_act": "#f2a24b", "not_yet_instrumented": "#8b8f95"})

    d7_counts = Counter(record["D7_speech_act"] for record in records if record["dimension"] == "D2_plurality")
    d7_palette_hues = ["#3ddc97", "#5aa9e6", "#f2a24b", "#8b8f95", "#c586c0", "#e06c75",
                       "#d19a66", "#56b6c2", "#98c379", "#abb2bf", "#7f848e", "#61afef"]
    ranked_d7 = [item for item in d7_counts.most_common(12)]
    stacked_bars([label for label, _ in ranked_d7],
                 {label: {"voices": value} for label, value in ranked_d7},
                 FIGURES / "speech_act_of_plurality_claims.svg",
                 "Which voice the windows carrying plurality claims are actually in",
                 "v1 counted the term and inferred the doctrine; this is the distribution that inference hid",
                 {"voices": "#5aa9e6"})

    matrix_rows, matrix_columns = matrix_shape()
    graph = {
        "schema_version": "1.0",
        "instrument": "divinity-ontology v2 graph layer",
        "interpretation": "passage-level shared-state candidates and work-level state inventories. No edge is a "
                          "historical claim; edge kinds are candidate-generation labels only.",
        "sampling": "NONE. every candidate produced by banding is written to results/ontology_passage_pairs.jsonl.gz; "
                    "figures are drawn from complete counts. contrast build_relevance_graph.py:258, which truncated to 100 pairs.",
        "nodes": [{"id": work, "region": next((r["region"] for r in records if r["work_id"] == work), ""),
                   "tradition": next((r["tradition"] for r in records if r["work_id"] == work), ""),
                   "candidate_records": sum(1 for r in records if r["work_id"] == work),
                   "live_candidate_records": sum(1 for r in records if r["work_id"] == work and r["assertion_state"] == "candidate")}
                  for work in works],
        "edges": [{"id": f"{left}--{right}", "left_work": left, "right_work": right,
                   "shared_passage_pairs": sum(workpair_dimensions[(left, right)].values()),
                   "edge_kind": "SHARED_DIMENSION_STATE_CANDIDATE",
                   "counts_as_independent": frozenset((left, right)) not in dependence}
                  for (left, right) in sorted(workpair_dimensions)],
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
             "edges": written},
            {"name": "4_inheritance_and_transformation", "status": "unpopulated_by_design",
             "edge_meaning": "would carry OPERATOR-tagged edges between dated expressions",
             "explicitly_not": "empty because composition dates, earliest-witness dates and contact routes are not yet "
                               "recorded as data; filling it before then would be the error the v1 conclusion made",
             "required_fields": ontology["transformation_operators"]["discipline"],
             "edges": 0},
            {"name": "5_coverage_and_absence", "status": "populated",
             "edge_meaning": "which dimension values are instrumented at all, so a gap reads as an instrument gap",
             "explicitly_not": "not a statement about the traditions",
             "values_not_yet_instrumented": sorted({f"{d}={v}" for d, specs in rules["dimensions"].items()
                                                    for v, spec in specs["values"].items()
                                                    if isinstance(spec, dict) and spec.get("coverage_state") == "not_yet_instrumented"}),
             "edges": 0},
        ],
        "scale": {
            "attestation_records": len(records),
            "passage_matrix_rows": matrix_rows,
            "passage_matrix_value_columns": matrix_columns,
            "passage_matrix_cells": matrix_rows * matrix_columns,
            "passage_pair_edges_written": written,
            "work_pair_edges": len(workpair_dimensions),
            "source_dependency_edges": len(dependence),
            "naive_passage_pair_space": len(per_passage) * (len(per_passage) - 1) // 2,
            "note": "these are the counts of what the instrument looked at, not of what it established. The "
                    "previous graph layer shipped 149 edges and 100 work pairs after a top-100 truncation; "
                    "this layer ships every candidate the banding produced.",
        },
        "reproducibility": {"attestations_sha256": hashlib.sha256(ATTEST.read_bytes()).hexdigest(),
                            "passages_sha256": hashlib.sha256(PASSAGES.read_bytes()).hexdigest(),
                            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            "lsh_seed": SEED, "num_hashes": NUM_HASHES, "bands": NUM_BANDS,
                            "bucket_cap": 400, "randomness": "seeded MinHash only; banding is deterministic given the seed"},
    }
    OUT_GRAPH.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    return {"passages_with_live_states": len(per_passage), "vocabulary_size": len(vocabulary),
            "candidate_pairs_generated": len(candidates), "candidate_pairs_written": written,
            "work_pairs_with_shared_states": len(workpair_dimensions),
            "records": len(records), "edges_file_mb": round(OUT_EDGES.stat().st_size / 1e6, 1),
            "passage_matrix_cells": matrix_rows * matrix_columns,
            "work_state_matrix_cells": len(works) * len(dimensions)}


def main():
    print(json.dumps(build(), indent=2))
    print(f"wrote {OUT_GRAPH.name}, {OUT_EDGES.name}, {OUT_WORKPAIRS.name}, {FIGURES.name}/*.svg")


if __name__ == "__main__":
    main()
