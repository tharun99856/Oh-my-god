#!/usr/bin/env python3
"""Divinity-ontology v3: twelve analytically distinct dimensions coded proposition by proposition.

What changed from v2, and why each change was made:

* D2 answered three questions at once, so plurality, the reality of rivals and the
  permission of worship were one label. It is now D2a/D2b/D2c, scanned independently.
* D7 answered four (speaker, act, genre, commitment), and they are now D7a-d. The old
  label set was not mutually exclusive: a hymn contains doctrine and a conditional
  contains a reported statement, so forcing one slot invented conflicts.
* D1, D3, D5 and D6 are set-valued, because a divinity can be personal AND the ground of
  being, transcendent AND indwelling, eternal AND cyclically recurrent.
* The unit of analysis is the proposition, not the utterance window. A window carrying
  "the creator made the world, other beings existed before it, those beings were
  subordinate" is three claims and is coded as three.
* Nothing is refused any more. The single `blocked_by_speech_act` state answered two
  questions with one label and discarded 54 records that did represent a concept. Every
  record now carries `conceptual_presence`, `doctrinal_endorsement` and
  `historical_transmission` separately, so a withheld endorsement costs the frame nothing
  it can say about the concept. `doctrinal_endorsement` is D7d's value copied onto the
  record -- one detector reading published under the answer-name of the frame's second
  question, not a second measurement of it.

"Analytically distinct" is deliberately not "orthogonal". Orthogonality is an empirical
property of observations, and no coder has scored these twelve questions yet; what is
claimed from the definitions alone is that the twelve are separately stateable and no one
of them restates another. The English detectors make the point the other way: one surface
string can populate D2a, D2b and D2c at once, so the dimensions are correlated in
observation while remaining distinct in definition.

Still English-translation only. The frame is multilingual-ready: the architecture, the
record shape and the lexicon scaffolding exist, and no source-language detector is
operational. A match remains a CANDIDATE for a human coder; the three-state assertion
logic (config/divinity_ontology.json > assertion_logic) is what keeps absence from
silently becoming a negative finding.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_gzip import gzip_text_writer  # noqa: E402

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

# Proposition segmentation. A window is broken where a connector can begin a new
# subject-predicate group. This is a detector, not a grammar: it over-splits coordinated
# predicates and under-splits parataxis, and `proposition_segmentation` in the run summary
# says so rather than pretending otherwise.
COORDINATOR = r"(?:and|but|or|nor|for|yet|so|then|therefore)"
SUBORDINATOR = (r"(?:that|which|who|whom|whose|when|while|where|since|because|although|though|"
                r"if|until|before|after|lest|whensoever|wherefore)")
PROPOSITION_BREAKS = re.compile(
    rf"(?:\s*[,;]\s*|\s+)(?:{COORDINATOR}\s+)?(?={SUBORDINATOR}\b)|\s+{COORDINATOR}\s+",
    re.IGNORECASE)
MIN_PROPOSITION_WORDS = 3
# A span this long is not a proposition whatever the connector analysis said: the KJV table
# of contents is one unbroken run with no sentence break and no connector. Flagged rather
# than silently coded, because a record whose "proposition" is a page of titles would make
# the proposition-level claim false.
MAX_PROPOSITION_CHARS = 300

PROPER_CANDIDATES = re.compile(
    r"\b(?:God|GOD|Lord|LORD|Allah|Brahman|Brahma|Shiva|Vishnu|Ishvara|Zeus|Jupiter|Odin|Thor|"
    r"Marduk|Ashur|Anu|Enlil|Hathor|Isis|El|Elohim|Yahweh|Jehovah|Tao|Dao|Ahura\s+Mazda)\b")
DIVINE_CLASS = re.compile(
    r"\b(?:god|gods|goddess|goddesses|deity|deities|divinity|the\s+divine|spirit|beings?|powers?|"
    r"idol|idols|images?)\b", re.IGNORECASE)
PRONOUN = re.compile(r"\b(?:he|him|his|himself|it|its|itself|thou|thee|thy|thine|you|your|ye|we|our|"
                     r"they|them|their)\b", re.IGNORECASE)

FIRST_PERSON_CLAIM = re.compile(r"\bi\s+am\b|\bmine\b|\bme\b|\bnone\s+else\b|\bno\s+god\s+but\b",
                                re.IGNORECASE)

# Marker -> the four D7 answers. One marker rarely settles all four questions, so these
# tables are partial by design and anything a marker does not decide is `undecidable`,
# which is a value in every D7 dimension rather than a gap.
MARKER_TO_D7A = {
    "reported_speech": "character_within_narrative",
    "non_divine_speaker": "opponent_or_denier",
    "editorial_frame": "editorial_or_ethnographic_frame",
    "vocative_address": "praying_or_praising_human_voice",
}
MARKER_TO_D7B = {
    "conditional_hypothetical": "condition",
    "reported_speech": "report",
    "question": "question",
    "vocative_address": "address_or_praise",
    "command_or_prohibition": "command",
    "non_divine_speaker": "boast",
    "denial_of_other_gods": "deny",
}
MARKER_TO_D7C = {
    "vocative_address": "hymn_or_prayer",
    "command_or_prohibition": "legal_statute",
    "argument_frame": "philosophical_argument",
    "mythic_narration": "mythic_narrative",
    "editorial_frame": "commentary_or_description",
    "question": "doubt_or_inquiry",
}
MARKER_TO_D7D = {
    "conditional_hypothetical": "suspended_or_held_open",
    "reported_speech": "attributed_not_endorsed",
    "question": "suspended_or_held_open",
    "editorial_frame": "attributed_not_endorsed",
    "non_divine_speaker": "rejected_in_text",
    "vocative_address": "not_applicable_non_assertive",
    "command_or_prohibition": "not_applicable_non_assertive",
    "mythic_narration": "undecidable",
}
# When several markers fire on one proposition, the one that most restricts what the clause
# can be read as claiming decides the act: a confession inside a conditional is a
# conditional, and a doctrine inside reported speech is somebody else's view.
D7B_PRECEDENCE = ["boast", "condition", "question", "command", "deny", "address_or_praise", "report",
                  "negate_apophatically", "assert"]
DEFAULT_ATTRIBUTION = "narrator_or_scribe"
ASSERTION_MODE = {
    "assert": "asserted", "question": "questioned", "condition": "conditional", "report": "attributed",
    "boast": "attributed_rejected_by_frame", "deny": "denied", "command": "prescribed",
    "address_or_praise": "addressed", "negate_apophatically": "apophatically_negated",
    "undecidable": "undetermined",
}
# The two fields that together license a doctrinal tally. A hymn addresses and a command
# prescribes; neither asserts that something is so, so neither endorses.
AFFIRMING_COMMITMENT = {"endorsed_by_text"}
AFFIRMING_ACTS = {"assert", "deny"}


def normalise(text):
    """Collapse whitespace runs and keep a norm->raw position map.

    v1 matched literal single-space patterns against raw Gutenberg text, which hard-wraps
    its lines: Isaiah 44:6 is stored as 'there is no\\nGod.' and the pattern silently
    missed it. Locators stay exact because every normalised index is mapped back through
    `map_to_raw`.
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


def raw_slice_bounds(text, map_to_raw, start, end):
    """Half-open raw bounds of a normalised [start, end) span."""
    lo = map_to_raw[min(start, len(map_to_raw) - 1)]
    hi = map_to_raw[end] if end < len(map_to_raw) else len(text)
    return lo, hi


def raw_match_span(text, map_to_raw, match):
    """The half-open raw span of a match, trimmed to the words it reports.

    A match that begins or ends on a normalised whitespace placeholder would otherwise
    resolve to raw characters the reader never sees, because surface_text strips them.
    """
    start, end = raw_slice_bounds(text, map_to_raw, match.start(), match.end())
    span = text[start:end]
    stripped = span.strip()
    start += len(span) - len(span.lstrip())
    return start, start + len(stripped)


def windows_of(norm_text):
    """Utterance windows: one bounded claim run, retained as the context of a proposition."""
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


def propositions_of(window):
    """Split one window into the propositions a reader would count as separate claims.

    Returns half-open spans into `window`. A fragment too short to carry a subject and a
    predicate is merged into the proposition before it, because "and he said" is not a
    claim on its own.
    """
    cuts, cursor = [], 0
    for match in PROPOSITION_BREAKS.finditer(window):
        if match.start() > cursor:
            cuts.append((cursor, match.start()))
        cursor = match.end()
    if len(window) > cursor:
        cuts.append((cursor, len(window)))
    if not cuts:
        return [(0, len(window))]
    merged = []
    for start, end in cuts:
        fragment = window[start:end].strip(" ,;:")
        if not fragment:
            continue
        if merged and len(fragment.split()) < MIN_PROPOSITION_WORDS:
            merged[-1] = (merged[-1][0], end)
            continue
        merged.append((start, end))
    return merged or [(0, len(window))]


def as_spec(spec):
    """Value specs are rule objects; kept for the prose-only entries the frame inherited."""
    return spec if isinstance(spec, dict) else {}


def build_matcher(values, prefix):
    """One alternation per dimension, each alternative in its own named group."""
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

    `ends` holds exclusive upper bounds, so the answer is the first index whose end is
    strictly greater than the position -- bisect_right, not bisect_right minus one. The
    minus-one version silently shifted every window by one and labelled claims with the
    speech act of their neighbour.
    """
    index = bisect_right(ends, position)
    return bounds[min(index, len(bounds) - 1)]


def span_covering(spans, start, end):
    """The proposition a match belongs to, widened until it holds the whole match.

    `no God beside me` can begin in one proposition and finish in the next, because the
    connector between them is exactly where the split was made. Assigning such a match to
    the clause it started in would publish a record whose span runs past its own
    proposition text, so the two are merged instead.
    """
    index = next((i for i, (s, e) in enumerate(spans) if s <= start < e), None)
    if index is None:
        return spans[0] if spans else (0, 0)
    lo, hi = spans[index]
    while hi < end and index + 1 < len(spans):
        index += 1
        hi = spans[index][1]
    return lo, hi


def compile_all():
    ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    dimensions = rules["dimensions"]
    matchers, value_names = {}, {}
    for key, spec in dimensions.items():
        prefix = re.sub(r"[^A-Za-z0-9]", "", key.split("_")[0]).lower() + "v"
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


def markers_by_window(text, bounds, ends, speech, marker_names):
    """Marker labels per window, decided from clause shape before any term is read."""
    per_window = defaultdict(set)
    for match in speech.finditer(text):
        start, end = window_at(ends, bounds, match.start())
        name = next(k for k, v in match.groupdict().items() if v is not None)
        per_window[(start, end)].add(marker_names[name])
    return per_window


def d7_answers(markers, proposition_text):
    """The four D7 readings of one proposition, from the markers that fired on its window."""
    boast_is_earned = "non_divine_speaker" in markers and bool(FIRST_PERSON_CLAIM.search(proposition_text))
    acts = {MARKER_TO_D7B[m] for m in markers if m in MARKER_TO_D7B}
    if "non_divine_speaker" in markers and not boast_is_earned:
        acts.discard("boast")
    d7b = next((candidate for candidate in D7B_PRECEDENCE if candidate in acts), "assert")

    # Self-speech and praying voice are detected from the proposition itself: the messenger
    # formula and the vocative are the only attribution evidence this instrument claims, and
    # where neither fires the framing voice is a stated default, not a finding.
    speakers = {MARKER_TO_D7A[m] for m in markers if m in MARKER_TO_D7A}
    if "non_divine_speaker" in markers and not boast_is_earned:
        speakers.discard("opponent_or_denier")
    self_speech = bool(FIRST_PERSON_CLAIM.search(proposition_text)) and "god" in proposition_text.lower()
    if len(speakers) == 1:
        d7a, basis = next(iter(speakers)), "speech-act marker in the window"
    elif len(speakers) > 1:
        d7a, basis = "undecidable", "several attribution readings fired and none outranks the others"
    elif self_speech:
        d7a, basis = "divine_self_speech", "first-person divine formula in the proposition"
    else:
        d7a, basis = DEFAULT_ATTRIBUTION, "default: no quote frame and no self-speech formula"

    genres = {MARKER_TO_D7C[m] for m in markers if m in MARKER_TO_D7C}
    d7c = next(iter(genres)) if len(genres) == 1 else "undecidable"

    commitments = {MARKER_TO_D7D[m] for m in markers if m in MARKER_TO_D7D}
    if len(commitments) == 1:
        d7d = next(iter(commitments))
    elif len(commitments) > 1:
        d7d = "undecidable"
    elif d7b in AFFIRMING_ACTS:
        d7d = "endorsed_by_text"
    else:
        d7d = "not_applicable_non_assertive"
    return {"D7a_speaker_attribution": d7a, "D7b_speech_act": d7b, "D7c_discourse_genre": d7c,
            "D7d_epistemic_commitment": d7d, "attribution_basis": basis}


def referent_of(proposition_text, matched_text):
    """What the proposition is about, as far as a term detector can tell."""
    proper = [p.strip() for p in PROPER_CANDIDATES.findall(proposition_text)]
    classes = [c.strip().lower() for c in DIVINE_CLASS.findall(proposition_text)]
    candidates = sorted(set(proper) | set(classes))
    if proper and classes:
        kind = "named_class_mixed"
    elif len(proper) > 1:
        kind = "multiple_named_candidates"
    elif len(proper) == 1:
        kind = "proper_name_candidate"
    elif classes:
        kind = "class_term"
    elif PRONOUN.search(proposition_text):
        kind = "pronoun"
    else:
        kind = "undetermined"
    return {"referent_surface": proper[0] if kind == "proper_name_candidate" else matched_text,
            "referent_kind": kind, "referent_candidates": candidates[:6],
            "referent_ambiguous": len(candidates) > 1}


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
    dimensions = rules["dimensions"]
    coverage = {key: spec["coverage_state"] for key, spec in dimensions.items()}
    cardinality = {key: spec.get("cardinality", "single") for key, spec in dimensions.items()}
    value_coverage = {(key, value): (as_spec(value_spec).get("coverage") or coverage[key])
                      for key, spec in dimensions.items() for value, value_spec in spec["values"].items()}

    records = []
    conflicts = Counter()
    endorsement_tally = Counter()
    proposition_counts = Counter()
    per_work_value = defaultdict(int)
    per_passage_value = defaultdict(int)
    eligible_words = 0
    passage_rows = []

    for passage in passages:
        if not passage["eligible_for_similarity"]:
            continue
        eligible_words += passage["word_count"] or 0
        work = passage["work_id"]
        text = passage["text"]
        norm, map_to_raw = normalise(text)
        bounds = windows_of(norm)
        ends = [b[1] for b in bounds]
        proposition_spans = {(start, end): [(start + a, start + b)
                                            for a, b in propositions_of(norm[start:end])]
                             for start, end in bounds}
        markers = markers_by_window(norm, bounds, ends, speech, marker_names)
        body_start = passage["body_char_start"]
        matched_propositions = set()
        passage_records = []

        for key, matcher in matchers.items():
            if matcher is None:
                continue
            for match in matcher.finditer(norm):
                value = value_names[key][match.lastgroup]
                window_bounds = window_at(ends, bounds, match.start())
                prop_start, prop_end = span_covering(proposition_spans[window_bounds],
                                                     match.start(), match.end())
                proposition = norm[prop_start:prop_end]
                window = norm[window_bounds[0]:window_bounds[1]]
                matched_propositions.add((prop_start, prop_end))
                answers = d7_answers(markers.get(window_bounds, set()), proposition)
                d7b, d7d = answers["D7b_speech_act"], answers["D7d_epistemic_commitment"]
                surface = " ".join(match.group(0).split())
                overlong = len(proposition) > MAX_PROPOSITION_CHARS
                state, note = "candidate", ""
                if value_coverage.get((key, value), "instrumented") == "not_yet_instrumented":
                    state, note = "not_yet_instrumented", "value has no validated English detector"
                elif overlong:
                    state, note = ("candidate_requires_human_disambiguation",
                                   "segmentation produced a run-on span, not a proposition")
                elif as_spec(dimensions[key]["values"][value]).get("disambiguation_needed"):
                    state, note = "candidate_requires_human_disambiguation", "value is declared disambiguation-prone"
                lo, hi = raw_slice_bounds(text, map_to_raw, prop_start, prop_end)
                wlo, whi = raw_slice_bounds(text, map_to_raw, *window_bounds)
                match_lo, match_hi = raw_match_span(text, map_to_raw, match)
                dependents = sorted({f"{other} ({rel})" for other, rel in dependent.get(work, set())})
                record = {
                    "record_id": f"{passage['passage_id']}:{key}:{body_start + lo}:{match.lastgroup}",
                    "work_id": work, "passage_id": passage["passage_id"],
                    "section_index": passage["section_index"], "section_heading": passage["section_heading"],
                    "dimension": key, "value": value, "cardinality": cardinality[key],
                    "surface_text": surface,
                    "char_start": body_start + match_lo, "char_end": body_start + match_hi,
                    "proposition_text": " ".join(proposition.split()),
                    "proposition_char_start": body_start + lo, "proposition_char_end": body_start + hi,
                    "proposition_overlong": overlong,
                    "window_char_start": body_start + wlo, "window_char_end": body_start + whi,
                    "D7a_speaker_attribution": answers["D7a_speaker_attribution"],
                    "D7b_speech_act": d7b,
                    "D7c_discourse_genre": answers["D7c_discourse_genre"],
                    "D7d_epistemic_commitment": d7d,
                    "attribution_basis": answers["attribution_basis"],
                    **referent_of(proposition, surface),
                    "assertion_mode": ASSERTION_MODE[d7b],
                    "conceptual_presence": ("represented_in_passage" if state != "not_yet_instrumented"
                                            else "undecidable_from_available_sources"),
                    "doctrinal_endorsement": d7d if state != "not_yet_instrumented" else "undecidable",
                    "historical_transmission": "not_yet_assessable",
                    "counts_as_affirmative_doctrine": bool(d7d in AFFIRMING_COMMITMENT and d7b in AFFIRMING_ACTS
                                                           and state != "not_yet_instrumented"),
                    "expression_language": "English (translation)",
                    "snippet": " ".join(window.split())[:SNIPPET_CHARS],
                    "speech_act_markers": sorted(markers.get(window_bounds, set())),
                    "assertion_state": state, "state_note": note,
                    "counts_as_independent_attestation": not dependents,
                    "work_dependence": dependents,
                    "anthology_reprint_flag": audit_flags.get(passage["passage_id"], ""),
                    "region": attributes.get(work, {}).get("region", ""),
                    "tradition": attributes.get(work, {}).get("tradition", ""),
                    "date_earliest": None, "date_latest": None, "dating_basis": None,
                    "coder_id": None, "second_coder_id": None, "agreement_status": "not_reviewed",
                    "verification_status": "machine_candidate_unadjudicated",
                }
                records.append(record)
                passage_records.append(record)
                endorsement_tally[record["doctrinal_endorsement"]] += 1

        # A single-valued dimension must not carry two values of one proposition. The clash is
        # recorded and handed to a reader; v2 chose by precedence and published no trace.
        by_proposition = defaultdict(set)
        for record in passage_records:
            if record["cardinality"] == "single":
                by_proposition[(record["proposition_char_start"], record["dimension"])].add(record["value"])
        for (prop_start, key), values in by_proposition.items():
            if len(values) < 2:
                continue
            conflicts[key] += 1
            for record in passage_records:
                if (record["proposition_char_start"] == prop_start and record["dimension"] == key
                        and record["assertion_state"] == "candidate"):
                    record["assertion_state"] = "candidate_requires_human_disambiguation"
                    record["state_note"] = "single-valued dimension matched more than one value"
                    record["value_conflict"] = sorted(values)

        # Counting happens after the conflict pass. Counting during it, as this file did until
        # now, let a matrix cell stay live for a record whose state the same run had already
        # demoted, so the matrix and the record file disagreed about what was found.
        for record in passage_records:
            if record["assertion_state"] == "candidate":
                per_work_value[(work, record["dimension"], record["value"])] += 1
                per_passage_value[(passage["passage_id"], record["dimension"], record["value"])] += 1
        proposition_counts[min(len(matched_propositions), 6)] += 1
        passage_rows.append((passage["passage_id"], work,
                             {f"{k}={v}": per_passage_value[(passage['passage_id'], k, v)]
                              for k, specs in dimensions.items() for v in specs["values"]
                              if per_passage_value[(passage['passage_id'], k, v)]}))

    return dict(records=records, conflicts=conflicts, endorsement_tally=endorsement_tally,
                proposition_counts=proposition_counts, per_work_value=per_work_value,
                passage_rows=passage_rows, eligible_words=eligible_words, coverage=coverage,
                cardinality=cardinality, value_coverage=value_coverage,
                dimensions=ontology["dimensions"], rules=rules)


def write_outputs(result):
    records = result["records"]
    with gzip_text_writer(OUT_ATTEST) as handle:
        for record in sorted(records, key=lambda r: (r["work_id"], r["passage_id"], r["char_start"],
                                                     r["dimension"], r["value"])):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    columns = sorted({f"{r['dimension']}={r['value']}" for r in records})
    with gzip_text_writer(OUT_PASSAGE_MATRIX) as handle:
        writer = csv.writer(handle)
        writer.writerow(["passage_id", "work_id", *columns])
        for passage_id, work, counts in sorted(result["passage_rows"]):
            writer.writerow([passage_id, work] + [counts.get(c, "") for c in columns])

    works = sorted({r["work_id"] for r in records})
    dimension_keys = sorted(result["dimensions"])
    non_independent_works = {r["work_id"] for r in records if not r["counts_as_independent_attestation"]}
    # Restricted to the same population as `candidate_count`, so the doctrinal column can
    # never exceed the column it is a subset of.
    affirming = Counter((r["work_id"], r["dimension"], r["value"]) for r in records
                        if r["counts_as_affirmative_doctrine"] and r["assertion_state"] == "candidate")
    with OUT_WORK_MATRIX.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["work_id", "dimension", "value", "candidate_count", "cardinality", "coverage_state",
                         "affirmative_doctrine_count", "work_has_dependent_reprint_records",
                         "counts_as_independent"])
        for work in works:
            dependents = work in non_independent_works
            for key in dimension_keys:
                for value in sorted(result["dimensions"][key]["values"]):
                    count = result["per_work_value"].get((work, key, value), 0)
                    writer.writerow([work, key, value, count, result["cardinality"][key],
                                     result["value_coverage"].get((key, value), "instrumented"),
                                     affirming[(work, key, value)],
                                     "yes" if dependents else "no",
                                     "yes" if count and not dependents else "no"])

    states = Counter(r["assertion_state"] for r in records)
    summary = {
        "instrument": "divinity-ontology v3",
        "purpose": "code divine-concept states on twelve analytically distinct dimensions, proposition by "
                   "proposition, across the whole corpus, for an inheritance-and-transformation question, not "
                   "for a universality test",
        "self_description": "multilingual-ready framework. Every detector in this run is an English "
                            "translation-text pattern; no source-language detector is operational.",
        "corpus": {"eligible_passages": len(result["passage_rows"]), "eligible_words": result["eligible_words"],
                   "works_with_candidates": len(works)},
        "candidate_records_total": len(records),
        "assertion_state_tally": dict(sorted(states.items())),
        "affirmative_doctrine_records": sum(1 for r in records if r["counts_as_affirmative_doctrine"]),
        "conceptual_presence_tally": dict(sorted(Counter(r["conceptual_presence"] for r in records).items())),
        "doctrinal_endorsement_tally": dict(sorted(result["endorsement_tally"].items())),
        "historical_transmission": {
            "value": "not_yet_assessable",
            "records": sum(1 for r in records if r["historical_transmission"] == "not_yet_assessable"),
            "why": "transmission needs dated expressions and documented routes. date_earliest, date_latest and "
                   "dating_basis are null in every record of this run, so the field is published rather than "
                   "inferred.",
        },
        "single_value_conflicts": dict(sorted(result["conflicts"].items())),
        "propositions_flagged_run_on": sum(1 for r in records if r["proposition_overlong"]),
        "matched_propositions_per_passage": {str(k): v for k, v in sorted(result["proposition_counts"].items())},
        "dimension_coverage": result["coverage"],
        "dimension_cardinality": result["cardinality"],
        "endorsement_scope": {
            "what_it_is": "doctrinal_endorsement is a field on every record, not a filter that deletes records. "
                          "The 54 matches v2 refused outright are retained here as conceptual evidence whose "
                          "endorsement is withheld.",
            "affirming_commitments": sorted(AFFIRMING_COMMITMENT),
            "affirming_acts": sorted(AFFIRMING_ACTS),
            "why_not_a_block": "a conditional about a divinity is not affirmed doctrine, but it is evidence that "
                               "the proposition is represented in that text, and reported speech preserves "
                               "evidence of competing beliefs. Collapsing the two questions cost v2 both.",
            "consequence": "counts_as_affirmative_doctrine is the only field that may be used for a doctrinal "
                           "tally, and it is machine-classified, not human-verified.",
            "d7d_alias": "`doctrinal_endorsement` is D7d's value written onto the record, not an independent "
                         "check on it: the two can never disagree except on a `not_yet_instrumented` row, where "
                         "the record field is forced to `undecidable` while D7d keeps the value its unvalidated "
                         "detector matched -- and that is the only divergence the field can show. Their agreement "
                         "is not evidence. The "
                         "questions genuinely apart from D7d are D7a (who speaks) and D7b (what act is "
                         "performed) -- Pharaoh drowning asserts, and the narrative attributes without "
                         "endorsing. The packet codes D7d and `doctrine_endorsed_by_text` as two separate coder "
                         "questions, so two codings will show whether the frame's second question comes apart "
                         "from D7d in observation or only in name.",
        },
        "proposition_segmentation": {
            "method": f"windows split at coordinating and subordinating connectors; fragments under "
                      f"{MIN_PROPOSITION_WORDS} words merged into the preceding proposition",
            "known_failure_modes": [
                "over-splits coordinated predicates that share a subject",
                "under-splits paratactic clauses joined by no connector, which Hebrew and Old Norse narrative "
                "use constantly",
                "a proposition carrying no divine term is not coded at all, so the proposition layer inherits "
                "the term detector's recall gap",
                "attribution defaults to the framing voice where no quote frame fires; attribution_basis says "
                "which reading was a default and which was found"],
            "consequence": "proposition counts are a machine approximation. The annotation packet codes whole "
                           "propositions, and where a coder segments them differently that is a measurement of "
                           "this segmentation, not an error to be corrected in the record.",
        },
        "values_not_yet_instrumented": sorted({f"{k}={v}" for (k, v), s in result["value_coverage"].items()
                                               if s == "not_yet_instrumented"}),
        "reading_rules": [
            "`candidate` means a human must code it; it does not mean attested.",
            "`candidate_requires_human_disambiguation` now includes the case where a single-valued dimension "
            "matched two values on one proposition; v2 chose by precedence and published no trace of it.",
            "`not_yet_instrumented` values are undetectable by this instrument and must never be reported as "
            "absent from a tradition.",
            "`doctrinal_endorsement` is not `conceptual_presence`: a withheld endorsement says nothing about "
            "whether the concept is in the text.",
            "`doctrinal_endorsement` is D7d's own value, so the two are one measurement and never corroborate "
            "each other; they differ only where the coverage state is `not_yet_instrumented` and the field is "
            "forced to `undecidable`. `counts_as_affirmative_doctrine` is their conjunction with the coverage "
            "state and inherits D7d's errors exactly.",
            "the twelve dimensions are analytically distinct by definition, which is not the claim that they are "
            "orthogonal in observation: one English surface string populates several of them at once, and no "
            "coder has scored them yet.",
            "`historical_transmission` is `not_yet_assessable` in every record and may not be argued from any "
            "number in this file.",
            "no number in this file may be used to order concepts historically: composition, witness and "
            "translation dates are separate fields and are not yet filled.",
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
                      ["corpus", "candidate_records_total", "assertion_state_tally",
                       "affirmative_doctrine_records", "doctrinal_endorsement_tally",
                       "single_value_conflicts", "dimension_coverage", "dimension_cardinality",
                       "values_not_yet_instrumented"]}, indent=2))
    print(f"wrote {OUT_ATTEST.name}, {OUT_PASSAGE_MATRIX.name}, {OUT_WORK_MATRIX.name}, {OUT_SUMMARY.name}")


if __name__ == "__main__":
    main()
