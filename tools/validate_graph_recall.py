#!/usr/bin/env python3
"""Measure what the superseded LSH blocking lost, against the exact inverted index that replaced it.

Two measurements, and the second is the one the reviewer asked for.

1. `subset` — the original measurement: over a deterministic stratified subset of live-state passages,
   brute-force compare every pair, and ask what fraction the real banding path recovers. This is the
   figure published as 0.023214, and it is a *subset* measurement: it must always be quoted as one.
2. `corpus_wide` — the same question over the whole live-state population, with the denominator taken
   from tools/build_ontology_graph.py's exact inverted index join rather than from a brute-force scan.
   No subset caveat applies to it, and the loss decomposition adds up exactly:
   `recovered_by_lsh + lost_to_bucket_cap + lost_to_banding = exact_distinct_cross_work_pairs`.

The graph builder no longer uses banding: `results/ontology_passage_pairs.jsonl.gz` and the layer-3
counts come from the exact index, whose recall against the relation it defines is 1 by construction.
This file therefore measures a superseded step, and it exists so that the replacement is a measured
before/after rather than a claim.

Discipline:
- the measurement reuses tools/build_ontology_graph.py's own functions (load_attestations, features_of,
  minhash_signatures, band_candidates, inverted_index, exact_sharing_layer). It does not reimplement the
  LSH path, so it measures the real thing, and it does not reimplement the exact path, so the
  denominator is the number the published graph actually rests on.
- the subset is chosen deterministically: stratify live-state passages by (work, number-of-live-states band)
  and take whole strata up to the quota, otherwise the first `quota` passage ids in sorted order. No random
  selection anywhere; the seed used by MinHash is the graph builder's own published seed.
- exact comparison and LSH comparison run over the same subset; the LSH path still runs over the full
  population, so bucket sizes and cap behaviour are the production ones.
- recall of the LSH step is not recall of the concept detector. A pair whose shared state no detector could
  ever match is invisible to both the exact comparison and the LSH step, and this measurement cannot see it
  either; that limitation is published in `what_this_does_not_measure`.

Output: results/graph_recall_validation.json plus a one-line quotable summary.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_ontology_graph as bog  # noqa: E402  the actual LSH path, imported not reimplemented

OUT_RECALL = ROOT / "results/graph_recall_validation.json"

STATE_BANDS = (("1", 1, 1), ("2", 2, 2), ("3-4", 3, 4), ("5-9", 5, 9), ("10+", 10, None))
QUOTA = 8  # whole strata up to this size are kept complete; larger strata take the first QUOTA sorted ids


def band_of(count):
    for label, low, high in STATE_BANDS:
        if count >= low and (high is None or count <= high):
            return label
    raise ValueError(f"live-state count {count} matches no band")


def select_subset(per_passage):
    """Deterministic stratified subset: (work, live-state band) strata, quota-capped in sorted order."""
    strata = defaultdict(list)
    for (work, passage), features in per_passage.items():
        strata[(work, band_of(len(features)))].append(passage)
    members = []
    whole = 0
    for stratum in sorted(strata):
        ordered = sorted(strata[stratum])
        members.extend((stratum[0], passage) for passage in ordered[:QUOTA])
        if len(ordered) <= QUOTA:
            whole += 1
    return sorted(members), {"strata_nonempty": len(strata), "strata_kept_whole": whole, "quota": QUOTA}


def exact_sharing_pairs(subset, per_passage):
    """Brute-force direct comparison over the subset: cross-work pairs sharing >=1 live state."""
    pairs = set()
    for left_index in range(len(subset)):
        left = subset[left_index]
        left_features = per_passage[left]
        for right_index in range(left_index + 1, len(subset)):
            right = subset[right_index]
            if left[0] == right[0]:
                continue
            if left_features & per_passage[right]:
                pairs.add(frozenset((left, right)))
    return pairs


def subset_pair_set(candidates, subset_ids):
    """Project banding output onto the subset: same pair identity (work, passage) frozensets as exact."""
    return {frozenset(pair) for pair in candidates if pair[0] in subset_ids and pair[1] in subset_ids}


def measure():
    records = bog.load_attestations()
    per_passage = bog.features_of(records)
    vocabulary = {feature for features in per_passage.values() for feature in features}
    subset, strata_info = select_subset(per_passage)
    subset_ids = set(subset)
    if len(subset_ids) != len(subset):  # defensive: (work, passage) keys are unique by construction
        raise AssertionError("subset selection produced duplicate passage keys")

    # production LSH path, over the full population, so bucket sizes and cap effects are real
    keys, signatures = bog.minhash_signatures(per_passage, vocabulary)
    capped_all = bog.band_candidates(keys, signatures, bucket_cap=bog.BUCKET_CAP)
    uncapped_all = bog.band_candidates(keys, signatures, bucket_cap=None)
    capped = subset_pair_set(capped_all, subset_ids)
    uncapped = subset_pair_set(uncapped_all, subset_ids)

    exact = exact_sharing_pairs(subset, per_passage)
    recovered = exact & capped
    lost_to_cap = (exact & uncapped) - capped
    lost_to_banding = exact - uncapped
    false_positives = capped - exact
    if not (len(recovered) + len(lost_to_cap) + len(lost_to_banding) == len(exact)):
        raise AssertionError("loss decomposition does not add up to the exact pair count")
    if not (lost_to_cap <= uncapped and recovered <= capped and capped <= uncapped):
        raise AssertionError("set relations between capped and uncapped banding inverted")

    # Corpus-wide: the denominator is the exact inverted index join -- the enumeration the published
    # graph now rests on -- so this figure carries no subset caveat. band_candidates deduplicates on
    # passage ids alone, which is lossless only while those ids are globally unique; check it, because
    # a collision here would silently shrink the candidate counts and inflate the loss.
    if len({passage for _, passage in per_passage}) != len(per_passage):
        raise AssertionError("passage ids are not globally unique; the LSH dedup key would drop real pairs")
    index = bog.inverted_index(per_passage)
    layer = bog.exact_sharing_layer(per_passage, index, display_per_work_pair=None)
    exact_total = sum(distinct for distinct, _, _ in layer["pair_counts"].values())
    capped_true = sum(1 for left, right in capped_all if per_passage[left] & per_passage[right])
    uncapped_true = sum(1 for left, right in uncapped_all if per_passage[left] & per_passage[right])
    if capped_true != len(capped_all) or uncapped_true != len(uncapped_all):
        raise AssertionError("some LSH candidate pairs share no live state; the true-positive count "
                            "diverged from the candidate count and the two must be reported apart")
    if exact_total <= 0:
        raise AssertionError("exact index found no cross-work sharing pairs; a zero denominator is not a recall")
    corpus_wide = {
        "exact_distinct_cross_work_pairs": exact_total,
        "exact_pair_multiplicity_by_feature": sum(m for _, m, _ in layer["pair_counts"].values()),
        "work_pairs_connected": sum(1 for d, _, _ in layer["pair_counts"].values() if d),
        "lsh_candidates_with_bucket_cap": len(capped_all),
        "lsh_candidates_bucket_cap_removed": len(uncapped_all),
        "recovered_by_lsh": capped_true,
        "recall": round(capped_true / exact_total, 6),
        "lost_to_bucket_cap": uncapped_true - capped_true,
        "lost_to_banding": exact_total - uncapped_true,
        "recall_if_bucket_cap_removed": round(uncapped_true / exact_total, 6),
        "loss_decomposition_check": (f"{capped_true} + {uncapped_true - capped_true} + "
                                     f"{exact_total - uncapped_true} = {exact_total}"),
        "precision_of_candidates": 1.0,
        "precision_is_measured_not_assumed": ("every candidate of both runs was re-tested for a shared live "
                                             f"state; {capped_true} of {len(capped_all)} and {uncapped_true} of "
                                             f"{len(uncapped_all)} passed, so banding produced no false "
                                             "positives here and its only defect was coverage"),
        "note": "the exact denominator is computed by the graph builder's own exact_sharing_layer with "
                "display_per_work_pair=None, so no cap and no display slice affects it. This is the "
                "corpus-wide form of the subset figure: the same loss decomposition over the whole "
                "live-state population instead of a stratified sample of it.",
    }
    if not (capped_true + corpus_wide["lost_to_bucket_cap"] + corpus_wide["lost_to_banding"] == exact_total):
        raise AssertionError("corpus-wide loss decomposition does not add up to the exact pair count")

    results = {
        "subset_definition": (f"deterministic stratified subset of {len(subset)} of {len(per_passage)} live-state "
                              f"passages: strata = (work, live-state band) over bands "
                              f"{[b for b, _, _ in STATE_BANDS]}, whole strata up to {QUOTA} passages kept "
                              f"complete, larger strata take the first {QUOTA} passage ids in sorted order; "
                              f"no random selection"),
        "pairwise_comparisons_within_subset": len(subset) * (len(subset) - 1) // 2,
        "exact_sharing_pairs": len(exact),
        "recovered_by_lsh": len(recovered),
        "recall": round(len(recovered) / len(exact), 6) if exact else None,
        "recall_scope": ("this recall is measured on the stratified subset above, not over the corpus. The "
                         "corpus-wide figure lives in `corpus_wide`; quoting this one without the subset "
                         "qualifier overstates or understates it and the two are not the same number."),
        "recall_if_bucket_cap_removed": round(len(recovered | lost_to_cap) / len(exact), 6) if exact else None,
        "lost_to_bucket_cap": len(lost_to_cap),
        "lost_to_banding": len(lost_to_banding),
        "loss_decomposition_check": "exact_sharing_pairs = recovered_by_lsh + lost_to_bucket_cap + lost_to_banding",
        "lsh_pairs_in_subset_not_in_exact": len(false_positives),
        "note_false_positives": "banding can return subset pairs that share no live state (hash collision with "
                               "no shared feature); the builder writes only pairs with shared states, so these "
                               "do not reach the edge file and do not affect recall",
    }
    document = {
        "schema_version": "1.1",
        "purpose": "measured recall of the superseded MinHash-LSH blocking step, against the exact inverted "
                   "index join that now generates results/ontology_passage_pairs.jsonl.gz. The current build "
                   "has no blocking approximation, so its recall against the relation it defines is 1 by "
                   "construction; these numbers are the measured cost of the approximation that was replaced.",
        "generated_by": "tools/validate_graph_recall.py",
        "current_graph_build": {
            "method": "exact_inverted_index_join",
            "recall_of_the_current_build": "1.0 by construction, not measured: the index is the join, so every "
                                           "cross-work pair sharing a live state is enumerated. What remains "
                                           "unmeasured is the detector, not the pairing.",
            "index_artifact": "results/ontology_passage_index.json.gz",
        },
        "reuses_the_graph_builders_own_path": {
            "module": "tools/build_ontology_graph.py",
            "functions": ["load_attestations", "features_of", "minhash_signatures", "band_candidates",
                          "inverted_index", "exact_sharing_layer"],
            "band_candidates_bucket_cap_argument": "the validator passes bucket_cap=None for the uncapped "
                                                   "comparison; production default bog.BUCKET_CAP is unchanged",
            "exact_sharing_layer_display_per_work_pair_argument": "the validator passes "
                                                                  "display_per_work_pair=None so no display "
                                                                  "slice bounds the corpus-wide denominator; "
                                                                  "the builder's production default is "
                                                                  f"bog.EDGES_DISPLAY_PER_WORK_PAIR = "
                                                                  f"{bog.EDGES_DISPLAY_PER_WORK_PAIR}",
            "lsh_ran_over": "the full live-state passage population, so bucket sizes and cap losses are the "
                            "production ones; only the pair sets are projected onto the subset",
        },
        "pair_definition": "cross-work pair of passages both carrying live states with >=1 common "
                           "dimension=value, where live means assertion_state == 'candidate' (v3 schema). "
                           "Co-occurrence of coded states, never a similarity or historical claim.",
        "inputs": {"attestations_sha256": hashlib.sha256(bog.ATTEST.read_bytes()).hexdigest()},
        "population": {"passages_with_live_states": len(per_passage),
                       "naive_passage_pair_space": len(per_passage) * (len(per_passage) - 1) // 2},
        "subset": {"selection_rule": "sorted strata, quota cap, deterministic first-K by passage_id; no random "
                                     "selection, no fitted parameters; MinHash uses the builder's published seed",
                   "state_band_labels": [{"label": label, "min_states": low,
                                          "max_states": high} for label, low, high in STATE_BANDS],
                   "stratum": "(work_id, live-state band)", **strata_info,
                   "passages_in_subset": len(subset),
                   "members": [{"work_id": work, "passage_id": passage} for work, passage in subset]},
        "parameters": {"num_hashes": bog.NUM_HASHES, "bands": bog.NUM_BANDS, "rows_per_band": bog.BAND_SIZE,
                       "seed": bog.SEED, "bucket_cap": bog.BUCKET_CAP},
        "results": results,
        "corpus_wide": corpus_wide,
        "what_this_does_not_measure": (
            "Recall of the LSH blocking step is recall of candidate pairing given the states already recorded; "
            "it is NOT recall of the concept detector. The exact comparison only knows pairs that share a live "
            "dimension=value state the detector wrote down, so a pair the term detector never could see — a value "
            "with no instrumented detector, a concept expressed in source language but translated away, a state "
            "recorded only as not_yet_instrumented or pending human disambiguation — is invisible to the exact "
            "set and to LSH alike, and no number in this file bounds it. That limitation applies to the "
            "corpus-wide block too: its denominator is complete for the relation as defined and silent about "
            "every relation the instrument cannot define. The `results` block additionally covers only the "
            "stratified subset, not the full pair space."),
        "summary_line": (f"superseded LSH blocking recall {corpus_wide['recall']:.6f} corpus-wide on "
                         f"{exact_total} exact sharing pairs "
                         f"({results['recall']:.6f} on the {results['exact_sharing_pairs']}-pair deterministic "
                         f"{len(subset)}-passage subset); "
                         f"{corpus_wide['lost_to_bucket_cap']} lost to the bucket cap {bog.BUCKET_CAP}, "
                         f"{corpus_wide['lost_to_banding']} lost to banding itself; the published graph now "
                         f"uses the exact index, whose recall against this relation is 1"),
    }
    return document


def main():
    document = measure()
    OUT_RECALL.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    print(document["summary_line"])
    print(f"wrote {OUT_RECALL.name}")


if __name__ == "__main__":
    main()
