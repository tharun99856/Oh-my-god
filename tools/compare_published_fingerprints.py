"""Compare every published artifact against the same artifact at a named git revision and say which bytes moved.

**Why this tool exists.** The reproduction sequence in `TEST_REPORT.md` section 13 takes about twenty-five
minutes, and at the end of it a reviewer is left with a question that no single artifact answers: did re-running
the pipeline change any *measurement*, or only the stamps that record when and against which source hash the run
happened to be made? The freshness assertions inside the run summaries prove the artifacts agree with their
inputs *now*; they say nothing about whether today's numbers are yesterday's numbers. This tool answers that by
digesting each artifact twice — once as bytes, once with the fields that are supposed to move stripped out —
and classifying every file as unchanged, stamp-only, or measurement-changed.

**What it does not establish.** A byte-identical rebuild shows that the pipeline is deterministic, not that it
is right; an artifact that measures the wrong thing will reproduce its wrongness perfectly. The baseline is
whatever revision is named: if that revision's artifacts were produced by different tools, then agreement with
it demonstrates only that the older run repeated, not that the method is sound. And files that exist in only one
of the two trees are reported as added or removed rather than counted as evidence either way.

    python tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json
    python tools/compare_published_fingerprints.py --against HEAD~1 --write-to tmp.json
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "results/fingerprint_diff.json"
SCOPE_DIRECTORIES = ("results", "config")
SCOPE_FILES = ("corpus/acquisition_manifest.json",)

# Fields whose job is to record that a run happened. They are removed from both sides before the stable digest,
# so a file whose only movement is a new timestamp or a new input hash is classified `stamps_only`.
VOLATILE_KEYS = {"generated_at", "timestamp", "verified_at", "compiled_at", "run_at",
                 "seed_provenance", "elapsed_seconds", "partial_run", "compared_at_utc"}
VOLATILE_SUFFIXES = ("_sha256", "_at_utc", "_at")

TEXT_EXTS = {".json", ".jsonl", ".csv", ".html", ".svg", ".txt", ".sql", ".yaml", ".yml"}
HEX_RUN = re.compile(r"\b[0-9a-f]{64}\b")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


def run_git(arguments):
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True)


def baseline_blob(revision, path):
    result = run_git(["show", f"{revision}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout


def strip_volatile(value):
    if isinstance(value, dict):
        return {key: strip_volatile(item) for key, item in sorted(value.items())
                if key not in VOLATILE_KEYS and not key.endswith(VOLATILE_SUFFIXES)}
    if isinstance(value, list):
        return [strip_volatile(item) for item in value]
    return value


def stable_digest(path, data):
    """A digest of the measurements, or None when the file has no parseable measured content."""
    if path.suffix not in TEXT_EXTS:
        return None
    text = data.decode("utf-8", errors="replace")
    if path.suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return hashlib.sha256(json.dumps(strip_volatile(payload), sort_keys=True,
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    if path.suffix == ".jsonl":
        rows = []
        for line in text.splitlines():
            try:
                rows.append(json.dumps(strip_volatile(json.loads(line)), sort_keys=True, ensure_ascii=False))
            except json.JSONDecodeError:
                rows.append(line)
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    # Rendered pages and CSVs carry provenance inline: a state page re-prints the hashes of the artifacts it
    # read, and a CSV can carry a passage digest in a column. Those are stamps that moved into the body, so
    # they are masked before the digest rather than counted as a changed measurement.
    masked = HEX_RUN.sub("DIGEST", text)
    masked = TIMESTAMP.sub("TIMESTAMP", masked)
    return hashlib.sha256(masked.encode("utf-8")).hexdigest()


def enumerate_paths(revision, exclude=None):
    paths = set()
    for directory in SCOPE_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file():
                paths.add(path.relative_to(ROOT).as_posix())
    for name in SCOPE_FILES:
        if (ROOT / name).is_file():
            paths.add(name)
    listed = run_git(["ls-tree", "-r", "--name-only", revision])
    if listed.returncode == 0:
        for line in listed.stdout.decode("utf-8", errors="replace").splitlines():
            if line.startswith(("results/", "config/")) or line in SCOPE_FILES:
                paths.add(line)
    if exclude:
        paths.discard(exclude)
    return sorted(paths)


def classify(current, base, current_stable, base_stable):
    if current is None:
        return "removed_since_baseline"
    if base is None:
        return "added_since_baseline"
    if current == base:
        return "byte_identical"
    if current_stable is None or base_stable is None:
        return "opaque_change"
    if current_stable == base_stable:
        return "stamps_only"
    return "measurement_changed"


def compare(revision="HEAD", exclude=None):
    resolved = run_git(["rev-parse", revision])
    if resolved.returncode != 0:
        raise SystemExit(f"`git rev-parse {revision}` failed: {resolved.stderr.decode('utf-8', errors='replace').strip()}")
    rows = []
    for name in enumerate_paths(revision, exclude=exclude):
        path = Path(name)
        current = (ROOT / name).read_bytes() if path.is_file() else None
        base = baseline_blob(revision, name)
        current_stable = stable_digest(path, current) if current is not None else None
        base_stable = stable_digest(path, base) if base is not None else None
        rows.append({
            "path": name,
            "status": classify(current, base, current_stable, base_stable),
            "bytes_now": len(current) if current is not None else None,
            "bytes_at_baseline": len(base) if base is not None else None,
            "sha256_now": hashlib.sha256(current).hexdigest() if current is not None else None,
            "sha256_at_baseline": hashlib.sha256(base).hexdigest() if base is not None else None,
            "measured_sha256_now": current_stable,
            "measured_sha256_at_baseline": base_stable,
        })
    tally = {}
    for row in rows:
        tally[row["status"]] = tally.get(row["status"], 0) + 1
    return {
        "produced_by": "python tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json",
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_revision": revision,
        "baseline_commit": resolved.stdout.decode("utf-8").strip(),
        "scope": {"directories": list(SCOPE_DIRECTORIES), "files": list(SCOPE_FILES)},
        "volatile_fields_stripped_before_the_measured_digest": sorted(VOLATILE_KEYS),
        "volatile_suffixes_stripped_before_the_measured_digest": sorted(VOLATILE_SUFFIXES),
        "non_json_text_digest_policy": ("64-hex runs and ISO-8601 timestamps are masked before the measured digest of "
                                        "a CSV, page or SVG, because rendered files reprint the hashes of what they read"),
        "files_compared": len(rows),
        "tally": tally,
        "changed": [row for row in rows if row["status"] != "byte_identical"],
        "files": rows,
        "interpretation": (
            "byte_identical means the rebuilt file is the file the baseline carried. stamps_only means the "
            "bytes differ but every difference sits in a field whose purpose is to record that a run happened "
            "(a timestamp, an elapsed time, or a hash of an input that itself moved). measurement_changed is "
            "the only status that should make a reader reopen the paper's tables, and added_since_baseline or "
            "removed_since_baseline mean the artifact set itself moved, which is a different kind of change."
        ),
        "what_this_does_not_establish": (
            "that the pipeline measures what it claims to measure: a deterministic instrument reproduces its own "
            "errors exactly as faithfully as its successes. It also does not establish that the baseline revision "
            "was produced by the tools now in the tree -- it compares bytes, not methods -- and a file listed as "
            "byte_identical here is byte_identical with a commit, not with the run that made that commit."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--against", default="HEAD", help="git revision to compare against (default HEAD)")
    parser.add_argument("--write-to", help=f"publish the report (default {DEFAULT_OUTPUT.name})")
    args = parser.parse_args(argv)
    output = Path(args.write_to) if args.write_to else DEFAULT_OUTPUT
    if not output.is_absolute():
        output = ROOT / output
    # The report describes itself otherwise: its own bytes are about to change, so it would be listed as a
    # changed measurement in the file it writes.
    relative = output.relative_to(ROOT).as_posix() if output.is_relative_to(ROOT) else None
    report = compare(args.against, exclude=relative)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {output.name} files_compared={report['files_compared']} tally={report['tally']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
