#!/usr/bin/env python3
"""Divinity-ontology v2: orthogonal dimension coding over the full corpus.

Replaces the ten conflated grammars of tools/divinity_terms.py with seven
orthogonal dimensions, each carrying its own value set, its own coverage state
and its own speech-act constraint. Runs over every eligible passage -- no
top-N sampling anywhere -- and writes the complete candidate set.

Nothing in this file asserts that a concept exists in a tradition. A match is a
CANDIDATE for a human coder; the three-state assertion logic
(config/divinity_ontology.json > assertion_logic) is what keeps absence from
silently becoming a negative finding.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "config/divinity_ontology.json"
RULES = ROOT / "config/ontology_english_rules.json"
LEXICON = ROOT / "config/divinity_lexicon.json"
DEPENDENCE = ROOT / "config/source_dependence.json"
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"
MANIFEST = ROOT / "config/corpus_manifest.csv"
AUDIT = ROOT / "results/exclusivist_monotheism_audit.json"
OUT_ATTEST = ROOT / "results/ontology_attestations.jsonl.gz"
OUT_PASSAGE_MATRIX = ROOT / "results/ontology_passage_matrix.csv.gz"
OUT_WORK_MATRIX = ROOT / "results/ontology_work_states.csv"
OUT_SUMMARY = ROOT / "results/ontology_run_summary.json"

WS = re.compile(r"\s+")
WINDOW_BREAKS = re.compile(r"(?<=[.!?;:])\s+|(?<=\{|\})|(?<=\*)\s+")
SNIPPET_CHARS = 220

# D7 values that let a doctrinal cardinality claim stand. A negation outside
# these voices is a different fact and must not be scored as a doctrine.
DOCTRINAL_VOICES = {"asserted_doctrine", "philosophical_argument"}


def normalise(text):
    """Collapse whitespace runs and keep a norm->raw position map.

    v1 matched literal single-space patterns against raw Gutenberg text, which
    hard-wraps its lines: Isaiah 44:6 is stored as 'there is no\\nGod.' and the
    pattern silently missed it. Locators stay exact because every normalised
    index is mapped back through `map_to_raw`.
    """
    if "\n" not in text and "  " not in text and "\t" not in text and "\r" not in text:
        return text, list(range(len(text)))
    parts, map_to_raw, cursor = [], [], 0
    for match in WS.finditer(text):
        segment = text[cursor:match.start()]
        parts.append(segment)
        map_to_raw.extend(range(cursor, cursor + len(segment)))
        parts.append(" ")
        map_to_raw.append(match.start())
        cursor = match.end()
    parts.append(text[cursor:])
    map_to_raw.extend(range(cursor, len(text)))
    return "".join(parts), map_to_raw


def raw_match_span(text, map_to_raw, match):
    """The half-open raw span of a match, trimmed to the words it reports.

    Every other instrument here promises that a record's span lands on its surface text. A match that begins
    or ends on a normalised whitespace placeholder would otherwise resolve to raw characters the reader never
    sees, because surface_text strips them.
    """
    start = map_to_raw[match.start()]
    end = map_to_raw[match.end()] if match.end() < len(map_to_raw) else len(text)
    span = text[start:end]
    stripped = span.strip()
    start += len(span) - len(span.lstrip())
    return start, start + len(stripped)


def windows_of(norm_text):
    """Utterance windows: one bounded claim run, the unit the frame codes."""
    bounds, cursor = [], 0
    for match in WINDOW_BREAKS.finditer(norm_text):
        end = match.start()
        if end - cursor > 1:
            bounds.append((cursor, end))
        cursor = match.end()
    if len(norm_text) - cursor > 1:
        bounds.append((cursor, len(norm_text)))
    if not bounds:
        bounds = [(0, len(norm_text))]
    return bounds


def as_spec(spec):
    """D7's value list is prose definitions, the others are rule objects."""
    return spec if isinstance(spec, dict) else {}


def build_matcher(values, prefix):
    """One alternation per dimension, each alternative in its own named group.

    Seven scans of a passage instead of one scan per value; group names carry
    the value identity back out of the match.
    """
    alternatives, name_map = [], {}
    for index, (value, raw_spec) in enumerate(sorted(values.items())):
        spec = as_spec(raw_spec)
        patterns = spec.get("patterns") or []
        if not patterns:
            continue
        name = f"{prefix}{index:02d}"
        joined = "|".join(f"(?:{p})" for p in patterns)
        alternatives.append(f"(?P<{name}>{joined})")
        name_map[name] = value
    if not alternatives:
        return None, {}
    return re.compile("|".join(alternatives), re.IGNORECASE), name_map


def window_at(ends, bounds, position):
    """The window whose half-open span contains `position`.

    `ends` holds exclusive upper bounds, so the answer is the first index whose
    end is strictly greater than the position -- bisect_right, not bisect_right
    minus one. The minus-one version silently shifted every window by one and
    labelled claims with the speech act of their neighbour.
    """
    index = bisect_right(ends, position)
    return bounds[min(index, len(bounds) - 1)]


def compile_all():
    ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    dimensions = rules["dimensions"]
    matchers, value_names = {}, {}
    for key, spec in dimensions.items():
        prefix = key.split("_")[0].lower() + "v"
        matcher, name_map = build_matcher(spec["values"], prefix)
        matchers[key], value_names[key] = matcher, name_map
    markers, marker_names = [], {}
    marker_specs = [(label, spec) for label, spec in sorted(rules["speech_act_markers"].items())
                    if isinstance(spec, dict) and spec.get("pattern")]
    for index, (label, spec) in enumerate(marker_specs):
        markers.append(f"(?P<m{index:02d}>{spec['pattern']})")
        marker_names[f"m{index:02d}"] = label
    speech = re.compile("|".join(markers), re.IGNORECASE)
    return ontology, rules, matchers, value_names, speech, marker_names


def speech_acts(text, bounds, ends, speech, marker_names):
    """D7 per window, decided from window shape before any term is read."""
    per_window = {}
    for match in speech.finditer(text):
        start, end = window_at(ends, bounds, match.start())
        name = next(k for k, v in match.groupdict().items() if v is not None)
        label = marker_names[name]
        per_window.setdefault((start, end), set()).add(label)
    return per_window


MARKER_TO_D7 = {
    "conditional_hypothetical": "conditional_hypothetical",
    "reported_speech": "reported_speech_of_opponent",
    "question": "doubt_or_inquiry",
    "vocative_address": "doxology_or_address",
    "command_or_prohibition": "prescriptive_command",
    "non_divine_speaker": "boast_of_non_divine_claimant",
    "editorial_frame": "editorial_or_ethnographic_description",
    "argument_frame": "philosophical_argument",
    "mythic_narration": "mythic_narration",
    "denial_of_other_gods": "polemic_denial",
}
# When several markers fire in one window, the one that most restricts what the
# sentence can be read as claiming wins; a confession inside a conditional is a
# conditional, and a doctrine inside reported speech is somebody else's view.
D7_PRECEDENCE = ["boast_of_non_divine_claimant", "conditional_hypothetical",
                 "reported_speech_of_opponent", "editorial_or_ethnographic_description",
                 "prescriptive_command", "doubt_or_inquiry", "polemic_denial",
                 "philosophical_argument", "doxology_or_address", "mythic_narration"]


FIRST_PERSON_CLAIM = re.compile(r"\bi\s+am\b|\bmine\b|\bme\b|\bnone\s+else\b|\bno\s+god\s+but\b", re.IGNORECASE)


def choose_d7(markers, window_text):
    labels = {MARKER_TO_D7[m] for m in markers if m in MARKER_TO_D7}
    for candidate in D7_PRECEDENCE:
        if candidate not in labels:
            continue
        # "king", "city" and "pharaoh" are ordinary narrative nouns, so the
        # non-divine-speaker marker fires constantly in romance and ethnography.
        # It may only outrank the other readings when a first-person divine claim
        # is actually present in the window, which is the condition the rule file states.
        if candidate == "boast_of_non_divine_claimant" and not FIRST_PERSON_CLAIM.search(window_text):
            continue
        return candidate
    return "asserted_doctrine"


def dependence_lookup():
    """Work-level non-independence plus, when present, the audit's passage-level flags."""
    rules = json.loads(DEPENDENCE.read_text(encoding="utf-8"))
    dependent = defaultdict(set)
    for rule in rules["pair_rules"]:
        if rule.get("exclude_from_independent_analysis"):
            dependent[rule["right_work"]].add((rule["left_work"], rule["relationship"]))
            dependent[rule["left_work"]].add((rule["right_work"], rule["relationship"]))
    for family in rules["work_families"]:
        if family.get("exclude_from_independent_analysis"):
            for work in family["work_ids"]:
                dependent[work].add(("family:" + family["family_id"], family["relationship"]))
    audit_flags = {}
    if AUDIT.exists():
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        for record in audit.get("matches", []):
            if not record.get("counts_as_independent_attestation", True):
                audit_flags[record.get("passage_id")] = record.get("original_textual_source", "dependent reprint")
    return dependent, audit_flags


def work_attributes():
    with MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        return {row["work_id"]: row for row in csv.DictReader(handle)}


def run(limit=None):
    ontology, rules, matchers, value_names, speech, marker_names = compile_all()
    passages = [json.loads(line) for line in PASSAGES.read_text(encoding="utf-8").splitlines()]
    if limit:
        passages = passages[:limit]
    attributes = work_attributes()
    dependent, audit_flags = dependence_lookup()
    coverage = {key: spec["coverage_state"] for key, spec in rules["dimensions"].items()}
    value_coverage = {(key, value): (as_spec(value_spec).get("coverage_state") or coverage[key])
                      for key, spec in rules["dimensions"].items()
                      for value, value_spec in spec["values"].items()}

    records = []
    blocked = Counter()
    per_work_value = defaultdict(int)
    per_passage_value = defaultdict(int)
    eligible_words = 0
    passage_rows = []

    for passage in passages:
        if not passage["eligible_for_similarity"]:
            continue
        eligible_words += passage["word_count"] or 0
        work = passage["work_id"]
        norm, map_to_raw = normalise(passage["text"])
        bounds = windows_of(norm)
        ends = [b[1] for b in bounds]
        acts = speech_acts(norm, bounds, ends, speech, marker_names)
        body_start = passage["body_char_start"]
        for key, matcher in matchers.items():
            if matcher is None:
                continue
            for match in matcher.finditer(norm):
                value = value_names[key][match.lastgroup]
                start, end = window_at(ends, bounds, match.start())
                markers = acts.get((start, end), set())
                window = norm[start:end]
                d7 = choose_d7(markers, window)
                state, note = "candidate", ""
                if key == "D2_plurality" and value in ("sole_existent_others_unreal", "none") \
                        and d7 not in DOCTRINAL_VOICES:
                    state, note = "blocked_by_speech_act", f"D7={d7}"
                    blocked[f"{value}|{d7}"] += 1
                if value_coverage.get((key, value), "instrumented") == "not_yet_instrumented":
                    state, note = "not_yet_instrumented", "value has no validated detector"
                needs_human = bool(as_spec(rules["dimensions"][key]["values"][value]).get("disambiguation_needed"))
                if state == "candidate" and needs_human:
                    state = "candidate_requires_human_disambiguation"
                raw_start = body_start + map_to_raw[min(start, len(map_to_raw) - 1)]
                # Both spans publish half-open [start, end) bounds in raw coordinates, matching the
                # convention every other instrument here uses for char_end.
                raw_end = body_start + (map_to_raw[end] if end < len(map_to_raw)
                                        else len(passage["text"]))
                match_raw_start, match_raw_end = raw_match_span(passage["text"], map_to_raw, match)
                match_raw_start += body_start
                match_raw_end += body_start
                snippet = " ".join(window.split())[:SNIPPET_CHARS]
                dependents = sorted({f"{other} ({rel})" for other, rel in dependent.get(work, set())})
                record = {
                    "record_id": f"{passage['passage_id']}:{key}:{match_raw_start}:{match.lastgroup}",
                    "work_id": work, "passage_id": passage["passage_id"],
                    "section_index": passage["section_index"], "section_heading": passage["section_heading"],
                    "dimension": key, "value": value, "surface_text": " ".join(match.group(0).split()),
                    "char_start": match_raw_start, "char_end": match_raw_end,
                    "window_char_start": raw_start, "window_char_end": raw_end,
                    "expression_language": "English (translation)", "snippet": snippet,
                    "D7_speech_act": d7, "speech_act_markers": sorted(markers),
                    "assertion_state": state, "block_reason": note,
                    "counts_as_independent_attestation": not dependents,
                    "work_dependence": dependents,
                    "anthology_reprint_flag": audit_flags.get(passage["passage_id"], ""),
                    "region": attributes.get(work, {}).get("region", ""),
                    "tradition": attributes.get(work, {}).get("tradition", ""),
                    "coder_id": None, "second_coder_id": None, "agreement_status": "not_reviewed",
                    "verification_status": "machine_candidate_unadjudicated",
                }
                records.append(record)
                if state == "candidate":
                    per_work_value[(work, key, value)] += 1
                    per_passage_value[(passage["passage_id"], key, value)] += 1
        passage_rows.append((passage["passage_id"], work,
                             {f"{k}={v}": per_passage_value[(passage['passage_id'], k, v)]
                              for k, specs in rules["dimensions"].items() for v in specs["values"]
                              if per_passage_value[(passage["passage_id"], k, v)]}))

    return dict(records=records, blocked=blocked, per_work_value=per_work_value,
                passage_rows=passage_rows, eligible_words=eligible_words,
                coverage=coverage, value_coverage=value_coverage,
                dimensions=ontology["dimensions"], rules=rules)


def write_outputs(result):
    records = result["records"]
    with gzip.open(OUT_ATTEST, "wt", encoding="utf-8", newline="") as handle:
        for record in sorted(records, key=lambda r: (r["work_id"], r["passage_id"], r["char_start"], r["dimension"])):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    columns = sorted({f"{r['dimension']}={r['value']}" for r in records})
    with gzip.open(OUT_PASSAGE_MATRIX, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["passage_id", "work_id", *columns])
        for passage_id, work, counts in sorted(result["passage_rows"]):
            writer.writerow([passage_id, work] + [counts.get(c, "") for c in columns])

    works = sorted({r["work_id"] for r in records})
    dimension_keys = sorted(result["dimensions"])
    non_independent_works = {r["work_id"] for r in records if not r["counts_as_independent_attestation"]}
    with OUT_WORK_MATRIX.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["work_id", "dimension", "value", "candidate_count", "coverage_state",
                         "work_has_dependent_reprint_records", "counts_as_independent"])
        for work in works:
            dependents = work in non_independent_works
            for key in dimension_keys:
                for value in sorted(result["dimensions"][key]["values"]):
                    count = result["per_work_value"].get((work, key, value), 0)
                    state = result["value_coverage"].get((key, value), "instrumented")
                    writer.writerow([work, key, value, count, state,
                                     "yes" if dependents else "no",
                                     "yes" if count and not dependents else "no"])

    states = Counter(r["assertion_state"] for r in records)
    summary = {
        "instrument": "divinity-ontology v2",
        "purpose": "code divine-concept states on seven orthogonal dimensions across the whole corpus, "
                   "for an inheritance-and-transformation question, not for a universality test",
        "corpus": {"eligible_passages": len(result["passage_rows"]), "eligible_words": result["eligible_words"],
                   "works_with_candidates": len(works)},
        "candidate_records_total": len(records),
        "assertion_state_tally": dict(sorted(states.items())),
        "blocked_by_speech_act": [
            {"value": key.split("|")[0], "speech_act": key.split("|")[1], "count": value}
            for key, value in result["blocked"].most_common()],
        "dimension_coverage": result["coverage"],
        "speech_act_block_scope": {
            "policed": ["D2_plurality=sole_existent_others_unreal", "D2_plurality=none"],
            "not_policed": "every other dimension value",
            "why": "D7 blocks a reading only where the value itself is a doctrinal assertion whose force depends "
                   "on who is speaking: 'only this divinity exists' and 'no divinities exist'. A matched D1 "
                   "personal_agent or D4 creator function inside an opponent's reported speech is still a "
                   "candidate, because the window may be narrating a cosmology the text reports rather than "
                   "endorses, and that distinction needs a reader, not a rule.",
            "consequence": "the blocked count is a floor on speech-act sensitivity, not the frame's total "
                           "caution. D7 is published as a field on every record and is scored against the "
                           "two-coder design in TRACK_B_METHOD_v2.md §9; do not infer from a small block count "
                           "that the instrument trusts its hits.",
        },
        "values_not_yet_instrumented": sorted({f"{k}={v}" for (k, v), s in result["value_coverage"].items()
                                               if s == "not_yet_instrumented"}),
        "reading_rules": [
            "`candidate` means a human must code it; it does not mean attested.",
            "`blocked_by_speech_act` is the frame refusing to read a doctrine out of a conditional, a "
            "question, an opponent's reported speech or a non-divine claimant's boast. v1 had no such state.",
            "`not_yet_instrumented` values are undetectable by this instrument and must never be reported "
            "as absent from a tradition.",
            "no number in this file may be used to order concepts historically: composition, witness and "
            "translation dates are separate fields in the ontology and are not yet filled.",
        ],
        "reproducibility": {
            "passages_sha256": hashlib.sha256(PASSAGES.read_bytes()).hexdigest(),
            "rules_sha256": hashlib.sha256(RULES.read_bytes()).hexdigest(),
            "ontology_sha256": hashlib.sha256(ONTOLOGY.read_bytes()).hexdigest(),
            "lexicon_sha256": hashlib.sha256(LEXICON.read_bytes()).hexdigest(),
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "randomness": "none: sorted iteration, no sampling, no fitted parameters",
            "python": sys.version.split()[0],
        },
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="code only the first N eligible passages (development runs)")
    args = parser.parse_args()
    summary = write_outputs(run(args.limit))
    print(json.dumps({k: summary[k] for k in
                      ["corpus", "candidate_records_total", "assertion_state_tally", "dimension_coverage",
                       "values_not_yet_instrumented"]}, indent=2))
    print(f"wrote {OUT_ATTEST.name}, {OUT_PASSAGE_MATRIX.name}, {OUT_WORK_MATRIX.name}, {OUT_SUMMARY.name}")


if __name__ == "__main__":
    main()
