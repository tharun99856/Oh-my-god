import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from text_pipeline import extract_body, segment_text

FIELDS = ["Title", "Author", "Translator", "Editor", "Release date", "Language", "Original publication"]


def parse_metadata(raw_text):
    header = raw_text.split("*** START OF", 1)[0]
    metadata = {}
    current = None
    for line in header.splitlines():
        stripped = line.strip()
        matched = False
        for field in FIELDS:
            if stripped.startswith(field + ":"):
                current = field
                metadata[current] = stripped.split(":", 1)[1].strip()
                matched = True
                break
        if not matched and current and stripped and line[:1].isspace():
            metadata[current] += " " + stripped
        elif not stripped:
            current = None
    return metadata


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def acquire(args):
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / args.manifest
    raw_dir = root / "corpus/raw"
    derived_dir = root / "corpus/derived"
    raw_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        works = list(csv.DictReader(handle))
    if args.only:
        selected = set(args.only.split(","))
        works = [work for work in works if work["work_id"] in selected]

    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    session = requests.Session()
    session.headers["User-Agent"] = "NarrativeResearchCorpus/1.0 (source-provenance research)"
    session.mount("https://", HTTPAdapter(max_retries=retry))
    records = []
    all_passages = []
    manifest_output = root / "corpus/acquisition_manifest.json"
    previous = {}
    if manifest_output.exists():
        previous = {item["work_id"]: item for item in json.loads(manifest_output.read_text(encoding="utf-8"))["works"]}

    for index, work in enumerate(works, 1):
        work_id = work["work_id"]
        book_id = work["gutenberg_id"]
        url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
        output = raw_dir / f"{work_id}.txt"
        record = dict(work)
        record.update({"source_url": url, "source_page": f"https://www.gutenberg.org/ebooks/{book_id}"})
        try:
            if output.exists():
                data = output.read_bytes()
                status = "cached"
            else:
                response = session.get(url, timeout=90)
                response.raise_for_status()
                data = response.content
                if len(data) > 200_000_000:
                    raise ValueError("Source exceeds 200 MB safety limit")
                partial = output.with_suffix(".part")
                partial.write_bytes(data)
                partial.replace(output)
                status = "downloaded"
                time.sleep(0.2)
            raw_text = data.decode("utf-8-sig")
            body, body_start, body_end = extract_body(raw_text)
            passages = segment_text(body, work_id, args.target_words, args.min_words)
            for passage in passages:
                passage["raw_char_start"] = body_start + passage["body_char_start"]
                passage["raw_char_end"] = body_start + passage["body_char_end"]
            with (derived_dir / f"{work_id}.clean.txt").open("w", encoding="utf-8", newline="") as clean_handle:
                clean_handle.write(body)
            all_passages.extend(passages)
            record.update(parse_metadata(raw_text))
            previous_time = previous.get(work_id, {}).get("acquired_at_utc")
            acquired_at = previous_time or (datetime.fromtimestamp(output.stat().st_mtime, timezone.utc).isoformat() if status == "cached" else datetime.now(timezone.utc).isoformat())
            record.update({
                "status": status,
                "sha256": sha256(data),
                "bytes": len(data),
                "acquired_at_utc": acquired_at,
                "rights_notice": "Project Gutenberg notice retained in raw source; verify copyright by jurisdiction",
                "body_char_start": body_start,
                "body_char_end": body_end,
                "passage_count": len(passages),
                "word_count": sum(p["word_count"] for p in passages),
            })
            print(f"[{index}/{len(works)}] {work_id}: {status}, {len(passages)} passages")
        except Exception as exc:
            record.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{index}/{len(works)}] {work_id}: FAILED: {exc}")
        records.append(record)

    manifest_output.write_text(json.dumps({
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_words": args.target_words,
        "min_words": args.min_words,
        "works": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with (derived_dir / "passages.jsonl").open("w", encoding="utf-8") as handle:
        for passage in all_passages:
            handle.write(json.dumps(passage, ensure_ascii=False) + "\n")
    failures = [record for record in records if record["status"] == "failed"]
    print(f"Completed: {len(records) - len(failures)} acquired, {len(failures)} failed, {len(all_passages)} passages")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="config/corpus_manifest.csv")
    parser.add_argument("--only")
    parser.add_argument("--target-words", type=int, default=350)
    parser.add_argument("--min-words", type=int, default=80)
    raise SystemExit(acquire(parser.parse_args()))
