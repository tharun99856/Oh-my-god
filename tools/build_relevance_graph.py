import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from run_similarity import sha256

ROOT = Path(__file__).resolve().parents[1]
CANVAS_PATH = Path.home() / ".qoder/tmp/C--Users-tharu-Downloads-god-research/canvases/narrative-relevance.canvas.tsx"
DEPENDENCE_PATH = ROOT / "config/source_dependence.json"
ANNOTATION_PATH = ROOT / "config/annotated_versions.json"
NARRATIVE_PAIRS_PATH = ROOT / "results/narrative_component_pairs.jsonl"


def lexical_layer(edges):
    """Layer 2. Retrieval, not resemblance: these edges say only that two passages came out of the
    same vector-space neighbourhood under one preregistered TF-IDF configuration."""
    return {
        "name": "similarity_candidates",
        "edge_kind": "RETRIEVED_AS_CANDIDATE",
        "status": "populated",
        "edge_meaning": "Work pair has at least one eligible passage pair whose TF-IDF cosine passed the retrieval threshold.",
        "explicitly_not": ["RESEMBLES", "DESCENDS_FROM", "BORROWS_FROM"],
        "edges": list(edges),
    }


def source_dependency_layer(config, works):
    """Layer 1. Documented reuse, translation, editing or shared-text-family relations. These are
    premises for interpretation, not findings of this pipeline."""
    known = {work_id for work_id in works}
    edges = []
    for family in config.get("work_families", []):
        members = [work_id for work_id in family.get("work_ids", []) if work_id in known]
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                edges.append({
                    "left_work": left,
                    "right_work": right,
                    "family_id": family["family_id"],
                    "relationship": family["relationship"],
                    "direction": "undirected",
                    "exclude_from_independent_analysis": family.get("exclude_from_independent_analysis", False),
                    "rationale": family.get("rationale"),
                    "edge_kind": "SOURCE_DEPENDENCE",
                })
    for rule in config.get("pair_rules", []):
        left, right = rule.get("left_work"), rule.get("right_work")
        if left in known and right in known:
            edges.append({
                "left_work": left,
                "right_work": right,
                "family_id": None,
                "relationship": rule["relationship"],
                "direction": rule.get("direction", "undirected"),
                "exclude_from_independent_analysis": rule.get("exclude_from_independent_analysis", True),
                "rationale": rule.get("rationale"),
                "edge_kind": "SOURCE_DEPENDENCE",
            })
    return {
        "name": "source_dependency",
        "edge_kind": "SOURCE_DEPENDENCE",
        "status": "populated",
        "edge_meaning": "One work is transmitted through, translated from, embedded in, or edited together with the other, or both draw on a documented common witness.",
        "explicitly_not": ["RETRIEVED_AS_CANDIDATE", "DESCENDS_FROM at narrative level"],
        "edges": edges,
    }


def resemblance_admission(pair):
    """The two mechanically decidable halves of the RESEMBLES promotion rule, evaluated per edge.

    A comparison becomes a resemblance verdict only when all four criteria hold; criteria (c) survival of
    the parameter sweeps and (d) the reviewer decision are not computable here, so no edge can be promoted
    from this field alone. It exists so that an edge lifted out of the graph still carries the reason it is
    not a verdict.
    """
    classes = pair.get("motif_comparison_class") or []
    components = pair["component_vector"]
    return {
        "criteria": {
            "witnesses_independently_attested": bool(pair["witnesses_not_marked_dependent"]
                                                    and pair.get("independence_basis") == "asserted"),
            "shared_comparison_class": len(classes) == 2 and classes[0] == classes[1],
            "above_zero_components_on_assessed_domains": bool(
                any(value is not None and value > 0 for value in components.values())
                and (components["S_motif"] is None or components["S_motif"] == 0 or pair["motif_domain"] >= 2)
                and (components["S_sequence"] is None or components["S_sequence"] == 0
                     or pair["aligned_event_pairs"] >= 2)),
            "survives_parameter_sweeps": None,
            "reviewer_decision_recorded": None,
        },
        "promoted": False,
        "not_promoted_because": "the reviewer decision and sweep-survival criteria are not computable in this build",
    }


def narrative_layer(annotation, pairs):
    """Layer 3. Every computed comparison is published as COMPARED_WITH, including the controls that are
    expected to be dissimilar. Calling an edge RESEMBLES is a judgement about the measured vector, so it is
    reserved for pairs that pass a stated resemblance criterion and receive a reviewed assessment; this build
    promotes none."""
    versions = annotation["versions"]
    nodes = [{
        "id": version["version_id"],
        "work_id": version["work_id"],
        "region": version["region"],
        "comparison_class": version.get("comparison_class"),
        "attestation_completeness": version.get("attestation_completeness"),
        "review_state": version.get("review_state"),
        "events": len(version["events"]),
    } for version in versions]
    edges = [{
        "id": f"{pair['left_version']}--{pair['right_version']}",
        "left_version": pair["left_version"],
        "right_version": pair["right_version"],
        "edge_kind": "COMPARED_WITH",
        "explicitly_not": ["RESEMBLES", "DESCENDS_FROM", "BORROWS_FROM", "a single similarity percentage"],
        "resemblance_admission": resemblance_admission(pair),
        "component_vector": pair["component_vector"],
        "motif_domain": pair["motif_domain"],
        "aligned_event_pairs": pair["aligned_event_pairs"],
        "sequence_permutation_p_value": pair["sequence_permutation_p_value"],
        "witnesses_not_marked_dependent": pair["witnesses_not_marked_dependent"],
        "expectation_group": pair["expectation_group"],
        "composite_score": pair["composite_score"],
        "historical_claim": pair["historical_claim"],
    } for pair in pairs]
    return {
        "name": "narrative_structure",
        "edge_kind": "COMPARED_WITH",
        "status": "populated",
        "edge_meaning": "Two annotated narrative versions were compared event-by-event, role-by-role and adjudicated-motif-by-motif; the component vector reports the outcome of that comparison and nothing more.",
        "explicitly_not": ["RESEMBLES", "DESCENDS_FROM", "BORROWS_FROM", "a single similarity percentage"],
        "resemblance_promotion_criterion": "an edge may be relabelled RESEMBLES only when a reviewer records that (a) both witnesses are independently attested rather than merely unmarked, (b) the same comparison class applies, (c) every component above zero sits on an assessed domain that is not flagged thin (motif domain at least 2 and at least 2 aligned event pairs), (d) at least one component survives the gap and weight sweeps, and (e) that decision is recorded with a reviewer. Each edge carries resemblance_admission with (a)-(c) computed; no edge in this build is promoted, so the layer contains zero RESEMBLES edges.",
        "nodes": nodes,
        "edges": edges,
    }


def historical_context_layer(works):
    """Layer 5. Dating, language and transmission caveats a reader needs before treating any edge as
    evidence. Deliberately thin: no date is invented that the source record does not carry."""
    return {
        "name": "historical_context",
        "status": "partial",
        "edge_meaning": "No contact or dating edges are asserted; the layer currently carries per-work context attributes only.",
        "nodes": [{
            "id": work_id,
            "tradition": work.get("tradition"),
            "region": work.get("region"),
            "source_role": work.get("source_role"),
            "original_language": work.get("original_language"),
            "overlap_group": work.get("overlap_group") or None,
            "cautions": work.get("cautions"),
            "rights_notice": work.get("rights_notice"),
        } for work_id, work in sorted(works.items())],
        "edges": [],
    }


def adjudication_layer():
    """Layer 4 exists so its emptiness is visible in the artifact instead of being implied by a
    coloured edge. Nothing has been adjudicated, so nothing is asserted."""
    return {
        "name": "adjudicated_historical_relationships",
        "edge_kind": "DESCENDS_FROM | BORROWS_FROM | INDEPENDENT_INVENTION | UNRESOLVED",
        "status": "unpopulated",
        "edges": [],
        "note": "Requires the calibrated inference step and per-edge evidence assessment; the pilot's expectation groups are predictions used for validation, not adjudications.",
    }


def build_layers(works, dependence, annotation, lexical_edges, narrative_pairs):
    return [
        source_dependency_layer(dependence, works),
        lexical_layer(lexical_edges),
        narrative_layer(annotation, narrative_pairs),
        adjudication_layer(),
        historical_context_layer(works),
    ]


def aggregate_pairs(records, passages):
    grouped = {}
    for record in records:
        left = passages[record["left"]]
        right = passages[record["right"]]
        key = tuple(sorted((left["work_id"], right["work_id"])))
        oriented_left = record["left"] if left["work_id"] == key[0] else record["right"]
        oriented_right = record["right"] if left["work_id"] == key[0] else record["left"]
        if key not in grouped:
            grouped[key] = {
                "left_work": key[0],
                "right_work": key[1],
                "max_score": record["score"],
                "candidate_passage_pairs": 0,
                "top_left_passage": oriented_left,
                "top_right_passage": oriented_right,
                "shared_motifs": record["shared_motifs"],
                "discovery_eligible": record["discovery_eligible"],
                "dependence_relationship": record["dependence_relationship"],
                "edge_kind": "RETRIEVED_AS_CANDIDATE",
            }
        edge = grouped[key]
        edge["candidate_passage_pairs"] += 1
        if record["score"] > edge["max_score"]:
            edge["max_score"] = record["score"]
            edge["top_left_passage"] = oriented_left
            edge["top_right_passage"] = oriented_right
            edge["shared_motifs"] = record["shared_motifs"]
    return sorted(grouped.values(), key=lambda edge: edge["max_score"], reverse=True)


def region_layout(nodes, edges):
    by_region = defaultdict(list)
    for node in nodes:
        by_region[node["region"]].append(node)
    degree = Counter()
    for edge in edges:
        degree[edge["left_work"]] += 1
        degree[edge["right_work"]] += 1
    positions = {}
    regions = sorted(by_region)
    for region_index, region in enumerate(regions):
        angle = 2 * math.pi * region_index / max(1, len(regions)) - math.pi / 2
        center_x = 600 + 255 * math.cos(angle)
        center_y = 370 + 235 * math.sin(angle)
        members = sorted(by_region[region], key=lambda node: node["id"])
        radius = 28 + 7 * len(members)
        for member_index, node in enumerate(members):
            member_angle = 2 * math.pi * member_index / max(1, len(members))
            positions[node["id"]] = {
                "x": round(center_x + radius * math.cos(member_angle), 2),
                "y": round(center_y + radius * math.sin(member_angle), 2),
                "degree": degree[node["id"]],
                "region_index": region_index,
            }
    return positions


def main():
    acquisition_path = ROOT / "corpus/acquisition_manifest.json"
    passages_path = ROOT / "corpus/derived/passages_v2.jsonl"
    summary_path = ROOT / "results/v2_run_summary.json"
    pairs_path = ROOT / "results/v2_candidate_pairs.jsonl"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    works = {work["work_id"]: work for work in acquisition["works"] if work["status"] != "failed"}
    passages = {passage["passage_id"]: passage for passage in (json.loads(line) for line in passages_path.read_text(encoding="utf-8").splitlines())}
    records = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    edges = aggregate_pairs(records, passages)
    dependence = json.loads(DEPENDENCE_PATH.read_text(encoding="utf-8"))
    annotation = json.loads(ANNOTATION_PATH.read_text(encoding="utf-8"))
    narrative_pairs = ([json.loads(line) for line in NARRATIVE_PAIRS_PATH.read_text(encoding="utf-8").splitlines()]
                       if NARRATIVE_PAIRS_PATH.exists() else [])
    selected_edges = [edge for edge in edges if edge["discovery_eligible"]][:100] + [edge for edge in edges if not edge["discovery_eligible"]][:50]
    work_ids = sorted({work_id for edge in selected_edges for work_id in (edge["left_work"], edge["right_work"])})
    nodes = [{
        "id": work_id,
        "title": works[work_id].get("Title", work_id),
        "region": works[work_id]["region"],
        "tradition": works[work_id]["tradition"],
        "source_role": works[work_id]["source_role"],
        "source_page": works[work_id]["source_page"],
    } for work_id in work_ids]
    positions = region_layout(nodes, selected_edges)
    for edge in selected_edges:
        edge["id"] = f"{edge['left_work']}--{edge['right_work']}"
    graph = {
        "schema_version": "3.0",
        "interpretation": "Work-level aggregation of lexical passage retrieval. Every edge in the top-level edges list is RETRIEVED_AS_CANDIDATE: it records that two works produced a passage pair above the retrieval threshold under one TF-IDF configuration. It is not a resemblance claim, and no edge in this file asserts descent or borrowing.",
        "edge_semantics": {
            "RETRIEVED_AS_CANDIDATE": "lexical neighbourhood coincidence under the stated retrieval model",
            "COMPARED_WITH": "two coded versions were put through the structural comparison; the component vector is the output of that operation, not a verdict",
            "RESEMBLES": "reserved for a reviewed assessment against the stated promotion criterion; this build emits zero such edges",
            "SOURCE_DEPENDENCE": "documented transmission, translation, embedding or shared witness",
            "DESCENDS_FROM | BORROWS_FROM": "adjudicated historical relation; not produced by this build",
        },
        "formula": "R_lex(p,q) = dot(tfidf(p),tfidf(q)) / (norm(tfidf(p))*norm(tfidf(q)))",
        "selection": "Top 100 discovery work pairs and top 50 known-dependence work pairs by maximum eligible passage cosine; full passage pairs remain in v2_candidate_pairs.jsonl",
        "nodes": nodes,
        "edges": selected_edges,
        "layers": build_layers(works, dependence, annotation, selected_edges, narrative_pairs),
        "reproducibility": {
            "passages_sha256": sha256(passages_path),
            "candidate_pairs_sha256": sha256(pairs_path),
            "run_summary_sha256": sha256(summary_path),
            "source_dependence_sha256": sha256(DEPENDENCE_PATH),
            "annotations_sha256": sha256(ANNOTATION_PATH),
            "narrative_pairs_sha256": sha256(NARRATIVE_PAIRS_PATH) if narrative_pairs else None,
        },
    }
    (ROOT / "results/v2_relevance_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8", newline="\r\n")

    discovery_edges = [edge for edge in edges if edge["discovery_eligible"]]
    with (ROOT / "results/v2_work_relevance.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["rank", "max_passage_cosine", "left_work", "right_work", "candidate_passage_pairs", "top_left_passage", "top_right_passage", "shared_motifs"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, edge in enumerate(discovery_edges[:500], 1):
            writer.writerow({
                "rank": rank,
                "max_passage_cosine": f"{edge['max_score']:.8f}",
                "left_work": edge["left_work"],
                "right_work": edge["right_work"],
                "candidate_passage_pairs": edge["candidate_passage_pairs"],
                "top_left_passage": edge["top_left_passage"],
                "top_right_passage": edge["top_right_passage"],
                "shared_motifs": "|".join(edge["shared_motifs"]),
            })

    priority = []
    for record in records:
        if not record["discovery_eligible"] or not record["shared_motifs"]:
            continue
        left = passages[record["left"]]
        right = passages[record["right"]]
        if works[left["work_id"]]["region"] == works[right["work_id"]]["region"]:
            continue
        priority.append((record, left, right))
    with (ROOT / "results/v2_priority_cross_region_motifs.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["rank", "score", "left_id", "right_id", "left_work", "right_work", "shared_motifs", "left_excerpt", "right_excerpt"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, (record, left, right) in enumerate(priority[:200], 1):
            writer.writerow({
                "rank": rank,
                "score": f"{record['score']:.8f}",
                "left_id": record["left"],
                "right_id": record["right"],
                "left_work": left["work_id"],
                "right_work": right["work_id"],
                "shared_motifs": "|".join(record["shared_motifs"]),
                "left_excerpt": " ".join(left["text"].split())[:600],
                "right_excerpt": " ".join(right["text"].split())[:600],
            })

    canvas_edges = []
    for edge in selected_edges:
        left = passages[edge["top_left_passage"]]
        right = passages[edge["top_right_passage"]]
        canvas_edges.append({
            **edge,
            "left_title": works[edge["left_work"]].get("Title", edge["left_work"]),
            "right_title": works[edge["right_work"]].get("Title", edge["right_work"]),
            "left_excerpt": " ".join(left["text"].split())[:600],
            "right_excerpt": " ".join(right["text"].split())[:600],
        })
    canvas_nodes = [{**node, **positions[node["id"]]} for node in nodes]
    data = {
        "works": summary["corpus"]["works"],
        "eligiblePassages": summary["corpus"]["eligible_passages"],
        "candidatePairs": summary["candidate_pairs"],
        "discoveryPairs": summary["discovery_pairs_not_known_dependent"],
        "dependentPairs": summary["known_dependent_pairs"],
        "randomP99": summary["random_cross_work_pairs"]["p99"],
        "matchedP99": summary["length_matched_cross_work_pairs"]["p99"],
        "wordShuffleMean": summary["order_diagnostics"]["unigram_bigram"]["word_shuffled"]["mean"],
        "sentenceShuffleMean": summary["order_diagnostics"]["unigram_bigram"]["sentence_shuffled"]["mean"],
    }
    template = r'''import { Code, H1, H2, Select, Text, ZoomableViewport, useCanvasState, useHostTheme } from 'qoder/canvas';

type Node = { id: string; title: string; region: string; tradition: string; source_role: string; x: number; y: number; degree: number; region_index: number };
type Edge = { id: string; left_work: string; right_work: string; left_title: string; right_title: string; max_score: number; candidate_passage_pairs: number; top_left_passage: string; top_right_passage: string; shared_motifs: string[]; discovery_eligible: boolean; dependence_relationship: string | null; left_excerpt: string; right_excerpt: string };

const nodes: Node[] = __NODES__;
const edges: Edge[] = __EDGES__;
const metrics = __METRICS__;

export default function NarrativeRelevance() {
  const { tokens } = useHostTheme();
  const [mode, setMode] = useCanvasState<string>('relevance-mode', 'discovery');
  const [threshold, setThreshold] = useCanvasState<string>('relevance-threshold', '0.15');
  const [selectedId, setSelectedId] = useCanvasState<string>('relevance-selected', '');
  const visible = edges.filter(edge => (mode === 'discovery' ? edge.discovery_eligible : !edge.discovery_eligible) && edge.max_score >= Number(threshold));
  const visibleIds = new Set(visible.flatMap(edge => [edge.left_work, edge.right_work]));
  const nodeMap = new Map(nodes.map(node => [node.id, node]));
  const selected = edges.find(edge => edge.id === selectedId) ?? visible[0];
  const ranked = edges.filter(edge => edge.discovery_eligible).slice(0, 40);
  const panel = { background: tokens.bg.panel, border: `1px solid ${tokens.stroke.tertiary}`, borderRadius: tokens.radius.md, padding: 16 };
  const button = { background: tokens.fill.secondary, color: tokens.text.primary, border: `1px solid ${tokens.stroke.secondary}`, borderRadius: tokens.radius.sm, padding: '8px 10px', cursor: 'pointer', textAlign: 'left' as const };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, color: tokens.text.primary, fontFamily: 'inherit' }}>
      <div>
        <H1>Global Narrative Relevance Graph</H1>
        <Text tone="secondary">65-work cleaned corpus · lexical candidate discovery · not an ancestry tree</Text>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        {[[metrics.works, 'Works'], [metrics.eligiblePassages.toLocaleString(), 'Eligible passages'], [metrics.discoveryPairs.toLocaleString(), 'Pairs not known dependent'], [metrics.dependentPairs.toLocaleString(), 'Known dependent pairs'], [metrics.randomP99.toFixed(4), 'Random-pair p99'], [metrics.matchedP99.toFixed(4), 'Length-matched p99']].map(([value, label]) => (
          <div key={String(label)} style={panel}><div style={{ fontSize: tokens.fontSize.xl, fontWeight: 650 }}>{value}</div><Text tone="secondary" size="small">{label}</Text></div>
        ))}
      </div>
      <div style={{ ...panel, borderColor: tokens.status.warningBorder, background: tokens.status.warningBg }}>
        <Text weight="semibold">Interpretation boundary</Text>
        <Text size="small">Every edge here is RETRIEVED_AS_CANDIDATE: unusually similar English translation wording under one TF-IDF configuration. It is not a resemblance verdict and does not estimate common descent, borrowing, or historical probability. “Not known dependent” means no configured dependence rule covers the pair, which is not proof of independence. The structural layer (tools/narrative_similarity.py) publishes COMPARED_WITH edges only; this build promotes none to RESEMBLES.</Text>
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Select value={mode} onChange={setMode} options={[{ value: 'discovery', label: 'Candidates not known dependent' }, { value: 'dependence', label: 'Known dependence controls' }]} style={{ minWidth: 260 }} />
        <Select value={threshold} onChange={setThreshold} options={[{ value: '0.15', label: 'Minimum cosine 0.15' }, { value: '0.25', label: 'Minimum cosine 0.25' }, { value: '0.40', label: 'Minimum cosine 0.40' }, { value: '0.60', label: 'Minimum cosine 0.60' }]} style={{ minWidth: 210 }} />
        <Text tone="secondary" size="small">{visible.length} work-level edges · click an edge for passages</Text>
      </div>
      <div style={{ ...panel, padding: 0, overflow: 'hidden' }}>
        <ZoomableViewport initialZoom={0.85} minZoom={0.45} maxZoom={2.5} wheelZoom="ctrlOrMeta" style={{ height: 720, background: tokens.bg.editor }}>
          <svg width={1200} height={740} viewBox="0 0 1200 740" role="img" aria-label="Work-level narrative lexical relevance network">
            {visible.map(edge => {
              const left = nodeMap.get(edge.left_work)!;
              const right = nodeMap.get(edge.right_work)!;
              const active = selected?.id === edge.id;
              return <line key={edge.id} x1={left.x} y1={left.y} x2={right.x} y2={right.y} stroke={mode === 'discovery' ? tokens.accent.control : tokens.status.warning} strokeWidth={active ? 7 : 1 + edge.max_score * 5} strokeOpacity={active ? 0.95 : 0.22 + edge.max_score * 0.45} onClick={() => setSelectedId(edge.id)} style={{ cursor: 'pointer' }}><title>{edge.left_title} ↔ {edge.right_title}: {edge.max_score.toFixed(4)}</title></line>;
            })}
            {nodes.filter(node => visibleIds.has(node.id)).map(node => <g key={node.id} onClick={() => { const incident = visible.find(edge => edge.left_work === node.id || edge.right_work === node.id); if (incident) setSelectedId(incident.id); }} style={{ cursor: 'pointer' }}>
              <circle cx={node.x} cy={node.y} r={Math.min(18, 7 + node.degree)} fill={tokens.chart.sequence[node.region_index % tokens.chart.sequence.length]} stroke={tokens.bg.editor} strokeWidth={2}><title>{node.title} · {node.region} · {node.source_role}</title></circle>
              <text x={node.x} y={node.y + Math.min(18, 7 + node.degree) + 13} textAnchor="middle" fill={tokens.text.primary} fontSize={10}>{node.id.length > 23 ? node.id.slice(0, 21) + '…' : node.id}</text>
            </g>)}
          </svg>
        </ZoomableViewport>
      </div>
      {selected && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <div style={panel}><H2>{selected.max_score.toFixed(4)} lexical cosine</H2><Text weight="semibold">{selected.left_title}</Text><Text tone="secondary" size="small">{selected.top_left_passage}</Text><p style={{ lineHeight: 1.55 }}>{selected.left_excerpt}</p></div>
        <div style={panel}><H2>{selected.candidate_passage_pairs} candidate passage pair(s)</H2><Text weight="semibold">{selected.right_title}</Text><Text tone="secondary" size="small">{selected.top_right_passage}</Text><p style={{ lineHeight: 1.55 }}>{selected.right_excerpt}</p></div>
        <div style={{ gridColumn: '1 / -1' }}><Text tone="secondary" size="small">{selected.discovery_eligible ? 'No configured dependence rule; historical relationship unresolved.' : `Excluded from independent discovery: ${selected.dependence_relationship}.`} Shared exploratory motifs: {selected.shared_motifs.length ? selected.shared_motifs.join(', ') : 'none detected'}.</Text></div>
      </div>}
      <H2>Strongest work-level candidates</H2>
      <Text tone="secondary" size="small">Ranked by the maximum eligible passage-pair cosine for each work pair; motifs do not boost the score.</Text>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {ranked.map((edge, index) => <button key={edge.id} onClick={() => setSelectedId(edge.id)} style={button}><strong>{index + 1}. {edge.max_score.toFixed(4)}</strong> · {edge.left_work} ↔ {edge.right_work}<br /><span style={{ color: tokens.text.secondary, fontSize: tokens.fontSize.sm }}>{edge.shared_motifs.length ? edge.shared_motifs.join(', ') : 'No exploratory motif tag'} · {edge.candidate_passage_pairs} passage pair(s)</span></button>)}
      </div>
      <H2>Formulations and diagnostics</H2>
      <div style={panel}><Code>{`idf(t) = ln((1 + N) / (1 + df(t))) + 1\ntf(t,d) = 1 + ln(count(t,d))\nR_lex(p,q) = (v_p · v_q) / (||v_p|| ||v_q||)`}</Code><Text size="small">v is L2-normalized TF-IDF using unigrams and bigrams, English stop words, sublinear term frequency, and at most 120,000 features. Candidates require R_lex ≥ 0.15 and up to six cross-work neighbors per passage.</Text></div>
      <div style={panel}><Code>{`S_sequence  Needleman-Wunsch event alignment\nS_causal    causal links over predicate families\nS_motif     weighted Jaccard inside a comparison class\nS_role      max-weight bipartite role matching\nS_symbol    symbolic overlap, double-count audited`}</Code><Text size="small">These five components are computed by tools/narrative_similarity.py on 14 source-bound narrative versions and published as a vector. They are deliberately not averaged into one score: the components disagree (for Noah–Gilgamesh S_sequence 0.09 against S_motif 0.55), and a composite would hide which measure is doing the work. Annotation is single-coder, so no inter-coder reliability figure exists yet.</Text></div>
      <Text tone="secondary" size="small">Order controls: mean original–word-shuffled similarity {metrics.wordShuffleMean.toFixed(4)}; mean original–sentence-shuffled similarity {metrics.sentenceShuffleMean.toFixed(4)}. High sentence-shuffle retention demonstrates that lexical relevance is not event-order reconstruction.</Text>
    </div>
  );
}
'''
    canvas = template.replace("__NODES__", json.dumps(canvas_nodes, ensure_ascii=False)).replace("__EDGES__", json.dumps(canvas_edges, ensure_ascii=False)).replace("__METRICS__", json.dumps(data))
    CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANVAS_PATH.write_text(canvas, encoding="utf-8", newline="")
    print(json.dumps({
        "work_nodes": len(nodes),
        "work_edges": len(selected_edges),
        "discovery_work_pairs": len(discovery_edges),
        "layers": {layer["name"]: len(layer.get("edges", [])) for layer in graph["layers"]},
        "layer_nodes": {layer["name"]: len(layer["nodes"]) for layer in graph["layers"] if "nodes" in layer},
        "graph": str(ROOT / "results/v2_relevance_graph.json"),
        "canvas": str(CANVAS_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
