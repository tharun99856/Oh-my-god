#!/usr/bin/env python3
"""Count every recall-probe cue over the eligible corpus and report which ones actually occur.

The cue list in `config/recall_probe_cues.json` was read off the corpus's own divine vocabulary rather than
generated from the detector's rule file. Reading is not verification: a name on the list that appears in no
eligible passage would silently shrink the source-driven stratum's population while the plan still reported
a cue list of the intended length. This tool counts each cue, in each work, over exactly the passages the
state coder codes, and writes the counts back into the config's `verification.results` block.

Cues that occur zero times are reported for removal; cues whose English form is also an ordinary word
(`Sin`, `Set`, `heaven`, `creator`) are reported as ambiguous but kept, because the ambiguity belongs to the
coder, not to a regex.

Usage:
    python tools/check_recall_cues.py            # report only
    python tools/check_recall_cues.py --write    # report and record the counts in the config
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import divinity_ontology as onto  # noqa: E402  same eligibility rule, same normalisation, not reimplemented

CUES = ROOT / "config/recall_probe_cues.json"
AMBIGUOUS = {"sin", "set", "heaven", "the heavens", "creator", "maker", "immortal", "immortals",
             "divine", "celestial", "the blessed", "holy one", "holy ones", "lat", "manat", "woyo",
             "first-begotten", "son of god"}


def cue_list(config):
    return [(kind, cue) for kind in ("divinity_nouns", "divinity_names") for cue in config[kind]]


def compile_cue_pattern(config):
    """The single anchored alternation the checker and the packet builder must not disagree about.

    Longest alternative first and anchored at both ends: without that, `god` wins inside `gods` and every
    cue that extends a shorter one reads as absent from a corpus that plainly contains it.
    `excluded_ambiguous_cues` retires cues whose English reading dominates the divine reading.
    """
    retired = {c.lower() for c in config.get("excluded_ambiguous_cues", {})}
    live = [(kind, cue) for kind, cue in cue_list(config) if cue.lower() not in retired]
    ordered = sorted({cue for _, cue in live}, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(c) for c in ordered) + r")\b", re.IGNORECASE)
    return pattern, live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="record the counts in the config file")
    args = parser.parse_args()

    config = json.loads(CUES.read_text(encoding="utf-8"))
    pattern, cues = compile_cue_pattern(config)
    hit_counter = Counter()
    per_work = Counter()
    passages = eligible_words = 0

    with open(onto.PASSAGES, encoding="utf-8") as handle:
        for line in handle:
            passage = json.loads(line)
            if not passage["eligible_for_similarity"]:
                continue
            passages += 1
            eligible_words += passage["word_count"] or 0
            norm, _ = onto.normalise(passage["text"])
            found = {m.group(0).lower() for m in pattern.finditer(norm)}
            if found:
                per_work[passage["work_id"]] += 1
            for _, cue in cues:
                if cue.lower() in found:
                    hit_counter[cue.lower()] += 1

    absent = [cue for _, cue in cues if hit_counter[cue.lower()] == 0]
    ambiguous = [cue for _, cue in cues if cue.lower() in AMBIGUOUS and hit_counter[cue.lower()]]
    print(f"eligible passages scanned: {passages:,}  eligible words: {eligible_words:,}  "
          f"passages with at least one cue: {sum(per_work.values()):,}")
    print(f"cues checked: {len(cues)}  occurring: {len(cues) - len(absent)}  absent from this corpus: {len(absent)}")
    if absent:
        print("  absent (remove from the list):")
        for cue in absent:
            print(f"    {cue}")
    if ambiguous:
        print(f"  kept but ambiguous in English: {len(ambiguous)} -> {', '.join(ambiguous[:12])} ...")
    print("  ten most frequent cues:")
    for cue, count in hit_counter.most_common(10):
        print(f"    {count:7,}  {cue}")

    if args.write:
        config["verification"]["results"] = {
            "eligible_passages": passages,
            "eligible_words": eligible_words,
            "cues_checked": len(cues),
            "cues_occurring": len(cues) - len(absent),
            "cues_absent_and_removed": absent,
            "ambiguous_kept": ambiguous,
            "occurrence_by_cue": dict(sorted(hit_counter.items(), key=lambda kv: -kv[1])),
            "works_with_at_least_one_cue": len(per_work),
        }
        for kind in ("divinity_nouns", "divinity_names"):
            config[kind] = [c for c in config[kind] if hit_counter[c.lower()] > 0]
        CUES.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                        newline="")
        print(f"rewrote {CUES.name}: {len(cues)} -> {len(config['divinity_nouns']) + len(config['divinity_names'])} cues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
