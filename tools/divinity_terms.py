"""Concept-of-divinity probe: does this corpus contain one divine concept or several?

The project's motive claim is that "God" is a single invented concept that spread. That claim has a
precondition nobody in the tradition has tested computationally: that the word picks out one thing
across the traditions being compared. This probe measures the precondition directly, on the same
passage-indexed corpus the retrieval instrument uses, and reports vocabulary families rather than a
score. It deliberately cannot measure belief, ritual, or metaphysical status -- see `cannot_support`.

Determinism: no randomness, no thresholds, iteration in sorted order. Output is reproducible from
the recorded SHA-256 of passages_v2.jsonl.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"
MANIFEST = ROOT / "config/corpus_manifest.csv"
OUTPUT = ROOT / "results/divinity_terms.json"

# Each family names a conceptual grammar, not a synonym set. A tradition that has family A and not
# family C is not "missing a word"; it is asking a different question about divinity.
FAMILIES = {
    "personal_creator_of_world": {
        "grammar": "a personal agent who brought the world into being and stands outside it",
        "patterns": [r"\bcreator\b", r"\bmaker of (?:heaven|earth|all things|the world|it)\b",
                     r"\b(?:god|the lord) that made\b", r"\bcreated the world\b",
                     r"\bfirst cause\b", r"\bform[ae]d all things\b"],
    },
    "supreme_being_attributes": {
        "grammar": "uniqueness and absolute power predicated of one being (omnipotence, self-existence)",
        "patterns": [r"\balmighty\b", r"\bombipotent\b", r"\bself-?existent\b", r"\bson of god\b",
                     r"\bgod of gods\b", r"\blord of hosts\b", r"\bthe most high\b"],
    },
    "plural_or_council_deities": {
        "grammar": "divinity as a plurality, often with an assembly, genealogy or hierarchy",
        "patterns": [r"\bcouncil of the gods\b", r"\bassembly of the gods\b", r"\bdivine council\b",
                     r"\bthe gods\b", r"\bthirty[- ]three gods\b", r"\bsons of god\b",
                     r"\belohim\b", r"\bdevas?\b", r"\btuatha de\b"],
    },
    "celestial_bureaucracy": {
        "grammar": "heaven as an administration with ranks, offices and reports",
        "patterns": [r"\bjade emperor\b", r"\bmandate of heaven\b", r"\bheavenly bureaucracy\b",
                     r"\bcelestial (?:ruler|official|court|bureau|functionary)\b",
                     r"\boffices? of heaven\b", r"\breport(?:ed|ing)? to the (?:son of heaven|emperor of heaven)\b"],
    },
    "impersonal_ground": {
        "grammar": "the ultimate is a principle, ground or absolute rather than a person",
        "patterns": [r"\bbrahman\b", r"\bthe absolute\b", r"\bultimate reality\b", r"\bdharmakaya\b",
                     r"\bein sof\b", r"\btao\b", r"\bdao\b", r"\bacosmic\b"],
    },
    "deified_human_or_ancestor": {
        "grammar": "divinity as a status conferred on a person who was formerly human",
        "patterns": [r"\bdeif(?:ied|ication)\b", r"\bdiviniz(?:ed|ation|e)\b", r"\bapotheosis\b",
                     r"\bmade a god\b", r"\bplaced among the gods\b", r"\bworshipped as a? ?god\b",
                     r"\bancestor worship\b", r"\beuhemerus\b"],
    },
    "spirit_immanent_in_things": {
        "grammar": "sacred power as a property of places, animals and objects, uncentered on a person",
        "patterns": [r"\bgreat spirit\b", r"\bmanitou\b", r"\bwakan\b", r"\borende\b",
                     r"\bspirits of the (?:earth|water|forest|trees|rocks|air)\b"],
    },
    "saving_descent": {
        "grammar": "a divinity that comes down to rescue, teach or restore",
        "patterns": [r"\bavatara\b", r"\bavatar\b", r"\bsaviour\b", r"\bsavior\b", r"\bmessiah\b",
                     r"\bdescended to earth\b", r"\bgod became man\b"],
    },
    "explicit_non_theism_or_skepticism": {
        "grammar": "text that denies, abolishes, declares unknowable, or argues against gods or a creator",
        "patterns": [r"\bno god\b", r"\bgods do not exist\b", r"\bthere is no god\b",
                     r"\bwithout a creator\b", r"\bdenial of the gods\b", r"\batheis(?:m|ts?)\b",
                     r"\bagnosti(?:c|cs|cism)\b", r"\bdoubt(?:ed|s)? the existence of the gods?\b",
                     r"\bquestion(?:ed|s)? the existence of (?:a )?god\b"],
    },
    "exclusivist_monotheism": {
        "grammar": "one divinity asserts sole existence and denies the reality of others -- an internal "
                    "doctrine of oneness, not a denial that divinity exists",
        "patterns": [r"\bno god but\b", r"\bno other gods\b", r"\bbeside me there is no god\b",
                     r"\bapart from (?:me|him) there is no god\b",
                     r"\bthere is no god (?:besides|but) (?:god|the lord|allah|him|the lord god)\b",
                     r"\bthe lord our god (?:is|be) one\b", r"\bthe lord is one\b"],
    },
}

# A bare negation is not non-theism. "There is no god but God" is the shahada, an emphatic affirmation, and
# "who is like unto thee among the gods" exalts rather than denies. These contexts are removed from the
# skepticism family and published as `excluded_matches` so the reader can check every judgement. The
# formula rule looks only forward: an unrelated "but" a few words later is not a monotheistic confession,
# and an earlier version of this rule used a ±60-character window that wrongly discarded genuine matches.
SKEPTICISM_EXCLUSIONS = {
    "monotheistic_formula_negation": {"look": "after", "chars": 25, "regex": r"\A\s*but\b"},
    "comparative_exaltation": {"look": "around", "chars": 60,
                               "regex": r"\b(?:like unto|comparable to|as) (?:the )?(?:lord|god|allah)\b"},
}

COMPILED = {name: re.compile("|".join(spec["patterns"]), re.IGNORECASE)
             for name, spec in FAMILIES.items()}

# Terms whose surface form is too common or too ambiguous to carry evidence; kept visible so the
# reader can see what was excluded rather than having to trust an invisible judgement.
REJECTED_TERMS = {
    r"\bmana\b": "matches mana as a plural of man and appears in unrelated ethnographic prose",
    r"\bthe law\b": "matches Mosaic-law and secular-law prose indiscriminately",
    r"\bdivine\b": "matches polite formulae, honorifics and secular praise",
    r"\bgod\b": "the target word itself: frequency tracks book genre and translation style, not concept",
    r"\bemperor\b": "matches Roman and Japanese secular rulers",
}

MAX_EXAMPLES_PER_FAMILY = 6
SNIPPET_CHARS = 150


def load_passages():
    return [json.loads(line) for line in PASSAGES.read_text(encoding="utf-8").splitlines()]


def work_attributes():
    """Region and tradition per work, from the acquisition manifest rather than from the text."""
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        return {row["work_id"]: {"region": row["region"], "tradition": row["tradition"]}
                for row in csv.DictReader(handle)}


def snippet(text, match):
    half = SNIPPET_CHARS // 2
    start = max(0, match.start() - half)
    end = min(len(text), match.end() + half)
    return ("…" if start else "") + re.sub(r"\s+", " ", text[start:end]).strip() + ("…" if end < len(text) else "")


def skepticism_exclusion(text, match):
    for label, rule in sorted(SKEPTICISM_EXCLUSIONS.items()):
        span = rule["chars"]
        if rule["look"] == "after":
            context = text[match.end():match.end() + span]
            hit = re.search(rule["regex"], context, re.IGNORECASE)
        else:
            context = text[max(0, match.start() - span):match.end() + span]
            hit = re.search(rule["regex"], context, re.IGNORECASE)
        if hit:
            return label
    return None


def scan(passages, attributes):
    eligible_words = defaultdict(int)
    works_in_index = set()
    hits = defaultdict(list)
    excluded = defaultdict(list)
    per_work = defaultdict(Counter)
    for passage in passages:
        work = passage["work_id"]
        works_in_index.add(work)
        if not passage["eligible_for_similarity"]:
            continue
        eligible_words[work] += passage["word_count"] or 0
        text = passage["text"]
        for name, pattern in COMPILED.items():
            for match in pattern.finditer(text):
                record = {
                    "family": name,
                    "term": match.group(0),
                    "work_id": work,
                    "passage_id": passage["passage_id"],
                    "region": attributes.get(work, {}).get("region"),
                    "tradition": attributes.get(work, {}).get("tradition"),
                    "char_start": passage["body_char_start"] + match.start(),
                    "char_end": passage["body_char_start"] + match.end(),
                    "snippet": snippet(text, match),
                }
                if name == "explicit_non_theism_or_skepticism":
                    reason = skepticism_exclusion(text, match)
                    if reason:
                        record["excluded_because"] = reason
                        excluded[reason].append(record)
                        continue
                    record["review_state"] = "unreviewed_machine_match"
                hits[name].append(record)
                per_work[work][name] += 1
    return hits, per_work, eligible_words, works_in_index, excluded


def summarize(hits, per_work, eligible_words, works_in_index, attributes, excluded):
    works_by_region = defaultdict(set)
    works_by_tradition = defaultdict(set)
    for work in sorted(works_in_index):
        works_by_region[attributes.get(work, {}).get("region") or "unassigned"].add(work)
        works_by_tradition[attributes.get(work, {}).get("tradition") or "unassigned"].add(work)
    corpus_words = sum(eligible_words.values())
    families = {}
    for name in sorted(FAMILIES):
        records = sorted(hits[name], key=lambda item: (item["work_id"], item["passage_id"], item["char_start"]))
        works = sorted({item["work_id"] for item in records})
        regions = sorted({item["region"] or "unassigned" for item in records})
        traditions = sorted({item["tradition"] or "unassigned" for item in records})
        families[name] = {
            "grammar": FAMILIES[name]["grammar"],
            "patterns": FAMILIES[name]["patterns"],
            "term_hits": len(records),
            "works_attested": len(works),
            "regions_attested": len(regions),
            "traditions_attested": len(traditions),
            "region_names": regions,
            "tradition_names": traditions,
            "works": works,
            "hits_per_10k_eligible_words": round(len(records) / (corpus_words / 10_000), 3),
            "examples": records[:MAX_EXAMPLES_PER_FAMILY],
        }
    breadth = Counter(len(counts) for counts in per_work.values() if counts)
    pair_cooccurrence = Counter()
    for counts in per_work.values():
        present = sorted(counts)
        for position, left in enumerate(present):
            for right in present[position + 1:]:
                pair_cooccurrence[f"{left} + {right}"] += 1
    total_works = len(works_in_index)
    universal = [name for name, item in families.items() if item["works_attested"] == total_works]
    widest = max(families.values(), key=lambda item: (item["regions_attested"], item["works_attested"]))["regions_attested"] if families else 0
    region_count = len(works_by_region)
    if universal:
        verdict = (f"{len(universal)} family is attested in every indexed work: {universal}. Note that this "
                   f"would not establish a shared referent either: universality is a stronger condition than "
                   f"inheritance requires, and one English wording recurring everywhere can equally be a "
                   f"translator's habit.")
    else:
        verdict = (f"no family is attested in every indexed work, and the broadest reaches {widest} of "
                   f"{region_count} regional labels. This is a vocabulary observation about English "
                   f"translations and nothing more. It is NOT evidence against a common origin: an "
                   f"inheritance-with-transformation hypothesis predicts divergence of surface forms, since "
                   f"abstraction, demotion, nominalisation and silencing are how concepts are transmitted; "
                   f"and every competing model (single origin, multiple origins, regional inheritance with "
                   f"mixing, independent convergence) predicts this same non-detection pattern, so the "
                   f"observation cannot rank them. Non-detection licenses only the report 'not detected in "
                   f"these sources'. See TRACK_B_METHOD_v2.md sections 3 and 8 for the frame that replaces "
                   f"these ten conflated grammars, and results/exclusivist_monotheism_audit.json for what "
                   f"the audit did to the oneness result below.")
    return {
        "families": families,
        "corpus": {
            "works_in_passage_index": total_works,
            "eligible_words": corpus_words,
            "regions": sorted(works_by_region),
            "works_per_region": {region: len(works) for region, works in sorted(works_by_region.items())},
            "works_per_tradition": {tradition: len(works) for tradition, works in sorted(works_by_tradition.items())},
        },
        "one_concept_test": {
            "question": "is there a divine concept shared by every part of this corpus?",
            "families_attested_somewhere": sum(1 for item in families.values() if item["term_hits"]),
            "families_attested_in_every_work": universal,
            "max_families_in_a_single_work": max(breadth) if breadth else 0,
            "works_by_number_of_families_present": {str(key): value for key, value in sorted(breadth.items())},
            "most_widespread_by_region_count": sorted(
                ((item["regions_attested"], item["works_attested"], name) for name, item in families.items()),
                reverse=True)[:3],
            "strongest_pairwise_cooccurrences": [
                {"families": key, "works": value} for key, value in pair_cooccurrence.most_common(6)],
            "verdict": verdict,
        },
        "skepticism_evidence": {
            "note": "Texts that deny or suspend belief in gods or a creator are the direct counterexample "
                    "to universality, so they are recorded with locators. A negation is not enough: the "
                    "monotheistic formula and comparative exaltation are excluded by the rules below, every "
                    "excluded match is published rather than discarded, and every kept match is marked "
                    "unreviewed, because a regular expression cannot decide whether a passage is doctrine, "
                    "hypothetical, or polemic.",
            "exclusion_rules": {label: rule["regex"] for label, rule in sorted(SKEPTICISM_EXCLUSIONS.items())},
            "records": sorted(hits["explicit_non_theism_or_skepticism"],
                              key=lambda item: (item["work_id"], item["passage_id"])),
            "excluded_matches": {label: sorted(items, key=lambda item: (item["work_id"], item["passage_id"]))
                                 for label, items in sorted(excluded.items())},
            "excluded_count": sum(len(items) for items in excluded.values()),
        },
        "oneness_claim_distribution": {
            "question": "the motive claim needs divinity to be one concept, and often borrows the doctrine "
                        "that divinity is literally one as its evidence; this reports where that doctrine "
                        "actually appears",
            "works_attested": families["exclusivist_monotheism"]["works"],
            "traditions_attested": families["exclusivist_monotheism"]["tradition_names"],
            "regions_attested": families["exclusivist_monotheism"]["region_names"],
            "term_hits": families["exclusivist_monotheism"]["term_hits"],
            "reading": "oneness is unevenly distributed across this corpus, which is a descriptive result. It "
                       "does NOT license the stronger sentence this field previously carried ('a doctrine of "
                       "particular traditions rather than the shared kernel'): the four 'works attested' are "
                       "not four independent witnesses. Eight of the nine sacred_books_east hits are Qur'an "
                       "material reprinted inside Wilson's anthology, which already counts the translation they "
                       "reprint, and the ninth is Thomas Carlyle's essay describing the formula rather than "
                       "confessing it -- a dependence rule the census ignored. Two hits are substring collisions "
                       "(1 Cor 6:17 'one spirit', 1 Ne 10:19 'one eternal round') that state nothing about divine "
                       "oneness, and three are worship prohibitions whose wording presupposes the very gods they "
                       "forbid. Matching after whitespace normalisation raises 46 hits to 51 and recovers Isaiah "
                       "44:6 and Mark 12:29, which the raw line-wraps had hidden. What survives is 34 "
                       "confessional matches in two independent works, kjv_bible and quran_sale -- a file whose "
                       "own title page prints Rodwell, not Sale, as its translator. See "
                       "results/exclusivist_monotheism_audit.json for every match, locator, verdict and missed "
                       "formula class.",
        },
    }


def build():
    passages = load_passages()
    attributes = work_attributes()
    hits, per_work, eligible_words, works_in_index, excluded = scan(passages, attributes)
    result = {
        "instrument": "divinity-terms probe v1",
        "purpose": "test the precondition of the single-origin motive claim: that 'god' names one concept "
                   "across the traditions compared",
        "method": "curated analyst-authored regular-expression families matched against the eligible "
                  "passages of the v2 corpus; frequencies, work attestation and regional attestation "
                  "reported per family; no score, no composite, no threshold",
        "measurement_unit": "matched term occurrences per family, normalised per 10k eligible words",
        "reproducibility": {
            "passages_sha256": hashlib.sha256(PASSAGES.read_bytes()).hexdigest(),
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "randomness": "none: sorted iteration, no sampling, no fitted parameters",
            "python": sys.version.split()[0],
        },
        "excluded_terms": REJECTED_TERMS,
        "what_this_measures": "the vocabulary available to nineteenth- and twentieth-century English "
                              "translators and editors of these works, which is the only version of the "
                              "concept this corpus can access",
        "cannot_support": [
            "that a concept is absent from a tradition: absence of an English term in one translation is "
            "not absence of the idea, and this corpus is monolingual",
            "that any tradition's adherents believe or do not believe anything; this is a text probe, not "
            "an interview or a ritual record",
            "that one family is historically prior to another: attestation counts here are not dated",
            "any conclusion about the existence or non-existence of supernatural beings, which no "
            "vocabulary census can address",
            "that a matched negation is doctrine: 'if no god withstand' is a conditional, 'beside me there "
            "is no God' is exclusivist monotheism, and 'atheists' in the Mahābhārata names a school in a "
            "doxography rather than the author's belief. The families separate these only partially, and "
            "every record still needs source-critical review",
            "that the families are exhaustive or non-overlapping; they are analyst-authored and would "
            "change under a second coders lexicon, which is the reliability test this probe lacks",
        ],
    }
    result.update(summarize(hits, per_work, eligible_words, works_in_index, attributes, excluded))
    return result


def main():
    result = build()
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    test = result["one_concept_test"]
    print(json.dumps({
        "families_attested": test["families_attested_somewhere"],
        "families_in_every_work": test["families_attested_in_every_work"],
        "max_families_in_a_work": test["max_families_in_a_single_work"],
        "most_widespread": test["most_widespread_by_region_count"],
        "skeptic_records": len(result["skepticism_evidence"]["records"]),
        "skeptic_records_excluded_as_non_skeptical": result["skepticism_evidence"]["excluded_count"],
        "works_with_no_family_matched": result["corpus"]["works_in_passage_index"] - sum(
            int(value) for key, value in
            result["one_concept_test"]["works_by_number_of_families_present"].items()),
        "eligible_words": result["corpus"]["eligible_words"],
    }, indent=2))
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
