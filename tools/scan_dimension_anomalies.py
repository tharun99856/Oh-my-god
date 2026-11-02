#!/usr/bin/env python3
"""Measure where cross-work concordance in this corpus exceeds what its own value frequencies predict.

Why this exists. The comparison layer ranks dimension blocks by mean pairwise similarity, and on the corpus
as it stands that ranking is mostly a measure of how flat each dimension's output is. `D7a_speaker_attribution`
is the most concordant key in the instrument at 0.834 and the least informative: two works drawn at random from
the same 45 works would agree 0.838 of the time. Subtracting the chance line is not a refinement, it is what
separates a finding about the traditions from a finding about a detector that prefers one value.

What it reports, in order of how much it hurts:

* a live/dead census of the twelve declared dimensions, because three of them carry a value for zero works;
* per dimension, observed pairwise agreement, the agreement its own marginals predict, and the excess;
* the same three numbers aggregated over the blocks the attractor prior ranks, so M4's ordering is checked
  against a quantity that could in principle come out wrong for a reason;
* the work pairs whose excess agreement is largest, and the pairs where the block an attractor says should be
  free out-agrees the block it says should be tight -- the signature descent predicts and convergence does not.

What it is not. No dates are filled, so nothing here is a transmission claim. The states are detector output
over English translations, not human coding. Works are not independent: a digest that reprints another work's
text inflates exactly the quantity this tool measures, so every pair carries its dependence flags rather than
being filtered on them. And the chance line is computed from the corpus's own value frequencies, which means a
dimension that is degenerate for a real reason (every tradition really does say the same thing) and a dimension
that is degenerate because the regex is lazy look identical here. They do not look identical in the packet,
which is why the packet still has to be coded.

Usage:
    python tools/scan_dimension_anomalies.py            # report to stdout
    python tools/scan_dimension_anomalies.py --write    # report and write results/dimension_anomalies.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import compare_models as cm  # noqa: E402  the same block definitions and similarity rules, not reimplemented

WORK_STATES = ROOT / "results/ontology_work_states.csv"
CONFIG_PATH = ROOT / "config/model_comparison_v3.json"
OUT = ROOT / "results/dimension_anomalies.json"
PRODUCED_BY = "python tools/scan_dimension_anomalies.py --write"
CHANCE_SEED = 20261102
CHANCE_REPETITIONS = 200
# A dimension whose observed agreement sits inside this band of its own chance line is reported as
# indistinguishable from chance. This is the scanner's descriptive band, not the separability registered for the
# block adjacency test; the two are different quantities measured on different units and happen to share a number.
CHANCE_BAND = 0.05


def load_work_states(path=WORK_STATES, frame="candidate_count"):
    """work -> dimension -> value(s), for works the chosen assertion frame actually populates.

    `candidate_count` is the detector's own claim that a proposition carries this value; `affirmative_doctrine_count`
    is its subset, the propositions the text endorses as doctrine. Scanning both is the point: if the ordering of the
    blocks changes between the frames, the ordering was a property of how loudly the detector fires and not of the
    traditions.
    """
    per_work = defaultdict(dict)
    declared_cardinality = {}
    dependent = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row["dimension"]
            declared_cardinality[key] = row["cardinality"]
            if row["work_has_dependent_reprint_records"] == "yes":
                dependent.add(row["work_id"])
            if int(row[frame]) <= 0:
                continue
            if row["value"] in ("", "undecidable", "none"):
                continue
            per_work[row["work_id"]].setdefault(key, set()).add(row["value"])
    return per_work, declared_cardinality, dependent


def value_marginals(per_work, key):
    """Per-value prevalence over the works that carry anything for this key, and the set size each work carries.

    Works are visited in id order and the returned probabilities are keyed in value order. Both are load-bearing:
    the chance null draws from this dict with a seeded generator, and a draw made from a set-derived sequence
    depends on string hash order, which changes between processes. The scan would then reproduce only under a
    pinned ``PYTHONHASHSEED``.
    """
    carriers = [frozenset(per_work[work][key]) for work in sorted(per_work) if key in per_work[work]]
    if not carriers:
        return {}, []
    counter = Counter()
    for values in carriers:
        counter.update(values)
    total = sum(counter.values())
    return ({value: counter[value] / total for value in sorted(counter)},
            [len(values) for values in carriers])


READINGS = ("declared_rule", "value_sets")


def score(left, right, statistic):
    """One pair's agreement on one dimension under one statistic, or None if either side carries nothing."""
    if not left or not right:
        return None
    if statistic == "exact_match":
        return 1.0 if left == right else 0.0
    union = left | right
    return len(left & right) / len(union) if union else None


def statistic_for_key(cardinality, key):
    """The statistic the frame declares: exact match on a single-valued key, Jaccard on a set-valued one."""
    return "exact_match" if cardinality[key] == "single" else "jaccard"


def chance_agreement(probabilities, sizes, rng, statistic, reps=CHANCE_REPETITIONS):
    """Mean pairwise agreement between synthetic works drawn from this dimension's own value frequencies.

    Each synthetic work draws exactly as many values as the real work it replaces, sampling without replacement
    with the observed per-value prevalence as the weights, and the pairs are then scored with the same statistic
    the real measurement used. Two things this null deliberately does not do: it does not preserve correlations
    *between* values inside a work, which is why a dimension whose detector always fires on two values together
    reports more excess than a fully independent coding would, and it does not survive label permutation as a
    test at all -- the mean over a complete graph is permutation-invariant, so shuffling which work owns which
    set changes nothing and a permutation "control" here would be theatre.
    """
    values = sorted(probabilities)
    if not values or not any(probabilities.values()):
        return None
    total = 0.0
    for _ in range(reps):
        rows = []
        for size in sizes:
            chosen = set()
            remaining = list(values)
            pool = [probabilities[v] for v in remaining]
            for _draw in range(min(size, len(remaining))):
                pick = rng.choices(range(len(remaining)), weights=pool, k=1)[0]
                chosen.add(remaining.pop(pick))
                pool.pop(pick)
                if not pool:
                    break
            rows.append(frozenset(chosen))
        scores = [value for value in (score(left, right, statistic) for left, right in combinations(rows, 2))
                  if value is not None]
        if scores:
            total += sum(scores) / len(scores)
    return total / reps


def observed_agreement(per_work, key, statistic):
    """Mean agreement over every pair of works in this population that both carry something for this key."""
    carriers = [frozenset(per_work[work][key]) for work in sorted(per_work) if key in per_work[work]]
    scores = [value for value in (score(left, right, statistic) for left, right in combinations(carriers, 2))
              if value is not None]
    if not scores:
        return None, 0
    return sum(scores) / len(scores), len(scores)


def carrier_observations(per_work, keys, cardinality):
    """Both readings of every dimension, over the carrier graph of this work population."""
    out = {}
    for key in keys:
        declared = observed_agreement(per_work, key, statistic_for_key(cardinality, key))
        sets = observed_agreement(per_work, key, "jaccard")
        out[key] = {"declared_rule": declared, "value_sets": sets}
    return out


def dimension_rows(per_work, keys, cardinality, rng, observations, population_label):
    """One row per declared dimension, for whichever pair population `observations` was measured over.

    `observations` maps a dimension to (mean, pairs) under each of the two readings. Each reading's chance line
    is drawn from the same works that supplied its observations and scored with the same statistic, because a
    mean measured over one pair population and a baseline measured over another, or over a different statistic,
    differ by the conditioning and by nothing about the traditions. `declared_rule` is the statistic the model
    comparison actually scores; `value_sets` is the one that stays defined when a key the frame calls
    single-valued arrives carrying several values.
    """
    rows = []
    for key in keys:
        probabilities, sizes = value_marginals(per_work, key)
        statistic = statistic_for_key(cardinality, key)
        single = cardinality[key] == "single"
        offending = sum(1 for size in sizes if size > 1) if single else 0
        dominant_value, dominant_share = (max(probabilities.items(), key=lambda item: item[1])
                                          if probabilities else (None, 0.0))
        measured = {}
        for reading in READINGS:
            observed, pairs = observations.get(key, {}).get(reading, (None, 0))
            expected = (chance_agreement(probabilities, sizes, rng,
                                         statistic if reading == "declared_rule" else "jaccard",
                                         CHANCE_REPETITIONS) if sizes else None)
            measured[reading] = {
                "statistic": statistic if reading == "declared_rule" else "jaccard",
                "pairs_compared": pairs,
                "observed_mean_similarity": round(observed, 6) if observed is not None else None,
                "chance_similarity_from_own_marginals": round(expected, 6) if expected is not None else None,
                "excess_over_chance": (round(observed - expected, 6)
                                       if observed is not None and expected is not None else None),
                "excess_within_declared_chance_band": (abs(observed - expected) < CHANCE_BAND
                                                       if observed is not None and expected is not None else None),
            }
        rows.append({
            "dimension": key,
            "cardinality_declared_by_the_frame": cardinality[key],
            "statistic_the_frame_declares": statistic,
            "population_measured": population_label,
            "works_with_an_attested_value": len(sizes),
            "works_in_corpus": len(per_work),
            "distinct_values_attested": len(probabilities),
            "mean_values_per_work": round(sum(sizes) / len(sizes), 4) if sizes else None,
            "dominant_value": dominant_value,
            "dominant_share_of_value_tokens": round(dominant_share, 6) if probabilities else None,
            "cells_where_a_single_valued_key_carries_more_than_one_value": offending if single else None,
            "works_where_the_exact_match_rule_has_no_defined_answer": (
                round(offending / len(sizes), 6) if single and sizes else None),
            "declared_rule": measured["declared_rule"],
            "value_sets": measured["value_sets"],
            "readings_disagree": (measured["declared_rule"]["excess_over_chance"] is not None
                                  and measured["value_sets"]["excess_over_chance"] is not None
                                  and abs(measured["declared_rule"]["excess_over_chance"]
                                          - measured["value_sets"]["excess_over_chance"]) >= CHANCE_BAND),
            "status": "live" if measured["declared_rule"]["pairs_compared"] else "dead_no_work_carries_a_value",
        })
    return rows


def dimension_table(per_work, keys, cardinality, rng):
    return dimension_rows(per_work, keys, cardinality, rng, carrier_observations(per_work, keys, cardinality),
                          "every pair of works that both carry a value for this dimension")


def scorable_graph(per_work, config, cardinality):
    """Per-dimension agreement over exactly the pairs the comparison layer scores, and the works they cover.

    `similarity_between` refuses a pair below `minimum_comparable_keys`, so the graph the model comparison runs
    on is a subset of the carrier graph, and it is a biased subset: a work rich enough to be comparable is not a
    random work. This is the population the gate's means come from, so it is the population the gate's chance
    line has to come from too, and it is scored with the statistic the gate uses.
    """
    totals = {reading: {} for reading in READINGS}
    covered = set()
    pairs = 0
    for left, right, state_a, state_b, scored in scored_pairs(per_work, config):
        pairs += 1
        covered.update((left, right))
        for key in scored["comparable_keys"]:
            left_values, right_values = set(state_a[key]), set(state_b[key])
            for reading in READINGS:
                value = score(left_values, right_values,
                              statistic_for_key(cardinality, key) if reading == "declared_rule" else "jaccard")
                if value is None:
                    continue
                cell = totals[reading].setdefault(key, [0.0, 0])
                cell[0] += value
                cell[1] += 1
    observations = {}
    for key in sorted({key for reading in totals.values() for key in reading}):
        entries = {}
        for reading in READINGS:
            cell = totals[reading].get(key)
            if cell and cell[1]:
                entries[reading] = (round(cell[0] / cell[1], 6), cell[1])
        observations[key] = entries
    population = {work: per_work[work] for work in sorted(covered)}
    return observations, population, pairs


READING_NOTE = {
    "declared_rule": ("scored with the statistic the model comparison uses, which is 0 or 1 on a key the frame "
                      "calls single-valued even when a work carries several"),
    "value_sets": ("scored as set overlap, which stays defined on a multi-valued cell but is not the quantity "
                   "the likelihoods are built from"),
}
QUANTITY_NOTE = {
    "raw": "blocks are measured over different numbers of live keys, so a mean over one block is not the same "
           "quantity as a mean over another",
    "chance_corrected": "the chance line comes from this population's own marginals, so a dimension that is "
                        "genuinely universal and a dimension the detector cannot separate produce the same excess",
    "chance_corrected_dropping_the_band_keys": "dropping a dimension for sitting inside the chance band is a "
        "choice about the instrument, not about the traditions, and it moves the ordering; both readings are "
        "published because neither is the one you should have to trust",
}


def block_table(rows, config):
    """Block means on every reading and every scale, with the declared adjacency verdict for each.

    The adjacencies are read with `compare_models.adjacency_verdicts`, the same function the M4 gate calls, so a
    scan and a run cannot disagree about what a tie is. Each chance-corrected column is additionally reported
    with the dimensions inside the chance band dropped from their blocks: a block mean that includes a key
    carrying no signal above its own marginals is a mean over noise, and whether that key is counted can decide
    an adjacency on arithmetic alone.
    """
    by_dimension = {row["dimension"]: row for row in rows}
    blocks = config["dimension_similarity_rules"]["dimension_blocks"]
    declared = cm.declared_block_propensities(config)
    ordering = config["m4_block_profile_test"]["declared_ordering"]
    minimum_spread = config["m4_block_profile_test"]["minimum_block_spread"]
    quantities = (("raw_mean_similarity", "raw"),
                  ("excess_mean_over_chance", "chance_corrected"),
                  ("excess_mean_over_chance_dropping_the_band_keys", "chance_corrected_dropping_the_band_keys"))
    summary = {}
    for name in ordering:
        live = [key for key in blocks[name] if by_dimension[key]["declared_rule"]["pairs_compared"]]
        readings = {}
        for reading in READINGS:
            band = [key for key in live if by_dimension[key][reading]["excess_within_declared_chance_band"]]
            raw = [by_dimension[key][reading]["observed_mean_similarity"] for key in live]
            excess = [by_dimension[key][reading]["excess_over_chance"] for key in live]
            informative = [by_dimension[key][reading]["excess_over_chance"] for key in live
                           if not by_dimension[key][reading]["excess_within_declared_chance_band"]]
            readings[reading] = {
                "keys_indistinguishable_from_chance": band,
                "raw_mean_similarity": round(sum(raw) / len(raw), 6) if raw else None,
                "excess_mean_over_chance": round(sum(excess) / len(excess), 6) if excess else None,
                "excess_mean_over_chance_dropping_the_band_keys": (
                    round(sum(informative) / len(informative), 6) if informative else None),
            }
        summary[name] = {
            "declared_propensity": declared[name],
            "keys_declared": blocks[name],
            "keys_live_on_this_corpus": live,
            "keys_dead_on_this_corpus": [key for key in blocks[name]
                                         if not by_dimension[key]["declared_rule"]["pairs_compared"]],
            "readings": readings,
        }
    verdicts = {}
    for reading in READINGS:
        for quantity, label in quantities:
            measured = {name: summary[name]["readings"][reading][quantity] for name in ordering
                        if summary[name]["readings"][reading][quantity] is not None}
            adjacent = cm.adjacency_verdicts(measured, config)
            spread = round(max(measured.values()) - min(measured.values()), 6) if len(measured) > 1 else None
            verdicts[f"{reading}_{label}"] = {
                "reading": reading,
                "quantity": label,
                "statistic": rows[0][reading]["statistic"] if rows else None,
                "block_means": measured,
                "ordering_observed": sorted(measured, key=lambda name: -measured[name]),
                "spread_across_blocks": spread,
                "adjacent_predictions": adjacent,
                "keys_carried_by_a_single_live_dimension": [name for name in measured
                                                            if len(summary[name]["keys_live_on_this_corpus"]) == 1],
                "why_this_can_be_wrong": QUANTITY_NOTE[label],
                "what_this_reading_is": READING_NOTE[reading],
            }
    return {"blocks": summary, "verdicts": verdicts, "minimum_block_spread_declared": minimum_spread}


def work_state_for(work, config):
    """The pair-level state dict `similarity_between` expects, with unpopulated keys left undecidable.

    Every key is passed as the set of values the detector actually produced, including the keys the frame
    declares single-valued. `similarity_between`'s single-valued branch compares values for equality, so a work
    carrying two of them is compared as a set: that is the most generous reading the declared rule can be given
    on data that do not obey it, and the count of cells where the rule had no defined answer is published in the
    dimension table rather than hidden by picking one of the two.
    """
    state = {}
    for key in cm.dimension_keys(config):
        values = sorted(work.get(key, []))
        state[key] = values if values else "undecidable"
    return state


def scored_pairs(per_work=None, config=None):
    """Every pair of works the comparison layer agrees to score, with the states it scored them from.

    One function owns the conditioning so that the scan, the pair ranking and the M4 gate cannot each implement
    `minimum_comparable_keys` slightly differently and then compare their numbers.
    """
    config = config or json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if per_work is None:
        per_work, _, _ = load_work_states()
    for left, right in combinations(sorted(per_work), 2):
        state_a = work_state_for(per_work[left], config)
        state_b = work_state_for(per_work[right], config)
        scored = cm.similarity_between(state_a, state_b, config)
        if scored["scorable"]:
            yield left, right, state_a, state_b, scored


def corpus_observations(config=None):
    """The pair set the M4 block-profile gate runs on, built from the corpus instead of from a fixture.

    Each item is the shape `observed_block_profile` reads. `scorable_graph` measures these same pairs for the
    scan, and this exists so a test can check that the gate and the scan read one population rather than two
    that happen to be the same size today.
    """
    return [{"pair_id": f"{left}|{right}", "similarity_class": scored["similarity_class"],
             "block_profile": scored["block_profile"]}
            for left, right, _, _, scored in scored_pairs(config=config)]


def pair_anomalies(per_work, rows, config, cardinality, dependent, top=15):
    """Rank work pairs by agreement above chance, and find the descent-shaped ones.

    The pair-level excess is measured under the statistic the frame declares for each key and against the chance
    line drawn on the graph these pairs belong to, so it is still a per-pair number compared to a per-dimension
    average: enough to rank pairs, not enough to certify one. `rows` here is the scored-graph table, because a
    pair only appears in this list if the comparison layer was willing to score it.
    """
    chance = {row["dimension"]: row["declared_rule"]["chance_similarity_from_own_marginals"] for row in rows}
    blocks = config["dimension_similarity_rules"]["dimension_blocks"]
    pair_rows = []
    for left, right, state_a, state_b, scored in scored_pairs(per_work, config):
        excess_per_key = {}
        jaccard_per_key = {}
        for key in scored["comparable_keys"]:
            values = (set(state_a[key]), set(state_b[key]))
            jaccard_per_key[key] = score(*values, "jaccard")
            declared = score(*values, statistic_for_key(cardinality, key))
            if declared is None or chance[key] is None:
                continue
            excess_per_key[key] = declared - chance[key]
        if not excess_per_key:
            continue
        excess = sum(excess_per_key.values()) / len(excess_per_key)
        block_excess = {}
        for name, keys in blocks.items():
            values = [excess_per_key[key] for key in keys if key in excess_per_key]
            block_excess[name] = round(sum(values) / len(values), 6) if values else None
        measured = [name for name in ("functional_or_pressure_prone", "arbitrary_or_expressive")
                    if block_excess[name] is not None]
        inverted = (len(measured) == 2
                    and block_excess["arbitrary_or_expressive"] > block_excess["functional_or_pressure_prone"])
        pair_rows.append({
            "work_a": left,
            "work_b": right,
            "comparable_keys": len(scored["comparable_keys"]),
            "observed_similarity_under_the_declared_rule": scored["similarity"],
            "observed_similarity_as_value_sets": round(sum(jaccard_per_key.values()) / len(jaccard_per_key), 6),
            "similarity_class": scored["similarity_class"],
            "excess_over_chance": round(excess, 6),
            "block_excess": block_excess,
            "arbitrary_block_outagrees_functional_block": inverted,
            "either_work_has_dependent_reprints": left in dependent or right in dependent,
        })
    pair_rows.sort(key=lambda row: -row["excess_over_chance"])
    inverted = [row for row in pair_rows if row["arbitrary_block_outagrees_functional_block"]]
    inverted.sort(key=lambda row: -(row["block_excess"]["arbitrary_or_expressive"]
                                    - row["block_excess"]["functional_or_pressure_prone"]))
    return {"top_pairs_by_excess_agreement": pair_rows[:top],
            "pairs_counted": len(pair_rows),
            "pairs_where_the_arbitrary_block_outagrees_the_functional_block": inverted[:top],
            "count_of_such_pairs": len(inverted),
            "reading": ("a high pair is a candidate for a shared transmission route, not evidence of one; and the "
                        "inverted list is the shape M4 says should be rare, so it is the list a reviewer should "
                        "read first")}


def scan(config=None):
    config = config or json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rng = random.Random(CHANCE_SEED)
    keys = cm.dimension_keys(config)
    cardinality = cm.cardinality_map(config)
    per_work, _, dependent = load_work_states()
    rows = dimension_table(per_work, keys, cardinality, rng)
    strict, _, _ = load_work_states(frame="affirmative_doctrine_count")
    strict_rows = dimension_table(strict, keys, cardinality, random.Random(CHANCE_SEED))
    graph_observations, graph_population, scorable_pairs = scorable_graph(per_work, config, cardinality)
    graph_rows = dimension_rows(graph_population, keys, cardinality, random.Random(CHANCE_SEED),
                                graph_observations,
                                "the pairs the comparison layer is willing to score, and the works they cover")
    movement = [{"dimension": graph["dimension"],
                 "reading": reading,
                 "statistic": carrier[reading]["statistic"],
                 "carrier_graph_mean": carrier[reading]["observed_mean_similarity"],
                 "scored_graph_mean": graph[reading]["observed_mean_similarity"],
                 "carrier_chance": carrier[reading]["chance_similarity_from_own_marginals"],
                 "scored_chance": graph[reading]["chance_similarity_from_own_marginals"],
                 "shift": (round(graph[reading]["observed_mean_similarity"]
                                 - carrier[reading]["observed_mean_similarity"], 6)
                           if graph[reading]["observed_mean_similarity"] is not None
                           and carrier[reading]["observed_mean_similarity"] is not None else None)}
                for carrier, graph in zip(rows, graph_rows) for reading in READINGS]
    furthest = max((item for item in movement if item["shift"] is not None), key=lambda item: abs(item["shift"]))
    carrier_order = block_table(rows, config)
    scored_order = block_table(graph_rows, config)
    digest = hashlib.sha256(WORK_STATES.read_bytes()).hexdigest()
    return {
        "produced_by": PRODUCED_BY,
        "inputs": {"work_states": "results/ontology_work_states.csv", "sha256": digest,
                   "config": "config/model_comparison_v3.json"},
        "null_model": {"name": "per-dimension configuration model",
                       "draws": CHANCE_REPETITIONS, "seed": CHANCE_SEED, "band": CHANCE_BAND,
                       "preserves": "each work's own number of values on that dimension, and the dimension's "
                                    "per-value prevalence",
                       "does_not_preserve": "correlations between values inside a work, so the excess here is an "
                                            "upper bound on any structure attributed to a dimension whose "
                                            "detector fires on co-occurring strings",
                       "why_not_a_permutation": "the mean over a complete graph is invariant to permuting which "
                                                "work owns which set, so a label-shuffled control would return "
                                                "the observed number and call it a null"},
        "works_scanned": len(per_work),
        "pairs_of_works_possible": len(per_work) * (len(per_work) - 1) // 2,
        "frame": "candidate_count > 0",
        "dimensions": rows,
        "dead_dimensions": [row["dimension"] for row in rows if row["status"].startswith("dead")],
        "indistinguishable_from_chance": {reading: [row["dimension"] for row in rows
                                                    if row[reading]["excess_within_declared_chance_band"]]
                                          for reading in READINGS},
        "blocks": carrier_order,
        "pair_graph": {
            "conditioning": ("the pairs compare_models.similarity_between scores, at least "
                             f"{config['dimension_similarity_rules']['minimum_comparable_keys']} comparable keys"),
            "pairs_scorable": scorable_pairs,
            "works_covered": len(graph_population),
            "dimensions": graph_rows,
            "chance_similarity_per_dimension": {row["dimension"]: row["declared_rule"][
                "chance_similarity_from_own_marginals"] for row in graph_rows
                if row["declared_rule"]["chance_similarity_from_own_marginals"] is not None},
            "blocks": scored_order,
            "why_a_second_population": (
                "the model comparison refuses a pair below the declared minimum comparable keys, so the means it "
                f"pools are measured over {scorable_pairs} of "
                f"{len(per_work) * (len(per_work) - 1) // 2} pairs covering "
                f"{len(graph_population)} of {len(per_work)} works, and a work rich enough to be scored is not a "
                "random work. On this corpus the observed mean of "
                f"`{furthest['dimension']}`, read as `{furthest['reading']}`, moves {furthest['shift']} between the "
                f"carrier graph and the scored graph — further than the {CHANCE_BAND} this scan uses to call an "
                "excess indistinguishable from chance. So a chance line has to name the graph it was drawn on "
                "before anyone subtracts it, and the chance numbers below come from the scored graph alone. This is "
                "the population the M4 block-profile test reads."),
            "movement_between_the_two_graphs": movement,
            "adjacency_verdicts_that_change_with_the_graph": {
                label: {"carrier_graph": carrier_order["verdicts"][label]["adjacent_predictions"],
                        "scored_graph": scored_order["verdicts"][label]["adjacent_predictions"]}
                for label in carrier_order["verdicts"]
                if [item["verdict"] for item in carrier_order["verdicts"][label]["adjacent_predictions"]]
                != [item["verdict"] for item in scored_order["verdicts"][label]["adjacent_predictions"]]},
            "indistinguishable_from_chance": {reading: [row["dimension"] for row in graph_rows
                                                        if row[reading]["excess_within_declared_chance_band"]]
                                              for reading in READINGS},
        },
        "sensitivity_under_the_endorsement_frame": {
            "frame": "affirmative_doctrine_count > 0",
            "dimensions": strict_rows,
            "blocks": block_table(strict_rows, config),
            "why": ("a block ordering that flips between the candidate frame and the endorsement frame is not a "
                    "fact about the traditions; the two frames differ only in how loudly the detector fired"),
        },
        "pairs": pair_anomalies(per_work, graph_rows, config, cardinality, dependent),
        "what_this_is_not": "no dates, so no transmission claim; detector output over English translations, not "
                            "human coding; works are not independent, so dependence is flagged per pair rather "
                            "than filtered away; the chance line comes from the corpus's own marginals",
    }


def print_block_ordering(prefix, blocks):
    for label, verdict in blocks["verdicts"].items():
        print(f"{prefix}{label}: {verdict['ordering_observed']}")
        for item in verdict["adjacent_predictions"]:
            print(f"   {item['stronger']} > {item['weaker']}: {item.get('observed_difference')} -> {item['verdict']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"write {OUT.relative_to(ROOT)}")
    arguments = parser.parse_args(argv)
    report = scan()
    print(f"{report['works_scanned']} works, {report['pairs_of_works_possible']} pairs possible, "
          f"{report['pairs']['pairs_counted']} scorable and chance-rated")
    print(f"dead dimensions: {', '.join(report['dead_dimensions']) or 'none'}")
    for row in report["dimensions"]:
        if row["status"].startswith("dead"):
            continue
        print(f"  {row['dimension']:32s} obs={row['declared_rule']['observed_mean_similarity']!s:>9} "
              f"chance={row['declared_rule']['chance_similarity_from_own_marginals']!s:>9} "
              f"excess={row['declared_rule']['excess_over_chance']!s:>9} "
              f"sets={row['value_sets']['excess_over_chance']!s:>9} "
              f"works={row['works_with_an_attested_value']:2d} distinct={row['distinct_values_attested']:2d} "
              f"mean_values_per_work={row['mean_values_per_work']}")
    dead = report["dead_dimensions"]
    if dead:
        print(f"declared and never fired: {', '.join(dead)}")
    print_block_ordering("block ordering, carrier graph ", report["blocks"])
    graph = report["pair_graph"]
    print(f"pair graph the comparison layer scores: {graph['pairs_scorable']} of "
          f"{report['pairs_of_works_possible']} pairs, {graph['works_covered']} of {report['works_scanned']} works")
    for row in graph["dimensions"]:
        if row["declared_rule"]["observed_mean_similarity"] is None:
            continue
        print(f"  {row['dimension']:32s} obs={row['declared_rule']['observed_mean_similarity']!s:>9} "
              f"chance={row['declared_rule']['chance_similarity_from_own_marginals']!s:>9} "
              f"excess={row['declared_rule']['excess_over_chance']!s:>9} "
              f"sets={row['value_sets']['excess_over_chance']!s:>9}")
    for reading, names in graph["indistinguishable_from_chance"].items():
        print(f"indistinguishable from chance on that graph, {reading}: {', '.join(names) or 'none'}")
    print_block_ordering("block ordering, scored graph ", graph["blocks"])
    pairs = report["pairs"]
    print(f"pairs where the arbitrary block outagrees the functional block: {pairs['count_of_such_pairs']}"
          f" of {pairs['pairs_counted']}")
    for row in pairs["top_pairs_by_excess_agreement"][:8]:
        print(f"   {row['work_a']:34s} {row['work_b']:34s} excess={row['excess_over_chance']:+.4f} "
              f"keys={row['comparable_keys']:2d} dependent={row['either_work_has_dependent_reprints']}")
    if arguments.write:
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
