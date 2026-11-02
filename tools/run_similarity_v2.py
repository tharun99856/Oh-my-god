import csv
import hashlib
import json
import platform
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer

from run_similarity import row_cosine, sha256, stats
from text_pipeline import WORD_RE

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261031


def build_dependence_index(config):
    families = {}
    for family in config["work_families"]:
        for work_id in family["work_ids"]:
            families[work_id] = family
    pair_rules = {
        frozenset((rule["left_work"], rule["right_work"])): rule
        for rule in config["pair_rules"]
    }
    return families, pair_rules


def dependence_between(left_work, right_work, works, families, pair_rules):
    rule = pair_rules.get(frozenset((left_work, right_work)))
    if rule:
        return rule
    left_family = families.get(left_work)
    right_family = families.get(right_work)
    if left_family and left_family is right_family:
        return left_family
    left_group = works[left_work].get("overlap_group")
    right_group = works[right_work].get("overlap_group")
    if left_group and left_group == right_group:
        return {
            "relationship": "manifest_overlap_group",
            "exclude_from_independent_analysis": True,
            "rationale": f"Both works belong to overlap group {left_group}.",
        }
    return None


def shuffle_sentences(text, rng):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    rng.shuffle(sentences)
    return " ".join(sentences)


def random_independent_pairs(rng, count, work_ids, works, families, pair_rules):
    left_values = []
    right_values = []
    while len(left_values) < count:
        left = rng.integers(0, len(work_ids), size=count * 2)
        right = rng.integers(0, len(work_ids), size=count * 2)
        for left_index, right_index in zip(left, right):
            left_work = work_ids[left_index]
            right_work = work_ids[right_index]
            if left_work == right_work:
                continue
            if dependence_between(left_work, right_work, works, families, pair_rules):
                continue
            left_values.append(int(left_index))
            right_values.append(int(right_index))
            if len(left_values) == count:
                break
    return np.array(left_values), np.array(right_values)


def length_matched_pairs(rng, count, word_counts, work_ids, works, families, pair_rules, bin_width=50):
    bins = defaultdict(list)
    for index, word_count in enumerate(word_counts):
        bins[int(word_count) // bin_width].append(index)
    left_values = []
    right_values = []
    while len(left_values) < count:
        left = int(rng.integers(0, len(work_ids)))
        tolerance = max(30, int(word_counts[left] * 0.25))
        minimum_bin = max(0, int(word_counts[left] - tolerance) // bin_width)
        maximum_bin = int(word_counts[left] + tolerance) // bin_width
        pool = []
        for bin_index in range(minimum_bin, maximum_bin + 1):
            pool.extend(bins.get(bin_index, []))
        pool = np.array(pool, dtype=int)
        valid = (
            (work_ids[pool] != work_ids[left])
            & (np.abs(word_counts[pool] - word_counts[left]) <= tolerance)
        )
        candidates = pool[valid]
        if not len(candidates):
            continue
        right = int(candidates[rng.integers(0, len(candidates))])
        if dependence_between(work_ids[left], work_ids[right], works, families, pair_rules):
            continue
        left_values.append(left)
        right_values.append(right)
    return np.array(left_values), np.array(right_values)


def vectorizer(ngram_range):
    return TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words="english",
        ngram_range=ngram_range,
        min_df=2,
        max_df=0.85,
        max_features=120000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )


def main():
    started = time.time()
    passages_path = ROOT / "corpus/derived/passages_v2.jsonl"
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    lexicon_path = ROOT / "config/motif_lexicon.json"
    dependence_path = ROOT / "config/source_dependence.json"
    all_passages = [json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines()]
    passages = [passage for passage in all_passages if passage["eligible_for_similarity"]]
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in acquisition["works"] if work["status"] != "failed"}
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    dependence_config = json.loads(dependence_path.read_text(encoding="utf-8"))
    families, pair_rules = build_dependence_index(dependence_config)
    texts = [passage["text"] for passage in passages]
    work_ids = np.array([passage["work_id"] for passage in passages])
    word_counts = np.array([passage["word_count"] for passage in passages])

    compiled_lexicon = {
        motif: [re.compile(r"(?<!\w)" + re.escape(term) + (r"s?" if term.isalpha() else "") + r"(?!\w)", re.IGNORECASE) for term in terms]
        for motif, terms in lexicon.items()
    }
    motif_hits = []
    with (ROOT / "results/v2_motif_candidates.jsonl").open("w", encoding="utf-8") as handle:
        for passage in passages:
            hits = [motif for motif, patterns in compiled_lexicon.items() if any(pattern.search(passage["text"]) for pattern in patterns)]
            motif_hits.append(hits)
            if hits:
                handle.write(json.dumps({"passage_id": passage["passage_id"], "work_id": passage["work_id"], "motifs": hits}) + "\n")

    mixed_vectorizer = vectorizer((1, 2))
    matrix = mixed_vectorizer.fit_transform(texts)
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
    random_left, random_right = random_independent_pairs(rng, 20000, work_ids, works, families, pair_rules)
    random_scores = row_cosine(matrix, random_left, random_right)
    matched_left, matched_right = length_matched_pairs(rng, 20000, word_counts, work_ids, works, families, pair_rules)
    matched_scores = row_cosine(matrix, matched_left, matched_right)

    sentence_eligible = np.array([
        index for index, text in enumerate(texts)
        if len(re.split(r"(?<=[.!?])\s+", text.strip())) >= 4
    ])
    sample_indices = rng.choice(sentence_eligible, size=min(256, len(sentence_eligible)), replace=False)
    word_shuffled_texts = []
    sentence_shuffled_texts = []
    for index in sample_indices:
        words = [match.group(0) for match in WORD_RE.finditer(texts[index])]
        rng.shuffle(words)
        word_shuffled_texts.append(" ".join(words))
        sentence_shuffled_texts.append(shuffle_sentences(texts[index], rng))
    mixed_original = matrix[sample_indices]
    mixed_word_scores = np.asarray(mixed_original.multiply(mixed_vectorizer.transform(word_shuffled_texts)).sum(axis=1)).ravel()
    mixed_sentence_scores = np.asarray(mixed_original.multiply(mixed_vectorizer.transform(sentence_shuffled_texts)).sum(axis=1)).ravel()
    bigram_vectorizer = vectorizer((2, 2))
    bigram_vectorizer.fit(texts)
    bigram_original = bigram_vectorizer.transform([texts[index] for index in sample_indices])
    bigram_word_scores = np.asarray(bigram_original.multiply(bigram_vectorizer.transform(word_shuffled_texts)).sum(axis=1)).ravel()
    bigram_sentence_scores = np.asarray(bigram_original.multiply(bigram_vectorizer.transform(sentence_shuffled_texts)).sum(axis=1)).ravel()

    def max_between(left_work, right_work):
        left_indices = np.flatnonzero(work_ids == left_work)
        right_indices = np.flatnonzero(work_ids == right_work)
        similarities = (matrix[left_indices] @ matrix[right_indices].T).toarray()
        position = np.unravel_index(int(np.argmax(similarities)), similarities.shape)
        left = int(left_indices[position[0]])
        right = int(right_indices[position[1]])
        return {
            "left": passages[left]["passage_id"],
            "right": passages[right]["passage_id"],
            "score": min(1.0, max(0.0, float(similarities[position]))),
        }

    overlap_checks = {
        "sacred_books_east_vs_quran_sale": max_between("sacred_books_east", "quran_sale"),
        "sacred_books_east_vs_dhammapada": max_between("sacred_books_east", "dhammapada_muller"),
    }

    ordered_pairs = sorted(((left, right, score) for (left, right), score in top_pairs.items()), key=lambda item: item[2], reverse=True)
    independent_pairs = []
    dependent_pair_count = 0
    with (ROOT / "results/v2_candidate_pairs.jsonl").open("w", encoding="utf-8") as all_handle, (ROOT / "results/v2_discovery_pairs.jsonl").open("w", encoding="utf-8") as discovery_handle:
        for left, right, score in ordered_pairs:
            left_work = passages[left]["work_id"]
            right_work = passages[right]["work_id"]
            dependence = dependence_between(left_work, right_work, works, families, pair_rules)
            discovery_eligible = dependence is None
            if discovery_eligible:
                independent_pairs.append((left, right, score))
            else:
                dependent_pair_count += 1
            record = {
                "left": passages[left]["passage_id"],
                "right": passages[right]["passage_id"],
                "score": round(score, 8),
                "shared_motifs": sorted(set(motif_hits[left]) & set(motif_hits[right])),
                "dependence_relationship": dependence["relationship"] if dependence else None,
                "discovery_eligible": discovery_eligible,
                "independence_interpretation": "not_known_dependent" if discovery_eligible else "known_or_suspected_dependence",
                "interpretation": "possible_textual_reuse" if score >= 0.80 else "candidate_only_not_historical_evidence",
            }
            all_handle.write(json.dumps(record) + "\n")
            if discovery_eligible:
                discovery_handle.write(json.dumps(record) + "\n")

    with (ROOT / "results/v2_top_pairs_for_review.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["rank", "score", "left_id", "right_id", "left_work", "right_work", "shared_motifs", "left_excerpt", "right_excerpt"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, (left, right, score) in enumerate(independent_pairs[:500], 1):
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
        "schema_version": "2.0",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
        "interpretation": "Cleaned English-translation lexical candidate retrieval only; not ancestry probability or historical relationship confidence",
        "corpus": {
            "works": len(works),
            "works_represented": len(set(work_ids)),
            "input_passages": len(all_passages),
            "excluded_or_short_passages": len(all_passages) - len(passages),
            "eligible_passages": len(passages),
            "eligible_words": int(word_counts.sum()),
            "source_words": sum(work["word_count"] for work in works.values()),
            "source_bytes": sum(work["bytes"] for work in works.values()),
            "regions": dict(Counter(work["region"] for work in works.values())),
            "source_roles": dict(Counter(work["source_role"] for work in works.values())),
            "passages_with_motif_hits": sum(bool(hits) for hits in motif_hits),
            "motif_hit_counts": dict(Counter(motif for hits in motif_hits for motif in hits)),
        },
        "configuration": {
            "seed": SEED,
            "vectorizer": json.loads(json.dumps(mixed_vectorizer.get_params(), default=str)),
            "vocabulary_size": len(mixed_vectorizer.vocabulary_),
            "neighbors_per_passage": neighbors,
            "minimum_retained_score": 0.15,
            "length_matching": "Absolute passage word-count difference no greater than max(30, 25% of the left passage length)",
        },
        "candidate_pairs": len(ordered_pairs),
        "known_dependent_pairs": dependent_pair_count,
        "discovery_pairs_not_known_dependent": len(independent_pairs),
        "random_cross_work_pairs": stats(random_scores),
        "length_matched_cross_work_pairs": {
            **stats(matched_scores),
            "mean_absolute_word_count_difference": float(np.mean(np.abs(word_counts[matched_left] - word_counts[matched_right]))),
        },
        "baseline_note": "Both baselines exclude same-work pairs and configured dependence rules; absence of a configured rule does not prove independence.",
        "order_diagnostics": {
            "sample_size": len(sample_indices),
            "selection": "Eligible passages containing at least four sentence-like segments",
            "interpretation": "Word shuffling tests local wording sensitivity. Sentence shuffling tests global order sensitivity; neither metric reconstructs narrative event order.",
            "unigram_bigram": {
                "word_shuffled": stats(mixed_word_scores),
                "sentence_shuffled": stats(mixed_sentence_scores),
            },
            "bigram_only": {
                "word_shuffled": stats(bigram_word_scores),
                "sentence_shuffled": stats(bigram_sentence_scores),
            },
        },
        "known_overlap_checks": overlap_checks,
        "reproducibility": {
            "acquisition_manifest_sha256": sha256(acquisition_path),
            "passages_sha256": sha256(passages_path),
            "motif_lexicon_sha256": sha256(lexicon_path),
            "source_dependence_sha256": sha256(dependence_path),
            "analysis_code_sha256": sha256(Path(__file__)),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }
    (ROOT / "results/v2_run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "works": summary["corpus"]["works"],
        "eligible_passages": len(passages),
        "candidate_pairs": len(ordered_pairs),
        "known_dependent_pairs": dependent_pair_count,
        "discovery_pairs": len(independent_pairs),
        "random_p99": summary["random_cross_work_pairs"]["p99"],
        "length_matched_p99": summary["length_matched_cross_work_pairs"]["p99"],
        "word_shuffled_mean": summary["order_diagnostics"]["unigram_bigram"]["word_shuffled"]["mean"],
        "sentence_shuffled_mean": summary["order_diagnostics"]["unigram_bigram"]["sentence_shuffled"]["mean"],
    }, indent=2))


if __name__ == "__main__":
    main()
