"""Print the full text of one or more passages: python tools/show_passage.py PASSAGE_ID ..."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
index = None


def load_index():
    global index
    if index is None:
        index = {}
        with (ROOT / "corpus/derived/passages_v2.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                passage = json.loads(line)
                index[passage["passage_id"]] = passage
    return index


for wanted in sys.argv[1:]:
    passage = load_index().get(wanted)
    if passage is None:
        print(f"### MISSING {wanted}")
        continue
    print(f"### {wanted} | {passage['work_id']} | section {passage['section_index']} h={passage['section_heading']!r} | {passage['word_count']}w | eligible={passage['eligible_for_similarity']}")
    print(passage["text"].strip())
    print()
