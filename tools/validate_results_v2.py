import hashlib
import json
from pathlib import Path

from run_similarity_v2 import build_dependence_index, dependence_between
from text_pipeline import WORD_RE

ROOT = Path(__file__).resolve().parents[1]


def verify_layers(graph, root, works, lexical_node_ids):
    """The five layers must stay separate. A lexical candidate may not be filed under the structural
    layer, and the adjudication layer must still be empty, because nothing has been adjudicated."""
    layers = {layer["name"]: layer for layer in graph["layers"]}
    expected = {"source_dependency", "similarity_candidates", "narrative_structure",
                "adjudicated_historical_relationships", "historical_context"}
    assert set(layers) == expected, f"Graph layers changed: {sorted(layers)}"
    for edge in layers["source_dependency"]["edges"]:
        assert edge["left_work"] in works and edge["right_work"] in works, "Source dependence edge names an unknown work"
        assert edge["left_work"] != edge["right_work"]
        assert edge["relationship"], "Source dependence edge without a relationship"
    candidates = layers["similarity_candidates"]
    assert len(candidates["edges"]) == len(graph["edges"]), "Candidate layer does not match the published edges"
    for edge in candidates["edges"]:
        assert edge["edge_kind"] == "RETRIEVED_AS_CANDIDATE"
        assert edge["left_work"] in lexical_node_ids and edge["right_work"] in lexical_node_ids
    structure = layers["narrative_structure"]
    version_ids = {node["id"] for node in structure["nodes"]}
    assert len(version_ids) == len(structure["nodes"]), "Duplicate narrative version node"
    annotation = json.loads((root / "config/annotated_versions.json").read_text(encoding="utf-8"))
    assert version_ids == {version["version_id"] for version in annotation["versions"]}, "Structural layer lost versions"
    pairs_path = root / "results/narrative_component_pairs.jsonl"
    assert graph["reproducibility"]["narrative_pairs_sha256"] == hashlib.sha256(pairs_path.read_bytes()).hexdigest(), "Stale structural layer"
    pairs = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()]
    assert len(structure["edges"]) == len(pairs), "Structural layer is not the full pair set"
    for edge in structure["edges"]:
        assert edge["left_version"] in version_ids and edge["right_version"] in version_ids
        assert edge["edge_kind"] == "COMPARED_WITH", "a comparison was published as a verdict"
        assert "resemblance_promotion_criterion" in structure, "RESEMBLES has no defined admission rule"
        admission = edge["resemblance_admission"]
        assert admission["promoted"] is False, "an edge was promoted to RESEMBLES without a reviewer decision"
        assert admission["criteria"]["reviewer_decision_recorded"] is None, \
            "a reviewer decision was synthesised by the builder"
        assert "RESEMBLES" in edge["explicitly_not"], "an edge lost its own semantic guard"
        assert edge["composite_score"] is None, "A composite appeared in the structural layer"
        assert edge["historical_claim"] is None, "A historical claim appeared in the structural layer"
        for name, value in edge["component_vector"].items():
            assert value is None or 0 <= value <= 1, f"Component {name} out of range"
    assert not any(edge["edge_kind"] == "RESEMBLES" for layer in layers.values() for edge in layer["edges"]), \
        "RESEMBLES asserted without a reviewed promotion decision"
    context = layers["historical_context"]
    assert {node["id"] for node in context["nodes"]} == set(works), "Historical context does not cover every work"
    assert context["edges"] == [], "Contact or dating edges asserted without a source"
    assert layers["adjudicated_historical_relationships"]["edges"] == [], "Historical relationships asserted without adjudication"
    return {
        "lexical_nodes": len(lexical_node_ids),
        "lexical_edges": len(graph["edges"]),
        "structural_nodes": len(version_ids),
        "layer_edges": {name: len(layer["edges"]) for name, layer in layers.items()},
    }


def main():
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    passages_path = ROOT / "corpus/derived/passages_v2.jsonl"
    passage_summary_path = ROOT / "corpus/derived/passages_v2_summary.json"
    run_summary_path = ROOT / "results/v2_run_summary.json"
    dependence_path = ROOT / "config/source_dependence.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works_list = acquisition["works"]
    works = {work["work_id"]: work for work in works_list}
    passages = [json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines()]
    dependence_config = json.loads(dependence_path.read_text(encoding="utf-8"))
    families, pair_rules = build_dependence_index(dependence_config)
    passage_by_id = {passage["passage_id"]: passage for passage in passages}
    assert all(work["status"] != "failed" for work in works_list), "Failed source remains"
    assert len(works) == len(works_list), "Duplicate work ID"
    assert len(passage_by_id) == len(passages), "Duplicate passage ID"

    raw_cache = {}
    for work in works_list:
        path = ROOT / f"corpus/raw/{work['work_id']}.txt"
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == work["sha256"], f"Hash mismatch: {work['work_id']}"
        raw = data.decode("utf-8-sig")
        with (ROOT / f"corpus/derived/{work['work_id']}.clean.txt").open(encoding="utf-8", newline="") as clean_handle:
            clean = clean_handle.read()
        assert raw[work["body_char_start"]:work["body_char_end"]] == clean, f"Clean offset mismatch: {work['work_id']}"
        raw_cache[work["work_id"]] = raw
    for passage in passages:
        raw = raw_cache[passage["work_id"]]
        assert raw[passage["raw_char_start"]:passage["raw_char_end"]] == passage["text"], f"Offset mismatch: {passage['passage_id']}"
        assert len(list(WORD_RE.finditer(passage["text"]))) == passage["word_count"], f"Word count mismatch: {passage['passage_id']}"

    passage_summary = json.loads(passage_summary_path.read_text(encoding="utf-8"))
    assert passage_summary["passages_sha256"] == hashlib.sha256(passages_path.read_bytes()).hexdigest(), "Stale passage summary"
    assert passage_summary["passages"] == len(passages)
    eligible = [passage for passage in passages if passage["eligible_for_similarity"]]
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    assert run_summary["reproducibility"]["passages_sha256"] == passage_summary["passages_sha256"], "Stale similarity run"
    assert run_summary["reproducibility"]["acquisition_manifest_sha256"] == hashlib.sha256(acquisition_path.read_bytes()).hexdigest(), "Stale acquisition manifest"
    assert run_summary["reproducibility"]["source_dependence_sha256"] == hashlib.sha256(dependence_path.read_bytes()).hexdigest(), "Stale dependence rules"
    assert run_summary["corpus"]["works"] == len(works)
    assert run_summary["corpus"]["input_passages"] == len(passages)
    assert run_summary["corpus"]["eligible_passages"] == len(eligible)

    all_pairs_path = ROOT / "results/v2_candidate_pairs.jsonl"
    discovery_pairs_path = ROOT / "results/v2_discovery_pairs.jsonl"
    all_pairs = [json.loads(line) for line in all_pairs_path.read_text(encoding="utf-8").splitlines()]
    discovery_pairs = [json.loads(line) for line in discovery_pairs_path.read_text(encoding="utf-8").splitlines()]
    expected_discovery = []
    dependent_count = 0
    for pair in all_pairs:
        assert 0 <= pair["score"] <= 1
        left = passage_by_id[pair["left"]]
        right = passage_by_id[pair["right"]]
        assert left["eligible_for_similarity"] and right["eligible_for_similarity"]
        assert left["work_id"] != right["work_id"]
        dependence = dependence_between(left["work_id"], right["work_id"], works, families, pair_rules)
        expected_eligible = dependence is None
        assert pair["discovery_eligible"] == expected_eligible, f"Dependence label mismatch: {pair['left']} / {pair['right']}"
        assert pair["dependence_relationship"] == (dependence["relationship"] if dependence else None)
        if expected_eligible:
            expected_discovery.append(pair)
        else:
            dependent_count += 1
    assert discovery_pairs == expected_discovery, "Discovery output does not match dependence filtering"
    assert len(all_pairs) == run_summary["candidate_pairs"]
    assert dependent_count == run_summary["known_dependent_pairs"]
    assert len(discovery_pairs) == run_summary["discovery_pairs_not_known_dependent"]
    graph_path = ROOT / "results/v2_relevance_graph.json"
    graph_counts = None
    if graph_path.exists():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        node_ids = {node["id"] for node in graph["nodes"]}
        assert len(node_ids) == len(graph["nodes"]), "Duplicate graph node"
        assert graph["reproducibility"]["candidate_pairs_sha256"] == hashlib.sha256(all_pairs_path.read_bytes()).hexdigest(), "Stale relevance graph"
        for edge in graph["edges"]:
            assert edge["left_work"] in node_ids and edge["right_work"] in node_ids
            assert 0 <= edge["max_score"] <= 1
            assert passage_by_id[edge["top_left_passage"]]["work_id"] == edge["left_work"], "Graph left excerpt orientation mismatch"
            assert passage_by_id[edge["top_right_passage"]]["work_id"] == edge["right_work"], "Graph right excerpt orientation mismatch"
            assert edge["edge_kind"] == "RETRIEVED_AS_CANDIDATE", "Lexical edge semantics drifted back to a resemblance claim"
        graph_counts = verify_layers(graph, ROOT, works, node_ids)
    print(json.dumps({
        "status": "passed",
        "works_verified": len(works),
        "passages_verified": len(passages),
        "eligible_passages_verified": len(eligible),
        "candidate_pairs_verified": len(all_pairs),
        "discovery_pairs_verified": len(discovery_pairs),
        "known_dependent_pairs_verified": dependent_count,
        "raw_hashes_verified": len(raw_cache),
        "graph_verified": graph_counts,
        "offset_and_freshness_checks": "passed",
    }, indent=2))


if __name__ == "__main__":
    main()
