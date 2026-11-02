"""Tests for the anomaly instrument and for the numbers the M4 block-profile gate reads off it.

These tests check an instrument, not a historical claim. They hold four things in place: that a seeded chance
draw returns the same bytes whatever the process's hash seed is, because a run-to-run drift in a Monte Carlo makes
every excess in the paper a sample of noise; that the committed artifact is what a fresh scan writes, so no
number in it was typed by hand; that a chance line is published with the statistic and the pair population that
measured it, because the gate's means and the scan's baseline disagreed until they were matched; and that the
scan and the gate, reading the same corpus through the same code, arrive at the same block profile.

The corpus facts asserted here are the ones the paper states. If a re-run of the detector moves one of them, the
test fails and the sentence in the paper has to be re-checked, which is the point.
"""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import compare_models as cm  # noqa: E402
import scan_dimension_anomalies as scan  # noqa: E402

ARTIFACT = ROOT / "results" / "dimension_anomalies.json"
CONFIG = json.loads((ROOT / "config" / "model_comparison_v3.json").read_text(encoding="utf-8"))
MINIMUM_SPREAD = CONFIG["m4_block_profile_test"]["minimum_block_spread"]
DEAD_BY_DETECTOR = ["D7b_speech_act", "D7c_discourse_genre", "D7d_epistemic_commitment"]

_SNIPPET = """
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))
import scan_dimension_anomalies as scan
per_work, _, _ = scan.load_work_states()
keys = scan.cm.dimension_keys(json.loads(scan.CONFIG_PATH.read_text(encoding="utf-8")))
cardinality = scan.cm.cardinality_map(json.loads(scan.CONFIG_PATH.read_text(encoding="utf-8")))
import random
out = {}
for key in ("D2a_acknowledged_population", "D7a_speaker_attribution", "D4_cosmic_function"):
    probabilities, sizes = scan.value_marginals(per_work, key)
    out[key] = {
        "marginals": probabilities,
        "sizes": sizes,
        "chance_exact": scan.chance_agreement(probabilities, sizes, random.Random(scan.CHANCE_SEED),
                                              "exact_match", scan.CHANCE_REPETITIONS),
        "chance_jaccard": scan.chance_agreement(probabilities, sizes, random.Random(scan.CHANCE_SEED),
                                                "jaccard", scan.CHANCE_REPETITIONS),
    }
print(json.dumps(out, sort_keys=True))
"""


def adjacent_by_pair(items, stronger, weaker):
    return next(item for item in items if item["stronger"] == stronger and item["weaker"] == weaker)


def escape(name):
    """A dimension or status key written the way the paper's source has to write it."""
    return name.replace("_", "\\_")


def artifact():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


_MEMO = {}


def gate_on_corpus():
    """The M4 block-profile test run on the corpus's own pairs, against this artifact's chance line."""
    if "gate" not in _MEMO:
        observations = scan.corpus_observations()
        table = cm.corpus_chance_similarity()
        _MEMO["gate"] = (observations, table, cm.attractor_block_profile_test(observations, CONFIG, table))
    return _MEMO["gate"]


class ChanceDrawIsDeterministic(unittest.TestCase):
    """A seeded Monte Carlo that reads a set-derived sequence drifts with PYTHONHASHSEED."""

    def run_with_seed(self, seed):
        environment = dict(os.environ, PYTHONHASHSEED=str(seed))
        finished = subprocess.run([sys.executable, "-c", _SNIPPET], cwd=str(ROOT), env=environment,
                                  capture_output=True, text=True, check=True)
        return finished.stdout.strip()

    def test_the_same_seed_returns_the_same_draw_under_every_hash_seed(self):
        first = self.run_with_seed(0)
        for seed in (1, 7, 12345):
            self.assertEqual(json.loads(first), json.loads(self.run_with_seed(seed)),
                             f"the chance draw moved under PYTHONHASHSEED={seed}")

    def test_the_marginals_are_ordered_by_value_and_the_sizes_by_work_id(self):
        printed = json.loads(self.run_with_seed(0))
        per_work, _, _ = scan.load_work_states()
        for key, cell in printed.items():
            self.assertEqual(list(cell["marginals"]), sorted(cell["marginals"]),
                             f"{key}'s marginals are in a hash-dependent order")
            expected = [len(set(per_work[work][key])) for work in sorted(per_work) if key in per_work[work]]
            self.assertEqual(cell["sizes"], expected, f"{key}'s carrier sizes are not in sorted work-id order")


class ArtifactIsReproducible(unittest.TestCase):
    """Every published number is a function of the corpus, or it is not allowed in the artifact."""

    @classmethod
    def setUpClass(cls):
        cls.reported = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        cls.fresh = scan.scan()

    def test_a_fresh_scan_reproduces_the_committed_artifact(self):
        self.assertEqual(json.dumps(self.fresh, sort_keys=True), json.dumps(self.reported, sort_keys=True))

    def test_the_artifact_names_the_input_it_was_computed_from(self):
        digest = hashlib.sha256((ROOT / "results" / "ontology_work_states.csv").read_bytes()).hexdigest()
        self.assertEqual(self.reported["inputs"]["sha256"], digest)
        self.assertEqual(self.reported["null_model"]["draws"], scan.CHANCE_REPETITIONS)
        self.assertEqual(self.reported["null_model"]["seed"], scan.CHANCE_SEED)

    def test_the_chance_band_is_the_scan_s_and_is_not_the_registered_block_separability(self):
        self.assertEqual(self.reported["null_model"]["band"], scan.CHANCE_BAND)
        self.assertNotIn("band", json.dumps(CONFIG["m4_block_profile_test"]))
        self.assertNotEqual(scan.CHANCE_BAND, MINIMUM_SPREAD + 1e-9)


class MeasurementsAreNamed(unittest.TestCase):
    """A mean without a named statistic and a named population cannot be subtracted from anything."""

    @classmethod
    def setUpClass(cls):
        cls.reported = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_every_dimension_publishes_both_readings_with_the_statistic_used(self):
        cardinality = cm.cardinality_map(CONFIG)
        for row in self.reported["dimensions"] + self.reported["pair_graph"]["dimensions"]:
            declared = cardinality[row["dimension"]] == "single"
            self.assertEqual(row["declared_rule"]["statistic"], "exact_match" if declared else "jaccard")
            self.assertEqual(row["value_sets"]["statistic"], "jaccard")
            self.assertEqual(row["statistic_the_frame_declares"], "exact_match" if declared else "jaccard")

    def test_the_two_tables_are_labelled_as_the_two_populations_they_measure(self):
        carrier = {row["population_measured"] for row in self.reported["dimensions"]}
        scored = {row["population_measured"] for row in self.reported["pair_graph"]["dimensions"]}
        self.assertEqual(len(carrier), 1)
        self.assertEqual(len(scored), 1)
        self.assertNotEqual(carrier, scored)
        self.assertEqual(next(iter(carrier)), "every pair of works that both carry a value for this dimension")

    def test_the_scored_graph_is_a_proper_subset_of_the_carrier_graph(self):
        graph = self.reported["pair_graph"]
        self.assertLess(graph["pairs_scorable"], self.reported["pairs_of_works_possible"])
        self.assertLess(graph["works_covered"], self.reported["works_scanned"])
        self.assertEqual(graph["conditioning"],
                         "the pairs compare_models.similarity_between scores, at least 6 comparable keys")

    def test_a_chance_line_is_published_for_every_dimension_the_gate_reads(self):
        lines = self.reported["pair_graph"]["chance_similarity_per_dimension"]
        for row in self.reported["pair_graph"]["dimensions"]:
            if row["declared_rule"]["pairs_compared"]:
                self.assertIn(row["dimension"], lines)


class CorpusAnomaliesArePublished(unittest.TestCase):
    """The four findings the paper states, each read from the artifact rather than restated here."""

    @classmethod
    def setUpClass(cls):
        cls.reported = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        cls.graph = cls.reported["pair_graph"]
        cls.rows = {row["dimension"]: row for row in cls.graph["dimensions"]}

    def test_three_declared_dimensions_never_fired_on_this_corpus(self):
        self.assertEqual(self.reported["dead_dimensions"], DEAD_BY_DETECTOR)
        for key in DEAD_BY_DETECTOR:
            row = next(item for item in self.reported["dimensions"] if item["dimension"] == key)
            self.assertEqual(row["works_with_an_attested_value"], 0)
            self.assertTrue(row["status"].startswith("dead"))

    def test_the_arbitrary_block_is_carried_by_two_live_keys_of_five(self):
        arbitrary = self.graph["blocks"]["blocks"]["arbitrary_or_expressive"]
        self.assertEqual(sorted(arbitrary["keys_dead_on_this_corpus"]), ["D7b_speech_act", "D7c_discourse_genre"])
        self.assertEqual(arbitrary["keys_live_on_this_corpus"], ["D7a_speaker_attribution",
                                                                "D1_ontological_category"])

    def test_the_speaker_attribution_key_sits_inside_the_chance_band(self):
        for reading in scan.READINGS:
            self.assertTrue(self.rows["D7a_speaker_attribution"][reading]["excess_within_declared_chance_band"],
                            f"D7a moved outside the band under {reading}")
        self.assertIn("D7a_speaker_attribution", self.graph["indistinguishable_from_chance"]["declared_rule"])

    def test_the_exact_match_rule_has_no_defined_answer_on_most_single_valued_cells(self):
        offenders = sum(row["cells_where_a_single_valued_key_carries_more_than_one_value"] or 0
                        for row in self.reported["dimensions"])
        carriers = sum(row["works_with_an_attested_value"] for row in self.reported["dimensions"]
                       if row["cells_where_a_single_valued_key_carries_more_than_one_value"] is not None)
        self.assertEqual(offenders, 89)
        self.assertEqual(carriers, 157)
        self.assertGreater(offenders / carriers, 0.5)

    def test_the_works_the_gate_reads_cover_are_dependent_at_the_top_of_the_ranking(self):
        for row in self.reported["pairs"]["top_pairs_by_excess_agreement"]:
            self.assertTrue(row["either_work_has_dependent_reprints"],
                            f"{row['work_a']} / {row['work_b']} is not a dependent pair")
        self.assertIn("not evidence of one", self.reported["pairs"]["reading"])

    def test_the_artifact_refuses_to_read_a_similarity_as_a_transmission(self):
        for phrase in ("no dates", "not human coding", "dependence is flagged"):
            self.assertIn(phrase, self.reported["what_this_is_not"])


class TheGraphYouChooseMovesAVerdict(unittest.TestCase):
    """Conditioning alone changes an adjacency, which is why both graphs are published."""

    @classmethod
    def setUpClass(cls):
        cls.reported = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        cls.graph = cls.reported["pair_graph"]

    def test_refusing_thin_pairs_flips_the_declared_adjacency(self):
        flips = self.graph["adjacency_verdicts_that_change_with_the_graph"]
        self.assertIn("declared_rule_chance_corrected_dropping_the_band_keys", flips)
        changed = adjacent_by_pair(flips["declared_rule_chance_corrected_dropping_the_band_keys"]["carrier_graph"],
                                   "structural", "arbitrary_or_expressive")
        on_graph = adjacent_by_pair(flips["declared_rule_chance_corrected_dropping_the_band_keys"]["scored_graph"],
                                    "structural", "arbitrary_or_expressive")
        self.assertEqual(changed["verdict"], cm.ADJACENCY_TIE)
        self.assertEqual(on_graph["verdict"], "reversed")

    def test_the_raw_ordering_is_not_a_tie_on_either_graph(self):
        for blocks in (self.reported["blocks"], self.graph["blocks"]):
            item = adjacent_by_pair(blocks["verdicts"]["declared_rule_raw"]["adjacent_predictions"],
                                    "structural", "arbitrary_or_expressive")
            self.assertLess(item["observed_difference"], -MINIMUM_SPREAD)
            self.assertEqual(item["verdict"], "reversed")

    def test_the_furthest_movement_between_graphs_is_larger_than_the_chance_band(self):
        movements = [item for item in self.graph["movement_between_the_two_graphs"] if item["shift"] is not None]
        furthest = max(movements, key=lambda item: abs(item["shift"]))
        self.assertGreater(abs(furthest["shift"]), self.reported["null_model"]["band"])
        self.assertIn(furthest["dimension"], self.graph["why_a_second_population"])


class ScanAndGateAgree(unittest.TestCase):
    """The M4 gate reads its chance line out of this artifact, so the two cannot disagree by construction."""

    @classmethod
    def setUpClass(cls):
        cls.reported = artifact()
        cls.observations, cls.table, cls.test_ = gate_on_corpus()

    def test_the_gate_reads_the_scored_graph_chance_line_and_publishes_its_sha(self):
        self.assertTrue(self.test_["chance_similarity_table"]["used"])
        self.assertEqual(self.test_["chance_similarity_table"]["path"], "results/dimension_anomalies.json")
        self.assertEqual(self.test_["chance_similarity_table"]["sha256"],
                         hashlib.sha256(ARTIFACT.read_bytes()).hexdigest())
        self.assertEqual(self.test_["chance_similarity_table"]["dimensions_supplied"], len(self.table["dimensions"]))
        self.assertEqual(self.table["dimensions"],
                         self.reported["pair_graph"]["chance_similarity_per_dimension"])

    def test_the_gate_and_the_scan_pool_the_same_chance_corrected_block_means(self):
        from_scan = {name: row["readings"]["declared_rule"]["excess_mean_over_chance"]
                     for name, row in self.reported["pair_graph"]["blocks"]["blocks"].items()}
        from_gate = self.test_["readings"]["excess_over_chance"]["block_means"]
        self.assertEqual(from_scan, from_gate)

    def test_the_same_pairs_refute_the_ordering_raw_and_tie_it_chance_corrected(self):
        raw = adjacent_by_pair(self.test_["readings"]["raw_similarity"]["adjacent_predictions"],
                               "structural", "arbitrary_or_expressive")
        corrected = adjacent_by_pair(self.test_["readings"]["excess_over_chance"]["adjacent_predictions"],
                                     "structural", "arbitrary_or_expressive")
        self.assertLess(raw["observed_difference"], -MINIMUM_SPREAD)
        self.assertEqual(raw["verdict"], "reversed")
        self.assertLess(abs(corrected["observed_difference"]), MINIMUM_SPREAD)
        self.assertEqual(corrected["verdict"], cm.ADJACENCY_TIE)

    def test_a_verdict_that_depends_on_the_scale_disqualifies_nothing(self):
        self.assertEqual(self.test_["status"], cm.STATUS_PROFILE_SCALE_DEPENDENT)
        self.assertNotIn(self.test_["status"], cm.STATUS_PROFILE_DISCONFIRMED)
        self.assertEqual(self.test_["readings_that_disconfirm"], ["raw_similarity"])
        self.assertEqual(self.test_["readings"]["excess_over_chance"]["status"], cm.STATUS_PROFILE_TIED)

    def test_the_gate_sees_the_pairs_the_comparison_layer_would_score(self):
        self.assertEqual(self.test_["pairs"], self.reported["pair_graph"]["pairs_scorable"])

    def test_the_per_dimension_means_are_reported_for_the_block_the_gate_judges(self):
        structural = self.test_["observed_block_profile"]["structural"]["per_dimension"]
        self.assertEqual(structural["D2a_acknowledged_population"]["excess_over_chance"],
                         round(structural["D2a_acknowledged_population"]["mean_similarity"]
                               - self.table["dimensions"]["D2a_acknowledged_population"], 6))


class CorpusObservationsMatchTheScanner(unittest.TestCase):
    """The observation set the gate is handed is the scanner's own scored graph, built the same way."""

    def test_every_observation_is_a_pair_the_comparison_layer_agrees_to_score(self):
        per_work, _, _ = scan.load_work_states()
        pairs = set()
        for left, right in combinations(sorted(per_work), 2):
            state_a = scan.work_state_for(per_work[left], CONFIG)
            state_b = scan.work_state_for(per_work[right], CONFIG)
            scored = cm.similarity_between(state_a, state_b, CONFIG)
            if scored["scorable"]:
                pairs.add((left, right))
        built = {tuple(item["pair_id"].split("|")) for item in scan.corpus_observations()}
        self.assertEqual(built, pairs)
        self.assertTrue(all(item.get("block_profile") for item in scan.corpus_observations()))


class PaperQuotesTheArtifact(unittest.TestCase):
    """The paper's anomaly table and its prose figures are copies of the artifact, so they are checked as copies.

    `tests/test_documented_counts.py` exists because a figure carried between drafts drifts and nobody notices.
    The same applies to a number typed out of a scan, so every load-bearing figure in the anomaly subsection is
    re-derived here from `results/dimension_anomalies.json` and looked for in `paper/main.tex` as written.
    """

    @classmethod
    def setUpClass(cls):
        cls.reported = artifact()
        cls.graph = cls.reported["pair_graph"]
        cls.scored = {row["dimension"]: row for row in cls.graph["dimensions"]}
        cls.tex = " ".join((ROOT / "paper" / "main.tex").read_text(encoding="utf-8").split())

    def paper_rows(self):
        block = self.tex.split(r"\label{tab:chance}")[1].split(r"\end{tabular}")[0]
        rows = {}
        for chunk in block.split(r"\\ "):
            if r"\dimkey{" not in chunk:
                continue
            cells = [cell.strip() for cell in chunk[chunk.index(r"\dimkey{"):].strip().split("&")]
            name = cells[0].split("{", 1)[1].rstrip("}").replace(r"\_", "_")
            rows[name] = cells[1:]
        return rows

    def assert_quoted(self, fragment):
        self.assertIn(" ".join(fragment.split()), self.tex,
                      f"paper/main.tex does not say {fragment!r} while the artifact does")

    def test_the_paper_table_is_the_artifact_rounded_to_three_places(self):
        rows = self.paper_rows()
        live = [row["dimension"] for row in self.graph["dimensions"] if row["declared_rule"]["pairs_compared"]]
        self.assertEqual(sorted(rows), sorted(live))
        for name, cells in rows.items():
            measured = self.scored[name]["declared_rule"]
            self.assertEqual(cells[0].replace(r"\_", "_"), measured["statistic"])
            self.assertEqual(int(cells[1]), measured["pairs_compared"])
            self.assertEqual(cells[2], f"{measured['observed_mean_similarity']:.3f}")
            self.assertEqual(cells[3], f"{measured['chance_similarity_from_own_marginals']:.3f}")
            self.assertEqual(cells[4], rf"\({measured['excess_over_chance']:+.3f}\)")
            undefined = self.scored[name]["works_where_the_exact_match_rule_has_no_defined_answer"]
            self.assertEqual(cells[5], "---" if undefined is None else rf"\({undefined:.3f}\)")

    def test_the_prose_figures_are_the_artifact_figures(self):
        null = self.reported["null_model"]
        d2c = self.scored["D2c_worship_exclusivity"]
        d7a = self.scored["D7a_speaker_attribution"]
        offenders = sum(row["cells_where_a_single_valued_key_carries_more_than_one_value"] or 0
                        for row in self.reported["dimensions"])
        carriers = sum(row["works_with_an_attested_value"] for row in self.reported["dimensions"]
                       if row["cells_where_a_single_valued_key_carries_more_than_one_value"] is not None)
        movements = [item for item in self.graph["movement_between_the_two_graphs"] if item["shift"] is not None]
        furthest = max(movements, key=lambda item: abs(item["shift"]))
        endorsement = next(row for row in self.reported["sensitivity_under_the_endorsement_frame"]["dimensions"]
                           if row["dimension"] == "D7a_speaker_attribution")
        self.assert_quoted(f"of \\({self.reported['pairs_of_works_possible']}\\) "
                           f"possible pairs of the \\({self.reported['works_scanned']}\\) works")
        self.assert_quoted(f"leaving \\({self.graph['pairs_scorable']}\\) pairs over "
                           f"\\({self.graph['works_covered']}\\) works")
        self.assert_quoted(f"\\dimkey{{{escape(furthest['dimension'])}}} moves "
                           f"\\({furthest['shift']:.4f}\\) between them")
        self.assert_quoted(f"larger than the \\({null['band']:.2f}\\) this scan uses")
        self.assert_quoted(f"\\texttt{{seed}} \\({null['seed']}\\), \\({null['draws']}\\) repetitions")
        self.assert_quoted(f"carrying \\({d2c['dominant_share_of_value_tokens']:.3f}\\) of the")
        self.assert_quoted(f"baseline at \\({d2c['declared_rule']['chance_similarity_from_own_marginals']:.3f}\\)")
        self.assert_quoted(f"Observed agreement is \\({d7a['declared_rule']['observed_mean_similarity']:.3f}\\)")
        self.assert_quoted(f"is \\({d7a['declared_rule']['chance_similarity_from_own_marginals']:.3f}\\), so the "
                           f"excess is \\({d7a['declared_rule']['excess_over_chance']:+.3f}\\)")
        self.assert_quoted(f"the excess is \\({endorsement['declared_rule']['excess_over_chance']:+.3f}\\)")
        self.assert_quoted(f"\\({offenders}\\) of the \\({carriers}\\) works")
        self.assert_quoted(f"undefined on \\({offenders / carriers:.3f}\\)")
        self.assert_quoted(f"\\({self.reported['pairs']['count_of_such_pairs']}\\) of the "
                           f"\\({self.graph['pairs_scorable']}\\) scored pairs")

    def test_the_block_means_the_paper_reports_are_the_ones_the_gate_computed(self):
        _, _, test_ = gate_on_corpus()
        order = CONFIG["m4_block_profile_test"]["declared_ordering"]
        for scale, phrase in (("raw_similarity", "raw mean similarity gives"),
                              ("excess_over_chance", "become")):
            means = test_["readings"][scale]["block_means"]
            joined = ", ".join(f"\\({means[name]:.3f}\\)" for name in order)
            self.assert_quoted(f"{phrase} {joined}")
        raw_item = adjacent_by_pair(test_["readings"]["raw_similarity"]["adjacent_predictions"],
                                    "structural", "arbitrary_or_expressive")
        corrected_item = adjacent_by_pair(test_["readings"]["excess_over_chance"]["adjacent_predictions"],
                                          "structural", "arbitrary_or_expressive")
        self.assert_quoted(f"a reversal of \\({raw_item['observed_difference']:+.3f}\\)")
        self.assert_quoted(f"the reversal is \\({corrected_item['observed_difference']:+.3f}\\)")
        self.assert_quoted(f"\\texttt{{{escape(test_['status'])}}} and disqualifies")
        for verdict in (test_["readings"]["raw_similarity"]["status"],
                        test_["readings"]["excess_over_chance"]["status"]):
            if verdict in cm.STATUS_PROFILE_DISCONFIRMED:
                self.assertIn(escape(verdict), self.tex)


if __name__ == "__main__":
    unittest.main()
