import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_similarity import sha256
from run_similarity_v2 import build_dependence_index, dependence_between, vectorizer

ROOT = Path(__file__).resolve().parents[1]


def main():
    started = time.time()
    passages_path = ROOT / "corpus/derived/passages_v2.jsonl"
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    dependence_path = ROOT / "config/source_dependence.json"
    passages = [json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines()]
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in acquisition["works"] if work["status"] != "failed"}
    dependence_config = json.loads(dependence_path.read_text(encoding="utf-8"))
    families, pair_rules = build_dependence_index(dependence_config)
    work_ids = np.array([passage["work_id"] for passage in passages])
    matrix = vectorizer((1, 2)).fit_transform([passage["text"] for passage in passages])
    top_pairs = {}
    batch_size = 128
    neighbors = 6
    for start in range(0, len(passages), batch_size):
        end = min(start + batch_size, len(passages))
        similarities = (matrix[start:end] @ matrix.T).toarray()
        for local_index in range(end - start):
            index = start + local_index
            row = similarities[local_index]
            row[work_ids == work_ids[index]] = -1
            candidates = np.argpartition(row, -neighbors)[-neighbors:]
            for other in candidates:
                score = min(1.0, max(0.0, float(row[other])))
                if score < 0.15:
                    continue
                left, right = sorted((index, int(other)))
                top_pairs[(left, right)] = max(score, top_pairs.get((left, right), 0.0))
        if start % (batch_size * 20) == 0:
            print(f"Scored {end}/{len(passages)} unfiltered passages")

    counts = {
        "candidate_pairs": 0,
        "pairs_involving_rule_excluded_passages": 0,
        "pairs_involving_short_passages": 0,
        "pairs_between_eligible_passages": 0,
        "known_dependent_pairs": 0,
    }
    with (ROOT / "results/v2_unfiltered_candidate_pairs.jsonl").open("w", encoding="utf-8") as handle:
        for (left, right), score in sorted(top_pairs.items(), key=lambda item: item[1], reverse=True):
            left_passage = passages[left]
            right_passage = passages[right]
            dependence = dependence_between(left_passage["work_id"], right_passage["work_id"], works, families, pair_rules)
            rule_excluded = bool(left_passage["exclusion_reason"] or right_passage["exclusion_reason"])
            short = bool(
                (not left_passage["eligible_for_similarity"] and not left_passage["exclusion_reason"])
                or (not right_passage["eligible_for_similarity"] and not right_passage["exclusion_reason"])
            )
            both_eligible = left_passage["eligible_for_similarity"] and right_passage["eligible_for_similarity"]
            counts["candidate_pairs"] += 1
            counts["pairs_involving_rule_excluded_passages"] += int(rule_excluded)
            counts["pairs_involving_short_passages"] += int(short)
            counts["pairs_between_eligible_passages"] += int(both_eligible)
            counts["known_dependent_pairs"] += int(dependence is not None)
            handle.write(json.dumps({
                "left": left_passage["passage_id"],
                "right": right_passage["passage_id"],
                "score": round(score, 8),
                "left_eligible": left_passage["eligible_for_similarity"],
                "right_eligible": right_passage["eligible_for_similarity"],
                "rule_excluded": rule_excluded,
                "short_passage": short,
                "dependence_relationship": dependence["relationship"] if dependence else None,
            }) + "\n")

    cleaned_path = ROOT / "results/v2_run_summary.json"
    cleaned = json.loads(cleaned_path.read_text(encoding="utf-8")) if cleaned_path.exists() else None
    summary = {
        "schema_version": "2.0",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
        "interpretation": "Descriptive same-corpus ablation. The unfiltered and cleaned models are fitted separately, so count differences also include vocabulary and IDF changes.",
        "input_passages": len(passages),
        **counts,
        "cleaned_candidate_pairs": cleaned["candidate_pairs"] if cleaned else None,
        "candidate_count_reduction_from_unfiltered": (
            1 - cleaned["candidate_pairs"] / counts["candidate_pairs"]
            if cleaned and counts["candidate_pairs"] else None
        ),
        "configuration": {
            "neighbors_per_passage": neighbors,
            "minimum_retained_score": 0.15,
            "vectorizer": "same TF-IDF settings as the v2 cleaned run",
        },
        "reproducibility": {
            "acquisition_manifest_sha256": sha256(acquisition_path),
            "passages_sha256": sha256(passages_path),
            "source_dependence_sha256": sha256(dependence_path),
            "analysis_code_sha256": sha256(Path(__file__)),
        },
    }
    (ROOT / "results/v2_cleaning_ablation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
