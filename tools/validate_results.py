import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    passages_path = ROOT / "corpus/derived/passages.jsonl"
    summary_path = ROOT / "results/run_summary.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works = acquisition["works"]
    passages = [json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines()]
    assert all(work["status"] != "failed" for work in works), "Failed source remains"
    assert len({work["work_id"] for work in works}) == len(works), "Duplicate work ID"
    assert len({passage["passage_id"] for passage in passages}) == len(passages), "Duplicate passage ID"
    assert sum(work["passage_count"] for work in works) == len(passages), "Passage count mismatch"

    raw_cache = {}
    for work in works:
        path = ROOT / f"corpus/raw/{work['work_id']}.txt"
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == work["sha256"], f"Hash mismatch: {work['work_id']}"
        raw_cache[work["work_id"]] = data.decode("utf-8-sig")
    for passage in passages:
        raw = raw_cache[passage["work_id"]]
        assert raw[passage["raw_char_start"]:passage["raw_char_end"]] == passage["text"], f"Offset mismatch: {passage['passage_id']}"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["reproducibility"]["passages_sha256"] == hashlib.sha256(passages_path.read_bytes()).hexdigest(), "Stale similarity run"
    assert summary["corpus"]["works"] == len(works)
    assert summary["corpus"]["passages"] == len(passages)
    pairs_path = ROOT / "results/candidate_pairs.jsonl"
    pair_count = 0
    for line in pairs_path.read_text(encoding="utf-8").splitlines():
        pair = json.loads(line)
        assert 0 <= pair["score"] <= 1
        pair_count += 1
    assert pair_count == summary["candidate_pairs"]
    assert (ROOT / "results/model_comparison.json").exists()
    print(json.dumps({
        "status": "passed",
        "works_verified": len(works),
        "passages_verified": len(passages),
        "candidate_pairs_verified": pair_count,
        "raw_hashes_verified": len(raw_cache),
        "stale_result_check": "passed",
    }, indent=2))


if __name__ == "__main__":
    main()
