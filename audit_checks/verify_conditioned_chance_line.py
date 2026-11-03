"""Independent check of the pair-conditioned chance line published in `results/dimension_anomalies.json`.

This is the run `AUDIT_REPORT.md` §2 quotes when it says the conditioned baseline was checked against an
implementation that does not share code with the scanner. Nothing here uses the scanner's RNG path: the null
below draws each work's value set by an exponential race over the same marginals and the same edge list, at
20,000 replicates, and compares the result to the published line within combined standard error.

    python audit_checks/verify_conditioned_chance_line.py

Section 1 reads the chance table as it stood at the commit the audit started from, so it needs the repository's
history, not a network. Run time is minutes, not seconds; the eight sub-estimates per dimension exist so the
scatter of this check is its own measurement rather than an assumption.
"""
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import scan_dimension_anomalies as scan  # noqa: E402

# The release the audit was taken against. The pre-correction chance table is what section 1 compares to, and
# after the audit's own commit `HEAD` carries the corrected one, so the revision is named rather than assumed.
BASELINE = "78b2ed7"

old = json.loads(subprocess.run(["git", "show", f"{BASELINE}:results/dimension_anomalies.json"],
                                cwd=ROOT, capture_output=True, check=True).stdout)
new = json.loads((ROOT / "results" / "dimension_anomalies.json").read_text(encoding="utf-8"))

print("baseline artifact sha256", hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest()[:12])
print("current  artifact sha256", hashlib.sha256(json.dumps(new, sort_keys=True).encode()).hexdigest()[:12])


def only_known_keys(node, reference):
    if isinstance(node, dict):
        return {key: only_known_keys(value, reference[key]) for key, value in node.items()
                if key in reference}
    return node


print("\n1. carrier-graph rows, restricted to the fields the baseline already published:")
dropped = [only_known_keys(row, old_row) for row, old_row in zip(new["dimensions"], old["dimensions"])]
print("   identical after dropping the added fields:", dropped == old["dimensions"])
moved = []
for row, old_row in zip(new["dimensions"], old["dimensions"]):
    if row == old_row:
        continue
    differing = [key for key in row
                 if key in old_row and only_known_keys(row[key], old_row[key]) != old_row[key]]
    moved.append((row["dimension"], differing))
print("   fields that differ once the added keys are dropped:", moved or "none")
newly_added = sorted({key for row in new["dimensions"] if isinstance(row.get("declared_rule"), dict)
                      for key in row["declared_rule"]} -
                     {key for row in old["dimensions"] if isinstance(row.get("declared_rule"), dict)
                      for key in row["declared_rule"]})
print("   fields this change adds:", newly_added)
print("   indistinguishable sets equal:",
      old["indistinguishable_from_chance"] == new["indistinguishable_from_chance"])

# 2. independent null: exponential-race weighted sampling without replacement over the scored edge list.
config = json.loads((ROOT / "config" / "model_comparison_v3.json").read_text(encoding="utf-8"))
cardinality = scan.cm.cardinality_map(config)
keys = scan.cm.dimension_keys(config)
graph_observations, graph_population, scorable_pairs, graph_edges = scan.scorable_graph(
    scan.load_work_states()[0], config, cardinality)


def race_line(probabilities, sizes, edges, statistic, reps, seed):
    values = sorted(probabilities)
    weights = [probabilities[v] for v in values]
    index = {v: position for position, v in enumerate(values)}
    rng = random.Random(seed)
    total = 0.0
    for _ in range(reps):
        rows = []
        for size in sizes:
            keys_by_sort = sorted(range(len(values)),
                                  key=lambda position: rng.expovariate(weights[position]))
            rows.append(frozenset(values[position] for position in keys_by_sort[:min(size, len(values))]))
        scored = [value for value in (scan.score(a, b, statistic) for a, b in
                                     ((rows[i], rows[j]) for i, j in edges)) if value is not None]
        total += sum(scored) / len(scored)
    return total / reps


published = {row["dimension"]: row for row in new["pair_graph"]["dimensions"]}
band_rows = {(row["dimension"], row["reading"]): row
             for row in new["chance_band_diagnostics"]["scored_graph"]["per_measurement"]}
print("\n2. published conditioned line vs an independently coded null (20,000 replicates)")
print(f"{'dimension':32s} {'published':>10s} {'race':>10s} {'diff':>9s} {'se(pub)':>8s} "
      f"{'se(race)':>8s} {'z':>6s} {'gap':>9s}")
z_scores = []
for key in keys:
    probabilities, sizes = scan.value_marginals(graph_population, key)
    if not sizes:
        continue
    edges = graph_edges[key]
    statistic = scan.statistic_for_key(cardinality, key)
    estimates = [race_line(probabilities, sizes, edges, statistic, 2500, 4242 + slot) for slot in range(8)]
    mean = sum(estimates) / len(estimates)
    se_race = (sum((value - mean) ** 2 for value in estimates) / (len(estimates) - 1) / len(estimates)) ** 0.5
    row = published[key]["declared_rule"]
    # The scanner's own replicate scatter sets the standard error of its 200-replicate line.
    se_published = band_rows[(key, "declared_rule")]["null_excess_sd"] / scan.CHANCE_REPETITIONS ** 0.5
    difference = row["chance_similarity_from_own_marginals"] - mean
    combined = (se_published ** 2 + se_race ** 2) ** 0.5
    z_scores.append((abs(difference / combined), abs(difference), key))
    print(f"{key:32s} {row['chance_similarity_from_own_marginals']:10.6f} {mean:10.6f} "
          f"{difference:+9.6f} {se_published:8.6f} {se_race:8.6f} {difference / combined:6.2f} "
          f"{row['conditioning_gap']:+9.6f}")

if z_scores:
    worst_z = max(z_scores)
    worst_diff = max(z_scores, key=lambda item: item[1])
    print(f"\n   largest |z| = {worst_z[0]:.2f} ({worst_z[2]}), largest absolute difference = "
          f"{worst_diff[1]:.4f} ({worst_diff[2]})")
    print("   every line agrees within two standard errors of the combined estimate:",
          all(item[0] < 2.0 for item in z_scores))

print("\n3. analytic expectation, which binds only where every carrier holds exactly one value")
for key in keys:
    if cardinality[key] != "single":
        continue
    probabilities, sizes = scan.value_marginals(graph_population, key)
    if not sizes:
        continue
    analytic = sum(value ** 2 for value in probabilities.values())
    row = published[key]["declared_rule"]
    if set(sizes) != {1}:
        print(f"{key:32s} not all carriers single-valued, so sum p_v^2 is not this line "
              f"(sum p_v^2={analytic:.6f} published={row['chance_similarity_from_own_marginals']:.6f})")
        continue
    print(f"{key:32s} analytic={analytic:.6f} published={row['chance_similarity_from_own_marginals']:.6f} "
          f"complete_graph={row['chance_similarity_over_all_pairs_of_carriers']:.6f} all_sizes_one=True")

print("\n4. the figures the paper quotes")
for key in keys:
    row = published[key]["declared_rule"]
    if row["excess_over_chance"] is None:
        continue
    baseline_row = next(r for r in old["pair_graph"]["dimensions"] if r["dimension"] == key)["declared_rule"]
    print(f"{key:32s} excess={row['excess_over_chance']:+.6f} baseline_excess={baseline_row['excess_over_chance']:+.6f} "
          f"inside_band={row['excess_within_declared_chance_band']}")
print("   verdicts that change with the chance line:",
      [item["dimension"] + "/" + item["reading"]
       for item in new["pair_graph"]["chance_line_conditioning"]
       ["band_verdicts_that_change_with_the_chance_line"]])
