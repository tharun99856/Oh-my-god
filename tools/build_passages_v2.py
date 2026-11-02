import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from narrative_v2 import segment_narrative

ROOT = Path(__file__).resolve().parents[1]


def main():
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    output_path = ROOT / "corpus/derived/passages_v2.jsonl"
    all_passages = []
    counts = Counter()
    for work in acquisition["works"]:
        if work["status"] == "failed":
            continue
        with (ROOT / f"corpus/derived/{work['work_id']}.clean.txt").open(encoding="utf-8", newline="") as clean_handle:
            body = clean_handle.read()
        passages = segment_narrative(body, work["work_id"])
        for passage in passages:
            passage["raw_char_start"] = work["body_char_start"] + passage["body_char_start"]
            passage["raw_char_end"] = work["body_char_start"] + passage["body_char_end"]
            if passage["eligible_for_similarity"]:
                counts["eligible"] += 1
            elif passage["exclusion_reason"]:
                counts["excluded_by_rule"] += 1
            else:
                counts["too_short"] += 1
            counts[passage["exclusion_reason"] or "unclassified_source_text"] += 1
        all_passages.extend(passages)
        print(f"{work['work_id']}: {len(passages)} passages")
    with output_path.open("w", encoding="utf-8") as handle:
        for passage in all_passages:
            handle.write(json.dumps(passage, ensure_ascii=False) + "\n")
    summary = {
        "schema_version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "acquisition_manifest_sha256": hashlib.sha256(acquisition_path.read_bytes()).hexdigest(),
        "passages_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "segmentation_code_sha256": hashlib.sha256((ROOT / "tools/narrative_v2.py").read_bytes()).hexdigest(),
        "build_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "passages": len(all_passages),
        "counts": dict(counts),
        "segmentation": "source-heading-aware sections with 450-word maximum; no claim that every passage is a complete narrative",
    }
    (ROOT / "corpus/derived/passages_v2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"passages": len(all_passages), "counts": dict(counts)}, indent=2))


if __name__ == "__main__":
    main()
