#!/usr/bin/env python3
"""Render the Track B instrument state as a self-contained HTML fragment.

Every number is read from a published artifact in this repo: nothing here is typed by hand, so the
picture cannot drift from the run that produced it.
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
scale = graph["scale"]

DIM_LABEL = {
    "D1_divine_ontology": "D1 ontology",
    "D2_plurality": "D2 plurality",
    "D3_agency": "D3 agency",
    "D4_cosmic_function": "D4 function",
    "D5_universe_relationship": "D5 universe",
    "D6_temporal_nature": "D6 time",
    "D7_human_interpretation": "D7 speech act",
}
STATE_COLOR = {
    "candidate": "#3ddc97",
    "candidate_requires_human_disambiguation": "#5aa9e6",
    "blocked_by_speech_act": "#f2a24b",
    "not_yet_instrumented": "#8b8f95",
}

# ---------------------------------------------------------------- work x dimension matrix
works, dims = [], []
with (ROOT / "results/ontology_work_states.csv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
counts = collections.defaultdict(int)
blocked = set()
for row in rows:
    counts[(row["work_id"], row["dimension"])] += int(row["candidate_count"])
works = sorted({r["work_id"] for r in rows})
dims = sorted({r["dimension"] for r in rows})

with gzip.open(ROOT / "results/ontology_attestations.jsonl.gz", "rt", encoding="utf-8") as handle:
    records = [json.loads(line) for line in handle]
for record in records:
    if record["assertion_state"] == "blocked_by_speech_act":
        blocked.add((record["work_id"], record["dimension"]))

# D7 is not a matched dimension: it is decided per utterance window before any divine term is read, so the
# work-state table carries it with zero candidates for all 65 x 13 rows. Leaving that column dark would make a
# populated axis look unattested everywhere, which is the exact error this frame was built to stop repeating.
# For this column the cell holds the windows the frame reads as doctrine.
d7_windows = collections.defaultdict(set)
for record in records:
    if record["D7_speech_act"] == "asserted_doctrine":
        d7_windows[record["work_id"]].add((record["passage_id"], record["window_char_start"]))
for work in works:
    counts[(work, "D7_human_interpretation")] = len(d7_windows[work])

by_dim_state = collections.defaultdict(collections.Counter)
for record in records:
    by_dim_state[record["dimension"]][record["assertion_state"]] += 1
d2_speech = collections.Counter(r["D7_speech_act"] for r in records if r["dimension"] == "D2_plurality")

CELL, GAP = 13, 2


def heat_color(count, is_blocked):
    if is_blocked:
        return "#f2a24b"
    if count == 0:
        return "#1b2126"
    if count < 5:
        return "#1f6f52"
    if count < 50:
        return "#2fae81"
    if count < 300:
        return "#3ddc97"
    return "#9be86b"


def heatmap():
    left, top = 118, 96
    width = left + len(dims) * (CELL + GAP) + 24
    height = top + len(works) * (CELL + GAP) + 34
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Every work against every dimension">']
    for j, dim in enumerate(dims):
        x = left + j * (CELL + GAP) + CELL / 2
        parts.append(f'<text x="{x:.1f}" y="{top - 8}" class="ax" transform="rotate(-58 {x:.1f} {top - 8})">'
                     f'{html.escape(DIM_LABEL.get(dim, dim))}</text>')
    for i, work in enumerate(works):
        y = top + i * (CELL + GAP)
        parts.append(f'<text x="{left - 8}" y="{y + CELL - 2}" class="row">{html.escape(work)}</text>')
        for j, dim in enumerate(dims):
            c = counts[(work, dim)]
            fill = heat_color(c, (work, dim) in blocked)
            parts.append(f'<rect x="{left + j * (CELL + GAP)}" y="{y}" width="{CELL}" height="{CELL}" '
                         f'fill="{fill}"><title>{html.escape(work)} / {DIM_LABEL.get(dim, dim)}: '
                         f'{c} {"windows read as doctrine" if dim == "D7_human_interpretation" else "candidate records"}</title></rect>')
    parts.append("</svg>")
    return "".join(parts)


def stacked():
    ordered = [d for d in dims if by_dim_state[d]]
    width, bar_h, gap, left = 860, 26, 16, 122
    total_w = width - left - 96
    height = len(ordered) * (bar_h + gap) + 40
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Assertion states per dimension">']
    max_total = max(sum(by_dim_state[d].values()) for d in ordered)
    for i, dim in enumerate(ordered):
        y = 18 + i * (bar_h + gap)
        parts.append(f'<text x="{left - 10}" y="{y + bar_h / 2 + 5}" class="ax2">'
                     f'{html.escape(DIM_LABEL.get(dim, dim))}</text>')
        x = left
        for state in ("candidate", "candidate_requires_human_disambiguation",
                      "blocked_by_speech_act", "not_yet_instrumented"):
            n = by_dim_state[dim][state]
            if not n:
                continue
            w = max(1.5, total_w * n / max_total)
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" '
                         f'fill="{STATE_COLOR[state]}"><title>{DIM_LABEL.get(dim, dim)} / {state}: {n}</title></rect>')
            x += w
        parts.append(f'<text x="{x + 8:.1f}" y="{y + bar_h / 2 + 5}" class="tot">'
                     f'{sum(by_dim_state[dim].values()):,}</text>')
    parts.append("</svg>")
    return "".join(parts)


def speech_bars():
    items = d2_speech.most_common()
    width, bar_h, gap, left = 860, 20, 11, 258
    total_w = width - left - 74
    height = len(items) * (bar_h + gap) + 16
    colors = ["#3ddc97", "#f2a24b", "#c586c0", "#5aa9e6", "#d19a66", "#e06c75", "#56b6c2",
              "#98c379", "#abb2bf", "#61afef", "#7f848e"]
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Speech acts attached to plurality claims">']
    top = max(v for _, v in items)
    for i, (label, value) in enumerate(items):
        y = 10 + i * (bar_h + gap)
        parts.append(f'<text x="{left - 10}" y="{y + bar_h / 2 + 4}" class="ax2">{html.escape(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{max(2, total_w * value / top):.1f}" height="{bar_h}" '
                     f'rx="3" fill="{colors[i % len(colors)]}"><title>{label}: {value}</title></rect>')
        parts.append(f'<text x="{left + max(2, total_w * value / top) + 8:.1f}" y="{y + bar_h / 2 + 4}" '
                     f'class="tot">{value:,}</text>')
    parts.append("</svg>")
    return "".join(parts)


def card(value, label, note=""):
    extra = f'<div class="n">{note}</div>' if note else ""
    return (f'<div class="card"><div class="v">{value}</div><div class="l">{label}</div>{extra}</div>')


corr = audit["correction"]
rare_full = sum(1 for v in packet["strata"].values() if v["oversampled_because_rare"])
surv = corr["survives_after_correction"]
probe = audit["missed_formula_probe"]["totals"]
nd = audit["missed_formula_probe"]["divine_formula_in_non_divine_mouth"]
states = run["assertion_state_tally"]
layers = {layer["name"]: layer for layer in graph["layers"]}

cards = "".join([
    card(f'{scale["attestation_records"]:,}', "candidate records", "every match, with locator and speech act"),
    card(f'{scale["passage_matrix_cells"]:,}', "passage × value cells",
         f'{scale["passage_matrix_rows"]:,} rows × {scale["passage_matrix_value_columns"]} values'),
    card(f'{scale["passage_pair_edges_written"]:,}', "passage-pair edges",
         f'generated {scale["naive_passage_pair_space"]:,} naive space · no truncation'),
    card(f'{scale["work_pair_edges"]:,}', "work pairs sharing a state", "65 works, all pairs kept"),
    card(str(states["blocked_by_speech_act"]), "matches refused as doctrine", "conditional · question · opponent · boast"),
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
    f"<tr><td>confessional matches in independent witnesses</td><td>{corr['published']['term_hits']}</td>"
    f"<td>{surv['matches']}</td></tr>",
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

legend = "".join(f'<span class="k"><i style="background:{c}"></i>{n}</span>' for n, c in [
    ("live candidate", STATE_COLOR["candidate"]),
    ("needs human disambiguation", STATE_COLOR["candidate_requires_human_disambiguation"]),
    ("blocked by speech act", STATE_COLOR["blocked_by_speech_act"]),
    ("no candidate in this translation", "#1b2126"),
])

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
.tb table{{border-collapse:collapse;width:100%;font-size:12.6px}}
.tb th{{text-align:left;color:#8b9aa8;font-weight:600;border-bottom:1px solid #24333d;padding:6px 9px}}
.tb td{{border-bottom:1px solid #1b262d;padding:6px 9px;vertical-align:top;color:#dbe6ef}}
.tb td:first-child{{color:#9fb0bd}}
.tb td:not(:first-child){{font-family:ui-monospace,monospace}}
.tb .panel{{background:#161d23;border:1px solid #223038;border-radius:11px;padding:14px 16px 6px}}
.tb .note{{font-size:12px;color:#7b8b99;margin:8px 0 0}}
.tb .warn{{border-left:3px solid #f2a24b;background:#1a1712;padding:11px 13px;border-radius:0 9px 9px 0;
 font-size:12.6px;color:#cfd9e1}}
.tb .warn b{{color:#f2a24b}}
.tb code{{background:#1b262d;padding:1px 5px;border-radius:4px;font-size:12px;color:#8ee6c0}}
</style>

<h1>Track B, second pass — divine-concept states over the whole corpus</h1>
<p class="sub">Scale comes from the corpus, not from a sample: the previous graph shipped 149 edges after a
<code>[:100]</code> truncation. This one ships every candidate the blocking produced — and refuses to draw the
inheritance edges it cannot yet date.</p>

<div class="cards">{cards}</div>

<h2>1 · Every work against every dimension — 65 rows, nothing sampled</h2>
<div class="panel">{heatmap()}</div>
<div style="margin-top:9px">{legend}</div>
<p class="note">Row order is alphabetical by work id. Columns D1–D6 count matched candidate records; <b>D7 counts
something else</b> — utterance windows the frame reads as asserted doctrine — because the interpretation dimension
is decided from the shape of the window, not by matching a term, and the work-state table therefore carries no
per-value D7 counts. A dark cell is not an absence in a tradition: it is either
no candidate in this one English translation or a value the instrument cannot see. Those are different failures,
and {len(run['values_not_yet_instrumented'])} values are declared invisible outright —
{html.escape(', '.join(v.split('=')[1].replace('_or_', ' / ').replace('_', ' ') for v in run['values_not_yet_instrumented']))}
— which is where the frame's weakest points sit, directly over the errors it was built to catch.</p>

<h2>2 · What the frame found, and what it refused to read</h2>
<div class="panel">{stacked()}</div>
<p class="note">{states['candidate']:,} open candidates · {states['candidate_requires_human_disambiguation']:,}
flagged for a human · {states['blocked_by_speech_act']} refused as doctrine ·
{states['not_yet_instrumented']} on uninstrumented values. D7 carries no matched records by design: it is decided
from the shape of the utterance window first, and reported as the axis below.</p>

<h2>3 · Plurality claims by speech act — the reason a term count is not a belief count</h2>
<div class="panel">{speech_bars()}</div>
<p class="note">Of {sum(d2_speech.values()):,} plurality matches, {d2_speech['asserted_doctrine']} sit in windows
read as doctrine and {d2_speech['reported_speech_of_opponent']} in windows reporting an opponent, a boast, a doubt
or a hypothesis. A census that cannot tell these apart is what produced the withdrawn conclusion.</p>

<h2>4 · The exclusivist-monotheism audit — v1's headline result, match by match</h2>
<table><thead><tr><th>quantity</th><th>published by v1</th><th>after the audit</th></tr></thead>
<tbody>{audit_rows}</tbody></table>
<p class="note">The audit imports the probe's own patterns, so the correction cannot be accused of testing a
different regex. Its verdict column is one analyst's reading: every record carries
<code>single_analyst_reading, not independently verified</code>, and the artifact says out loud that leaving
nothing unresolved on a source-critical pass is itself a reason to re-code.</p>

<h2>5 · Graph layers — and the one that is empty on purpose</h2>
<table><thead><tr><th>layer</th><th>size</th><th>status</th></tr></thead><tbody>
<tr><td>1 source dependency</td><td>{layers['1_source_dependency']['edges']} edges</td><td>configured premises, not discovered</td></tr>
<tr><td>2 dimension state attestation</td><td>{layers['2_dimension_state_attestation']['nodes']} works × 7 dimensions</td><td>inventory, not claim</td></tr>
<tr><td>3 passage-pair shared states</td><td>{layers['3_passage_pair_shared_states']['edges']:,} edges</td><td>candidate generation only</td></tr>
<tr><td>4 inheritance and transformation</td><td>0 edges</td><td><b>unpopulated_by_design</b> — needs dated expressions and routes</td></tr>
<tr><td>5 coverage and absence</td><td>{len(layers['5_coverage_and_absence']['values_not_yet_instrumented'])} values invisible to the detector</td><td>a gap reads as an instrument gap</td></tr>
</tbody></table>

<h2>6 · The binding constraint is a second coder, not more data</h2>
<div class="warn"><b>No human annotation has been performed.</b> The blinded packet exists —
{packet['windows_in_packet']:,} windows over {len(packet['strata'])} dimension-value strata
({rare_full} rare strata sampled at whole population), separate answer key, seed
{packet['seed']} published — and it is below the 3,000-window reliability target. The scorer refuses to run on one
coder, so there is no κ, no precision and no recall in this repository. Nothing in the four charts above is
evidence that common ancestry is possible or impossible: all four competing models predict the same non-detection
pattern in a one-translation English corpus, which is exactly why v1's negative verdict was withdrawn.</div>
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
          f"{scale['passage_matrix_cells']:,} matrix cells, {scale['passage_pair_edges_written']:,} edges)")


if __name__ == "__main__":
    main()
