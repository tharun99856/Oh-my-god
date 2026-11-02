"""Narrative-similarity engine: structural comparison of annotated narrative versions.

This is the component the research audit found missing. It does NOT use TF-IDF. It reads
source-bound event annotations (config/annotated_versions.json) and reports a component
vector per pair:

    S_sequence  Needleman-Wunsch alignment of event sequences (order sensitive)
    S_causal    weighted overlap of causal links between coded predicate families
    S_motif     weighted Jaccard over verified motifs, restricted to assessed domains
    S_role      maximum-weight bipartite matching of participant roles
    S_symbol    weighted overlap of symbolic objects, with a double-count audit

No composite score is produced and no historical claim is made. A component that cannot be
measured is reported as null, never renormalised away.

Run: python tools/narrative_similarity.py [--lexical]
Outputs: results/narrative_component_pairs.jsonl and .csv, results/narrative_validation.json,
         results/narrative_run_summary.json, optionally results/narrative_lexical_baseline.json
"""
import argparse
import csv
import hashlib
import itertools
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import kendalltau, spearmanr

ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_PATH = ROOT / "config/annotated_versions.json"
DEPENDENCE_PATH = ROOT / "config/source_dependence.json"
PASSAGES_PATH = ROOT / "corpus/derived/passages_v2.jsonl"
RESULTS = ROOT / "results"
LEXICAL_CACHE = RESULTS / "narrative_lexical_baseline.json"

STOP_TERMS = {
    "with", "from", "into", "onto", "upon", "then", "that", "this", "their", "there",
    "after", "before", "which", "while", "because", "against", "along", "himself",
    "itself", "being", "having", "over", "under", "again", "have", "will", "shall",
    "must", "should", "could", "would", "than", "when", "where", "who", "whom",
    "whose", "both", "each", "other", "such", "very", "much", "made", "make",
    "makes", "gets", "got", "gives", "given", "took", "taken", "came", "gone",
}


def lex_terms(text):
    tokens = re.findall(r"[a-z][a-z']{2,}", (text or "").lower())
    return {token for token in tokens if token not in STOP_TERMS}


def normalise_term(term):
    return re.sub(r"\s+", " ", (term or "").strip().lower())


def build_family_index(manual):
    family_of = {}
    for family, predicates in manual["predicate_families"].items():
        for predicate in predicates:
            family_of[predicate] = family
    return family_of


def predicate_similarity(left, right, family_of, credits):
    if left == right:
        return credits["exact"]
    if family_of.get(left) is not None and family_of.get(left) == family_of.get(right):
        return credits["same_family"]
    return credits["different_family"]


def participant_score(left, right, credits):
    """Functional comparison. Surface names are never used: referent is a coder assertion of
    narrative identity, so a re-translation cannot change the score."""
    if left["role"] != right["role"]:
        return credits["different_role"]
    if left.get("referent") and left["referent"] == right.get("referent"):
        return credits["same_role_same_referent"]
    if left.get("referent_kind") == right.get("referent_kind"):
        return credits["same_role_same_referent_kind"]
    return credits["same_role_different_referent_kind"]


def matched_participant_score(left_parts, right_parts, credits):
    """Maximum-weight bipartite matching, normalised by the larger participant set."""
    universe = max(len(left_parts), len(right_parts))
    if universe == 0:
        return None
    matrix = np.zeros((len(left_parts) or 1, len(right_parts) or 1))
    for i, left in enumerate(left_parts):
        for j, right in enumerate(right_parts):
            matrix[i, j] = participant_score(left, right, credits)
    rows, columns = linear_sum_assignment(-matrix)
    return float(matrix[rows, columns].sum()) / universe


def set_jaccard(left_set, right_set):
    if left_set is None or right_set is None:
        return None
    if not left_set and not right_set:
        return None
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else None


def event_similarity(left, right, family_of, weights):
    """Weighted mean of the event parts that can actually be measured.

    A coder who left an outcome unwritten has not recorded that the outcomes differ, so the outcome
    term drops out of the average instead of contributing a zero; otherwise annotation completeness
    would leak into the score as narrative difference. Participant sets only drop out when neither
    side coded any participant: one witness crediting an agent and the other crediting none is a
    real coding difference and stays a zero.
    """
    parts = weights["event_similarity_parts"]
    predicate_part = predicate_similarity(left["predicate"], right["predicate"], family_of, weights["predicate_credit"])
    participant_part = matched_participant_score(left["participants"], right["participants"], weights["participant_pair_credit"])
    outcome_part = set_jaccard(lex_terms(left.get("outcome")), lex_terms(right.get("outcome")))
    total = parts["predicate"] * predicate_part
    weight = parts["predicate"]
    if participant_part is not None:
        total += parts["participant"] * participant_part
        weight += parts["participant"]
    if outcome_part is not None:
        total += parts["outcome"] * outcome_part
        weight += parts["outcome"]
    return total / weight if weight else 0.0


def event_sim_matrix(left_events, right_events, family_of, weights):
    rows = len(left_events)
    columns = len(right_events)
    matrix = np.zeros((rows, columns))
    for i, left in enumerate(left_events):
        for j, right in enumerate(right_events):
            matrix[i, j] = event_similarity(left, right, family_of, weights)
    return matrix


def align_matrix(similarity, gap):
    """Needleman-Wunsch on a precomputed mismatch surface. Returns (score, distance, pairs)."""
    m, n = similarity.shape
    if m == 0 or n == 0:
        return None, None, []
    cost = np.full((m + 1, n + 1), np.inf)
    trace = np.zeros((m + 1, n + 1), dtype=np.int8)
    cost[0, 0] = 0.0
    # step 0 = align, step 1 = left event unpaired (came from cost[i-1][j]), step 2 = right event
    # unpaired (came from cost[i][j-1]). The border cells are pure runs of one gap direction.
    cost[1:, 0] = np.arange(1, m + 1) * gap
    trace[1:, 0] = 1
    cost[0, 1:] = np.arange(1, n + 1) * gap
    trace[0, 1:] = 2
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            mismatch = 1.0 - similarity[i - 1, j - 1]
            options = (cost[i - 1, j - 1] + mismatch, cost[i - 1, j] + gap, cost[i, j - 1] + gap)
            best = int(np.argmin(options))
            cost[i, j] = options[best]
            trace[i, j] = best
    pairs = []
    i, j = m, n
    while i > 0 or j > 0:
        step = int(trace[i, j])
        if step == 0:
            pairs.append((i - 1, j - 1, float(similarity[i - 1, j - 1])))
            i, j = i - 1, j - 1
        elif step == 1:
            pairs.append((i - 1, None, 0.0))
            i -= 1
        else:
            pairs.append((None, j - 1, 0.0))
            j -= 1
    pairs.reverse()
    # Self-check: replay the emitted path and confirm it reproduces the DP cost. A traceback that
    # consumed the wrong index would silently mislabel which events were matched, and the matched
    # event list is the part of the output a reviewer actually reads.
    replayed = sum((1.0 - value) for a, b, value in pairs if a is not None and b is not None)
    replayed += gap * sum(1 for a, b, _ in pairs if a is None or b is None)
    if abs(replayed - cost[m, n]) > 1e-9:
        raise AssertionError(f"Traceback/replay mismatch: {replayed} != {cost[m, n]}")
    matched = [(a, b) for a, b, _ in pairs if a is not None and b is not None]
    left_indices = [a for a, _ in matched]
    right_indices = [b for _, b in matched]
    if left_indices != sorted(left_indices) or right_indices != sorted(right_indices):
        raise AssertionError("Alignment is not order-preserving")
    score = 1.0 - cost[m, n] / max(m, n)
    return float(max(0.0, min(1.0, score))), float(cost[m, n]), pairs


def sequence_components(left, right, context, weights=None):
    weights = weights or context["weights"]
    similarity = event_sim_matrix(left["events"], right["events"], context["family_of"], weights)
    score, distance, pairs = align_matrix(similarity, weights["gap_penalty"])
    return score, distance, pairs, similarity


def unrestricted_sequence_score(similarity, gap):
    """Ordering-free counterpart of S_sequence: the same cost model, but the matching may cross.

    Cost of a k-pair matching is (k - sum of its similarities) + gap * (m + n - 2k), whose k term is
    k * (2 * gap - 1). For gap >= 0.5 that coefficient is non-negative, so more pairs never cost
    more and the relaxed optimum pairs off min(m, n) events -- which is what the assignment problem
    solves. The difference between the two scores is then the price paid for event order alone.
    """
    m, n = similarity.shape
    if m == 0 or n == 0:
        return None
    if gap < 0.5:
        return None
    rows, columns = linear_sum_assignment(1.0 - similarity)
    matched_cost = float((1.0 - similarity[rows, columns]).sum())
    distance = matched_cost + gap * (m + n - 2 * min(m, n))
    return float(max(0.0, min(1.0, 1.0 - distance / max(m, n))))


def assessed_motifs(version, checklists):
    """Motifs this version actually adjudicates. A motif counts as assessed only when the coder
    looked for it: either it is on the version's comparison-class checklist, in which case a zero is
    a real absence, or it is asserted with count > 0. Under a partial attestation, checklist items
    that were not found stay unassessed instead of being scored as evidence of difference."""
    complete = version.get("attestation_completeness") == "full"
    asserted = {motif["motif_id"]: motif["count"] for motif in version["motifs"]}
    assessed = {}
    for motif_id in checklists.get(version.get("comparison_class"), []):
        count = asserted.get(motif_id, 0)
        if count > 0 or complete:
            assessed[motif_id] = count
    for motif_id, count in asserted.items():
        if count > 0:
            assessed[motif_id] = count
    return assessed


def motif_components(left, right, registry, cap, checklists):
    left_assessed = assessed_motifs(left, checklists)
    right_assessed = assessed_motifs(right, checklists)
    shared_ids = sorted(set(left_assessed) & set(right_assessed))
    if not shared_ids:
        return None, 0, 0, []
    numerator = 0.0
    denominator = 0.0
    matched = []
    for motif_id in shared_ids:
        weight = min(registry[motif_id]["weight"], cap)
        left_count = left_assessed[motif_id]
        right_count = right_assessed[motif_id]
        numerator += weight * min(left_count, right_count)
        denominator += weight * max(left_count, right_count)
        if left_count and right_count:
            matched.append(motif_id)
    return (numerator / denominator if denominator else None), len(matched), len(shared_ids), matched


def role_component(left, right, weights):
    left_parts = [part for event in left["events"] for part in event["participants"]]
    right_parts = [part for event in right["events"] for part in event["participants"]]
    return matched_participant_score(left_parts, right_parts, weights["participant_pair_credit"])


def causal_edges(version, family_of):
    by_id = {event["event_id"]: event for event in version["events"]}
    return [
        (family_of.get(by_id[source]["predicate"], by_id[source]["predicate"]),
         family_of.get(by_id[target]["predicate"], by_id[target]["predicate"]))
        for source, target in version.get("causal_links", [])
        if source in by_id and target in by_id
    ]


def causal_component(left, right, family_of):
    left_edges = causal_edges(left, family_of)
    right_edges = causal_edges(right, family_of)
    if not left_edges or not right_edges:
        return None, []
    left_counts = {}
    right_counts = {}
    for edge in left_edges:
        left_counts[edge] = left_counts.get(edge, 0) + 1
    for edge in right_edges:
        right_counts[edge] = right_counts.get(edge, 0) + 1
    numerator = sum(min(count, right_counts.get(edge, 0)) for edge, count in left_counts.items())
    denominator = sum(max(left_counts.get(edge, 0), right_counts.get(edge, 0)) for edge in set(left_counts) | set(right_counts))
    shared = sorted(edge for edge in left_counts if edge in right_counts)
    return (numerator / denominator if denominator else None), shared


def symbol_terms(version):
    terms = set()
    for symbol in version.get("symbols", []):
        terms |= lex_terms(symbol)
    for event in version["events"]:
        for participant in event["participants"]:
            if participant["role"] in ("instrument", "product"):
                terms |= lex_terms(participant["term"])
    return terms


def symbol_component(left, right, registry, matched_motifs):
    left_terms = symbol_terms(left)
    right_terms = symbol_terms(right)
    shared = sorted(left_terms & right_terms)
    score = set_jaccard(left_terms, right_terms)
    already_counted = []
    for motif_id in matched_motifs:
        label_terms = lex_terms(registry[motif_id]["label"])
        if label_terms & set(shared):
            already_counted.append(motif_id)
    return score, shared, already_counted


def permutation_test(similarity, gap, draws, rng):
    """Empirical null: re-ordering either event sequence must rarely reach the observed score."""
    observed, _, _ = align_matrix(similarity, gap)
    m, n = similarity.shape
    hits = 0
    scores = []
    for _ in range(draws):
        permuted = similarity[rng.permutation(m)][:, rng.permutation(n)]
        score, _, _ = align_matrix(permuted, gap)
        scores.append(score)
        if score >= observed - 1e-12:
            hits += 1
    return observed, (hits + 1) / (draws + 1), float(statistics.mean(scores))


def expectation_group(expectations, left_id, right_id):
    for group, pairs in expectations.items():
        if group == "note":
            continue
        for pair in pairs:
            if set(pair) == {left_id, right_id}:
                return group
    return "unlabelled"


def compare_versions(left, right, context, rng):
    weights = context["weights"]
    registry = context["registry"]
    score, distance, pairs, similarity = sequence_components(left, right, context)
    p_value, null_mean = None, None
    if score is not None:
        _, p_value, null_mean = permutation_test(similarity, weights["gap_penalty"], weights["permutations"], rng)
    motif_score, motif_matched_count, motif_domain, matched_motif_ids = motif_components(
        left, right, registry, weights["motif_weight_cap"], context["checklists"])
    causal_score, causal_shared = causal_component(left, right, context["family_of"])
    symbol_score, shared_symbols, double_counted = symbol_component(left, right, registry, matched_motif_ids)
    return {
        "left_version": left["version_id"],
        "right_version": right["version_id"],
        "left_work": left["work_id"],
        "right_work": right["work_id"],
        "left_region": left["region"],
        "right_region": right["region"],
        "cross_region": left["region"] != right["region"],
        "component_vector": {
            "S_sequence": round(score, 6) if score is not None else None,
            "S_causal": round(causal_score, 6) if causal_score is not None else None,
            "S_motif": round(motif_score, 6) if motif_score is not None else None,
            "S_role": None,
            "S_symbol": round(symbol_score, 6) if symbol_score is not None else None,
        },
        "sequence_distance": round(distance, 6) if distance is not None else None,
        "sequence_permutation_p_value": round(p_value, 6) if p_value is not None else None,
        "sequence_permutation_null_mean": round(null_mean, 6) if null_mean is not None else None,
        "aligned_event_pairs": sum(1 for a, b, _ in pairs if a is not None and b is not None),
        "alignment_gaps": sum(1 for a, b, _ in pairs if a is None or b is None),
        "aligned_event_ids": [[left["events"][a]["event_id"], right["events"][b]["event_id"]] for a, b, _ in pairs if a is not None and b is not None],
        "event_counts": [len(left["events"]), len(right["events"])],
        "motif_matched": motif_matched_count,
        "motif_comparison_class": [left.get("comparison_class"), right.get("comparison_class")],
        "motif_domain": motif_domain,
        "shared_motifs": matched_motif_ids,
        "causal_shared_edges": len(causal_shared),
        "shared_symbols": shared_symbols,
        "symbols_also_counted_as_motifs": double_counted,
        "attestation_states": [left.get("attestation_completeness"), right.get("attestation_completeness")],
        "review_states": [left.get("review_state"), right.get("review_state")],
        "witnesses_not_marked_dependent": bool(left.get("independent_witness", True) and right.get("independent_witness", True)),
        "independence_basis": "asserted" if "independent_witness" in left and "independent_witness" in right else "no configured dependence rule; not a positive independence judgement",
        "expectation_group": expectation_group(context["expectations"], left["version_id"], right["version_id"]),
        "composite_score": None,
        "historical_claim": None,
    }


def load_context():
    annotation = json.loads(ANNOTATION_PATH.read_text(encoding="utf-8"))
    manual = annotation["coding_manual"]
    return {
        "annotation": annotation,
        "manual": manual,
        "weights": manual["alignment_weights"],
        "registry": annotation["motif_registry"],
        "family_of": build_family_index(manual),
        "checklists": manual["comparison_class_checklists"],
        # The domain a same-class pair reaches when both witnesses attest fully: every checklist
        # motif was adjudicated on both sides. Anything smaller means a partial attestation.
        "class_domain": {name: len(items) for name, items in manual["comparison_class_checklists"].items()},
        "expectations": annotation["expected_relation_annotations"],
        "versions": {version["version_id"]: version for version in annotation["versions"]},
    }


def annotation_coverage(context):
    """How often the event average had to drop an unmeasurable part. Reported because the same
    renormalisation that stops missing coding from reading as difference also makes two pairs with
    different annotation depth only loosely comparable."""
    events = [event for version in context["annotation"]["versions"] for event in version["events"]]
    return {
        "events": len(events),
        "events_without_outcome": sum(1 for event in events if not (event.get("outcome") or "").strip()),
        "events_whose_outcome_yields_no_lexical_terms": sum(1 for event in events if not lex_terms(event.get("outcome"))),
        "events_without_participants": sum(1 for event in events if not event["participants"]),
        "note": "On this pilot no event pair lost a part to renormalisation, so the fix changed no published score; it protects against shallower future coding.",
        "versions_with_partial_attestation": [
            version["version_id"] for version in context["annotation"]["versions"]
            if version.get("attestation_completeness") != "full"],
    }


def dependence_labels():
    """Reuse the retrieval pipeline's dependence index so the two never disagree."""
    from run_similarity_v2 import build_dependence_index, dependence_between

    dependence = json.loads(DEPENDENCE_PATH.read_text(encoding="utf-8"))
    acquisition = json.loads((ROOT / "corpus/acquisition_manifest.json").read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in acquisition["works"]}
    families, pair_rules = build_dependence_index(dependence)

    def label(left_work, right_work):
        if left_work == right_work:
            return "same_work"
        found = dependence_between(left_work, right_work, works, families, pair_rules)
        return found["relationship"] if found else None

    return label


def lexical_baseline(context):
    """Max lexical passage similarity between the two versions' cited passages, using the frozen
    v2 TF-IDF settings fitted over the whole eligible corpus. Used only to test whether the
    structural model adds information the retriever does not have."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    wanted = {passage_id for version in context["annotation"]["versions"] for passage_id in version["passages"]}
    annotated = {}
    corpus_texts = []
    with PASSAGES_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if not record["eligible_for_similarity"]:
                continue
            corpus_texts.append(record["text"])
            if record["passage_id"] in wanted:
                annotated[record["passage_id"]] = record["text"]
    missing = sorted(wanted - set(annotated))
    vectorizer = TfidfVectorizer(sublinear_tf=True, stop_words="english", ngram_range=(1, 2),
                                 max_df=0.85, max_features=120000, dtype=np.float32)
    vectorizer.fit(corpus_texts)
    ids = sorted(annotated)
    matrix = vectorizer.transform([annotated[pid] for pid in ids])
    dense = np.asarray(matrix.todense(), dtype=np.float64)
    norms = np.linalg.norm(dense, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = dense / norms
    index = {pid: position for position, pid in enumerate(ids)}
    scores = {}
    for left, right in itertools.combinations(context["annotation"]["versions"], 2):
        best = None
        for left_id in left["passages"]:
            for right_id in right["passages"]:
                if left_id == right_id or left_id not in index or right_id not in index:
                    continue
                value = float(np.clip(unit[index[left_id]] @ unit[index[right_id]], 0.0, 1.0))
                best = value if best is None else max(best, value)
        scores[f"{left['version_id']}|{right['version_id']}"] = best
    return {
        "corpus_documents_fitted": len(corpus_texts),
        "passages_used": len(ids),
        "missing_passages": missing,
        "pair_max_lexical": scores,
        "note": "Lexical retrieval score over the cited windows only. A retrieval signal, not narrative evidence.",
    }


def qap_correlation(rows, lexical, context, permutations, seed):
    """Quadratic-assignment permutation test for the structural-versus-lexical association.

    The 91 pair scores come from 14 versions, so each version contributes 13 of the observations and the
    pairs are not independent draws. A textbook Spearman p-value assumes independence and therefore
    understates uncertainty here. QAP keeps both matrices fixed, permutes the *version labels* of one
    matrix jointly over rows and columns, and recomputes the correlation, which preserves each version's
    total contribution while breaking the link between the two measures.

    p = (1 + number of permutation correlations with |rho| >= |rho_observed|) / (draws + 1), two-sided,
    with the +1 correction so a permutation cannot produce a reported p of zero.
    """
    if not lexical:
        return None
    versions = [version["version_id"] for version in context["annotation"]["versions"]]
    index = {version_id: position for position, version_id in enumerate(versions)}
    lookup = lexical["pair_max_lexical"]
    structural, lexical_values = {}, {}
    for row in rows:
        sequence = row["component_vector"]["S_sequence"]
        lexical_value = lookup.get(f"{row['left_version']}|{row['right_version']}")
        if sequence is None or lexical_value is None:
            continue
        key = (index[row["left_version"]], index[row["right_version"]])
        structural[key] = structural[key[::-1]] = sequence
        lexical_values[key] = lexical_values[key[::-1]] = lexical_value
    positions = list(itertools.combinations(range(len(versions)), 2))
    positions = [cell for cell in positions if cell in structural]
    if len(positions) < 6:
        return None
    observed = float(spearmanr([lexical_values[cell] for cell in positions],
                               [structural[cell] for cell in positions]).statistic)
    rng = np.random.default_rng(seed)
    extremes = 0
    draws = 0
    for _ in range(permutations):
        permuted = rng.permutation(len(versions))
        left, right = [], []
        for i, j in positions:
            cell = (int(permuted[i]), int(permuted[j]))
            if cell in structural:
                left.append(lexical_values[cell])
                right.append(structural[(i, j)])
        if len(left) < 6:
            continue
        draws += 1
        if abs(float(spearmanr(left, right).statistic)) >= abs(observed) - 1e-12:
            extremes += 1
    if not draws:
        return None
    return {
        "observed_spearman_rho": round(observed, 6),
        "pair_observations": len(positions),
        "versions_permuted": len(versions),
        "permutation_draws_used": draws,
        "permutation_draws_requested": permutations,
        "two_tailed_p_value": round((1 + extremes) / (draws + 1), 6),
        "extreme_draws": extremes,
        "method": "quadratic assignment on version labels, seed and draw count recorded in reproducibility",
        "why_not_the_textbook_p": "the 91 pair scores share 14 versions, so each version contributes 13 correlated observations and an independence-based p-value understates uncertainty",
    }


def build_validation(rows, context, lexical):
    weights = context["weights"]
    annotation = context["annotation"]
    groups = ["same_narrative_dependent_witnesses", "same_tradition_different_episode",
              "same_class_different_tradition_to_test", "predicted_unrelated_negative", "unlabelled"]

    def group_summary(group):
        members = [row for row in rows if row["expectation_group"] == group]
        sequences = [row["component_vector"]["S_sequence"] for row in members if row["component_vector"]["S_sequence"] is not None]
        motifs = [row["component_vector"]["S_motif"] for row in members if row["component_vector"]["S_motif"] is not None]
        domains = [row["motif_domain"] for row in members if row["component_vector"]["S_motif"] is not None]
        return {
            "pairs": len(members),
            "scored": len(sequences),
            "mean_S_sequence": round(statistics.mean(sequences), 6) if sequences else None,
            "min_S_sequence": round(min(sequences), 6) if sequences else None,
            "max_S_sequence": round(max(sequences), 6) if sequences else None,
            "mean_S_motif": round(statistics.mean(motifs), 6) if motifs else None,
            "mean_motif_domain_where_scored": round(statistics.mean(domains), 6) if domains else None,
        }

    summary = {group: group_summary(group) for group in groups}
    dependent = [row for row in rows if row["expectation_group"] == "same_narrative_dependent_witnesses"]
    negatives = [row for row in rows if row["expectation_group"] == "predicted_unrelated_negative"]
    violations = []
    for good in dependent:
        for bad in negatives:
            if (good["component_vector"]["S_sequence"] or 0) <= (bad["component_vector"]["S_sequence"] or 0):
                violations.append({"dependent": [good["left_version"], good["right_version"]],
                                   "negative": [bad["left_version"], bad["right_version"]]})

    component_disagreement = [
        {
            "pair": [row["left_version"], row["right_version"]],
            "S_sequence": row["component_vector"]["S_sequence"],
            "S_motif": row["component_vector"]["S_motif"],
            "motif_domain": row["motif_domain"],
            "S_role": row["component_vector"]["S_role"],
            "S_symbol": row["component_vector"]["S_symbol"],
        }
        for row in rows
        if row["component_vector"]["S_sequence"] is not None and row["component_vector"]["S_motif"] is not None
        and abs(row["component_vector"]["S_motif"] - row["component_vector"]["S_sequence"]) > 0.35
    ]

    lexical_rows = []
    if lexical:
        lookup = lexical["pair_max_lexical"]
        for row in rows:
            value = lookup.get(f"{row['left_version']}|{row['right_version']}")
            if value is not None and row["component_vector"]["S_sequence"] is not None:
                lexical_rows.append((value, row["component_vector"]["S_sequence"]))
    rho = None
    p_value = None
    if len(lexical_rows) >= 5:
        result = spearmanr([pair[0] for pair in lexical_rows], [pair[1] for pair in lexical_rows])
        rho = round(float(result.statistic), 6)
        p_value = round(float(result.pvalue), 6)
    qap = qap_correlation(rows, lexical, context, weights["permutations"], weights["seed"])

    return {
        "status": "passed" if not violations else "attention",
        "headline": {
            "dependent_witness_pairs_rank_above_all_predicted_unrelated_negatives": not violations,
            "pairs_scoring_above_event_order_permutation_null_at_p_0_05": sum(
                1 for row in rows if (row["sequence_permutation_p_value"] or 1) <= 0.05),
            "pairs_compared": len(rows),
        },
        "group_summary": summary,
        "motif_domain_reliability": {
            "rule": "a motif score over an assessed domain of one or two motifs is arithmetically valid but too thin to read as agreement",
            "pairs_with_motif_score": sum(1 for row in rows if row["component_vector"]["S_motif"] is not None),
            "pairs_with_domain_of_one": sum(1 for row in rows if row["component_vector"]["S_motif"] is not None and row["motif_domain"] == 1),
            "pairs_with_domain_of_two_or_less": sum(1 for row in rows if row["component_vector"]["S_motif"] is not None and row["motif_domain"] <= 2),
            "pairs_at_full_comparison_class_domain": sum(
                1 for row in rows if row["component_vector"]["S_motif"] is not None
                and row["motif_domain"] == context["class_domain"].get(row["motif_comparison_class"][0], -1)
                and row["motif_comparison_class"][0] == row["motif_comparison_class"][1]),
            "note": "Cross-class pairs are NA, not zero: the coder never adjudicated the other class's motifs.",
        },
        "discrimination_violations": violations,
        "order_sensitivity": order_sensitivity_test(context),
        "synonym_stability": synonym_stability_test(context),
        "sensitivity_analysis": sensitivity_sweep(rows, context),
        "leave_one_region_out": leave_one_region_out(context),
        "structural_vs_lexical": {
            "pairs_with_both_scores": len(lexical_rows),
            "spearman_rho_S_sequence_vs_max_lexical": rho,
            "independence_p_value": p_value,
            "independence_p_value_status": "not admissible as significance: pair observations share versions and are not independent draws",
            "quadratic_assignment_test": qap,
            "lexical_measure": "maximum cosine over the passage windows the annotation actually cites for the two versions, not a whole-work maximum",
            "residual_limitation": "still a maximum, so a version citing more windows keeps a small advantage; window counts per version are uneven",
            "status": "exploratory",
            "multiple_comparisons": "one prespecified association; the other reported tests are the order-permutation null, renaming stability and the discrimination check, and no correction is applied to any of them",
            "interpretation": "If rho is low, structural similarity carries information the lexical retriever does not, and vice versa. Neither is a historical measure.",
        },
        "component_disagreement_examples": sorted(component_disagreement, key=lambda item: -(item["S_sequence"] or 0))[:15],
        "counts": {
            "versions": len(annotation["versions"]),
            "events": sum(len(version["events"]) for version in annotation["versions"]),
            "pairs": len(rows),
            "pairs_with_sequence_score": sum(1 for row in rows if row["component_vector"]["S_sequence"] is not None),
            "pairs_with_motif_score": sum(1 for row in rows if row["component_vector"]["S_motif"] is not None),
            "pairs_with_causal_score": sum(1 for row in rows if row["component_vector"]["S_causal"] is not None),
            "pairs_with_role_score": sum(1 for row in rows if row["component_vector"]["S_role"] is not None),
            "pairs_with_symbol_score": sum(1 for row in rows if row["component_vector"]["S_symbol"] is not None),
            "pairs_with_na_motif": sum(1 for row in rows if row["component_vector"]["S_motif"] is None),
        },
        "interpretation": "These are descriptive component measurements over analyst annotations. No value here is a probability of ancestry and no composite was formed.",
    }


def order_sensitivity_test(context):
    """Three separate questions, because one blunt verdict hides which assumption is doing the work:
    (1) does event order matter at all, (2) how much of S_sequence is that order penalty, and
    (3) is S_motif blind to order, as the decomposition requires?"""
    weights = context["weights"]
    versions = context["annotation"]["versions"]
    rng = np.random.default_rng(weights["seed"])
    drops = []
    order_losses = []
    motif_delta = []
    fully_paired = 0
    for left, right in itertools.combinations(versions, 2):
        score, _, pairs, similarity = sequence_components(left, right, context)
        if score is None:
            continue
        if sum(1 for a, b, _ in pairs if a is not None and b is not None) == min(len(left["events"]), len(right["events"])):
            fully_paired += 1
        order = rng.permutation(len(right["events"]))
        permuted_score, _, _ = align_matrix(similarity[:, order], weights["gap_penalty"])
        drops.append(score - permuted_score)
        free = unrestricted_sequence_score(similarity, weights["gap_penalty"])
        if free is not None:
            order_losses.append(free - score)
        motif_score, _, _, _ = motif_components(left, right, context["registry"], weights["motif_weight_cap"], context["checklists"])
        shuffled_version = dict(right, events=[right["events"][position] for position in order])
        motif_shuffled, _, _, _ = motif_components(left, shuffled_version, context["registry"], weights["motif_weight_cap"], context["checklists"])
        if motif_score is not None and motif_shuffled is not None:
            motif_delta.append(abs(motif_score - motif_shuffled))
    mean_drop = statistics.mean(drops) if drops else None
    # Preregistered floor: a sequence component that on average moves less than 0.02 under a random
    # re-ordering is behaving like a bag of events, and must not be described as an event-sequence
    # measure in the write-up.
    floor = 0.02
    return {
        "pairs_tested": len(drops),
        "mean_sequence_drop_under_single_sequence_permutation": round(mean_drop, 6) if drops else None,
        "max_sequence_drop": round(max(drops), 6) if drops else None,
        "pairs_losing_score_to_order_constraint": sum(1 for loss in order_losses if loss > 1e-9),
        "pairs_where_the_shorter_sequence_is_fully_matched": fully_paired,
        "mean_order_constraint_loss": round(statistics.mean(order_losses), 6) if order_losses else None,
        "max_order_constraint_loss": round(max(order_losses), 6) if order_losses else None,
        "mean_abs_motif_change_under_permutation": round(statistics.mean(motif_delta), 6) if motif_delta else None,
        "requirement": "permuting event order must lower S_sequence and must leave S_motif unchanged",
        "checks": {
            "motif_invariant_under_event_reordering": bool(motif_delta) and statistics.mean(motif_delta) < 1e-9,
            "some_pairs_pay_for_order": any(loss > 1e-9 for loss in order_losses),
            "mean_permutation_drop_above_preregistered_floor": bool(drops) and mean_drop > floor,
        },
        "preregistered_floor": floor,
        "passed": bool(drops) and mean_drop > floor and (not motif_delta or statistics.mean(motif_delta) < 1e-9),
        "analytic_note": (
            "The mismatch cost is 1 - s, which lives in [0, 1] and therefore never exceeds the "
            "preregistered gap of 1.0; gapping both events would cost twice as much as aligning them. "
            "A Needleman-Wunsch alignment run under those settings is consequently closer to a "
            "maximum-weight order-preserving matching than to a classical sequence alignment with "
            f"substantial indels: {fully_paired} of {len(drops)} pairs matched every event of the "
            f"shorter sequence, and a random re-ordering removes only {round(mean_drop, 4)} of score "
            "on average. The order signal is present but small, and it is measured directly as the "
            f"loss against the crossing relaxation (mean {round(statistics.mean(order_losses), 4) if order_losses else 'n/a'}, "
            f"non-zero for {sum(1 for loss in order_losses if loss > 1e-9) if order_losses else 0} of "
            f"{len(order_losses) if order_losses else 0} pairs). S_sequence must therefore be described "
            "as an event-matching score, not a plot-order score. Strengthening order sensitivity would "
            "mean dropping the gap below the mismatch ceiling, which imports a free parameter and "
            "changes what the measure means; the gap sweep in sensitivity_analysis shows the ranking "
            "moving by roughly that amount. Reported rather than tuned."
        ),
    }


def synonym_stability_test(context):
    """Renaming participants without changing their coded role must not move S_sequence:
    the model reads the coding, not the translator's vocabulary."""
    weights = context["weights"]
    versions = context["annotation"]["versions"]
    rng = np.random.default_rng(weights["seed"])
    changes = []
    tested = 0
    for left, right in itertools.combinations(versions, 2):
        base, _, _, _ = sequence_components(left, right, context)
        if base is None:
            continue
        renamed = json.loads(json.dumps(right))
        for event in renamed["events"]:
            for participant in event["participants"]:
                participant["term"] = f"renamed_{int(rng.integers(10000))}"
        alt, _, _, _ = sequence_components(left, renamed, context)
        if alt is not None:
            changes.append(abs(base - alt))
        tested += 1
    return {
        "pairs_tested": tested,
        "max_abs_S_sequence_change_under_pure_renaming": round(max(changes), 6) if changes else None,
        "expected": 0.0,
        "passed": bool(changes) and max(changes) < 1e-9,
    }


def sensitivity_sweep(rows, context):
    weights = context["weights"]
    versions = context["annotation"]["versions"]
    base_order = ranking(rows, "S_sequence")
    variants = {}
    for gap in (0.5, 0.75, 1.0, 1.25, 1.5):
        tuned = json.loads(json.dumps(weights))
        tuned["gap_penalty"] = gap
        variants[f"gap_penalty_{gap}"] = rank_movement(base_order, structural_rank(context, tuned))
    for credit in (0.25, 0.5, 0.75):
        tuned = json.loads(json.dumps(weights))
        tuned["predicate_credit"]["same_family"] = credit
        variants[f"same_family_credit_{credit}"] = rank_movement(base_order, structural_rank(context, tuned))
    for cap in (0.6, 0.8, 1.0):
        tuned = json.loads(json.dumps(weights))
        tuned["motif_weight_cap"] = cap
        variants[f"motif_weight_cap_{cap}"] = rank_movement(ranking(rows, "S_motif"), motif_rank(context, tuned))
    return {
        "reference_ranking_pairs": len(base_order),
        "variants": variants,
        "note": "mean_absolute_rank_shift is mean |rank displacement| divided by the full ranking range (P-1), so 0 means the variant reproduces the published order and 1 means it reverses it; kendall_tau is reported alongside as ordering agreement over the pairs present in both orderings. Large movement means the ordering is parameter-bound and must not be read as a settled similarity claim.",
    }


def ranking(rows, component):
    return [f"{row['left_version']}|{row['right_version']}" for row in sorted(
        (row for row in rows if row["component_vector"][component] is not None),
        key=lambda row: -row["component_vector"][component])]


def structural_rank(context, weights):
    scored = []
    for left, right in itertools.combinations(context["annotation"]["versions"], 2):
        score, _, _, _ = sequence_components(left, right, context, weights)
        if score is not None:
            scored.append((f"{left['version_id']}|{right['version_id']}", score))
    scored.sort(key=lambda item: -item[1])
    return [pair for pair, _ in scored]


def motif_rank(context, weights):
    scored = []
    for left, right in itertools.combinations(context["annotation"]["versions"], 2):
        score, _, _, _ = motif_components(left, right, context["registry"], weights["motif_weight_cap"], context["checklists"])
        if score is not None:
            scored.append((f"{left['version_id']}|{right['version_id']}", score))
    scored.sort(key=lambda item: -item[1])
    return [pair for pair, _ in scored]


def rank_movement(base, variant):
    """Movement between two orderings of the same pair set.

    mean_absolute_rank_shift = mean over base positions of |pos_variant(pair) - pos_base(pair)| / (P-1),
    where P is the number of ranked pairs, so 0 means an identical ordering and 1 means the two orderings
    are exact reversals; roughly 0.29 is therefore 'the average pair moved about 29% of the whole ranking'.
    Pairs absent from the variant are charged the midpoint position and counted separately, because silently
    dropping them would make a variant that scores many pairs NA look stable.
    kendall_tau is the rank correlation between the two orderings over pairs present in both, which is the
    measure to quote if a reader wants ordering agreement rather than displacement.
    """
    if not base or not variant:
        return None
    positions = {pair: index for index, pair in enumerate(variant)}
    denominator = max(len(base) - 1, 1)
    missing = [pair for pair in base if pair not in positions]
    deltas = [abs(positions.get(pair, len(base) // 2) - index) / denominator for index, pair in enumerate(base)]
    shared = [pair for pair in base if pair in positions]
    tau = None
    if len(shared) >= 3:
        base_ranks = [index for index, pair in enumerate(base) if pair in positions]
        variant_ranks = [positions[pair] for pair in shared]
        tau = round(float(kendalltau(base_ranks, variant_ranks).statistic), 6)
    return {
        "mean_absolute_rank_shift": round(statistics.mean(deltas), 6),
        "kendall_tau": tau,
        "pairs_compared": len(shared),
        "pairs_missing_from_variant": len(missing),
        "scale": "mean absolute rank displacement divided by the full ranking range (P-1); 0 = identical order, 1 = exact reversal",
    }


def leave_one_region_out(context):
    """Re-derive empirical motif weights (inverse document frequency over the annotated versions)
    with one region withheld, and check whether the ranking survives."""
    versions = context["annotation"]["versions"]
    regions = sorted({version["region"] for version in versions})
    base_weights = empirical_motif_weights(versions, context["registry"], context["weights"], context["checklists"])
    base_rank = motif_rank_with(context, base_weights)
    output = {}
    for region in regions:
        held = [version for version in versions if version["region"] != region]
        if len(held) < 3:
            continue
        weights = empirical_motif_weights(held, context["registry"], context["weights"], context["checklists"])
        output[region] = rank_movement(base_rank, motif_rank_with(context, weights))
    output["weights_rule"] = "empirical weight = 1 / log(2 + versions asserting the motif), capped at the preregistered cap"
    output["note"] = "Judgement weights and corpus-derived weights are reported side by side; the pilot cannot yet justify a single set."
    return output


def empirical_motif_weights(versions, registry, weights, checklists):
    document_frequency = {}
    for version in versions:
        for motif_id in assessed_motifs(version, checklists):
            document_frequency[motif_id] = document_frequency.get(motif_id, 0) + 1
    derived = {}
    for motif_id in registry:
        frequency = document_frequency.get(motif_id, 0)
        if frequency == 0:
            derived[motif_id] = registry[motif_id]["weight"]
        else:
            derived[motif_id] = min(weights["motif_weight_cap"], 1.0 / np.log(2 + frequency))
    return derived


def motif_rank_with(context, weights_by_motif):
    scored = []
    cap = context["weights"]["motif_weight_cap"]
    registry = dict(context["registry"])
    for motif_id, value in weights_by_motif.items():
        registry[motif_id] = dict(registry[motif_id], weight=value)
    for left, right in itertools.combinations(context["annotation"]["versions"], 2):
        score, _, _, _ = motif_components(left, right, registry, cap, context["checklists"])
        if score is not None:
            scored.append((f"{left['version_id']}|{right['version_id']}", score))
    scored.sort(key=lambda item: -item[1])
    return [pair for pair, _ in scored]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexical", action="store_true", help="also compute the TF-IDF baseline for the same pairs")
    arguments = parser.parse_args()

    context = load_context()
    label = dependence_labels()
    rng = np.random.default_rng(context["weights"]["seed"])
    rows = []
    for left, right in itertools.combinations(context["annotation"]["versions"], 2):
        row = compare_versions(left, right, context, rng)
        row["component_vector"]["S_role"] = round(role_component(left, right, context["weights"]), 6)
        row["lexical_dependence_label"] = label(row["left_work"], row["right_work"])
        rows.append(row)

    lexical = None
    if arguments.lexical:
        lexical = lexical_baseline(context)
        RESULTS.mkdir(exist_ok=True)
        LEXICAL_CACHE.write_text(json.dumps(lexical, indent=2), encoding="utf-8")
    elif LEXICAL_CACHE.exists():
        lexical = json.loads(LEXICAL_CACHE.read_text(encoding="utf-8"))
    if lexical:
        lookup = lexical["pair_max_lexical"]
        for row in rows:
            row["lexical_max_r_lex"] = lookup.get(f"{row['left_version']}|{row['right_version']}")

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "narrative_component_pairs.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    fields = ["left_version", "right_version", "left_region", "right_region", "cross_region",
              "S_sequence", "S_causal", "S_motif", "S_role", "S_symbol", "lexical_max_r_lex",
              "sequence_permutation_p_value", "sequence_permutation_null_mean",
              "aligned_event_pairs", "alignment_gaps", "event_counts", "motif_matched", "motif_domain",
              "shared_symbols", "symbols_also_counted_as_motifs", "lexical_dependence_label",
              "expectation_group", "witnesses_not_marked_dependent", "independence_basis", "review_states", "attestation_states",
              "composite_score", "historical_claim"]
    with (RESULTS / "narrative_component_pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        ordered = sorted(rows, key=lambda row: (row["component_vector"]["S_sequence"] is None,
                                                 -(row["component_vector"]["S_sequence"] or 0)))
        for row in ordered:
            flat = {field: row.get(field) for field in fields if field in row}
            for component in ("S_sequence", "S_causal", "S_motif", "S_role", "S_symbol"):
                flat[component] = row["component_vector"][component]
            flat["event_counts"] = "x".join(str(count) for count in row["event_counts"])
            flat["review_states"] = "+".join(str(state) for state in row["review_states"])
            flat["attestation_states"] = "+".join(str(state) for state in row["attestation_states"])
            flat["shared_symbols"] = ";".join(row["shared_symbols"])
            flat["symbols_also_counted_as_motifs"] = ";".join(row["symbols_also_counted_as_motifs"])
            writer.writerow(flat)

    validation = build_validation(rows, context, lexical)
    (RESULTS / "narrative_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")

    summary = {
        "engine": "narrative_similarity",
        "engine_version": "1.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "annotation_set_version": context["annotation"]["annotation_set_version"],
        "reproducibility": {
            "annotations_sha256": hashlib.sha256(ANNOTATION_PATH.read_bytes()).hexdigest(),
            "source_dependence_sha256": hashlib.sha256(DEPENDENCE_PATH.read_bytes()).hexdigest(),
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "seed": context["weights"]["seed"],
            "permutations": context["weights"]["permutations"],
            "numpy": np.__version__,
        },
        "versions": len(context["versions"]),
        "pairs": len(rows),
        "annotation_coverage": annotation_coverage(context),
        "alignment_weights": context["weights"],
        "status": validation["status"],
        "headline": validation["headline"],
        "interpretation": "Component vectors only. No composite percentage is produced, and no edge here asserts common descent, borrowing or influence.",
    }
    (RESULTS / "narrative_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
