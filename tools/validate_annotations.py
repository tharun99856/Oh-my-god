"""Check that every annotation in config/annotated_versions.json is vocabulary-legal and quote-verifiable.

This is the audit's requirement that an annotation store the exact passage supporting it,
not merely a label. Run: python tools/validate_annotations.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / "config/annotated_versions.json"
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"

GAP = re.compile(r"\s*\.\.\.\s*|\s*…\s*")
BRACKETED = re.compile(r"\[[^\]]{0,20}\]")
SYMBOLS = re.compile(r"[_*<>]")
SPACE_RUNS = re.compile(r"\s+")
TRANSLITERATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "…": "...", "️": "",
})


def normalize(text):
    text = text.translate(TRANSLITERATE)
    text = BRACKETED.sub(" ", text)
    text = SYMBOLS.sub("", text)
    text = SPACE_RUNS.sub(" ", text)
    return text.strip().lower()


def load_passages():
    passages = {}
    with PASSAGES.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            passages[record["passage_id"]] = record
    return passages


def main():
    annotation = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    passages = load_passages()
    manual = annotation["coding_manual"]
    errors = []
    warnings = []

    family_members = {}
    for family, predicates in manual["predicate_families"].items():
        for predicate in predicates:
            if predicate in family_members:
                errors.append(f"predicate {predicate} in two families")
            family_members[predicate] = family

    roles = set(manual["role_vocabulary"])
    motifs = annotation["motif_registry"]
    versions = annotation["versions"]
    version_ids = [version["version_id"] for version in versions]
    if len(set(version_ids)) != len(version_ids):
        errors.append("duplicate version_id")

    quote_checks = 0
    for version in versions:
        vid = version["version_id"]
        listed = set(version["passages"])
        for missing in sorted(listed - set(passages)):
            errors.append(f"{vid}: cited passage does not exist: {missing}")
        orders = [event["order"] for event in version["events"]]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            errors.append(f"{vid}: event orders are not 1..n: {orders}")
        event_ids = [event["event_id"] for event in version["events"]]
        if len(set(event_ids)) != len(event_ids):
            errors.append(f"{vid}: duplicate event_id")
        event_id_set = set(event_ids)
        for source, target in version.get("causal_links", []):
            if source not in event_id_set or target not in event_id_set:
                errors.append(f"{vid}: causal link to unknown event {source}->{target}")
        for event in version["events"]:
            predicate = event["predicate"]
            if predicate not in family_members:
                errors.append(f"{vid}/{event['event_id']}: predicate outside vocabulary: {predicate}")
            for participant in event["participants"]:
                if participant["role"] not in roles:
                    errors.append(f"{vid}/{event['event_id']}: role outside vocabulary: {participant['role']}")
                if not participant["term"].strip():
                    errors.append(f"{vid}/{event['event_id']}: empty participant term")
                if not participant.get("referent", "").strip():
                    errors.append(f"{vid}/{event['event_id']}: participant has no coder-asserted referent")
                if not participant.get("referent_kind", "").strip():
                    errors.append(f"{vid}/{event['event_id']}: participant has no referent_kind")
            passage_id = event["evidence_passage"]
            if passage_id not in passages:
                errors.append(f"{vid}/{event['event_id']}: unknown evidence passage {passage_id}")
                continue
            if passage_id not in listed:
                errors.append(f"{vid}/{event['event_id']}: evidence passage not in version passages: {passage_id}")
            passage = passages[passage_id]
            if passage["work_id"] != version["work_id"]:
                errors.append(f"{vid}/{event['event_id']}: evidence from another work ({passage['work_id']})")
            if not passage["eligible_for_similarity"]:
                warnings.append(f"{vid}/{event['event_id']}: evidence passage excluded by cleaning rules")
            haystack = normalize(passage["text"])
            for fragment in GAP.split(event["quote"].strip()):
                fragment = normalize(fragment)
                if not fragment:
                    continue
                quote_checks += 1
                if fragment not in haystack:
                    errors.append(f"{vid}/{event['event_id']}: quote not found in {passage_id}: {fragment[:70]!r}")
        for motif in version["motifs"]:
            if motif["motif_id"] not in motifs:
                errors.append(f"{vid}: motif outside registry: {motif['motif_id']}")
            if motif["count"] and motif.get("evidence_passage") not in passages:
                errors.append(f"{vid}: motif evidence passage missing for {motif['motif_id']}")
            if motif["count"] == 0 and motif.get("evidence_passage"):
                errors.append(f"{vid}: absent motif carries evidence for {motif['motif_id']}")

    allowed_states = {"source_verified", "transcribed"}
    for version in versions:
        if version["review_state"] not in allowed_states:
            errors.append(f"{version['version_id']}: unexpected review_state")
    for group, pairs in annotation["expected_relation_annotations"].items():
        if group == "note":
            continue
        for pair in pairs:
            for version_id in pair:
                if version_id not in version_ids:
                    errors.append(f"{group}: expectation names unknown version {version_id}")

    expected_keys = {
        "note",
        "same_narrative_dependent_witnesses",
        "same_tradition_different_episode",
        "same_class_different_tradition_to_test",
        "predicted_unrelated_negative",
    }
    if set(annotation["expected_relation_annotations"]) - expected_keys:
        errors.append("unexpected expectation group")

    report = {
        "annotation_set_version": annotation["annotation_set_version"],
        "versions": len(versions),
        "events": sum(len(version["events"]) for version in versions),
        "causal_links": sum(len(version.get("causal_links", [])) for version in versions),
        "motif_assertions": sum(len(version["motifs"]) for version in versions),
        "vocabulary_predicates": len(family_members),
        "quote_fragments_checked": quote_checks,
        "errors": errors,
        "warnings": warnings,
        "status": "passed" if not errors else "failed",
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
