#!/usr/bin/env python3
"""Independent-coding packet: a blinded, stratified sample of utterance windows.

The frame's own gate table says the binding constraint is a second coder, not more
data. This produces the two files that let one exist:

  results/annotation_packet_coder_view.csv  -- what a coder sees: window text,
  locator, and empty fields. No machine value, no dimension name, no expected
  answer, and the row order is shuffled so the stratification is not readable.

  results/annotation_packet_key.jsonl       -- the answer key: token, stratum, and
  the machine candidate the coder is being tested against. Joined on `token` only
  after both coders have finished.

Scoring is tools/score_annotation.py. Nothing here pretends a coding has happened:
every record is `pending`, and no reliability number can be produced by this repo
alone.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTEST = ROOT / "results/ontology_attestations.jsonl.gz"
OUT_VIEW = ROOT / "results/annotation_packet_coder_view.csv"
OUT_KEY = ROOT / "results/annotation_packet_key.jsonl"
OUT_PLAN = ROOT / "results/annotation_sampling_plan.json"

CODER_COLUMNS = ["token", "window_text", "locator_work", "locator_passage", "locator_chars",
                 "D1_ontology", "D2_plurality", "D3_agency", "D4_functions_semicolon",
                 "D5_universe", "D6_temporal", "D7_speech_act",
                 "independent_of_translation", "notes", "coder_id", "coding_date"]
# D4 is set-valued, so its column takes a semicolon list rather than forcing a single
# choice and then scoring that forced choice as agreement.

# Three states are codable by a human, so all three are sampled: a machine `candidate`
# tests what the instrument found, a `blocked_by_speech_act` record tests whether the
# frame's refusal is the refusal a reader would make, and
# `candidate_requires_human_disambiguation` is the state whose name says a human has to
# decide -- leaving it out would sample only the rows the instrument is already sure of.
SAMPLING_STATES = ("candidate", "blocked_by_speech_act", "candidate_requires_human_disambiguation")


def stratified_sample(records, per_stratum, seed):
    """Rare states get sampled harder than common ones, or precision per value is unestimable."""
    by_stratum = defaultdict(list)
    for record in records:
        by_stratum[f"{record['dimension']}={record['value']}"].append(record)
    rng = random.Random(seed)
    selected, plan = {}, {}
    for stratum, items in sorted(by_stratum.items()):
        pool = sorted(items, key=lambda r: r["record_id"])
        rng.shuffle(pool)
        take = pool[:min(per_stratum, len(pool))]
        plan[stratum] = {"population": len(items), "sampled": len(take),
                         "oversampled_because_rare": len(items) <= per_stratum}
        for record in take:
            selected[record["record_id"]] = record
    # Windows recur across dimensions; one coder sees one window once and codes all
    # seven dimensions on it, otherwise the same text is judged twice in two rows. The
    # group is a list, not a set: records are dicts, and a set would lose the per-record
    # detail the key file publishes.
    merged = defaultdict(list)
    for record in selected.values():
        merged[(record["work_id"], record["passage_id"], record["window_char_start"])].append(record)
    return merged, plan


def build(per_stratum, seed):
    records = []
    with gzip.open(ATTEST, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["assertion_state"] in SAMPLING_STATES:
                records.append(record)
    merged, plan = stratified_sample(records, per_stratum, seed)
    rng = random.Random(seed + 1)
    rows = []
    for (work, passage, window_start), group in sorted(merged.items()):
        token = hashlib.sha256(f"{work}|{passage}|{window_start}".encode()).hexdigest()[:12]
        # Sorted before anything is read out of the group: one window can carry several
        # matches on one dimension, and which value the key publishes must not depend on
        # the order the sampler happened to visit them in.
        group = sorted(group, key=lambda r: r["record_id"])
        first = group[0]
        machine = {}
        every_value = {}
        for record in group:
            machine.setdefault(record["dimension"], record["value"])
            every_value.setdefault(record["dimension"], []).append(record["value"])
        blocked = sorted({r["dimension"] for r in group
                          if r["assertion_state"] == "blocked_by_speech_act"})
        ambiguous = sorted(d for d, values in every_value.items() if len(set(values)) > 1)
        rows.append((token, first["snippet"], work, passage,
                     f"{first['char_start']}-{first['char_end']}", machine, blocked, ambiguous))
    rng.shuffle(rows)

    with OUT_VIEW.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CODER_COLUMNS)
        writer.writeheader()
        for token, snippet, work, passage, chars, _machine, _blocked, _ambiguous in rows:
            writer.writerow({"token": token, "window_text": snippet, "locator_work": work,
                             "locator_passage": passage, "locator_chars": chars,
                             **{c: "" for c in CODER_COLUMNS[6:]}})

    with OUT_KEY.open("w", encoding="utf-8", newline="") as handle:
        for token, _snippet, work, passage, chars, machine, blocked, ambiguous in rows:
            handle.write(json.dumps({"token": token, "work_id": work, "passage_id": passage,
                                     "char_span": chars, "machine_assignment": machine,
                                     "machine_blocked_dimensions": blocked,
                                     "machine_ambiguous_dimensions": ambiguous,
                                     "status": "pending_two_independent_codings"},
                                    ensure_ascii=False) + "\n")
    return {
        "instrument": "annotation packet v2",
        "seed": seed, "per_stratum_target": per_stratum,
        "windows_in_packet": len(rows),
        "states_sampled": list(SAMPLING_STATES),
        "windows_with_more_than_one_machine_value_on_a_dimension": sum(1 for r in rows if r[7]),
        "strata": plan,
        "blinding": ["coder view carries no dimension name, no machine value and no expected answer",
                     "row order randomised so the oversampling of rare values is not visible",
                     "answer key is a separate file and is joined only after both coders finish"],
        "known_blinding_leak": ["the locator names the work, so a coder with domain knowledge can guess "
                                "what the window is about; full blinding would need the source withheld, "
                                "which would make the coding worse rather than better"],
        "not_yet_done": ["no coder has coded this packet", "no kappa or precision figure exists",
                         "the machine assignment in the key is single-analyst and is a candidate, not a gold standard"],
        "reproducibility": {"attestations_sha256": hashlib.sha256(ATTEST.read_bytes()).hexdigest(),
                            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-stratum", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    plan = build(args.per_stratum, args.seed)
    OUT_PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"windows_in_packet": plan["windows_in_packet"],
                      "strata": len(plan["strata"]),
                      "rare_strata_fully_sampled": sum(1 for v in plan["strata"].values()
                                                       if v["oversampled_because_rare"])}, indent=2))
    print(f"wrote {OUT_VIEW.name}, {OUT_KEY.name}, {OUT_PLAN.name}")


if __name__ == "__main__":
    main()
