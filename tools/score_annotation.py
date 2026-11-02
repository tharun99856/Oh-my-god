#!/usr/bin/env python3
"""Score two completed coding packets: agreement, machine precision, and detector recall.

Usage:
    python tools/score_annotation.py --coder-a FILE.csv --coder-b FILE.csv

Reads the answer key written by prepare_annotation_packet.py, plus the corpus-wide
detector output in results/ontology_attestations.jsonl.gz (recall's numerator), and
produces results/annotation_reliability.json. It refuses to run on one coder: a single
coding is the thing this project has been short of, and a script that lets it be
reported as reliability is part of the problem.

v3 scores the twelve dimensions with the cardinality the ontology actually declares,
imported from the packet tool rather than restated here, so the sheet a coder fills
in and the sheet this script reads cannot drift apart. Set-valued dimensions
(D1, D3, D4, D5, D6) are scored by Jaccard, not exact match: forcing one choice
there and scoring the forced choice as agreement would invent concordance.

Consensus is the intersection of the two coders' value sets. A value one coder saw
and the other did not is reported as `seen_by_one_coder_only`, not folded into the
machine's precision figure.

v3.1 separates the two things the packet can measure, because they live in different
rows and the earlier version confused them:

  precision comes from `machine_candidate` rows. Those are propositions the detector
      already flagged, sampled within a value stratum, so a per-value hit rate is an
      honest conditional.

  recall comes from the `no_candidate_*` probe rows -- propositions the detector
      flagged as nothing. A miss cannot be found among hits, so recall is estimated
      the survey way: each probe row carries the exact inclusion probability of its
      stratum, and a value two coders independently read into a missed proposition
      contributes its weight (1/pi, Horvitz-Thompson) to that value's estimated miss
      count. The estimate is then detected / (detected + weighted misses), with
      `detected` counted over the whole corpus rather than over the packet.

The two row groups are never pooled into one machine-vs-human figure, and the probe
rows carry no machine value to be wrong about. A key file whose probe rows have no
weight is refused: a recall number computed without weights is a count of the
sample, not of the corpus.

v3.2 adds the construct check the ontology documentation promised. D7d
`epistemic_commitment` and the coder question `doctrine_endorsed_by_text` offer the
same six labels, because the tool that writes the record field writes it as D7d's own
value. That alias is invisible in machine output -- an association between a field and
a copy of itself is 1.0 and says nothing -- so what is compared is one coder's two
answers, proposition by proposition. Until a coder fills both columns the block reports
`pending_human_coding` and no number at all.

v3.3 fixes three ways this scorer could report a recall figure too high, found by
reading its own arithmetic against the shipped records rather than by a coder:

  a detection was any record. 47,641 records include 379 whose `assertion_state` is
      `not_yet_instrumented` -- a declared absence of a detector, over five values -- and
      140 whose state is `candidate_requires_human_disambiguation`, a value the detector
      refused to choose. Both counted as detections, so `from_lost_past` would have had a
      numerator of 202 and a nonzero recall for an instrument that does not exist. Only
      `candidate` is a detection now; the two states are counted and published as
      exclusions, and the packet builder no longer treats their propositions as hits.

  recall's numerator was uncorrected for precision. Every machine record was assumed a
      true positive, so the false-positive share measured on the candidate rows never
      reached the recall denominator. The headline figure now multiplies detections by
      that precision; the uncorrected figure is still published, labelled as an upper
      bound that assumes the detector never errs.

  a stratum's weight coverage was asserted, not measured. The artifact used to print
      `weight_sum_equals_population_only_if_every_drawn_row_is_coded: True` beside its own
      `unit_answer_missing` counter. Coverage is now computed from the rows the key drew
      against the rows both coders answered, and missed counts are divided by it, so
      uncoded draws widen the estimate in the conservative direction instead of
      quietly shrinking it.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_annotation_packet import (  # noqa: E402
    ANSWER_VOCABULARIES, DETECTION_STATE, PROBE_ROLE_PREFIX, QUESTION_COLUMNS, REFERENT_COLUMN,
    UNIT_COLUMN, coding_columns, column_cardinalities)

KEY = ROOT / "results/annotation_packet_key.jsonl"
ATTESTATIONS = ROOT / "results/ontology_attestations.jsonl.gz"
OUT = ROOT / "results/annotation_reliability.json"

# A probe row is a miss only when both readers independently decline the null. Any
# looser rule lets one coder's over-reading become a corpus-wide miss.
NULL_UNIT_ANSWER = "not_a_divine_proposition"
UNDECIDABLE = "undecidable"

# The construct check's two columns. D7d is a dimension column, `doctrine_endorsed_by_text` a
# coder question, and their answer vocabularies are the same six labels by design.
D7D_DIMENSION = "D7d_epistemic_commitment"
ENDORSEMENT_COLUMN = "doctrine_endorsed_by_text"


def display_path(path):
    """Repo-relative when it can be, absolute when it cannot: a tmp path in a test must not crash the run."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def binomial_upper_bound_on_p(successes, trials, alpha=0.05):
    """One-sided exact Clopper-Pearson upper bound on a stratum's miss share.

    Used because a stratum that finds no miss has to report a bound rather than a recall of
    1.0. The bound is the p at which P(X <= successes) = alpha: high enough that the small
    count actually observed would be a 5% event. For zero successes that equation is
    (1-p)^n = alpha, whose closed form is 1 - alpha^(1/n); for a positive count it is solved
    by bisection on the binomial CDF, evaluated by downward recurrence so a 900-row stratum
    does not overflow.
    """
    if not trials:
        return None
    if successes == 0:
        return 1 - alpha ** (1 / trials)

    def cdf(p):
        if p >= 1.0:
            return 1.0 if successes >= trials else 0.0
        term = math.exp(math.log(math.comb(trials, successes)) + successes * math.log(p)
                        + (trials - successes) * math.log1p(-p))
        total, j = term, successes
        while j > 0:
            term *= j / (trials - j + 1) * (1 - p) / p
            total += term
            j -= 1
            if term < 1e-15 * total:
                break
        return min(total, 1.0)

    lo, hi = successes / trials, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def read_packet(path):
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["token"]] = row
    return rows


def key_index(path):
    index = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for line in handle:
            record = json.loads(line)
            index[record["token"]] = record
    return index


def is_probe(record):
    return str(record.get("sample_role") or "").startswith(PROBE_ROLE_PREFIX)


def require_probe_weights(key):
    """Refuse to estimate recall from rows that cannot represent the population they were drawn from.

    Returns `(probe rows, per-stratum register)`. The register carries the population, the weight and the
    number of drawn rows for each stratum, taken from the key rather than guessed at read time: the drawn
    count is what coverage is measured against, and a stratum whose rows disagree about its own population
    cannot be weighted at all.
    """
    probe = [record for record in key.values() if is_probe(record)]
    unweighted = [record["token"] for record in probe
                  if not isinstance(record.get("sampling_weight"), (int, float))
                  or record["sampling_weight"] <= 0]
    if unweighted:
        raise SystemExit(
            f"{len(unweighted)} of {len(probe)} no-candidate probe rows in the key carry no sampling weight "
            "(e.g. " + ", ".join(unweighted[:3]) + "). Weighted Horvitz-Thompson estimation is the only "
            "legitimate way to turn a probe sample into a corpus miss count; refusing to report an unweighted "
            "count as recall. Rebuild the packet with tools/prepare_annotation_packet.py.")
    if not probe:
        raise SystemExit(
            "the key has no no_candidate probe rows, so this packet cannot measure recall: it samples only "
            "propositions the machine already flagged, and a sample of hits contains no misses. Rebuild it "
            "with tools/prepare_annotation_packet.py (v3 packet or later).")
    register = {}
    for role in sorted({str(record["sample_role"]) for record in probe}):
        rows = [record for record in probe if record["sample_role"] == role]
        populations = {record.get("stratum_population") for record in rows}
        weights = {round(float(record["sampling_weight"]), 6) for record in rows}
        if populations == {None} or len(populations) > 1 or len(weights) > 1:
            raise SystemExit(
                f"probe stratum `{role}` spans {len(populations)} distinct stratum_population values and "
                f"{len(weights)} distinct weights across {len(rows)} rows. One exact inclusion probability per "
                "stratum is the only thing that makes a Horvitz-Thompson total unbiased for the population it "
                "was drawn from, so a stratum that reports two populations cannot be weighted. Rebuild the "
                "packet with tools/prepare_annotation_packet.py.")
        register[role] = {"stratum_population": next(iter(populations)),
                          "sampling_weight": next(iter(weights)), "rows_drawn": len(rows)}
    return probe, register


def detected_by_value(path):
    """Corpus-wide count of distinct propositions carrying a *detection* for each value.

    Recall's numerator has to be the detector's whole output, not the packet's slice of it:
    `detected / (detected + estimated_misses)` mixes a sample count with a population estimate
    if `detected` is read off the sampled rows.

    `assertion_state: candidate` is the only state that detects. A `not_yet_instrumented` record
    announces that no detector for that value exists, and a `candidate_requires_human_disambiguation`
    record names a value the detector declined to choose; counting either as a detection gave five
    values a nonzero numerator and a published recall for an instrument that does not exist. The two
    states are tallied and returned so the artifact can show what it excluded.
    """
    seen = set()
    propositions = set()
    excluded = Counter()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            state = record.get("assertion_state") or DETECTION_STATE
            proposition = (record["work_id"], record["passage_id"], record["proposition_char_start"])
            if state != DETECTION_STATE:
                excluded[state] += 1
                continue
            seen.add((f"{record['dimension']}={record['value']}", proposition))
            propositions.add(proposition)
    return dict(Counter(label for label, _ in seen)), len(propositions), dict(excluded)


def proposition_level_recall(detected, confirmation_share, misses, misses_conservative, misses_bound):
    """The corpus-wide recall figures, corrected for what the candidate rows say about precision.

    `detected` counts every proposition the detector asserted something about, and two readers keep only a
    share of those, so a recall numerator is `detected * share`: the rest are false positives, and a false
    positive cannot be a true positive. Where no candidate row was coded the share is unknown, the figure
    stays uncorrected, and the key names that rather than hiding it -- an uncorrected recall is an upper
    bound, not a result. Misses enter twice: the realised weighted count, widened where draws went uncoded,
    and each stratum's one-sided 95% bound summed, which is the number to publish.
    """
    effective = detected * confirmation_share if confirmation_share is not None else detected
    total = effective + misses_conservative
    uncorrected_total = detected + misses_conservative
    return {
        "detected_propositions_corpus_wide": detected,
        "detection_confirmation_share_from_candidate_rows": confirmation_share,
        "true_positive_propositions_implied": round(effective, 2),
        "estimated_missed_divine_propositions_weighted": round(misses, 2),
        "estimated_missed_divine_propositions_coverage_adjusted": round(misses_conservative, 2),
        "upper_bound_on_missed_divine_propositions_95pct": round(misses_bound, 2),
        "recall_of_divine_propositions_point": round(effective / total, 4) if total else None,
        "recall_of_divine_propositions_upper_bound_ignoring_precision": (
            round(detected / uncorrected_total, 4) if uncorrected_total and confirmation_share is not None
            else None),
        "recall_of_divine_propositions_lower_bound_95pct": (
            round(effective / (effective + misses_bound), 4) if (effective + misses_bound) else None),
        "reads_as": "of the propositions in the corpus that a divine claim is about, this share is the "
                    "detector's. The numerator is the corpus-wide detection count discounted by the share "
                    "two readers kept among the flagged propositions; the denominator adds the weighted "
                    "misses the probe found, widened by the weight the coders could not get to. The lower "
                    "bound replaces those misses with each stratum's one-sided 95% upper bound, summed. "
                    "Publish the lower bound.",
    }


def cohens_kappa(pairs):
    """Pairs of (a, b) category assignments, observed vs chance agreement."""
    n = len(pairs)
    if not n:
        return None, 0
    agree = sum(1 for a, b in pairs if a == b) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum((first[category] / n) * (second[category] / n) for category in set(first) | set(second))
    return ((agree - chance) / (1 - chance) if chance < 1 else None), n


def jaccard(left, right):
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def construct_view(pairs):
    """One coder's D7d answers against that same coder's endorsement answers, row by row.

    The machine cannot produce this figure: `divinity_ontology.py` writes the record field as
    `"doctrinal_endorsement": d7d`, so a machine-vs-machine association is 1.0 by construction.
    Only two human codings give it content, so an empty `pairs` reports no number at all.
    """
    n = len(pairs)
    disagreements = [(commitment, endorsement) for commitment, endorsement in pairs
                     if commitment != endorsement]
    kappa, _ = cohens_kappa(pairs)
    return {
        "rows_answering_both_questions": n,
        "exact_agreement": round((n - len(disagreements)) / n, 4) if n else None,
        "cohen_kappa": round(kappa, 4) if kappa is not None else None,
        "kappa_is_none_when_only_one_category_occurs": kappa is None and n > 0,
        "marginal_distribution_D7d": dict(sorted(Counter(c for c, _ in pairs).items())),
        "marginal_distribution_" + ENDORSEMENT_COLUMN: dict(sorted(Counter(e for _, e in pairs).items())),
        "disagreement_cells": dict(sorted(Counter(f"{c} -> {e}" for c, e in disagreements).items())),
    }


def parse_cell(row, column, cardinality):
    raw = (row.get(column) or "").strip()
    if not raw:
        return frozenset()
    if cardinality == "set":
        return frozenset(v.strip() for v in raw.split(";") if v.strip())
    return frozenset([raw])


def both_readers_decline_the_null(row_a, row_b):
    """True when two readers, independently, refuse to code a row as mundane.

    One coder's over-reading must not become a corpus-wide miss, so a row counts only when
    both filled the unit column and neither chose `not_a_divine_proposition` or `undecidable`.
    `too_large_should_split` and `too_small_should_join` do count: each says a divine claim
    is on the page and only the segmentation is wrong, which is a detector miss either way.

    The same rule decides both directions of error: on a probe row it is a miss the detector
    walked past, and on a candidate row it is a detection the readers confirm rather than refuse.
    """
    units = {(row_a.get(UNIT_COLUMN) or "").strip(), (row_b.get(UNIT_COLUMN) or "").strip()}
    return bool(all(units)) and not (units & {NULL_UNIT_ANSWER, UNDECIDABLE})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coder-a", required=True, type=Path)
    parser.add_argument("--coder-b", required=True, type=Path)
    parser.add_argument("--key", type=Path, default=KEY,
                        help="answer key; a synthetic key is how the weighted recall estimator gets tested")
    parser.add_argument("--attestations", type=Path, default=ATTESTATIONS,
                        help="the corpus-wide detector output that supplies recall's numerator")
    parser.add_argument("--out", type=Path, default=OUT,
                        help="where to write; a developer run against synthetic sheets must not "
                             "overwrite the canonical reliability file with figures no human produced")
    args = parser.parse_args()
    if args.coder_a.resolve() == args.coder_b.resolve():
        raise SystemExit("one sheet supplied twice is not two independent codings")
    a, b, key = read_packet(args.coder_a), read_packet(args.coder_b), key_index(args.key)
    columns = coding_columns()
    cardinality = column_cardinalities()
    overlap = sorted(set(a) & set(b))
    if not overlap:
        raise SystemExit("the two packets share no tokens; nothing to compare")
    if len(overlap) < 2:
        raise SystemExit("one shared row is not a reliability sample; a second coder has to code the packet")
    probe_records, strata_register = require_probe_weights(key)
    detected_counts, detected_propositions, excluded_records = detected_by_value(args.attestations)

    exact_pairs = defaultdict(list)
    exact_pairs_by_group = defaultdict(list)
    jaccard_scores = defaultdict(list)
    jaccard_by_group = defaultdict(list)
    consensus = defaultdict(dict)
    partial_union = defaultdict(dict)
    one_coder_only = defaultdict(Counter)
    per_value = defaultdict(lambda: {"machine_proposed": 0, "human_confirmed": 0, "both": 0})
    undecidable_rate = {}
    referent_given = Counter()
    machine_strict_single = defaultdict(lambda: {"machine_offered_one_value": 0, "consensus_matched": 0})
    rows_by_group = defaultdict(Counter)
    probe_rows_in = defaultdict(lambda: {"rows_coded_by_both": 0, "weight_sum": 0.0,
                                         "declined_null": 0, "declined_null_weight": 0.0,
                                         "unit_answer_missing": 0, "coders_disagree_on_null": 0})
    # Recall's numerator has to be true positives, not machine firings. The candidate rows are the only
    # place the two questions can be compared, so the share of flagged propositions that both readers keep
    # is measured here and applied to the corpus-wide detection count below.
    candidate_rows_answered_by_both = 0
    candidate_rows_confirmed_divine = 0
    weighted_value_misses = defaultdict(lambda: {"stratum_weight": defaultdict(float),
                                                 "consensus_rows": 0})
    construct_pairs = defaultdict(list)

    for token in overlap:
        row_a, row_b = a[token], b[token]
        record = key[token]
        probe = is_probe(record)
        group = "probe" if probe else "machine_candidate"
        weight = float(record.get("sampling_weight") or 0.0)
        role = str(record.get("sample_role") or "")
        rows_by_group[group]["rows_compared"] += 1
        machine_sets = record["machine_values_by_dimension"]
        declines_null = both_readers_decline_the_null(row_a, row_b)
        if (row_a.get(UNIT_COLUMN) or "").strip() and (row_b.get(UNIT_COLUMN) or "").strip():
            if not probe:
                candidate_rows_answered_by_both += 1
                if declines_null:
                    candidate_rows_confirmed_divine += 1
        if probe:
            tally = probe_rows_in[role]
            units = {(row_a.get(UNIT_COLUMN) or "").strip(), (row_b.get(UNIT_COLUMN) or "").strip()}
            if not all(units):
                # A row a reader left blank is not a row that was coded and found empty: it is a draw that
                # was never realised, and it belongs in the uncovered remainder. Counting it as coded would
                # push coverage to 1.0 on a half-coded stratum and shrink the miss estimate accordingly.
                tally["unit_answer_missing"] += 1
            else:
                tally["rows_coded_by_both"] += 1
                tally["weight_sum"] += weight
                if declines_null:
                    tally["declined_null"] += 1
                    tally["declined_null_weight"] += weight
                elif units & {NULL_UNIT_ANSWER}:
                    tally["coders_disagree_on_null"] += (
                        1 if (row_a.get(UNIT_COLUMN) or "").strip()
                        != (row_b.get(UNIT_COLUMN) or "").strip() else 0)
        for dimension, column in columns.items():
            left = parse_cell(row_a, column, cardinality[dimension])
            right = parse_cell(row_b, column, cardinality[dimension])
            if not left and not right:
                continue
            rows_by_group[group][dimension] += 1
            if cardinality[dimension] == "single":
                if left and right:
                    exact_pairs[dimension].append(((next(iter(left))), next(iter(right))))
                    exact_pairs_by_group[(group, dimension)].append((next(iter(left)), next(iter(right))))
            jaccard_scores[dimension].append(jaccard(left, right))
            jaccard_by_group[(group, dimension)].append(jaccard(left, right))
            agreed = left & right
            consensus[dimension][token] = agreed
            partial_union[dimension][token] = left | right
            for value in (left | right) - agreed:
                one_coder_only[dimension][value] += 1
            if probe and declines_null:
                # A probe row has no machine value to be right or wrong about; its consensus
                # values are evidence about what the detector missed, weighted by 1/pi -- but only
                # on a row both readers still treat as a divine proposition, or a value named on a
                # row one of them called mundane would inflate that value's miss count.
                for value in agreed - {UNDECIDABLE}:
                    bucket = weighted_value_misses[f"{dimension}={value}"]
                    bucket["stratum_weight"][role] += weight
                    bucket["consensus_rows"] += 1
                continue
            machine = set(machine_sets.get(dimension, []))
            for value in machine:
                per_value[f"{dimension}={value}"]["machine_proposed"] += 1
            for value in agreed - {UNDECIDABLE}:
                per_value[f"{dimension}={value}"]["human_confirmed"] += 1
                if value in machine:
                    per_value[f"{dimension}={value}"]["both"] += 1
            if cardinality[dimension] == "single" and len(machine) == 1 and len(agreed) == 1:
                strict = machine_strict_single[dimension]
                strict["machine_offered_one_value"] += 1
                if next(iter(agreed)) == next(iter(machine)):
                    strict["consensus_matched"] += 1
        for column in (UNIT_COLUMN, *QUESTION_COLUMNS):
            left, right = (row_a.get(column) or "").strip(), (row_b.get(column) or "").strip()
            if left and right:
                exact_pairs[column].append((left, right))
        d7d_column = columns.get(D7D_DIMENSION)
        if d7d_column:
            # One coder's two answers to the same question, not two coders' answers to one
            # question: this is the only association the shipped packet can measure at all.
            for coder, row in (("a", row_a), ("b", row_b)):
                commitment = (row.get(d7d_column) or "").strip()
                endorsement = (row.get(ENDORSEMENT_COLUMN) or "").strip()
                if commitment and endorsement:
                    construct_pairs[(coder, group)].append((commitment, endorsement))
        for coder, row in (("a", row_a), ("b", row_b)):
            tally = undecidable_rate.setdefault(coder, Counter())
            tally["propositions_coded"] += 1
            if (row.get(UNIT_COLUMN) or "").strip():
                # What this coder actually answered, in this row group. The packet-wide count would be
                # the same for both coders whatever either of them did, which is what the earlier line
                # reported.
                tally[f"{group}_rows_answered"] += 1
            selections = []
            for dimension, column in columns.items():
                selections.extend(parse_cell(row, column, cardinality[dimension]))
            tally["undecidable_choices"] += sum(1 for s in selections if s == UNDECIDABLE)
            tally["total_choices"] += len(selections)
            tally["referent_terms_given"] += 1 if (row.get(REFERENT_COLUMN) or "").strip() else 0
        referent_given["both_coders_named_a_referent"] += (
            1 if (row_a.get(REFERENT_COLUMN) or "").strip() and (row_b.get(REFERENT_COLUMN) or "").strip() else 0)
        referent_given["rows_by_sample_role." + role] += 1

    strata = {}
    for role, tally in sorted(probe_rows_in.items()):
        register = strata_register.get(role) or {}
        n_population = int(register.get("stratum_population") or 0)
        drawn = int(register.get("rows_drawn") or 0)
        drawn_weight = drawn * float(register.get("sampling_weight") or 0.0)
        coded = tally["rows_coded_by_both"]
        coverage = (tally["weight_sum"] / drawn_weight) if drawn_weight else None
        p_upper = binomial_upper_bound_on_p(tally["declined_null"], coded)
        # Uncoded draws are not evidence of absence: a stratum whose rows went partly unanswered is
        # holding back misses it never saw, so the miss count is divided by the realised weight share.
        # That widens the estimate, which is the only direction a recall floor is allowed to fail in.
        adjusted = (tally["declined_null_weight"] / coverage
                    if coverage else tally["declined_null_weight"])
        strata[role] = {
            "stratum_population": n_population or None,
            "rows_drawn_in_key": drawn,
            "rows_coded_by_both": coded,
            "sampling_weight": round(tally["weight_sum"] / coded, 4) if coded else None,
            "weight_sum_of_coded_rows": round(tally["weight_sum"], 2),
            "weight_sum_of_the_drawn_stratum": round(drawn_weight, 2) or None,
            "coverage_of_drawn_weight": round(coverage, 6) if coverage is not None else None,
            "coded_weight_as_share_of_stratum_population": (
                round(tally["weight_sum"] / n_population, 6) if n_population else None),
            "declined_null": tally["declined_null"],
            "estimated_missed_divine_propositions_weighted": round(tally["declined_null_weight"], 2),
            "estimated_missed_divine_propositions_coverage_adjusted": round(adjusted, 2),
            "estimated_miss_share_of_stratum": (round(tally["declined_null_weight"] / tally["weight_sum"], 6)
                                                if tally["weight_sum"] else None),
            "coders_disagree_on_null": tally["coders_disagree_on_null"],
            "unit_answer_missing": tally["unit_answer_missing"],
            "one_sided_95pct_upper_bound_on_miss_share": round(p_upper, 6) if p_upper is not None else None,
            "one_sided_95pct_upper_bound_on_missed_propositions": (
                round(n_population * p_upper, 2) if p_upper is not None and n_population else None),
        }
    misses_found = sum(t["estimated_missed_divine_propositions_weighted"] for t in strata.values())
    misses_conservative = sum(t["estimated_missed_divine_propositions_coverage_adjusted"] or 0
                              for t in strata.values())
    # Summing two one-sided 95% bounds is conservative for the pooled count; it over-covers
    # rather than under-covers, which is the direction a recall floor has to fail in.
    misses_bound = sum(t["one_sided_95pct_upper_bound_on_missed_propositions"] or 0 for t in strata.values())
    candidate_confirmation_share = (round(candidate_rows_confirmed_divine / candidate_rows_answered_by_both, 6)
                                    if candidate_rows_answered_by_both else None)

    by_value = {}
    for label in sorted(set(detected_counts) | set(weighted_value_misses)):
        bucket = weighted_value_misses.get(label)
        detected = detected_counts.get(label, 0)
        found = round(sum(bucket["stratum_weight"].values()), 2) if bucket else 0.0
        found_adjusted = (round(sum(weight / (strata[role]["coverage_of_drawn_weight"] or 1.0)
                                    for role, weight in bucket["stratum_weight"].items()), 2)
                          if bucket else 0.0)
        counts = per_value.get(label) or {}
        proposed, both = counts.get("machine_proposed", 0), counts.get("both", 0)
        precision = (both / proposed) if proposed else None
        numerator = detected * precision if precision is not None else detected
        entry = {
            "detected_propositions_corpus_wide": detected,
            "precision_within_sampled_candidates": round(precision, 4) if precision is not None else None,
            "precision_sampled_from_candidate_rows": proposed,
            "true_positive_propositions_implied": round(numerator, 2),
            "estimated_missed_propositions_weighted": found,
            "estimated_missed_propositions_coverage_adjusted": found_adjusted,
            "misses_by_probe_stratum": ({k: round(v, 2) for k, v in sorted(bucket["stratum_weight"].items())}
                                        if bucket else {}),
            "probe_rows_with_consensus_for_this_value": bucket["consensus_rows"] if bucket else 0,
            "recall_hat": (round(numerator / (numerator + found_adjusted), 4)
                           if (numerator + found_adjusted) else None),
            "recall_hat_upper_bound_ignoring_precision": (
                round(detected / (detected + found_adjusted), 4) if (detected + found_adjusted) else None),
        }
        if precision is None and detected:
            entry["precision_status"] = (
                "uncorrected: no machine_candidate row proposing this value was coded by both readers, so its "
                "true-positive share is unknown and `recall_hat` here still assumes every detection is real")
        if not bucket and detected:
            # A perfect-recall claim from an empty probe sample is exactly the kind of number
            # this project has been asked to stop producing.
            entry["recall_hat"] = None
            entry["status"] = "no_probe_evidence_yet: the point estimate would be 1.0 only because " \
                              "no sampled no-record proposition carries this value in consensus"
        elif not detected:
            entry["status"] = "the detector produced no record for this label anywhere in the corpus, so " \
                              "recall_hat is 0 where the probe found a miss and undefined where it did not; " \
                              "neither says the corpus is empty of the concept, only that this instrument " \
                              "is silent on the label"
        by_value[label] = entry

    def coder_rate(counter):
        out = dict(sorted(counter.items()))
        out["undecidable_share_of_choices"] = (round(out["undecidable_choices"] / out["total_choices"], 4)
                                               if out.get("total_choices") else None)
        out["rows_answered_with_a_unit"] = (out.get("machine_candidate_rows_answered", 0)
                                            + out.get("probe_rows_answered", 0))
        out["referent_share_of_rows"] = (round(out["referent_terms_given"] / out["propositions_coded"], 4)
                                         if out.get("propositions_coded") else None)
        return out

    result = {
        "instrument": "annotation reliability scorer v3.2",
        "unit_scored": "proposition",
        "propositions_compared": len(overlap),
        "rows_by_sample_role": {k: dict(sorted(v.items())) for k, v in sorted(rows_by_group.items())},
        "dimensions_by_cardinality": {
            "single": sorted(d for d, c in cardinality.items() if c == "single"),
            "set": sorted(d for d, c in cardinality.items() if c == "set"),
        },
        "single_valued_dimensions": {},
        "set_valued_dimensions": {},
        "coder_answer_sets_used": {c: sorted(v) for c, v in ANSWER_VOCABULARIES.items()},
        "undecidable_selection_rate": {coder: coder_rate(counter)
                                       for coder, counter in sorted(undecidable_rate.items())},
        "referent_identification": dict(sorted(referent_given.items())),
        "machine_vs_human_by_value": {},
        "estimator_note": "two estimands, two row groups. `machine_vs_human_by_value` and every precision-like "
                          "figure below come from machine_candidate rows only, because only those rows have a "
                          "machine value to be wrong about. `detector_recall` comes from the no_candidate probe "
                          "rows only, weighted by 1/pi. The two are never pooled: pooling them would compute "
                          "recall out of a sample that cannot contain a miss. What the candidate rows do lend "
                          "recall is a rate, not a count -- the share of flagged propositions two readers kept "
                          "-- because a numerator of raw machine firings would count every false positive the "
                          "precision table just found as a true positive.",
        "detector_recall": {
            "estimand": "P(a proposition that carries divine concept v is flagged by the detector with a record "
                        "for v), over propositions the detector's own segmentation produced in eligible passages",
            "numerator_source": display_path(args.attestations),
            "propositions_with_any_machine_record_corpus_wide": detected_propositions,
            "probe_strata": strata,
            "probe_rows_in_key": len(probe_records),
            "probe_rows_coded_by_both": sum(t["rows_coded_by_both"] for t in strata.values()),
            "records_excluded_as_non_detections": excluded_records,
            "records_excluded_because": "only `assertion_state: candidate` detects; `not_yet_instrumented` "
                                        "declares that no detector for the value exists and "
                                        "`candidate_requires_human_disambiguation` is a value the detector "
                                        "declined to choose, so counting either would give a value with no "
                                        "instrument a nonzero numerator and a published recall",
            "proposition_level": proposition_level_recall(
                detected_propositions, candidate_confirmation_share,
                misses_found, misses_conservative, misses_bound),
            "by_value": by_value,
            "assumptions": [
                "a probe row is a miss only when both coders, independently, decline the null "
                "(`not_a_divine_proposition`); a single coder's over-reading is not projected onto the corpus",
                "the estimator is Horvitz-Thompson with one exact inclusion probability per stratum: "
                "estimated misses = sum of 1/pi over the rows that qualify, which is design-unbiased for the "
                "no-record population of that stratum",
                "a stratum whose drawn rows were only partly coded is widened, not quietly shortened: the "
                "miss count is divided by the share of the drawn weight two readers actually reached, which "
                "assumes uncoded draws miss at the coded rate. Uncoded rows are reported per stratum, and a "
                "key that reports two different populations for one stratum is refused rather than averaged",
                "recall's numerator is the detection count discounted by the candidate-row confirmation "
                "share, because a flagged proposition one reader rejects is not a true positive; where no "
                "candidate row for a value was coded, that discount is unknown and the entry says so instead "
                "of pretending to be corrected",
                "a probe value is only counted on a row both readers also kept as a divine proposition, so a "
                "label named on a row one of them called mundane inflates nothing",
                "the two probe strata are disjoint by construction (a proposition is either cue-positive or it "
                "is not), so their weighted counts add without double-counting",
                "a value's `recall_hat` counts only misses that both coders named with that exact value; misses "
                "the coders read as divine without agreeing on a label inflate no value's denominator, so every "
                "per-value figure is optimistic by that amount",
                "a value the probe sample never produced has no estimate at all; the field reports that rather "
                "than 1.0",
                "the probe universe is the detector's segmentation: a divine claim the splitter merged or "
                "fragmented is outside the frame and cannot be counted as a miss here",
            ],
        },
        "reading_rules": [
            "kappa near 0 means the frame is not carving the texts where coders carve them; it does not mean "
            "the coders were careless",
            "an undecidable rate of zero from either coder means that coder is assigning rather than reading",
            "consensus is the intersection of the two coders' sets; `seen_by_one_coder_only` is reported "
            "beside precision, not folded into it",
            "`label_kind` = `machine_only` is a precision failure of the detector; `human_only` inside the "
            "candidate rows is a value-assignment failure on a proposition the detector already flagged -- "
            "it is NOT recall, because the propositions the detector never flagged are not in this table at "
            "all; recall lives in `detector_recall`, which is why the packet carries no_candidate probe rows",
            "strict_single_value_match is the harder number: it counts only candidate rows where the machine "
            "offered exactly one value and the coders agreed on exactly one",
            "no historical conclusion follows from any number in this file",
        ],
        "not_claimed": ["that the machine assignment is a gold standard -- it is one analyst's candidate set",
                        "that these coders exist; the script refuses to produce a single-coder figure",
                        "that a proposition-level kappa validates the segmentation: see the "
                        "unit_is_a_single_proposition row, which measures the segmentation directly",
                        "that a per-value recall_hat of 0.0 means the corpus contains no such proposition: it "
                        "means the detector produced no record for it anywhere",
                        "that the D7d / doctrine_endorsed_by_text construct check has run: it needs two human "
                        "codings and reports `pending_human_coding` until a coder fills both columns"],
    }

    for dimension in sorted(cardinality):
        column = columns[dimension]
        entry = {"coder_column": column, "n_compared": len(jaccard_scores[dimension]),
                 "mean_jaccard": round(sum(jaccard_scores[dimension]) / len(jaccard_scores[dimension]), 4)
                 if jaccard_scores[dimension] else None,
                 "propositions_with_full_consensus": sum(1 for v in consensus[dimension].values() if v),
                 "agreement_split_by_row_group": {}}
        for group in ("machine_candidate", "probe"):
            scores = jaccard_by_group.get((group, dimension)) or []
            split = {"n_compared": len(scores),
                     "mean_jaccard": round(sum(scores) / len(scores), 4) if scores else None,
                     "rows_of_this_dimension_in_this_group": rows_by_group[group].get(dimension, 0)}
            if cardinality[dimension] == "single":
                pairs = exact_pairs_by_group.get((group, dimension)) or []
                kappa, n = cohens_kappa(pairs)
                split["cohen_kappa"] = round(kappa, 4) if kappa is not None else None
                split["kappa_n"] = n
            entry["agreement_split_by_row_group"][group] = split
        if cardinality[dimension] == "single" and exact_pairs.get(dimension):
            kappa, n = cohens_kappa(exact_pairs[dimension])
            entry["cohen_kappa"] = round(kappa, 4) if kappa is not None else None
            entry["kappa_n"] = n
            entry["observed_agreement"] = round(
                sum(1 for x, y in exact_pairs[dimension] if x == y) / n, 4) if n else None
            strict = machine_strict_single[dimension]
            entry["strict_single_value_match"] = (
                round(strict["consensus_matched"] / strict["machine_offered_one_value"], 4)
                if strict["machine_offered_one_value"] else None)
            entry["strict_single_value_n"] = strict["machine_offered_one_value"]
            entry["strict_single_value_rows_are_candidate_rows_only"] = True
        entry["seen_by_one_coder_only"] = dict(sorted(one_coder_only[dimension].items()))
        if cardinality[dimension] == "set":
            result["set_valued_dimensions"][dimension] = entry
        else:
            result["single_valued_dimensions"][dimension] = entry

    for label, counts in sorted(per_value.items()):
        proposed, confirmed, both = (counts["machine_proposed"], counts["human_confirmed"], counts["both"])
        kind = ("machine_and_human" if both else
                "machine_only" if proposed and not confirmed else
                "human_only_in_candidate_rows" if confirmed and not proposed else
                "disagreed_in_candidate_rows")
        result["machine_vs_human_by_value"][label] = {
            "label_kind": kind,
            "rows_are_machine_candidate_rows_only": True,
            "machine_proposed_in_sampled_candidate_rows": proposed,
            "human_consensus_in_sampled_candidate_rows": confirmed,
            "both": both,
            "precision_within_sampled_candidates": round(both / proposed, 4) if proposed else None,
            "human_confirmation_rate_conditional_on_detection": (
                round(both / confirmed, 4) if confirmed else None),
        }

    for column in (UNIT_COLUMN, *QUESTION_COLUMNS):
        pairs = exact_pairs.get(column) or []
        kappa, n = cohens_kappa(pairs)
        result.setdefault("coder_answer_columns", {})[column] = {
            "cohen_kappa": round(kappa, 4) if kappa is not None else None, "n": n,
            "marginal_distribution": dict(sorted(Counter(x for x, _ in pairs).items()))}

    tested = sum(len(v) for v in construct_pairs.values())
    result["construct_checks"] = {
        "d7d_and_doctrinal_endorsement": {
            "the_claim_under_test": "the record's `doctrinal_endorsement` field is not a second question beside "
                                   "D7d: tools/divinity_ontology.py writes it as the D7d value itself, so the two "
                                   "disagree only on a `not_yet_instrumented` row, where the record forces the "
                                   "field to `undecidable`, and only human coding can test whether "
                                   "readers treat them as one question or two",
            "why_the_machine_cannot_test_it": "an association computed from a field that is a copy of the other is "
                                              "1.0 by construction and measures nothing",
            "what_is_compared": f"one coder's `{D7D_DIMENSION}` answer against that same coder's "
                                f"`{ENDORSEMENT_COLUMN}` answer, proposition by proposition, reported per coder "
                                "and per row group; the two columns offer the same six labels",
            "rows_answering_both_questions": tested,
            "by_coder_and_row_group": ({f"{coder}.{group}": construct_view(pairs)
                                        for (coder, group), pairs in sorted(construct_pairs.items())}
                                       if tested else {}),
            "status": ("measured" if tested else
                       "pending_human_coding: no coder has filled either column, so no association is reported. "
                       "The claim stands as a declared alias in config/divinity_ontology.json "
                       "> distinctness_status, not as a validated one."),
            "how_to_read_it": "near-perfect agreement says two coder questions behave as one, which is what the "
                              "alias predicts and is not evidence that D7d is a good dimension; the disagreements "
                              "are the finding, because a systematic pattern there means readers are answering two "
                              "different questions and the alias is wrong",
            "not_evidence_of": ["that the twelve dimensions are empirically distinct: that needs the cross-"
                               "dimension association matrix this script does not compute",
                               "that either column is correct about the text; a construct check compares two "
                               "answers, never an answer and the world"],
        }
    }

    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"propositions_compared": len(overlap),
                      "construct_check_status": result["construct_checks"]["d7d_and_doctrinal_endorsement"]["status"],
                      "probe_rows_coded_by_both": result["detector_recall"]["probe_rows_coded_by_both"],
                      "kappa_by_single_valued_dimension": {
                          d: v.get("cohen_kappa") for d, v in result["single_valued_dimensions"].items()},
                      "mean_jaccard_by_set_valued_dimension": {
                          d: v["mean_jaccard"] for d, v in result["set_valued_dimensions"].items()},
                      "detector_recall_of_divine_propositions":
                          result["detector_recall"]["proposition_level"]["recall_of_divine_propositions_point"],
                      "recall_lower_bound_95pct":
                          result["detector_recall"]["proposition_level"]
                          ["recall_of_divine_propositions_lower_bound_95pct"],
                      "values_with_a_recall_estimate": sum(
                          1 for v in result["detector_recall"]["by_value"].values()
                          if v.get("recall_hat") is not None)},
                     indent=2))
    print(f"wrote {display_path(args.out)}")


if __name__ == "__main__":
    main()
