"""Print passage identifiers and snippets matching a pattern, for grounding annotations.

Usage: python tools/find_passages.py PATTERN [WORK_ID ...]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "corpus/derived/passages_v2.jsonl"


def load():
    with PASSAGES.open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def main():
    pattern = re.compile(sys.argv[1], re.IGNORECASE)
    works = set(sys.argv[2:])
    context = 140
    matches = 0
    for passage in load():
        if works and passage["work_id"] not in works:
            continue
        text = passage["text"]
        hit = pattern.search(text)
        if not hit:
            continue
        matches += 1
        start = max(0, hit.start() - context)
        end = min(len(text), hit.end() + context)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        print(f"{passage['passage_id']} [{passage['word_count']}w] ...{snippet}...")
        if matches >= 12:
            print("(truncated: narrow the pattern or list works)")
            break
    if not matches:
        print("no matches")


if __name__ == "__main__":
    main()
