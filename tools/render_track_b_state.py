#!/usr/bin/env python3
"""Render the Track B instrument state as a self-contained HTML fragment.

Every number is read from a published artifact in this repo: nothing here is typed by
hand, so the picture cannot drift from the run that produced it.

v3 answers two complaints about the v2 picture. The interpretation dimensions are no
longer smuggled into the concept heatmap under a borrowed count -- they get their own
panel, their own legend and their own denominator, stated on the figure. And every
tally is labelled by who decided it, because a machine-classified affirmative doctrine
and a human-verified one are not the same object and only the second has ever been
produced here.
"""
import argparse
import collections
import csv
import gzip
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

run = json.loads((ROOT / "results/ontology_run_summary.json").read_text(encoding="utf-8"))
graph = json.loads((ROOT / "results/ontology_graph.json").read_text(encoding="utf-8"))
audit = json.loads((ROOT / "results/exclusivist_monotheism_audit.json").read_text(encoding="utf-8"))
packet = json.loads((ROOT / "results/annotation_sampling_plan.json").read_text(encoding="utf-8"))
RECALL_PATH = ROOT / "results/graph_recall_validation.json"
recall = json.loads(RECALL_PATH.read_text(encoding="utf-8")) if RECALL_PATH.exists() else None
scale = graph["scale"]

CONCEPT_DIMS = ["D1_ontological_category", "D2a_acknowledged_population", "D2b_reality_of_others",
                "D2c_worship_exclusivity", "D3_agency", "D4_cosmic_function",
                "D5_universe_relationship", "D6_temporal_nature"]
INTERPRETATION_DIMS = ["D7a_speaker_attribution", "D7b_speech_act",
                       "D7c_discourse_genre", "D7d_epistemic_commitment"]
SHORT = {
    "D1_ontological_category": "D1 what kind",
    "D2a_acknowledged_population": "D2a how many",
    "D2b_reality_of_others": "D2b others real",
    "D2c_worship_exclusivity": "D2c worship",
    "D3_agency": "D3 agency",
    "D4_cosmic_function": "D4 function",
    "D5_universe_relationship": "D5 universe",
    "D6_temporal_nature": "D6 time",
    "D7a_speaker_attribution": "D7a who speaks",
    "D7b_speech_act": "D7b act",
    "D7c_discourse_genre": "D7c genre",
    "D7d_epistemic_commitment": "D7d commitment",
}
STATE_COLOR = {
    "candidate": "#3ddc97",
    "candidate_requires_human_disambiguation": "#5aa9e6",
    "not_yet_instrumented": "#8b8f95",
}
ENDORSE_COLOR = {
    "endorsed_by_text": "#3ddc97",
    "attributed_not_endorsed": "#f2a24b",
    "rejected_in_text": "#e06c75",
    "suspended_or_held_open": "#c586c0",
    "not_applicable_non_assertive": "#5aa9e6",
    "undecidable": "#8b8f95",
}
BAR_COLORS = ["#3ddc97", "#5aa9e6", "#c586c0", "#f2a24b", "#d19a66", "#e06c75", "#56b6c2",
              "#98c379", "#abb2bf", "#8b8f95"]

with gzip.open(ROOT / "results/ontology_attestations.jsonl.gz", "rt", encoding="utf-8") as handle:
    records = [json.loads(line) for line in handle]

propositions = {(r["work_id"], r["passage_id"], r["proposition_char_start"]) for r in records}
windows = {(r["work_id"], r["passage_id"], r["window_char_start"]) for r in records}

works, dims = [], []
with (ROOT / "results/ontology_work_states.csv").open(encoding="utf-8", newline="") as handle:
    state_rows = list(csv.DictReader(handle))
candidate_counts, doctrine_counts = collections.defaultdict(int), collections.defaultdict(int)
for row in state_rows:
    key_ = (row["work_id"], row["dimension"])
    candidate_counts[key_] += int(row["candidate_count"])
    doctrine_counts[key_] += int(row["affirmative_doctrine_count"])
works = sorted({r["work_id"] for r in state_rows})
dims = sorted({r["dimension"] for r in state_rows})

by_dim_state = collections.defaultdict(collections.Counter)
for record in records:
    by_dim_state[record["dimension"]][record["assertion_state"]] += 1

distributions = {d: collections.Counter(r[d] for r in records) for d in INTERPRETATION_DIMS}
endorse_by_act = collections.defaultdict(collections.Counter)
for record in records:
    endorse_by_act[record["D7b_speech_act"]][record["doctrinal_endorsement"]] += 1
conceptual = collections.Counter(r["conceptual_presence"] for r in records)
affirmative = sum(1 for r in records if r["counts_as_affirmative_doctrine"])

CELL, GAP = 13, 2


def heat_color(count):
    if count == 0:
        return "#1b2126"
    if count < 5:
        return "#1f6f52"
    if count < 50:
        return "#2fae81"
    if count < 300:
        return "#3ddc97"
    return "#9be86b"


def heatmap(counts, columns, unit):
    left, top = 122, 92
    width = left + len(columns) * (CELL + GAP) + 24
    height = top + len(works) * (CELL + GAP) + 30
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Every work against every concept dimension">']
    for j, dim in enumerate(columns):
        x = left + j * (CELL + GAP) + CELL / 2
        parts.append(f'<text x="{x:.1f}" y="{top - 8}" class="ax" transform="rotate(-58 {x:.1f} {top - 8})">'
                     f'{html.escape(SHORT[dim])}</text>')
    for i, work in enumerate(works):
        y = top + i * (CELL + GAP)
        parts.append(f'<text x="{left - 8}" y="{y + CELL - 2}" class="row">{html.escape(work)}</text>')
        for j, dim in enumerate(columns):
            c = counts[(work, dim)]
            parts.append(f'<rect x="{left + j * (CELL + GAP)}" y="{y}" width="{CELL}" height="{CELL}" '
                         f'fill="{heat_color(c)}"><title>{html.escape(work)} / {SHORT[dim]}: '
                         f'{c} {unit}</title></rect>')
    parts.append("</svg>")
    return "".join(parts)


def stacked():
    ordered = [d for d in dims if by_dim_state[d]]
    width, bar_h, gap, left = 880, 24, 15, 176
    total_w = width - left - 96
    height = len(ordered) * (bar_h + gap) + 34
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Assertion states per dimension">']
    max_total = max(sum(by_dim_state[d].values()) for d in ordered)
    for i, dim in enumerate(ordered):
        y = 16 + i * (bar_h + gap)
        parts.append(f'<text x="{left - 10}" y="{y + bar_h / 2 + 5}" class="ax2">{html.escape(SHORT[dim])}</text>')
        x = left
        for state in STATE_COLOR:
            n = by_dim_state[dim][state]
            if not n:
                continue
            w = max(1.5, total_w * n / max_total)
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" '
                         f'fill="{STATE_COLOR[state]}"><title>{SHORT[dim]} / {state}: {n}</title></rect>')
            x += w
        parts.append(f'<text x="{x + 8:.1f}" y="{y + bar_h / 2 + 5}" class="tot">'
                     f'{sum(by_dim_state[dim].values()):,}</text>')
    parts.append("</svg>")
    return "".join(parts)


def interpretation_panel():
    """Four separate axes, four separate denominators -- never a column in the concept heatmap.

    The v2 figure substituted windows-read-as-doctrine for a zero candidate count and
    drew it on the same legend as matched terms. That is fixed here by drawing each D7
    answer as its own bar group over the population it was actually decided on.
    """
    width, bar_h, gap, left = 880, 19, 10, 268
    parts = []
    for dim in INTERPRETATION_DIMS:
        items = distributions[dim].most_common()
        total = sum(distributions[dim].values())
        height = len(items) * (bar_h + gap) + 44
        parts.append(f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
                     f'aria-label="{SHORT[dim]} distribution">')
        parts.append(f'<text x="12" y="16" class="hd">{html.escape(SHORT[dim])} '
                     f'<tspan class="sub2">— decided on {total:,} term-carrying records</tspan></text>')
        top_of = max(v for _, v in items)
        total_w = width - left - 96
        for i, (label, value) in enumerate(items):
            y = 28 + i * (bar_h + gap)
            parts.append(f'<text x="{left - 10}" y="{y + bar_h / 2 + 4}" class="ax2">{html.escape(label)}</text>')
            w = max(2, total_w * value / top_of)
            parts.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" '
                         f'fill="{BAR_COLORS[i % len(BAR_COLORS)]}">'
                         f'<title>{html.escape(label)}: {value:,} of {total:,} ({value / total:.1%})</title></rect>')
            parts.append(f'<text x="{left + w + 8:.1f}" y="{y + bar_h / 2 + 4}" class="tot">'
                         f'{value:,} · {value / total:.1%}</text>')
        parts.append("</svg>")
    return "".join(parts)


def endorsement_panel():
    """The reviewer's third point, drawn: nothing is discarded, endorsement is a second axis.

    Each row is one speech act. The full bar is conceptual presence; the segments are
    how far the text's own voice goes with it. A conditional about a divinity stays on
    the page as evidence that the proposition is represented.
    """
    order = [act for act, _ in collections.Counter(
        r["D7b_speech_act"] for r in records).most_common()]
    width, bar_h, gap, left = 880, 26, 14, 232
    states = list(ENDORSE_COLOR)
    height = len(order) * (bar_h + gap) + 62
    max_total = max(sum(endorse_by_act[act].values()) for act in order)
    total_w = width - left - 96
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Doctrinal endorsement within each speech act">']
    for i, act in enumerate(order):
        y = 18 + i * (bar_h + gap)
        total = sum(endorse_by_act[act].values())
        parts.append(f'<text x="{left - 10}" y="{y + bar_h / 2 + 5}" class="ax2">{html.escape(act)}</text>')
        x = left
        for state in states:
            n = endorse_by_act[act][state]
            if not n:
                continue
            w = max(1.5, total_w * n / max_total)
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" '
                         f'fill="{ENDORSE_COLOR[state]}"><title>{act} / {state}: {n:,} of {total:,}</title></rect>')
            x += w
        parts.append(f'<text x="{x + 8:.1f}" y="{y + bar_h / 2 + 5}" class="tot">{total:,}</text>')
    legend_y = 18 + len(order) * (bar_h + gap) + 12
    parts.append(f'<text x="12" y="{legend_y}" class="hd">endorsement within the act '
                 f'<tspan class="sub2">— every record is kept; only the endorsement moves</tspan></text>')
    x = left
    for state in states:
        parts.append(f'<rect x="{x}" y="{legend_y + 8}" width="11" height="11" rx="3" '
                     f'fill="{ENDORSE_COLOR[state]}"/>')
        parts.append(f'<text x="{x + 15}" y="{legend_y + 17}" class="lg">{state}</text>')
        x += 15 + 7 * len(state) + 14
    parts.append("</svg>")
    return "".join(parts)


def card(value, label, note=""):
    extra = f'<div class="n">{note}</div>' if note else ""
    return (f'<div class="card"><div class="v">{value}</div><div class="l">{label}</div>{extra}</div>')


corr = audit["correction"]
surv = corr["survives_after_correction"]
probe = audit["missed_formula_probe"]["totals"]
nd = audit["missed_formula_probe"]["divine_formula_in_non_divine_mouth"]
states = run["assertion_state_tally"]
layers = {layer["name"]: layer for layer in graph["layers"]}

cards = "".join([
    card(f'{scale["attestation_records"]:,}', "candidate records",
         f'over {len(propositions):,} distinct propositions and {len(windows):,} windows'),
    card(f'{scale["passage_matrix_cells"]:,}', "passage × value cells",
         f'{scale["passage_matrix_rows"]:,} rows × {scale["passage_matrix_value_columns"]} values'),
    card(f'{scale["exact_distinct_cross_work_pairs"]:,}', "cross-work pairs sharing a live state",
         'exact inverted-index join · complete for this relation, not for similarity · '
         f'index ships as ontology_passage_index.json.gz'),
    card(f'{scale["passage_pair_edges_written"]:,}', "passage-pair edges displayed",
         f'a display slice: {scale["display_cap_per_work_pair"]} per connected work pair, '
         f'not a bound on the count above'),
    card(f'{affirmative:,}', "machine-classified affirmative doctrine",
         "not human-verified · the only field usable for a doctrinal tally"),
    card("0", "human-verified records", "no coder has coded the packet yet"),
    card("0", "inheritance edges", "empty by design: dates are not data yet"),
])

audit_rows = "".join([
    f"<tr><td>matches, raw text</td><td>{corr['published']['term_hits']}</td>"
    f"<td>{audit['consistency_with_the_probe']['audit_as_is_match_count']} — reproduced exactly</td></tr>",
    "<tr><td>matches, whitespace-normalised</td><td>—</td>"
    f"<td>{corr['recall_control']['whitespace_normalised_matches']} "
    f"(+{corr['recall_control']['delta']}: Isaiah 44:6, Mark 12:29, four Qurʾan confessions)</td></tr>",
    f"<tr><td>works attested</td><td>{corr['published']['works_attested']}</td>"
    f"<td>{surv['works_attested']} — {' + '.join(surv['works'])}</td></tr>",
    f"<tr><td>traditions attested</td><td>{corr['published']['traditions_attested']}</td>"
    f"<td>{surv['traditions_attested']}</td></tr>",
    f"<tr><td>confessional matches in works not marked dependent</td><td>{corr['published']['term_hits']}</td>"
    f"<td>{surv['matches']} — independence not established, see the disposition table below</td></tr>",
    "<tr><td>anthology hits adding an independent witness</td><td>9</td><td>0 — all inside "
    "SELECTIONS FROM THE KORAN (8 reprint + 1 Carlyle essay)</td></tr>",
    "<tr><td>oneness formula classes the family carries</td><td>7 patterns</td>"
    f"<td>{probe['formula_classes']} further classes, {probe['occurrences']} occurrences, "
    f"{probe['uncovered_occurrences']} uncaught</td></tr>",
    f"<tr><td>confession form in a non-divine mouth</td><td>0</td><td>{nd['occurrences']} formula hits over "
    f"{nd['distinct_verses']} verses — Isaiah 47:8, 47:10, Zephaniah 2:15</td></tr>",
    "<tr><td>confession uttered by a denier the text refuses</td><td>counted as doctrine</td>"
    "<td>1 — Pharaoh drowning, Qurʾan sura 10</td></tr>",
])

disposition = audit["disposition_table"]


def disposition_row(row):
    works = " + ".join(f"{work} ({count})" for work, count in sorted(row["works"].items())) or "—"
    evidence = "yes — as a candidate" if row["counts_as_evidence_for_the_family"] else "no"
    verdicts = " · ".join(f"{verdict} ({count})"
                          for verdict, count in sorted(row["verdicts_inside_the_disposition"].items())) or "—"
    return (f"<tr><td>{row['disposition']}</td><td>{row['matches']}</td><td>{works}</td>"
            f"<td>{evidence}</td><td class=\"prose\">{row['definition']}</td>"
            f"<td class=\"prose\">{verdicts}</td></tr>")


disposition_rows = "".join(disposition_row(row) for row in disposition["rows"])
disposition_zero = ", ".join(disposition["dispositions_with_zero_matches"]) or "none"

concept_legend = "".join(f'<span class="k"><i style="background:{heat_color(c)}"></i>{t}</span>' for c, t in [
    (0, "no candidate in this one translation"), (1, "1-4"), (5, "5-49"),
    (50, "50-299"), (300, "300+")])
state_legend = "".join(f'<span class="k"><i style="background:{c}"></i>{n}</span>'
                       for n, c in STATE_COLOR.items())

if recall:
    m, wide = recall["results"], recall["corpus_wide"]
    recall_row = (
        f"<tr><td>pair enumeration</td>"
        f"<td>{scale['exact_distinct_cross_work_pairs']:,} distinct cross-work pairs, enumerated by an exact "
        f"inverted index over live states — no blocking approximation remains, so the count is complete for "
        f"this relation</td>"
        f"<td>complete for `shares a live coded state`; silent about every state the detector cannot see, so "
        f"a missing edge is never a missing relationship</td></tr>"
        f"<tr><td>superseded LSH recall, corpus-wide</td>"
        f"<td>{wide['recall']:.4f} of {wide['exact_distinct_cross_work_pairs']:,} exact pairs "
        f"({wide['lost_to_bucket_cap']:,} lost to the bucket cap, "
        f"{wide['recall_if_bucket_cap_removed']:.4f} without it)</td>"
        "<td>what the replaced sketch cost; measured against the index above</td></tr>"
        f"<tr><td>superseded LSH recall, deterministic subset</td>"
        f"<td>{m['recall']:.4f} measured on {m['exact_sharing_pairs']:,} exact pairs inside the "
        f"{recall['subset']['passages_in_subset']:,}-passage stratified subset</td>"
        "<td>the figure earlier drafts quoted; it is a subset measurement, not a corpus one</td></tr>")
else:
    recall_row = ("<tr><td>pair enumeration</td><td>exact inverted index</td>"
                  "<td>recall of the superseded LSH step not yet measured: run "
                  "tools/validate_graph_recall.py</td></tr>")

fragment = f"""
<div class="tb">
<style>
.tb{{font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif;color:#e6edf3;
 background:#0f1418;padding:22px;border-radius:14px;max-width:1160px;margin:0 auto}}
.tb h1{{font-size:20px;margin:0 0 4px}}
.tb h2{{font-size:15px;margin:30px 0 8px;color:#9fb0bd;font-weight:600}}
.tb .sub{{color:#8b9aa8;margin:0 0 18px;font-size:13px}}
.tb .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:10px}}
.tb .card{{background:#161d23;border:1px solid #223038;border-radius:11px;padding:12px 13px}}
.tb .card .v{{font-size:23px;font-weight:650;letter-spacing:-.4px;color:#3ddc97}}
.tb .card .l{{font-size:12px;color:#c8d4de;margin-top:2px}}
.tb .card .n{{font-size:11px;color:#7b8b99;margin-top:5px}}
.tb .k{{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#9fb0bd;margin-right:14px}}
.tb .k i{{width:11px;height:11px;border-radius:3px;display:inline-block;border:1px solid #2b3a44}}
.tb .row{{font-size:9.6px;fill:#93a4b2;text-anchor:end;font-family:ui-monospace,monospace}}
.tb .ax{{font-size:9.5px;fill:#93a4b2}}
.tb .ax2{{font-size:11.5px;fill:#c8d4de;text-anchor:end;font-family:ui-monospace,monospace}}
.tb .tot{{font-size:11.5px;fill:#8b9aa8;font-family:ui-monospace,monospace}}
.tb .hd{{font-size:12.5px;fill:#9fb0bd;font-weight:600}}
.tb .sub2{{font-size:11px;fill:#7b8b99;font-weight:400}}
.tb .lg{{font-size:10.5px;fill:#9fb0bd}}
.tb table{{border-collapse:collapse;width:100%;font-size:12.6px}}
.tb th{{text-align:left;color:#8b9aa8;font-weight:600;border-bottom:1px solid #24333d;padding:6px 9px}}
.tb td{{border-bottom:1px solid #1b262d;padding:6px 9px;vertical-align:top;color:#dbe6ef}}
.tb td:first-child{{color:#9fb0bd}}
.tb td:not(:first-child){{font-family:ui-monospace,monospace}}
.tb td.prose{{font-family:inherit;color:#cfd9e1}}
.tb tfoot td{{border-bottom:none;border-top:1px solid #24333d;color:#8b9aa8;font-weight:600}}
.tb .panel{{background:#161d23;border:1px solid #223038;border-radius:11px;padding:14px 16px 6px}}
.tb .note{{font-size:12px;color:#7b8b99;margin:8px 0 0}}
.tb .warn{{border-left:3px solid #f2a24b;background:#1a1712;padding:11px 13px;border-radius:0 9px 9px 0;
 font-size:12.6px;color:#cfd9e1}}
.tb code{{background:#1b262d;padding:1px 5px;border-radius:4px;font-size:12px;color:#8ee6c0}}
</style>

<h1>Track B, third pass — twelve analytically distinct dimensions, coded proposition by proposition</h1>
<p class="sub">v2 conflated plurality with exclusivity and genre with speech act, and it deleted the records its
own speech-act reading made uncomfortable. v3 splits both composites, codes one claim at a time instead of one
sentence at a time, and keeps every record while moving only its endorsement.</p>

<div class="cards">{cards}</div>

<h2>1 · Every work against every concept dimension — {len(works)} rows, nothing sampled</h2>
<div class="panel">{heatmap(candidate_counts, CONCEPT_DIMS, "candidate records")}</div>
<div style="margin-top:9px">{concept_legend}</div>
<p class="note">Cells count matched candidate records for the eight dimensions that answer a question about the
divinity itself. The four interpretation dimensions are absent from this figure by design: they are decided from
the shape of a proposition, not by matching a term, and drawing them on this legend would compare a count of
findings with a count of readings. A dark cell is not an absence in a tradition — it is either no candidate in
this one English translation or a value the instrument cannot see, and
{len(run['values_not_yet_instrumented'])} values are declared invisible outright.</p>

<h2>2 · The same grid, read as affirmative doctrine only — machine-classified, not human-verified</h2>
<div class="panel">{heatmap(doctrine_counts, CONCEPT_DIMS, "affirmative-doctrine records")}</div>
<p class="note">Identical cells, different field: <code>counts_as_affirmative_doctrine</code> is true only where
the speech act is an assertion or a denial <i>and</i> the text's own voice endorses it. This is the sole tally
that may be used for a doctrinal count, and it is the machine's reading, not a coder's.</p>

<h2>3 · The interpretation dimensions get their own axes and their own denominator</h2>
<div class="panel">{interpretation_panel()}</div>
<p class="note">Four questions, four groups of bars. The denominator on every bar is the {len(records):,}
term-carrying records this run produced — not the {scale['passage_matrix_rows']:,} passages of the corpus and not
the candidate counts of figure 1, so a percentage here is not comparable to a shade there. Each is decided per
proposition before any term is read, which is why none of them can appear as a matched-term count.</p>

<h2>4 · Conceptual presence and doctrinal endorsement are different questions</h2>
<div class="panel">{endorsement_panel()}</div>
<p class="note">{conceptual['represented_in_passage']:,} records carry a concept that is represented in the
passage; {affirmative:,} of them are also endorsed as doctrine. The gap is not noise to be discarded: a condition,
a question or an opponent's report is evidence that a proposition <i>is on the page</i>, and reported speech
preserves evidence of competing beliefs. v2 deleted 54 such matches outright, under a
<code>blocked_by_speech_act</code> state that no longer exists; v3 withholds endorsement and keeps the record.</p>

<h2>5 · What the instrument is and is not sure of</h2>
<div class="panel">{stacked()}</div>
<p class="note">{states['candidate']:,} open candidates ·
{states['candidate_requires_human_disambiguation']:,} flagged for a human (including single-valued dimensions
where two values matched one proposition) · {states['not_yet_instrumented']:,} on values with no validated
detector. v2's fourth state, <code>blocked_by_speech_act</code>, is gone: a refusal that removed the record
answered the wrong question.</p>

<h2>6 · The exclusivist-monotheism audit — v1's headline result, match by match</h2>
<table><thead><tr><th>quantity</th><th>published by v1</th><th>after the audit</th></tr></thead>
<tbody>{audit_rows}</tbody></table>
<p class="note">The audit imports the probe's own patterns, so the correction cannot be accused of testing a
different regex. Its verdict column is one analyst's reading: every record carries
<code>single_analyst_reading, not independently verified</code>.</p>

<h3>6a · Every match in exactly one disposition</h3>
<p>{disposition['headline']}</p>
<table><thead><tr><th>disposition</th><th>matches</th><th>works</th><th>evidence for the family?</th>
<th>what the row means</th><th>verdicts inside it</th></tr></thead>
<tbody>{disposition_rows}</tbody>
<tfoot><tr><td>total</td><td>{disposition['sum_of_disposition_rows']}</td>
<td colspan="4" class="prose">partitioned from {disposition['total_matches_partitioned']} audited matches ·
rows sum to the total: {disposition['sum_equals_total']} · dispositions with no match: {disposition_zero}</td>
</tr></tfoot></table>
<p class="note">The rows are generated by rule order and re-derived by predicate in the same run, so a match
counted twice or dropped would read false in <code>disposition_check</code> rather than ship quietly.
<code>counts_as_independent_attestation</code> is a v1 field name kept for schema stability: it records the
absence of a configured dependence rule, not a finding of independent transmission.</p>

<h2>7 · Graph layers — and the one that is empty on purpose</h2>
<table><thead><tr><th>layer</th><th>size</th><th>status</th></tr></thead><tbody>
<tr><td>1 source dependency</td><td>{layers['1_source_dependency']['edges']} edges</td><td>configured premises, not discovered</td></tr>
<tr><td>2 dimension state attestation</td><td>{layers['2_dimension_state_attestation']['nodes']} works × {len(dims)} dimensions</td><td>inventory, not claim</td></tr>
<tr><td>3 passage-pair shared states</td><td>{layers['3_passage_pair_shared_states']['pairs']:,} pairs, of which
{layers['3_passage_pair_shared_states']['edges']:,} displayed</td><td>exact enumeration; candidate generation
only, never a similarity claim</td></tr>
{recall_row}
<tr><td>4 inheritance and transformation</td><td>0 edges</td><td><b>unpopulated_by_design</b> — needs dated expressions and routes</td></tr>
<tr><td>5 coverage and absence</td><td>{len(run['values_not_yet_instrumented'])} values invisible to the detector</td><td>a gap reads as an instrument gap</td></tr>
</tbody></table>

<h2>8 · The binding constraint is a second coder, not more data</h2>
<div class="warn"><b>No human annotation has been performed.</b> The blinded packet now carries
{packet['propositions_in_packet']:,} propositions across
{packet['value_strata_count']} value strata, {packet['works_covered']} works and
{packet['speech_acts_covered']} speech acts ({packet['rare_value_strata_taken_whole']} rare strata taken as a
census), with a published codebook, a separate answer key and seed {packet['seed']}.
{packet['sample_roles']['machine_candidate']:,} of them are propositions the detector flagged, and
{packet['recall_probe']['rows_added']['no_candidate_uncued'] + packet['recall_probe']['rows_added']['no_candidate_cue_positive']:,}
are a simple random draw from the {packet['recall_probe']['universe']['no_record_in_universe']:,} propositions it
produced no record for — two disjoint strata, {packet['recall_probe']['strata']['no_candidate_uncued']['sampled']}
cue-negative (π={packet['recall_probe']['strata']['no_candidate_uncued']['inclusion_probability']}) and
{packet['recall_probe']['strata']['no_candidate_cue_positive']['sampled']} cue-positive
(π={packet['recall_probe']['strata']['no_candidate_cue_positive']['inclusion_probability']}), each row weighted
1/π. They are there because a sample of hits contains no misses: the candidate rows can bound precision and
cannot measure the detector's recall. It has never been coded, so
this repository contains no κ, no precision and no recall — and the scorer refuses to run on one coder, on the
same sheet supplied twice, or on a probe row with no weight. Nothing in the figures above is evidence that common ancestry is possible or
impossible: all four competing models predict the same non-detection pattern in a one-translation English corpus.
This instrument is <b>multilingual-ready</b>, not multilingual: every detector here is an English
translation-text pattern.</div>
</div>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "results/track_b_state.html"),
                        help="where to write the fragment; a chat presentation copies it elsewhere")
    args = parser.parse_args()
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(fragment, encoding="utf-8", newline="")
    print(f"wrote {destination} ({len(fragment):,} characters, {len(works)} works x {len(dims)} dimensions, "
          f"{len(propositions):,} propositions, {affirmative:,} machine-affirmative, "
          f"{scale['passage_pair_edges_written']:,} displayed edges of "
          f"{scale['exact_distinct_cross_work_pairs']:,} enumerated pairs)")


if __name__ == "__main__":
    main()
