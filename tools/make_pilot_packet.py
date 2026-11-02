#!/usr/bin/env python3
"""Build the handout a second and third coder need: a slice, a codebook, and instructions.

The packet exists (`results/annotation_packet_coder_view.csv`, 6,199 propositions) and the scorer exists
(`tools/score_annotation.py`), and neither of them has ever been used, because the thing missing from this
project is not another instrument. It is two people who have not spoken to each other filling the same sheet.
A packet of 6,199 rows asking twelve questions per row is not something you hand to a stranger on the strength
of a README; it is roughly 74,000 judgments, and the first thing a real pilot has to establish is whether the
frame can be executed by anyone other than the person who wrote it.

So this tool cuts a pilot out of the packet and writes the three files a coder is given:

  results/pilot_packet_coder_view.csv   the slice. Same columns, same blinded cells, same shuffle as the
      packet -- no machine value appears anywhere in it, and no row order reveals which stratum a row came
      from.

  results/pilot_slice.json              the derivation: which strata, how many rows each, the inclusion
      probability each row carried, the seed, and the SHA-256 of the two source files. A slice chosen by
      looking at the rows is a slice that can be argued about; this one is a seed and an arithmetic.

  annotation/PILOT_CODEBOOK.md          the value lists, rendered from `results/annotation_codebook.csv`
      rather than retyped beside it.

  annotation/CODER_INSTRUCTIONS.md      what to fill in, what empty means, and the independence rule.

Both markdown files are generated, so the counts inside them are the counts the slice has. The `--check`
flag re-renders all four artifacts and reports any byte that differs, which is how a hand-edit of the
instructions shows up as a failure rather than as a quiet second version of the truth.

What a pilot is for, stated before anyone runs one: whether two readers converge on the same values, and
whether a reader who did not write the frame can finish a sheet without asking the author. It is not a
reliability estimate for the corpus, it is not a precision estimate for any of the 93 values, and the
300-row slice is not design-weighted to be either. `tools/score_annotation.py --pilot` enforces that by
never opening the answer key: agreement is all a pilot is allowed to produce.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_annotation_packet import (  # noqa: E402
    ANSWER_VOCABULARIES, UNIT_COLUMN, coding_columns, column_cardinalities)

PACKET = ROOT / "results/annotation_packet_coder_view.csv"
KEY = ROOT / "results/annotation_packet_key.jsonl"
CODEBOOK = ROOT / "results/annotation_codebook.csv"
PLAN = ROOT / "results/annotation_sampling_plan.json"

OUT_SHEET = ROOT / "results/pilot_packet_coder_view.csv"
OUT_DERIVATION = ROOT / "results/pilot_slice.json"
OUT_CODEBOOK_MD = ROOT / "annotation/PILOT_CODEBOOK.md"
OUT_INSTRUCTIONS_MD = ROOT / "annotation/CODER_INSTRUCTIONS.md"

DEFAULT_SIZE = 300
DEFAULT_SEED = 20261102

# Every row answers these three, whatever it does with the dimensions. A sheet missing one of them is not a
# completed coding; it is a partially completed one, and a partially completed one is what the packet's own
# weight-coverage field was invented to stop being silently favourable.
REQUIRED_COLUMNS = (UNIT_COLUMN, "concept_represented", "doctrine_endorsed_by_text")

CANDIDATE_ROLE = "machine_candidate"
PROBE_ROLES = ("no_candidate_uncued", "no_candidate_cue_positive")


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crlf(text):
    """Markdown the repo stores as CRLF, so a handout and a header file do not disagree about bytes."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def rel(path):
    """Repo-relative with forward slashes: a path inside a handout should not depend on whose OS wrote it."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def read_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def roles_by_token(path=KEY):
    """Token -> sample role, read from the key. The key is used for *selection* only.

    Nothing from it reaches a coder: the sheet is cut from the blinded coder view, so a role tells the
    slicer which stratum a token belongs to and tells the coder nothing at all.
    """
    out = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            out[record["token"]] = str(record.get("sample_role") or "")
    return out


def allocate(populations, size):
    """Largest-remainder proportional allocation, with the role name as the deterministic tie-break.

    Ties on the fractional part are broken by name rather than by dict order so that the allocation cannot
    depend on which Python hash seed happened to run the build.
    """
    total = sum(populations.values())
    if not total or size <= 0 or size > total:
        raise SystemExit(f"cannot allocate {size} rows out of a packet of {total}")
    exact = {role: size * count / total for role, count in populations.items()}
    shares = {role: int(value) for role, value in exact.items()}
    remaining = size - sum(shares.values())
    order = sorted(exact, key=lambda role: (-(exact[role] - shares[role]), role))
    for role in order[:remaining]:
        shares[role] += 1
    return shares


def draw(rng, tokens, count):
    """A simple random sample without replacement, from a list sorted before the rng ever sees it."""
    if count > len(tokens):
        raise SystemExit(f"stratum has {len(tokens)} rows, asked for {count}")
    return sorted(rng.sample(sorted(tokens), count))


def select(size=DEFAULT_SIZE, seed=DEFAULT_SEED, packet=PACKET, key=KEY):
    fieldnames, rows = read_rows(packet)
    roles = roles_by_token(key)
    missing = [row["token"] for row in rows if row["token"] not in roles]
    if missing:
        raise SystemExit(f"{len(missing)} packet rows have no key entry, so no stratum can be named for them")
    by_role = {}
    for row in rows:
        by_role.setdefault(roles[row["token"]], []).append(row)
    populations = {role: len(group) for role, group in sorted(by_role.items())}
    shares = allocate(populations, size)
    rng = random.Random(seed)
    chosen = set()
    per_role_drawn = {}
    for role in sorted(shares):
        tokens = [row["token"] for row in by_role[role]]
        picked = draw(rng, tokens, shares[role])
        per_role_drawn[role] = picked
        chosen.update(picked)
    if len(chosen) != size:
        raise SystemExit(f"the draw produced {len(chosen)} distinct tokens for a target of {size}")
    # Sheet order is packet order, which the builder already shuffled: a second shuffle would be a second
    # thing to reproduce and a second chance to leak the strata back into the row order.
    sheet_rows = [row for row in rows if row["token"] in chosen]
    return fieldnames, sheet_rows, populations, shares, per_role_drawn


def judgments_per_row():
    """How many answers one row demands: every dimension column plus the three fixed questions."""
    return len(coding_columns()) + len(REQUIRED_COLUMNS)


def codebook_values_by_dimension():
    """Dimension -> the value names a sheet may contain, read from the codebook the coder was given.

    The scorer needs this because a value that is not on the frame's list is not a disagreement, it is a
    coding mistake, and scoring it as its own category would turn one reader's typo into evidence that the
    frame does not agree with itself.
    """
    out = {}
    for row in read_rows(CODEBOOK)[1]:
        out.setdefault(row["dimension"], set()).add(row["value"])
    return out


def codebook_partition():
    """(dimension value rows, fixed-question answer rows), split on whether the codebook's dimension is one.

    The codebook carries both kinds of row, and the two counts mean different things: the dimension rows
    are the vocabulary the corpus instrument declares, the fixed-question rows are the coder's own answer
    options. A handout that called the sum of the two a value count would contradict every other page of
    this project, so the split is made here, once, and both files read the same numbers.
    """
    dimensions = coding_columns()
    rows = read_rows(CODEBOOK)[1]
    fixed = [r for r in rows if r["dimension"] not in dimensions]
    return [r for r in rows if r["dimension"] in dimensions], fixed


def codebook_markdown():
    fields, rows = read_rows(CODEBOOK)
    for column in ("dimension", "cardinality", "question_this_dimension_answers", "coverage_state",
                   "value", "value_definition"):
        if column not in fields:
            raise SystemExit(f"the codebook CSV lost its {column} column, so this renderer has nothing to read")
    dimension_rows, fixed_rows = codebook_partition()
    dimension_count = len({r["dimension"] for r in dimension_rows})
    fixed_questions = len({r["dimension"] for r in fixed_rows})
    order, grouped = [], {}
    for row in rows:
        dimension = row["dimension"]
        if dimension not in grouped:
            grouped[dimension] = {"cardinality": row["cardinality"], "question": row["question_this_dimension_answers"],
                                  "coverage": row["coverage_state"], "values": []}
            order.append(dimension)
        grouped[dimension]["values"].append((row["value"], row["value_definition"]))
    lines = [
        "# Coding frame: the value lists",
        "",
        "Generated by `tools/make_pilot_packet.py` from `results/annotation_codebook.csv`. Do not edit this",
        "file: an edit here is a second version of the frame that the scorer has never seen, and `--check`",
        "will fail. Edit the codebook CSV and re-run the builder.",
        "",
        f"The frame has {dimension_count} dimensions carrying {len(dimension_rows)} values, and",
        f"{fixed_questions} questions that are not dimensions, with {len(fixed_rows)} answers between them.",
        "",
        "How to write an answer:",
        "",
        "- a column marked **single**: one value name, alone, exactly as spelled below;",
        "- a column marked **set**: as many value names as the proposition supports, separated by `;`;",
        "- an empty cell means *no value on this list applies*, which is an answer, not a gap;",
        "- a value name not on this list cannot be scored, so if none of these fit and you think something",
        "  does, write the word you would use in the `notes` column instead.",
        "",
    ]
    coding = coding_columns()
    absent = sorted(set(coding) - set(order))
    unlisted = sorted(set(order) - set(coding) - {r["dimension"] for r in fixed_rows})
    if unlisted:
        raise SystemExit(f"the codebook lists dimensions this frame does not code: {unlisted}")
    for dimension in sorted(coding):
        entry = grouped.get(dimension)
        column = coding[dimension]
        lines += [f"## `{column}`", ""]
        if entry is None:
            lines += ["**The codebook CSV carries no rows for this dimension at all.** Treat this column as one",
                      "you cannot answer; the reason it is empty is that this build has not written its value",
                      "definitions yet, and that is a gap in the instrument, not in your reading of the text.", ""]
            continue
        lines += [
            f"**Cardinality:** {entry['cardinality']}.  ",
            f"**Coverage in the corpus instrument:** `{entry['coverage']}`.",
            "",
            f"{entry['question']}",
            "",
            "| value | what it names |",
            "|---|---|",
        ]
        lines += [f"| `{value}` | {definition} |" for value, definition in sorted(entry["values"])]
        if not entry["values"]:
            lines += ["| *(no values listed)* | see the coverage state above |"]
        lines += [""]
    lines += [f"## The {fixed_questions} questions that are not dimensions", ""]
    for row_dimension in sorted({r["dimension"] for r in fixed_rows}):
        entry = grouped[row_dimension]
        vocabulary = ANSWER_VOCABULARIES.get(row_dimension) or {}
        if set(vocabulary) != {value for value, _ in entry["values"]}:
            raise SystemExit(
                f"{row_dimension} disagrees between the codebook CSV and the packet builder's own "
                "vocabulary, so the handout would teach answers the scorer refuses")
        lines += [f"### `{row_dimension}`", "", f"{entry['question']}", "",
                  "| answer | meaning |", "|---|---|"]
        lines += [f"| `{value}` | {definition} |" for value, definition in sorted(entry["values"])]
        lines += [""]
    if absent:
        lines += ["## Dimensions with no codebook rows", "", ", ".join(f"`{name}`" for name in absent), ""]
    return "\n".join(lines) + "\n"


def instructions_markdown(derivation):
    size = derivation["pilot_rows"]
    returned_sheets = list(derivation.get("coders_who_have_returned_sheets") or [])
    if returned_sheets:
        returned = (f"{len(returned_sheets)} sheet(s) on record: "
                    + ", ".join(f"`{coder}`" for coder in sorted(returned_sheets))
                    + ". A pilot needs two, coded independently, before any agreement figure is printed.")
    else:
        returned = ("Nobody has returned a sheet for this pilot as of the build recorded in\n"
                    "`results/pilot_slice.json`. Until two arrive, every agreement figure in this project\n"
                    "stays absent, and the project's own report says so rather than guessing at it.")
    return "\n".join([
        "# Pilot coding instructions",
        "",
        "Generated by `tools/make_pilot_packet.py`. The numbers below come from `results/pilot_slice.json`,",
        "which comes from the packet itself.",
        "",
        "## What you have been sent",
        "",
        f"- `{rel(OUT_SHEET)}` -- one row per proposition, {size} rows.",
        f"- `{rel(OUT_CODEBOOK_MD)}` -- the value lists every column may take.",
        "- this file.",
        "",
        "The sheet has the proposition in `proposition_text`, a longer stretch of the same passage in",
        "`context_window_text`, and where it came from in `locator_work` and `locator_passage`. It has no",
        "machine answers in it, and it has no answers anyone else has written.",
        "",
        "## What to do",
        "",
        "1. Copy the sheet. Put your own identifier in `coder_id` on every row, and today's date in",
        "   `coding_date`. Keep the copy, do not edit the file you were sent.",
        "2. Read `proposition_text`. That is what you are coding. `context_window_text` is there to tell",
        "   you who is speaking and what kind of passage it is; do not code the window.",
        f"3. Fill `{UNIT_COLUMN}` on every row. It is the one column that is never empty: if the row is not",
        "   one proposition about one divine referent, say so there rather than leaving the rest blank.",
        "4. For each dimension column, use the value names in the codebook exactly. Empty means none applies.",
        "5. Fill `concept_represented` and `doctrine_endorsed_by_text`. They are different questions: the",
        "   first asks whether a claim about divinity is on the page, the second asks whether the text's own",
        "   voice is committing to it. A passage reporting somebody else's belief scores",
        "   `represented` and `attributed_not_endorsed`.",
        "6. Send the file back. Do not send a summary, a spreadsheet of your conclusions, or a screenshot.",
        "",
        f"One row asks {derivation['judgments_per_row']} answers, so this sheet asks {derivation['judgments_total']}.",
        "It is a pilot: the point is to find out whether the frame can be filled in by someone who did not",
        "design it, and how long that takes. Record how long it took you in `notes` if you would like the",
        "timing to be part of the result.",
        "",
        "## The rule that makes the result worth anything",
        "",
        "**Two people code this independently.** That means: do not discuss a row while either of you is",
        "still coding; do not look at the other person's sheet; do not read the project's paper, its test",
        "report, or its machine output before you finish. Disagreement is the measurement. If you and the",
        "other coder agree on everything, the frame has told you nothing except that two people can copy",
        "each other.",
        "",
        "When you are unsure, choose `undecidable` where the column offers it, and leave a dimension cell",
        "empty otherwise. A confident wrong answer and an honest `undecidable` are scored differently, and",
        "the second one is more useful.",
        "",
        "## What the pilot is for, and what it will not do",
        "",
        "- it measures agreement between two readers on these columns;",
        "- it shows whether the segmentation is right often enough to be worth coding at full scale;",
        f"- it does **not** produce a precision figure: the frame declares {derivation['dimension_values_in_frame']}",
        f"  values and this slice holds {size} rows out of {derivation['packet_rows']}, which is not an",
        "  allocation that can say anything about any single value;",
        "- it does **not** produce a recall figure. Recall is estimated from the packet's probe rows at full",
        "  scale, and a pilot slice carries the probe strata only as a smoke test;",
        "- the scorer for the pilot (`python tools/score_annotation.py --pilot --coder-a A.csv --coder-b",
        "  B.csv`) never opens the machine's answer key, which is how it enforces the two sentences above.",
        "",
        "## Who is missing",
        "",
        returned,
        "",
        "## How this slice was chosen",
        "",
        "The rows are a random sample of the project's full coding packet, drawn by a published seed",
        f"(seed {derivation['seed']}, allocation largest-remainder proportional to the packet's own strata).",
        "The per-stratum counts and the token lists are in `results/pilot_slice.json` rather than here, on",
        "purpose: which rows the machine flagged, and how many of them it flagged nothing for, is information",
        "that can change how hard a reader looks, and a pilot where two coders know the machine's confidence",
        "is not a pilot of the frame. It changes nothing about how you code a row.",
        "",
    ]) + "\n"


def build(size=DEFAULT_SIZE, seed=DEFAULT_SEED):
    fieldnames, sheet_rows, populations, shares, per_role = select(size=size, seed=seed)
    for role in (CANDIDATE_ROLE, *PROBE_ROLES):
        if not shares.get(role):
            raise SystemExit(
                f"the slice carries no {role} rows, so it would not be piloting the design the packet "
                "actually uses -- a smaller --size is not the fix, the strata have to survive")
    cardinality = column_cardinalities()
    dimension_rows, fixed_rows = codebook_partition()
    for column in ("token", "proposition_text"):
        if column not in fieldnames:
            raise SystemExit(f"the packet lost its {column} column")
    for row in sheet_rows:
        for column in list(cardinality) + list(REQUIRED_COLUMNS):
            if (row.get(column) or "").strip():
                raise SystemExit(
                    f"the coder view is not blank: token {row['token']} already carries a value in {column}. "
                    "A sheet with machine answers in it cannot be coded blind, so the slice refuses to build.")
    judgments = judgments_per_row()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    packet_roles = plan.get("sample_roles") or {}
    derivation = {
        "instrument": "two-coder pilot slice, v3 packet",
        "status": "pilot_prepared_not_coded",
        "purpose": "executability and inter-coder agreement on a 300-row slice; not a corpus-scale "
                   "reliability, precision or recall estimate",
        "seed": seed,
        "pilot_rows": len(sheet_rows),
        "packet_rows": sum(populations.values()),
        "judgments_per_row": judgments,
        "judgments_total": len(sheet_rows) * judgments,
        "packet_judgments_per_coder": plan.get("sizing", {}).get("judgments_per_coder"),
        "dimensions_in_frame": len(cardinality),
        "dimension_values_in_frame": len(dimension_rows),
        "fixed_question_answers_in_frame": len(fixed_rows),
        "role_names_in_packet": {role: int(packet_roles.get(role, populations.get(role, 0)))
                                 for role in sorted(populations)},
        "strata": {
            role: {
                "packet_rows": populations[role],
                "allocated": shares[role],
                "inclusion_probability": round(shares[role] / populations[role], 10),
                "sampling_weight": populations[role] / shares[role] if shares[role] else None,
                "tokens": per_role[role],
            }
            for role in sorted(populations)
        },
        "allocation_rule": "largest-remainder proportional to the packet's own strata, ties broken by role "
                           "name; a simple random sample without replacement inside each stratum, drawn from "
                           "the stratum's tokens sorted lexicographically so the sequence cannot depend on a "
                           "Python hash seed",
        "sheet_order": "packet order, which the packet builder already shuffled; the slice applies no second "
                       "shuffle, so row order carries no stratum information that the packet did not already "
                       "suppress",
        "blinding": "the sheet is cut from the blinded coder view. The answer key is read only to learn which "
                    "stratum each token belongs to, and no key field is written into the sheet.",
        "required_columns": list(REQUIRED_COLUMNS),
        "source_files": {
            "packet": {"path": rel(PACKET), "sha256": sha256_of(PACKET),
                       "rows": sum(populations.values())},
            "key": {"path": rel(KEY), "sha256": sha256_of(KEY),
                    "used_for": "sample_role per token, nothing else"},
            "codebook": {"path": rel(CODEBOOK), "sha256": sha256_of(CODEBOOK)},
            "sampling_plan": {"path": rel(PLAN), "sha256": sha256_of(PLAN)},
        },
        "what_this_cannot_support": [
            "a precision estimate for any single value: the slice is too small to hold the packet's value "
            "strata, and the 11 census strata the packet planned are not represented here by design",
            "a recall estimate: the probe rows survive in the slice in proportion, not by design weight, "
            "and the pilot scorer never opens the key, so no miss can be counted",
            "an inter-coder reliability coefficient for the corpus: it is a coefficient for 300 rows coded "
            "by two people who volunteered for a pilot",
            "any figure at all until two sheets come back: this artifact records a prepared kit and the "
            "absence of coders, not a measurement",
        ],
        "coders_who_have_returned_sheets": [],
        "distributed_files": "filled by render_all: a file cannot carry its own SHA-256, so the derivation "
                             "hashes the three handouts and no number of its own is claimed here",
    }
    return fieldnames, sheet_rows, derivation


def render_sheet(fieldnames, sheet_rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for row in sheet_rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return buffer.getvalue().encode("utf-8")


def render_handouts(fieldnames, sheet_rows, derivation):
    """The three files a coder is handed. The derivation is deliberately not among them."""
    return {
        OUT_SHEET: render_sheet(fieldnames, sheet_rows),
        OUT_CODEBOOK_MD: crlf(codebook_markdown()),
        OUT_INSTRUCTIONS_MD: crlf(instructions_markdown(derivation)),
    }


def render_all(fieldnames, sheet_rows, derivation):
    handouts = render_handouts(fieldnames, sheet_rows, derivation)
    stamped = dict(derivation)
    stamped["distributed_files"] = {
        rel(path): {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for path, payload in sorted(handouts.items(), key=lambda item: rel(item[0]))
    }
    return {**handouts,
            OUT_DERIVATION: (json.dumps(stamped, indent=2, ensure_ascii=False) + "\n").encode("utf-8")}


def write(artifacts):
    for path, payload in artifacts.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--check", action="store_true",
                        help="re-render every artifact and report which ones differ, writing nothing")
    args = parser.parse_args()
    fieldnames, sheet_rows, derivation = build(size=args.size, seed=args.seed)
    artifacts = render_all(fieldnames, sheet_rows, derivation)
    if args.check:
        stale = [rel(path) for path, payload in sorted(artifacts.items(), key=lambda item: rel(item[0]))
                 if (Path(path).read_bytes() if Path(path).exists() else None) != payload]
        print(json.dumps({"status": "stale" if stale else "current", "differ": stale,
                          "pilot_rows": derivation["pilot_rows"], "seed": derivation["seed"]}, indent=2))
        return 1 if stale else 0
    write(artifacts)
    print(json.dumps({
        "pilot_rows": derivation["pilot_rows"],
        "packet_rows": derivation["packet_rows"],
        "judgments_per_row": derivation["judgments_per_row"],
        "judgments_total": derivation["judgments_total"],
        "strata": {role: {"packet": row["packet_rows"], "allocated": row["allocated"],
                          "weight": round(row["sampling_weight"], 4)}
                   for role, row in derivation["strata"].items()},
        "written": sorted(rel(path) for path in artifacts),
        "sha256": {rel(path): hashlib.sha256(payload).hexdigest()[:16]
                   for path, payload in artifacts.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
