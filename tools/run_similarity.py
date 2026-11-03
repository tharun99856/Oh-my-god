import csv
import hashlib
import json
import platform
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer

from text_pipeline import WORD_RE

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261031


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_cosine(matrix, left, right):
    return np.asarray(matrix[left].multiply(matrix[right]).sum(axis=1)).ravel()


def stats(values):
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p95": float(np.quantile(values, 0.95)),
        "p99": float(np.quantile(values, 0.99)),
        "max": float(np.max(values)),
    }


def main():
    started = time.time()
    passages_path = ROOT / "corpus/derived/passages.jsonl"
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    lexicon_path = ROOT / "config/motif_lexicon.json"
    passages = [json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines()]
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in acquisition["works"] if work["status"] != "failed"}
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    texts = [passage["text"] for passage in passages]
    work_ids = np.array([passage["work_id"] for passage in passages])

    compiled_lexicon = {
        motif: [re.compile(r"(?<!\w)" + re.escape(term) + (r"s?" if term.isalpha() else "") + r"(?!\w)", re.IGNORECASE) for term in terms]
        for motif, terms in lexicon.items()
    }
    motif_hits = []
    for passage in passages:
        hits = [motif for motif, patterns in compiled_lexicon.items() if any(pattern.search(passage["text"]) for pattern in patterns)]
        motif_hits.append(hits)
    with (ROOT / "results/motif_candidates.jsonl").open("w", encoding="utf-8", newline="\r\n") as handle:
        for passage, hits in zip(passages, motif_hits):
            if hits:
                handle.write(json.dumps({"passage_id": passage["passage_id"], "work_id": passage["work_id"], "motifs": hits}) + "\n")

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.85,
        max_features=120000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)
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
            count = min(neighbors, len(row))
            candidates = np.argpartition(row, -count)[-count:]
            for other in candidates:
                score = min(1.0, max(0.0, float(row[other])))
                if score < 0.15:
                    continue
                left, right = sorted((index, int(other)))
                top_pairs[(left, right)] = max(score, top_pairs.get((left, right), 0.0))
        if start % (batch_size * 20) == 0:
            print(f"Scored {end}/{len(passages)} passages")

    rng = np.random.default_rng(SEED)
    random_left = rng.integers(0, len(passages), size=20000)
    random_right = rng.integers(0, len(passages), size=20000)
    valid = work_ids[random_left] != work_ids[random_right]
    random_left = random_left[valid]
    random_right = random_right[valid]
    random_scores = row_cosine(matrix, random_left, random_right)

    sample_indices = rng.choice(len(passages), size=256, replace=False)
    shuffled_texts = []
    for index in sample_indices:
        words = [match.group(0) for match in WORD_RE.finditer(texts[index])]
        rng.shuffle(words)
        shuffled_texts.append(" ".join(words))
    shuffled_matrix = vectorizer.transform(shuffled_texts)
    shuffled_scores = np.asarray(matrix[sample_indices].multiply(shuffled_matrix).sum(axis=1)).ravel()

    def max_between(left_work, right_work):
        left_indices = np.flatnonzero(work_ids == left_work)
        right_indices = np.flatnonzero(work_ids == right_work)
        similarities = (matrix[left_indices] @ matrix[right_indices].T).toarray()
        position = np.unravel_index(int(np.argmax(similarities)), similarities.shape)
        left = int(left_indices[position[0]])
        right = int(right_indices[position[1]])
        return {"left": passages[left]["passage_id"], "right": passages[right]["passage_id"], "score": min(1.0, max(0.0, float(similarities[position])))}

    overlap_checks = {
        "sacred_books_east_vs_quran_sale": max_between("sacred_books_east", "quran_sale"),
        "sacred_books_east_vs_dhammapada": max_between("sacred_books_east", "dhammapada_muller"),
    }

    ordered_pairs = sorted(((left, right, score) for (left, right), score in top_pairs.items()), key=lambda item: item[2], reverse=True)
    with (ROOT / "results/candidate_pairs.jsonl").open("w", encoding="utf-8", newline="\r\n") as handle:
        for left, right, score in ordered_pairs:
            handle.write(json.dumps({
                "left": passages[left]["passage_id"],
                "right": passages[right]["passage_id"],
                "score": round(score, 8),
                "shared_motifs": sorted(set(motif_hits[left]) & set(motif_hits[right])),
                "interpretation": "possible_textual_reuse" if score >= 0.80 else "candidate_only_not_historical_evidence",
            }) + "\n")

    with (ROOT / "results/top_pairs_for_review.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["rank", "score", "left_id", "right_id", "left_work", "right_work", "shared_motifs", "left_excerpt", "right_excerpt"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, (left, right, score) in enumerate(ordered_pairs[:500], 1):
            writer.writerow({
                "rank": rank,
                "score": f"{score:.6f}",
                "left_id": passages[left]["passage_id"],
                "right_id": passages[right]["passage_id"],
                "left_work": works[passages[left]["work_id"]].get("Title", passages[left]["work_id"]),
                "right_work": works[passages[right]["work_id"]].get("Title", passages[right]["work_id"]),
                "shared_motifs": "|".join(sorted(set(motif_hits[left]) & set(motif_hits[right]))),
                "left_excerpt": " ".join(texts[left].split())[:500],
                "right_excerpt": " ".join(texts[right].split())[:500],
            })

    summary = {
        "schema_version": "1.0",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
        "interpretation": "English-translation lexical candidate retrieval only; not ancestry probability or historical relationship confidence",
        "corpus": {
            "works": len(works),
            "passages": len(passages),
            "words": sum(work["word_count"] for work in works.values()),
            "source_bytes": sum(work["bytes"] for work in works.values()),
            "regions": dict(Counter(work["region"] for work in works.values())),
            "source_roles": dict(Counter(work["source_role"] for work in works.values())),
            "passages_with_motif_hits": sum(bool(hits) for hits in motif_hits),
            "motif_hit_counts": dict(Counter(motif for hits in motif_hits for motif in hits)),
        },
        "configuration": {
            "seed": SEED,
            "vectorizer": json.loads(json.dumps(vectorizer.get_params(), default=str)),
            "vocabulary_size": len(vectorizer.vocabulary_),
            "neighbors_per_passage": neighbors,
            "minimum_retained_score": 0.15,
        },
        "candidate_pairs": len(ordered_pairs),
        "random_cross_work_pairs": stats(random_scores),
        "shuffled_sequence_sensitivity": stats(shuffled_scores),
        "known_overlap_checks": overlap_checks,
        "reproducibility": {
            "acquisition_manifest_sha256": sha256(acquisition_path),
            "passages_sha256": sha256(passages_path),
            "motif_lexicon_sha256": sha256(lexicon_path),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }
    (ROOT / "results/run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\r\n")
    print(json.dumps({
        "works": summary["corpus"]["works"],
        "passages": len(passages),
        "candidate_pairs": len(ordered_pairs),
        "random_p99": summary["random_cross_work_pairs"]["p99"],
        "shuffled_mean": summary["shuffled_sequence_sensitivity"]["mean"],
        "known_overlap_checks": overlap_checks,
    }, indent=2))


if __name__ == "__main__":
    main()
