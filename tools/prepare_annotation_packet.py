#!/usr/bin/env python3
"""Independent-coding packet: a blinded, stratified sample of propositions.

v2 sampled utterance windows and asked a coder to read seven dimensions off a
sentence fragment. v3 follows the reviewer's correction: the coding target is one
proposition about an identified divine referent, and the window is carried alongside
as context rather than treated as the thing being coded.

  results/annotation_packet_coder_view.csv   what a coder sees: the proposition, its
      context window, its locator, its source attributes, and empty coding columns.
      No machine value, no expected answer; row order shuffled so the stratification
      is not readable.

  results/annotation_packet_key.jsonl        the answer key: token, the machine value
      set per dimension, the assertion state per dimension and whether the machine
      itself flagged the row for disambiguation. Joined on `token` only after both
      coders have finished.

  results/annotation_codebook.csv            the value sets, one row per dimension
      value, with the question that dimension answers and its cardinality. Without
      this a coding sheet is not independently executable by a second reader.

Three candidate strata are enforced -- dimension value, work, and D7b speech act -- because
v2 stratified only by value and therefore could report precision per value and
nothing else.

Those three strata all draw from propositions that already carry a machine record, which is why they can
only ever measure precision. A sample of hits cannot contain a miss, and the miss rate is what recall is.
`not_yet_instrumented` is not the answer either: that state names a value the detector declares it cannot
be trusted on, which is a declared gap, not an estimate of what the detector actually walked past. So the
packet now also draws from the propositions that produced no record at all. The no-record universe is cut
in two disjoint strata -- propositions containing no divine cue, and propositions containing at least one
cue from `config/recall_probe_cues.json` -- each drawn as its own simple random sample, so each row carries
an exact inclusion probability and the pooled miss estimate is design-unbiased over the whole no-record
population rather than over the convenient part of it. The cued stratum is where misses concentrate; the
uncued stratum is what stops that concentration from becoming the estimate.

Nothing here pretends a coding has happened: every record stays `pending`, and no
reliability number can be produced by this repo alone.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import divinity_ontology as onto  # noqa: E402  the detector's own segmentation, imported not reimplemented
from check_recall_cues import compile_cue_pattern  # noqa: E402  one cue matcher, not two

ATTEST = ROOT / "results/ontology_attestations.jsonl.gz"
PASSAGES = onto.PASSAGES
ONTOLOGY = ROOT / "config/divinity_ontology.json"
CUE_CONFIG = ROOT / "config/recall_probe_cues.json"
OUT_VIEW = ROOT / "results/annotation_packet_coder_view.csv"
OUT_KEY = ROOT / "results/annotation_packet_key.jsonl"
OUT_CODEBOOK = ROOT / "results/annotation_codebook.csv"
OUT_PLAN = ROOT / "results/annotation_sampling_plan.json"

CONTEXT_CHARS = 1000

# Row roles, named once so the builder that writes them and the scorer that reads
# them cannot drift into two different vocabularies.
ROLE_CANDIDATE = "machine_candidate"
PROBE_ROLES = ("no_candidate_uncued", "no_candidate_cue_positive")
PROBE_ROLE_PREFIX = "no_candidate"

# The three questions a coder is actually asked, kept separate because v2 collapsed
# them: is the concept represented here, and does the text's own voice endorse it.
QUESTION_COLUMNS = ["concept_represented", "doctrine_endorsed_by_text"]
UNIT_COLUMN = "unit_is_a_single_proposition"
REFERENT_COLUMN = "referent_terms"

# Fixed vocabularies for the non-dimension columns, published in the codebook so a
# second coder is not inventing a code the scorer has never seen.
ANSWER_VOCABULARIES = {
    UNIT_COLUMN: {
        "single_proposition": "this is one claim about one divine referent, as the machine cut it",
        "too_large_should_split": "this text carries more than one claim and should have been cut",
        "too_small_should_join": "this fragment is not a claim on its own; it belongs with its neighbour",
        "not_a_divine_proposition": "no claim about divinity is made here at all",
        "undecidable": "a reader cannot say",
    },
    "concept_represented": {
        "represented": "the concept is on the page, whoever is affirming it",
        "not_represented": "the matched words carry no divine concept here",
        "undecidable": "a reader cannot say",
    },
    "doctrine_endorsed_by_text": {
        "endorsed_by_text": "the voice the text itself is endorsing states it as fact",
        "attributed_not_endorsed": "somebody states it and the text does not take that up as true",
        "rejected_in_text": "the text states it in order to deny it",
        "suspended_or_held_open": "asserted only inside a condition, a wish or a question",
        "not_applicable_non_assertive": "nothing is being asserted here, so endorsement does not arise",
        "undecidable": "a reader cannot say",
    },
}

# All three codable states are sampled. `not_yet_instrumented` is in the list on
# purpose: those rows name values this detector cannot be trusted on, and a human
# read of them is how such a value gets validated. Dropping them would sample only
# the rows the instrument is already sure of.
SAMPLING_STATES = ("candidate", "candidate_requires_human_disambiguation", "not_yet_instrumented")

# Sampling all three is right; calling all three a detection is not. `not_yet_instrumented` records the
# absence of a detector and `candidate_requires_human_disambiguation` records a value the detector refused
# to choose, so a proposition carrying only those two was never flagged for anything. Treating it as a hit
# removed it from the frame where a miss can be found and put it in recall's numerator at the same time.
DETECTION_STATE = "candidate"


@lru_cache(maxsize=1)
def dimensions():
    return json.loads(ONTOLOGY.read_text(encoding="utf-8"))["dimensions"]


def coding_columns():
    """Dimension -> coder-view column name, derived once so packet and scorer cannot drift.

    Set-valued dimensions take a semicolon list; forcing a single choice there and
    then scoring the forced choice as agreement would invent concordance.
    """
    out = {}
    for key, spec in sorted(dimensions().items()):
        out[key] = key if spec["cardinality"] == "single" else key + "_semicolon"
    return out


@lru_cache(maxsize=1)
def column_cardinalities():
    return {key: spec["cardinality"] for key, spec in sorted(dimensions().items())}


def proposition_key(record):
    return (record["work_id"], record["passage_id"], record["proposition_char_start"])


def load_records():
    records = []
    with gzip.open(ATTEST, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["assertion_state"] in SAMPLING_STATES:
                records.append(record)
    return records


def group_by_proposition(records):
    groups = defaultdict(list)
    for record in records:
        groups[proposition_key(record)].append(record)
    for group in groups.values():
        group.sort(key=lambda r: r["record_id"])
    return groups


def value_strata_for(group):
    """Dimension values a proposition is a candidate for, concept strata only.

    A proposition carrying only D7 answers is a speech-act observation, not a
    concept observation, so it reaches the packet through the act stratum rather
    than a value stratum.
    """
    concept_dimensions = {d for d in column_cardinalities() if not d.startswith("D7")}
    return sorted(f"{r['dimension']}={r['value']}" for r in group
                  if r["dimension"] in concept_dimensions)


def enumerate_universe(hit_keys, cue_pattern):
    """Every proposition in every eligible passage, split into hit / no-hit-uncued / no-hit-cued.

    Segmentation is the detector's own -- normalise, then windows_of, then propositions_of -- because a
    recall probe that cut its units differently would be measuring a different population than the one the
    detector claims to cover. The key is the attestation key: (work, passage, body_start + raw start).

    Tuples are stored as (passage_id, norm_start, norm_end, key, raw_end) so the sampled few thousand can
    be re-read for text in a second pass; holding 1.4M proposition strings would be the difference between a
    tool that runs on a laptop and one that does not.
    """
    total = passages = 0
    uncued, cued = [], []
    with open(PASSAGES, encoding="utf-8") as handle:
        for line in handle:
            passage = json.loads(line)
            if not passage["eligible_for_similarity"]:
                continue
            passages += 1
            work, pid, body_start, text = (passage["work_id"], passage["passage_id"],
                                           passage["body_char_start"], passage["text"])
            norm, map_to_raw = onto.normalise(text)
            for w_start, w_end in onto.windows_of(norm):
                for a, b in onto.propositions_of(norm[w_start:w_end]):
                    lo, hi = onto.raw_slice_bounds(text, map_to_raw, w_start + a, w_start + b)
                    key = (work, pid, body_start + lo)
                    total += 1
                    if key in hit_keys:
                        continue
                    fragment = norm[w_start + a:w_start + b]
                    item = (pid, w_start + a, w_start + b, key, body_start + hi)
                    (cued if cue_pattern.search(fragment) else uncued).append(item)
    return {"propositions_in_universe": total, "eligible_passages_scanned": passages,
            "hit_by_the_machine": len(hit_keys)}, sorted(uncued), sorted(cued)


def fetch_probe_text(sampled):
    """Re-read only the passages a probe row needs, and recover the proposition plus its window."""
    wanted = defaultdict(list)
    for pid, n_start, n_end, key, raw_end in sampled:
        wanted[pid].append((n_start, n_end, key, raw_end))
    out = {}
    with open(PASSAGES, encoding="utf-8") as handle:
        for line in handle:
            passage = json.loads(line)
            pid = passage["passage_id"]
            if pid not in wanted:
                continue
            norm, _ = onto.normalise(passage["text"])
            windows = onto.windows_of(norm)
            for n_start, n_end, key, raw_end in wanted[pid]:
                window = next(((s, e) for s, e in windows if s <= n_start < e), (n_start, n_end))
                out[key] = {
                    "proposition_text": " ".join(norm[n_start:n_end].split()),
                    "window_text": " ".join(norm[window[0]:window[1]].split())[:CONTEXT_CHARS],
                    "proposition_char_end": raw_end,
                    "window_char_start": passage["body_char_start"] + window[0],
                    "window_char_end": passage["body_char_start"] + window[1],
                    "proposition_overlong": (n_end - n_start) > onto.MAX_PROPOSITION_CHARS,
                }
    return out


def draw_simple_random(pool, target, rng):
    """Simple random sample without replacement: every member has inclusion probability n/N, exactly."""
    items = list(pool)
    rng.shuffle(items)
    take = items[:min(target, len(items))]
    return take, len(items), (len(take) / len(items) if items else 0.0)


def stratified_pick(groups, per_stratum, per_work, per_act, seed):
    """Pick propositions three ways, then union the picks.

    Value strata carry precision; work strata carry the finding that a value behaves
    differently in a romance than in a hymn; speech-act strata carry the reviewer's
    point that endorsement depends on who is speaking.
    """
    rng = random.Random(seed)
    by_value, by_work, by_act = defaultdict(list), defaultdict(list), defaultdict(list)
    for key, group in groups.items():
        for value in value_strata_for(group):
            by_value[value].append(key)
        by_work[group[0]["work_id"]].append(key)
        by_act[f"D7b={group[0]['D7b_speech_act']}"].append(key)

    picked, plan, membership = set(), {"value_strata": {}, "work_strata": {}, "speech_act_strata": {}}, {}
    for label, buckets, target in (("value_strata", by_value, per_stratum),
                                   ("work_strata", by_work, per_work),
                                   ("speech_act_strata", by_act, per_act)):
        for stratum, keys in sorted(buckets.items()):
            pool = sorted(keys)
            rng.shuffle(pool)
            take = pool[:min(target, len(pool))]
            picked.update(take)
            membership[f"{label}:{stratum}"] = set(take)
            plan[label][stratum] = {"population": len(keys), "sampled": len(take),
                                    "whole_population_taken": len(keys) <= target}
    return picked, plan, membership


def candidate_inclusion_probability(key, membership, plan):
    """Inclusion probability for a row the three detection strata could have reached.

    The three strata are drawn independently of one another, so the union probability is written as
    1 - product(1 - n_h/N_h). That is exact under Bernoulli sampling and an approximation under
    without-replacement sampling inside a stratum; it is published as an approximation, and a row in a
    census stratum gets pi = 1 outright.
    """
    keep = 1.0
    for name, members in membership.items():
        if key not in members:
            continue
        label, _, stratum = name.partition(":")
        info = plan[label][stratum]
        if info["whole_population_taken"]:
            return 1.0
        keep *= 1.0 - (info["sampled"] / info["population"]) if info["population"] else 0.0
    return 1.0 - keep


def build(per_stratum, per_work, per_act, probe_uncued, probe_cued, seed):
    records = load_records()
    groups = group_by_proposition(records)
    picked, plan, membership = stratified_pick(groups, per_stratum, per_work, per_act, seed)
    columns = coding_columns()
    cardinality = column_cardinalities()
    fieldnames = (["token", "proposition_text", "context_window_text", "locator_work",
                   "locator_passage", "proposition_chars", "window_chars", "tradition",
                   "region", "date_range", REFERENT_COLUMN, UNIT_COLUMN,
                   *columns.values(), *QUESTION_COLUMNS, "notes", "coder_id", "coding_date"])

    rows, keys = [], []
    for key in sorted(picked):
        work, passage, prop_start = key
        group = groups[key]
        first = group[0]
        values_by_dimension, states_by_dimension, doctrine_by_dimension = {}, {}, {}
        for record in group:
            values_by_dimension.setdefault(record["dimension"], []).append(record["value"])
            states_by_dimension[record["dimension"]] = record["assertion_state"]
            doctrine_by_dimension[record["dimension"]] = bool(record["counts_as_affirmative_doctrine"])
        values_by_dimension = {d: sorted(set(v)) for d, v in values_by_dimension.items()}
        ambiguous = sorted(d for d, v in values_by_dimension.items()
                           if cardinality[d] == "single" and len(v) > 1)
        token = hashlib.sha256(f"{work}|{passage}|{prop_start}".encode()).hexdigest()[:12]
        rows.append({
            "token": token,
            "proposition_text": first["proposition_text"],
            "context_window_text": first["snippet"][:CONTEXT_CHARS],
            "locator_work": work,
            "locator_passage": passage,
            "proposition_chars": f"{first['proposition_char_start']}-{first['proposition_char_end']}",
            "window_chars": f"{first['window_char_start']}-{first['window_char_end']}",
            "tradition": first["tradition"],
            "region": first["region"],
            "date_range": "",
            REFERENT_COLUMN: "",
            UNIT_COLUMN: "",
            **{columns[d]: "" for d in columns},
            **{c: "" for c in QUESTION_COLUMNS},
            "notes": "", "coder_id": "", "coding_date": "",
        })
        keys.append({
            "token": token, "work_id": work, "passage_id": passage,
            "proposition_char_start": prop_start,
            "proposition_char_span": rows[-1]["proposition_chars"],
            "window_char_span": rows[-1]["window_chars"],
            "machine_values_by_dimension": values_by_dimension,
            "machine_assertion_state_by_dimension": states_by_dimension,
            "machine_counts_as_affirmative_doctrine_by_dimension": doctrine_by_dimension,
            "machine_ambiguous_single_valued_dimensions": ambiguous,
            "machine_proposition_flagged_overlong": bool(first["proposition_overlong"]),
            "machine_referent_candidates": sorted({c for r in group for c in r["referent_candidates"]}),
            "strata": value_strata_for(group),
            "sample_role": ROLE_CANDIDATE,
            "inclusion_probability": round(
                candidate_inclusion_probability(key, membership, plan), 12),
            "sampling_weight": None,
            "status": "pending_two_independent_codings",
        })

    # ---- recall probe: propositions the machine produced no record for -------------------------------
    cue_config = json.loads(CUE_CONFIG.read_text(encoding="utf-8"))
    cue_pattern, live_cues = compile_cue_pattern(cue_config)
    detections = {key for key, group in groups.items()
                  if any(r["assertion_state"] == DETECTION_STATE for r in group)}
    universe_stats, pool_uncued, pool_cued = enumerate_universe(detections, cue_pattern)
    universe_stats["propositions_with_any_machine_record"] = len(groups)
    universe_stats["of_which_the_machine_asserted_nothing"] = len(groups) - len(detections)
    universe_stats["records_excluded_as_non_detections"] = sum(
        1 for record in records if record["assertion_state"] != DETECTION_STATE)
    universe_stats["of_which_not_yet_instrumented"] = sum(
        1 for record in records if record["assertion_state"] == "not_yet_instrumented")
    universe_stats["of_which_requires_human_disambiguation"] = sum(
        1 for record in records if record["assertion_state"] == "candidate_requires_human_disambiguation")
    probe_rng = random.Random(seed + 2)
    take_uncued, n_uncued, pi_uncued = draw_simple_random(pool_uncued, probe_uncued, probe_rng)
    take_cued, n_cued, pi_cued = draw_simple_random(pool_cued, probe_cued, probe_rng)
    probe_text = fetch_probe_text(take_uncued + take_cued)
    attributes = onto.work_attributes()
    probe_added, probe_strata = {}, {}
    for role, drawn, population, prob in (
            (PROBE_ROLES[0], take_uncued, n_uncued, pi_uncued),
            (PROBE_ROLES[1], take_cued, n_cued, pi_cued)):
        added = 0
        for _pid, _ns, _ne, key, _raw_end in sorted(drawn, key=lambda t: t[3]):
            work, passage, prop_start = key
            piece = probe_text.get(key)
            if piece is None:
                continue
            added += 1
            attr = attributes.get(work, {})
            token = hashlib.sha256(f"{work}|{passage}|{prop_start}".encode()).hexdigest()[:12]
            rows.append({
                "token": token,
                "proposition_text": piece["proposition_text"],
                "context_window_text": piece["window_text"],
                "locator_work": work,
                "locator_passage": passage,
                "proposition_chars": f"{prop_start}-{piece['proposition_char_end']}",
                "window_chars": f"{piece['window_char_start']}-{piece['window_char_end']}",
                "tradition": attr.get("tradition", ""),
                "region": attr.get("region", ""),
                "date_range": "",
                REFERENT_COLUMN: "",
                UNIT_COLUMN: "",
                **{columns[d]: "" for d in columns},
                **{c: "" for c in QUESTION_COLUMNS},
                "notes": "", "coder_id": "", "coding_date": "",
            })
            keys.append({
                "token": token, "work_id": work, "passage_id": passage,
                "proposition_char_start": prop_start,
                "proposition_char_span": rows[-1]["proposition_chars"],
                "window_char_span": rows[-1]["window_chars"],
                "sample_role": role,
                "stratum_population": population,
                "inclusion_probability": round(prob, 12),
                "sampling_weight": round(1.0 / prob, 4) if prob else None,
                "machine_values_by_dimension": {},
                "machine_assertion_state_by_dimension": {},
                "machine_counts_as_affirmative_doctrine_by_dimension": {},
                "machine_ambiguous_single_valued_dimensions": [],
                "machine_proposition_flagged_overlong": piece["proposition_overlong"],
                "machine_referent_candidates": [],
                "strata": [f"probe={role}"],
                "status": "pending_two_independent_codings",
            })
        probe_added[role] = added
        probe_strata[role] = {
            "population": population,
            "sampled": added,
            "inclusion_probability": round(prob, 12) if population else None,
            "sampling_weight": round(1.0 / prob, 4) if population and prob else None,
            "draw": "simple random sample without replacement over the whole stratum, so the "
                    "inclusion probability is n/N exactly and needs no approximation",
        }

    order = list(range(len(rows)))
    random.Random(seed + 1).shuffle(order)
    rows = [rows[i] for i in order]
    for record in keys:
        if record["sample_role"] == ROLE_CANDIDATE and record["inclusion_probability"]:
            record["sampling_weight"] = round(1.0 / record["inclusion_probability"], 4)
    keys_by_token = {k["token"]: k for k in keys}

    with OUT_VIEW.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with OUT_KEY.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(keys_by_token[row["token"]], ensure_ascii=False) + "\n")

    with OUT_CODEBOOK.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dimension", "cardinality", "question_this_dimension_answers",
                         "coverage_state", "value", "value_definition", "coder_column"])
        for key, spec in sorted(dimensions().items()):
            for value, definition in sorted(spec["values"].items()):
                writer.writerow([key, spec["cardinality"], spec["question"],
                                 spec["coverage_state"], value,
                                 definition if isinstance(definition, str) else json.dumps(definition),
                                 columns[key]])
        for column, vocabulary in ANSWER_VOCABULARIES.items():
            for value, definition in sorted(vocabulary.items()):
                writer.writerow([column, "single", "the coder's own read, not a detector output",
                                 "coder_answer_set", value, definition, column])

    value_populations = {k: v["population"] for k, v in plan["value_strata"].items()}
    census = [k for k, v in plan["value_strata"].items() if v["whole_population_taken"]]
    return {
        "instrument": "annotation packet v3.1",
        "unit_of_analysis": "one proposition about an identified divine referent, with its "
                            "utterance window carried as context",
        "sizing": {
            "propositions": len(rows),
            "machine_candidate_rows": sum(1 for k in keys if k["sample_role"] == ROLE_CANDIDATE),
            "recall_probe_rows": sum(probe_added.values()),
            "judgments_per_coder": len(rows) * len(columns),
            "why_this_size": "the binding constraint is a second coder, not more data; the packet is "
                             "sized so every value stratum carries enough rows to put a usable interval "
                             "on its precision, rare strata are taken as a census, and the two no-candidate "
                             "strata are sized to bound the miss rate rather than to exhaust it",
            "worst_case_95pct_margin_on_a_value_precision_at_target": "±0.124 at n=60 (p=0.5, normal approximation)",
            "strata_taken_as_census": len(census),
            "census_strata": sorted(census),
            "minimum_tier_if_only_one_coder_is_available": f"code the {len(census)} census strata first: those "
                                                           "are the values with the least evidence, and they "
                                                           "are the rows a single analyst's reading is least "
                                                           "likely to have got right",
        },
        "recall_probe": {
            "why_it_was_added": "the three detection strata all draw from propositions that already carry a "
                                "machine record, so they can estimate precision and cannot estimate recall: a "
                                "sample of hits contains no misses. not_yet_instrumented is a declared gap on "
                                "a named value, not an estimate of what the detector walked past.",
            "universe": universe_stats | {
                "no_record_in_universe": n_uncued + n_cued,
                "of_which_cue_positive": n_cued,
                "of_which_cue_negative": n_uncued,
            },
            "strata": probe_strata,
            "rows_added": probe_added,
            "segmentation": "the detector's own normalise -> windows_of -> propositions_of, so the probe "
                            "population is the population the detector claims to cover",
            "cue_list": {"file": "config/recall_probe_cues.json",
                         "cues_operative": len(live_cues),
                         "cues_retired_ambiguous": len(cue_config.get("excluded_ambiguous_cues", {})),
                         "sha256": hashlib.sha256(CUE_CONFIG.read_bytes()).hexdigest(),
                         "status": "a sampling instruction; a cue never produces an attestation, a value "
                                   "assignment or a doctrinal count"},
            "estimator": {
                "detected_v": "propositions carrying an `assertion_state: candidate` record for value v, "
                              "counted over the whole corpus, not over the packet",
                "what_is_not_a_detection": "a `not_yet_instrumented` record names a value this detector declares "
                                           "it cannot detect, and a `candidate_requires_human_disambiguation` "
                                           "record names a value it refused to choose. Neither is a detection: "
                                           "counting them gave values with no detector a nonzero numerator, and "
                                           "counting their propositions as hits removed them from the frame where "
                                           "a miss could be found. Both are still sampled, in the candidate "
                                           "strata, so a human read can validate them.",
                "estimated_misses_v": "the sum of sampling_weight over probe rows a human coded as carrying "
                                      "value v -- Horvitz-Thompson, one weight per drawn proposition",
                "recall_hat_v": "detected_v / (detected_v + estimated_misses_v)",
                "pooled_across_both_probe_strata": True,
                "why_two_strata_not_one": "misses concentrate where the text names a divinity, so a single "
                                          "uniform draw would spend almost all of its rows on propositions "
                                          "with nothing in them and leave the dense region unmeasured; "
                                          "stratifying and weighting keeps the pooled estimate design-unbiased "
                                          "over the whole no-record universe while still looking hard at the "
                                          "part where a miss is likely",
                "precision_still_comes_from": "the machine_candidate rows; probe rows carry no machine value "
                                              "to be wrong about",
            },
            "what_this_still_cannot_measure": [
                "a divine proposition no human reader can identify from the proposition and its window either",
                "propositions the segmentation itself never produced: a claim that spans two segments, or one "
                "the window splitter merged away, is outside the universe this probe draws from",
                "any value whose detector gap is structural rather than lexical, except insofar as a human "
                "coding a probe row happens to name it",
            ],
        },
        "sample_roles": {ROLE_CANDIDATE: sum(1 for k in keys if k["sample_role"] == ROLE_CANDIDATE),
                         **probe_added},
        "seed": seed, "per_value_stratum_target": per_stratum,
        "per_work_stratum_target": per_work, "per_speech_act_stratum_target": per_act,
        "probe_uncued_target": probe_uncued, "probe_cue_positive_target": probe_cued,
        "propositions_in_packet": len(rows),
        "states_sampled": list(SAMPLING_STATES),
        "dimensions_coded": len(columns),
        "set_valued_dimensions": sorted(k for k, c in cardinality.items() if c == "set"),
        "single_valued_dimensions": sorted(k for k, c in cardinality.items() if c == "single"),
        "strata_enforced": ["dimension value", "work", "D7b speech act",
                            "no-record proposition, cue-negative", "no-record proposition, cue-positive"],
        "strata": plan,
        "value_strata_count": len(value_populations),
        "rare_value_strata_taken_whole": sum(1 for v in plan["value_strata"].values()
                                             if v["whole_population_taken"]),
        "works_covered": len(plan["work_strata"]),
        "speech_acts_covered": len(plan["speech_act_strata"]),
        "propositions_where_machine_gives_two_values_on_a_single_valued_dimension":
            sum(1 for k in keys if k["machine_ambiguous_single_valued_dimensions"]),
        "propositions_flagged_overlong": sum(1 for k in keys if k["machine_proposition_flagged_overlong"]),
        "blinding": ["coder view carries no machine value, no dimension name and no expected answer",
                     "row order randomised so the oversampling of rare values is not visible",
                     "a probe row and a detection row are indistinguishable in the coder view: same columns, "
                     "same locator format, no stratum marker, so a coder cannot tell which kind of row is "
                     "being coded and cannot code the two kinds to different standards",
                     "answer key is a separate file and is joined only after both coders finish"],
        "known_blinding_leak": ["the locator names the work, so a coder with domain knowledge can guess "
                                "what the proposition is about; full blinding would need the source withheld, "
                                "which would make the coding worse rather than better"],
        "questions_kept_separate": {
            "concept_represented": "is this concept represented in the proposition at all",
            "doctrine_endorsed_by_text": "does the voice the text itself endorses affirm it",
            "historical_transmission": "not asked of a coder: transmission needs dated expressions and "
                                       "documented routes, and a single proposition cannot carry either",
        },
        "not_yet_done": ["no coder has coded this packet", "no kappa or precision figure exists",
                         "no recall figure exists either: the probe rows are un coded, so the detector's miss "
                         "rate is still a design and not a measurement",
                         "the machine assignment in the key is single-analyst and is a candidate, "
                         "not a gold standard",
                         "date_range is blank in the coder view because the corpus carries no composition "
                         "date field that survives provenance checking"],
        "reproducibility": {"attestations_sha256": hashlib.sha256(ATTEST.read_bytes()).hexdigest(),
                            "ontology_sha256": hashlib.sha256(ONTOLOGY.read_bytes()).hexdigest(),
                            "passages_sha256": hashlib.sha256(PASSAGES.read_bytes()).hexdigest(),
                            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-stratum", type=int, default=60)
    parser.add_argument("--per-work", type=int, default=35)
    parser.add_argument("--per-act", type=int, default=45)
    parser.add_argument("--probe-uncued", type=int, default=900,
                        help="rows drawn from no-record propositions that carry no divine cue")
    parser.add_argument("--probe-cued", type=int, default=600,
                        help="rows drawn from no-record propositions that do carry a divine cue")
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    plan = build(args.per_stratum, args.per_work, args.per_act, args.probe_uncued, args.probe_cued,
                 args.seed)
    OUT_PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"propositions_in_packet": plan["propositions_in_packet"],
                      "value_strata": plan["value_strata_count"],
                      "rare_value_strata_taken_whole": plan["rare_value_strata_taken_whole"],
                      "works_covered": plan["works_covered"],
                      "speech_acts_covered": plan["speech_acts_covered"],
                      "no_record_universe": plan["recall_probe"]["universe"]["no_record_in_universe"],
                      "probe_rows": plan["recall_probe"]["rows_added"],
                      "probe_inclusion_probabilities": {
                          k: v["inclusion_probability"] for k, v in plan["recall_probe"]["strata"].items()}},
                     indent=2))
    print(f"wrote {OUT_VIEW.name}, {OUT_KEY.name}, {OUT_CODEBOOK.name}, {OUT_PLAN.name}")


if __name__ == "__main__":
    main()
