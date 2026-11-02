#!/usr/bin/env python3
"""Attestation scaffold: three separate date fields per work, as data rather than prose.

RESEARCH_PROTOCOL.md 12.3 records "Composition, attestation and inferred age separated"
as only PARTLY met: separated in the schema and discussed in prose for individual
cases, but never held as fields. That gap is why an undated attestation count could
be read as a chronology. This creates the fields for every work and marks honestly
which of them are filled.

Nothing here dates a concept. Composition and earliest-witness dates are left as
`requires_specialist_input` for works where this project has no philological basis to
assert one; filling them from a guess would reintroduce exactly the error the
separation exists to prevent.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "corpus/acquisition_manifest.json"
CORPUS = ROOT / "config/corpus_manifest.csv"
OUT = ROOT / "results/attestation_scaffold.csv"
OUT_SUMMARY = ROOT / "results/attestation_scaffold_summary.json"

COLUMNS = ["work_id", "title", "original_language", "translator_or_editor", "source_role",
           "region", "tradition", "composition_date_claim", "composition_date_basis",
           "composition_date_confidence", "earliest_witness_date", "witness_date_basis",
           "edition_or_translation_date", "edition_date_status", "digitised_text_date", "text_type",
           "usable_for_priority_claims", "requires_specialist_input", "note"]

# CANDIDATE edition dates, asserted from general knowledge of these printings and NOT
# checked against the title pages. `edition_date_status` below records that, and the
# scaffold's own gate says an unverified date cannot support a priority claim. The
# digitised file's own header is the first place to check; where the acquisition
# manifest carried an "Original publication" field that value is preferred.
EDITION_DATE_CANDIDATES = {
    "kjv_bible": ("1611", "authorised edition printed 1611; the corpus file is a modern digitisation of it"),
    "quran_sale": ("1734", "George Sale's translation, first printed 1734"),
    "upanishads_mead": ("1884", "Müller's Sacred Books of the East volume edition"),
    "dhammapada_muller": ("1881", "Sacred Books of the East volume containing Müller's Dhammapada"),
    "sacred_books_east": ("1900", "Wilson's anthology edition as digitised"),
    "bhagavad_gita_arnold": ("1885", "Arnold's verse translation, first printed 1885"),
    "mahabharata_v1": ("1883-1896", "Kumhari-Bibek Mahābhārata print series"),
    "ramayana_griffith": ("1870-1877", "Griffith's translations"),
    "popol_vuh": ("1850-1854", "Ximénez manuscript edition; the K'iche' text is earlier"),
    "iliad": ("1899", "Butler's prose translation as digitised"),
    "odyssey": ("1897", "Butler's prose translation as digitised"),
    "hesiod_homerica": ("1914", "Homerica printing"),
    "beowulf": ("1895-1899", "Gumming's translation"),
    "kalevala": ("1850", "Caird's translation"),
    "vishnu_purana": ("1840", "Wilson's edition"),
    "book_of_enoch": ("1893", "Charles' translation"),
    "chaldean_genesis": ("1876", "Smith's work"),
}
ORAL_OR_COMPILED_LATE = {
    # These are 19th-20th century recordings of oral tradition: the printed date is
    # not the concept's date and no witness date reaches pre-contact use.
    "cherokee_myths", "iroquois_myths", "iroquois_stories", "creek_migration", "navaho_legends",
    "maori_port_hills", "maui_legends", "euahlayi_tribe", "bantu_folklore", "west_african_folk_tales",
    "south_african_folk_tales", "zulu_customs_folklore", "tinguian_traditions", "cunnie_rabbit",
    "where_animals_talk", "australian_legendary_tales", "filipino_popular_tales",
    "philippine_folk_tales", "japanese_fairy_tales", "chinese_fairy_book", "chinese_wonder_book",
    "chinese_folklore", "myths_legends_china", "myths_legends_japan", "strange_stories_chinese",
    "myths_north_american", "myths_mexico_peru", "arabian_nights", "celtic_myths", "mabinogion",
}


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    works = manifest["works"] if isinstance(manifest, dict) else manifest
    attributes = {}
    if CORPUS.exists():
        with CORPUS.open(encoding="utf-8-sig", newline="") as handle:
            attributes = {row["work_id"]: row for row in csv.DictReader(handle)}

    rows, filled, specialist_needed = [], 0, 0
    for work in sorted(works, key=lambda item: item["work_id"]):
        work_id = work["work_id"]
        attrs = attributes.get(work_id, {})
        translation = EDITION_DATE_CANDIDATES.get(work_id)
        manifest_date = (work.get("Original publication") or "").strip()
        if manifest_date and manifest_date != "requires_specialist_input":
            translation = (manifest_date, "stated in the acquisition manifest header")
        if translation:
            filled += 1
        oral = work_id in ORAL_OR_COMPILED_LATE
        requires = "translation_date" if not translation else ""
        if not translation:
            specialist_needed += 1
        usable = "no"
        rows.append({
            "work_id": work_id, "title": work.get("Title", ""),
            "original_language": work.get("original_language", ""),
            "translator_or_editor": work.get("Translator", work.get("Editor", "")),
            "source_role": work.get("source_role", ""),
            "region": work.get("region", attrs.get("region", "")),
            "tradition": work.get("tradition", attrs.get("tradition", "")),
            "composition_date_claim": "requires_specialist_input",
            "composition_date_basis": "no philological basis held by this project",
            "composition_date_confidence": "none",
            "earliest_witness_date": ("requires_specialist_input (oral tradition: no textual witness "
                                      "pre-dating the printed recording)" if oral
                                      else "requires_specialist_input"),
            "witness_date_basis": "printed recording is the earliest witness available here" if oral else "",
            "edition_or_translation_date": translation[0] if translation else "requires_specialist_input",
            "edition_date_status": ("unverified_secondary_memory_needs_title_page_check" if translation and
                                    "manifest header" not in translation[1] else
                                    "from_acquisition_manifest" if translation else "no_date_asserted"),
            "digitised_text_date": (work.get("Release date", "") or "").split("[")[0].strip(),
            "text_type": ("oral tradition as recorded by a collector" if oral
                          else "anthology with editorial commentary" if work.get("source_role") == "anthology"
                          else "scripture or epic in translation"),
            "usable_for_priority_claims": usable,
            "requires_specialist_input": (requires + ("|composition_and_witness" if requires else "")).lstrip("|"),
            "note": ("the printed date is a recording date, not an attestation date for the concept"
                     if oral else ""),
        })

    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "instrument": "attestation scaffold v1",
        "works": len(rows),
        "edition_or_translation_date_filled": filled,
        "works_needing_specialist_date_input": specialist_needed,
        "works_usable_for_priority_claims_today": 0,
        "why_every_usable_flag_is_no": [
            "a priority claim needs a composition or earliest-witness date, and this project holds none that "
            "it can cite from a critical edition",
            "a translation or printing date constrains when the English wording existed, not when the concept "
            "was held -- conflating the two is what let v1's undated counts read as chronology",
            "for the collector-recorded oral traditions the printed date is a recording date; the tradition's "
            "antiquity is not datable from this corpus at all, which is a limit on the instrument and not a "
            "claim that the concept is recent",
        ],
        "consequence_for_track_b": "TRACK_B_METHOD_v2.md section 6 score (v) dated-first-attestation ordering "
                                   "cannot be computed until this file's composition and witness columns are "
                                   "filled by specialists; the scaffold exists so that 'not yet filled' is a "
                                   "recorded state rather than an invisible assumption",
        "reproducibility": {"manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"works": len(rows), "translation_dates_filled": filled,
                      "needing_specialist_dates": specialist_needed,
                      "usable_for_priority_claims": 0}, indent=2))
    print(f"wrote {OUT.name}, {OUT_SUMMARY.name}")


if __name__ == "__main__":
    main()
