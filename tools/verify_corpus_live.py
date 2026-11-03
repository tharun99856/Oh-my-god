"""Re-read every acquired text from its public source and record whether it still matches.

This repository's reproducibility claim has two halves that are easy to conflate. The first is internal: the
published artifacts record the SHA-256 of the bytes they were computed from, the tests re-hash those bytes,
and a stale artifact fails. The second is external: the bytes themselves came from a website that other
people can edit. Nothing in the internal half can detect the second, which is why a reviewer reproducing
this study from `tools/acquire_corpus.py` can get a corpus that no longer matches the shipped manifest and
correctly conclude that the freshness gates are broken when they are not.

The tool answers that question by measuring it. It downloads, hashes and compares, writes nothing into the
corpus, and publishes per-work status. Run:

    python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json

Without --write-to it prints the summary and publishes nothing.
"""
import argparse
import difflib
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

MANIFEST_PATH = ROOT / "corpus/acquisition_manifest.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def describe_difference(acquired, live, limit=6, window=90):
    """Where the two copies part company, as a byte offset, a printable window and a line-level characterisation.

    The byte count alone is not a description of a drift. When the publisher's edit changes the file's length,
    every later byte is compared against a byte that is no longer in the same place, so a one-line header edit
    in a 718 KB text is reported as hundreds of thousands of "differing positions". This quotes the window
    around the *first* difference, which stays short whatever the shift does, and then realigns the two copies
    line by line and publishes how many separate edits there actually are. The line count is what a reader needs
    to judge whether a drift could move a number; the positional count cannot answer that on its own.
    """
    offsets = [index for index, (left, right) in enumerate(zip(acquired, live)) if left != right]
    if not offsets and len(acquired) != len(live):
        return {"differing_bytes_in_common_prefix": 0,
                "length_change": len(live) - len(acquired),
                "explanation": "identical up to the end of the shorter copy, so this is an appended or "
                               "truncated file rather than an edit"}
    start = offsets[0]
    stop = offsets[-1]

    def snippet(data):
        raw = data[max(0, start - window):start + window]
        text = re.sub(r"[^\x20-\x7e\r\n\t]", "?", raw.decode("utf-8", "replace"))
        return text.strip()

    difference = {"differing_bytes_in_common_prefix": len(offsets),
                  "first_differing_offset": start,
                  "last_differing_offset": stop,
                  "length_change": len(live) - len(acquired),
                  "acquired_snippet": snippet(acquired),
                  "live_snippet": snippet(live)}
    difference.update(characterise_by_lines(acquired, live, limit))
    blocks = difference["differing_line_blocks"]
    if len(offsets) <= 64:
        difference["explanation"] = ("the publisher edited the file in place; the two copies differ at "
                                     f"{len(offsets)} byte position(s)")
    elif blocks is not None and blocks <= limit:
        difference["explanation"] = (
            f"the two copies differ at {len(offsets)} byte positions, which is the arithmetic of a shift rather "
            f"than {len(offsets)} edits: realigned line by line they differ at {blocks} block(s), and the file's "
            f"length changed by {abs(len(live) - len(acquired))} byte(s)")
    else:
        difference["explanation"] = (f"the two copies differ at {len(offsets)} byte positions and at {blocks} "
                                     "line block(s), too many to quote")
    return difference


def decode(data):
    return re.sub(r"[^\x20-\x7e\r\n\t]", "?", data.decode("utf-8", "replace"))


def characterise_by_lines(acquired, live, limit, maximum_lines=40000, context=200):
    """How many separate edits the two copies actually contain, and the first few of them quoted.

    Returns `differing_line_blocks` as None when the file is too large to align, because a missing characterisation
    is honest and a silently truncated one is not.
    """
    left, right = decode(acquired).splitlines(), decode(live).splitlines()
    if len(left) > maximum_lines or len(right) > maximum_lines:
        return {"differing_line_blocks": None, "acquired_lines": len(left), "live_lines": len(right),
                "line_differences": [],
                "line_characterisation": "not attempted: the file is larger than this tool aligns line by line"}
    blocks = []
    for tag, first, last, other_first, other_last in \
            difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        blocks.append({"edit": tag,
                       "acquired_line": first + 1,
                       "acquired_text": " / ".join(line[:context] for line in left[first:last][:3]),
                       "live_line": other_first + 1,
                       "live_text": " / ".join(line[:context] for line in right[other_first:other_last][:3])})
    return {"differing_line_blocks": len(blocks),
            "acquired_lines": len(left),
            "live_lines": len(right),
            "line_differences": blocks[:limit],
            "line_characterisation": (f"the two copies align to {len(blocks)} separate edit(s) once compared "
                                      f"line by line instead of byte by byte"
                                      if blocks else "the two copies differ only in byte alignment")}


def check(work, acquired_dir, delay, attempts):
    record = {"work_id": work["work_id"], "gutenberg_id": work.get("gutenberg_id"),
              "source_url": work["source_url"], "acquired_sha256": work["sha256"],
              "acquired_bytes": work["bytes"]}
    path = acquired_dir / f"{work['work_id']}.txt"
    if not path.exists():
        record["status"] = "acquired_copy_absent"
        record["interpretation"] = "corpus/raw/ is gitignored; run tools/acquire_corpus.py locally first"
        return record
    acquired = path.read_bytes()
    if sha256(acquired) != work["sha256"]:
        record["status"] = "local_copy_does_not_match_the_manifest"
        record["local_sha256"] = sha256(acquired)
        record["interpretation"] = ("the bytes on this machine are not the bytes the manifest recorded, so "
                                    "the comparison below is against a substituted local copy")
        return record
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(work["source_url"],
                                             headers={"User-Agent": "NarrativeResearchCorpus/1.0 "
                                                                     "(source-provenance research)"})
            with urllib.request.urlopen(request, timeout=120) as handle:
                live = handle.read()
            break
        except Exception as exc:
            last = exc
            time.sleep(delay * (attempt + 1))
    else:
        record["status"] = "fetch_failed"
        record["error"] = f"{type(last).__name__}: {last}"
        return record
    time.sleep(delay)
    live_digest = sha256(live)
    record["live_sha256"] = live_digest
    record["live_bytes"] = len(live)
    if live_digest == work["sha256"]:
        record["status"] = "match"
        return record
    record["status"] = "drifted"
    record["difference"] = describe_difference(acquired, live)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-to", help="publish the report as a JSON artifact at this path")
    parser.add_argument("--works", help="comma-separated work ids; the default is every work in the manifest")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds to wait between requests")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args(argv)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    works = manifest["works"]
    if args.works:
        wanted = {name.strip() for name in args.works.split(",") if name.strip()}
        known = {work["work_id"] for work in works}
        unknown = sorted(wanted - known)
        if unknown:
            raise SystemExit(f"--works names ids the manifest does not declare: {unknown}")
        works = [work for work in works if work["work_id"] in wanted]

    acquired_dir = ROOT / "corpus/raw"
    results = []
    for index, work in enumerate(works, 1):
        record = check(work, acquired_dir, args.delay, args.attempts)
        results.append(record)
        print(f"[{index}/{len(works)}] {record['work_id']}: {record['status']}")

    tally = {}
    for record in results:
        tally[record["status"]] = tally.get(record["status"], 0) + 1
    report = {
        "produced_by": "python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha256(MANIFEST_PATH.read_bytes()),
        "works_checked": len(results),
        "tally": dict(sorted(tally.items())),
        "drifted": [record["work_id"] for record in results if record["status"] == "drifted"],
        "works": results,
        "interpretation": (
            "External stability, not internal freshness. A match means the publisher still serves the bytes "
            "the manifest recorded; a drift means a fresh run of tools/acquire_corpus.py on this machine "
            "would produce a different corpus from the one every published artifact was computed from. "
            "Neither result changes any number in this repository: the artifacts are pinned to the recorded "
            "hashes, and the tests re-hash those bytes. What a drift changes is what a third party can "
            "re-acquire, so the manifest, not the live site, is the authority for this study's measurements."
        ),
        "what_it_does_not_establish": (
            "It does not show the acquired texts are correct, complete or rights-clean; it does not date the "
            "edit; and one run is a snapshot, not a monitoring record. Works whose acquired copy is absent "
            "because corpus/raw/ is gitignored are reported separately rather than counted as drift."
        ),
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.write_to:
        target = Path(args.write_to)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
        print(f"wrote {target} works_checked={len(results)} tally={report['tally']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
