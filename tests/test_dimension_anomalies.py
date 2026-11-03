"""Tests for the anomaly instrument and for the numbers the M4 block-profile gate reads off it.

These tests check an instrument, not a historical claim. They hold six things in place: that a seeded chance
draw returns the same bytes whatever the process's hash seed is, because a run-to-run drift in a Monte Carlo makes
every excess in the paper a sample of noise; that the committed artifact is what a fresh scan writes, so no
number in it was typed by hand; that a chance line is published with the statistic, the pair population and the
pair set that measured it, because the gate's means and the scan's baseline disagreed until they were matched, and
so did the two halves of one subtraction on the scored graph; that the scan and the gate, reading the same corpus
through the same code, arrive at the same block profile; that the analyst-set 0.05 band is published next to the
false-positive rate its own null produces, because a count of dimensions outside a band means nothing until that
rate is known; and that the band verdict the two possible chance lines produce is published as a comparison
rather than as a preference, because one dimension's verdict moves between them.

The corpus facts asserted here are the ones the paper states. If a re-run of the detector moves one of them, the
test fails and the sentence in the paper has to be re-checked, which is the point.
"""

import hashlib
import json
import os
import random
import subprocess
import sys
import unittest
from itertools import combinations, permutations
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


def _subset_weight(combo, probabilities):
    """The exact probability that the scan's successive weighted draw returns exactly this set.

    Summed over every order the values could be picked in, each order's probability being the running ratio the
    sampler itself computes: the value's weight over whatever mass is still in the pool.
    """
    total = 0.0
    for order in permutations(sorted(combo)):
        remaining = dict(probabilities)
        product = 1.0
        for value in order:
            product *= remaining[value] / sum(remaining.values())
            del remaining[value]
        total += product
    return total


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
    """The anomaly findings the paper states, each read from the artifact rather than restated here."""

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


class TheGraphYouChooseMovesTheNumbers(unittest.TestCase):
    """The two pair graphs give different means, which is why both are published.

    This class pinned a stronger claim until the chance line was corrected: that refusing thin pairs flipped the
    ``structural > arbitrary'' adjacency from a tie on the carrier graph to a reversal on the scored graph. The
    flip was not the pair set. It was one half of each subtraction having been drawn on a different design -- the
    scored graph's baseline computed over every pair of its 52 carriers while its observed mean ran over the 1237
    scorable pairs -- and the dimension that crossed the band once both halves shared a design was
    ``D6_temporal_nature'', which the band-key drop then removes. With the line conditioned on the scored pairs
    the two graphs read the same adjacency the same way, so the defensible claim is the one about the means.
    """

    @classmethod
    def setUpClass(cls):
        cls.reported = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        cls.graph = cls.reported["pair_graph"]

    def test_conditioning_the_baseline_leaves_no_adjacency_verdict_graph_dependent(self):
        self.assertEqual(self.graph["adjacency_verdicts_that_change_with_the_graph"], {},
                         "an adjacency now changes with the pair graph, so the paper's finding (4) has to be "
                         "re-read before it is re-quoted")

    def test_both_graphs_read_the_band_dropped_adjacency_as_the_same_tie(self):
        quantity = "declared_rule_chance_corrected_dropping_the_band_keys"
        pairs = (self.reported["blocks"]["verdicts"][quantity]["adjacent_predictions"],
                 self.graph["blocks"]["verdicts"][quantity]["adjacent_predictions"])
        verdicts = [adjacent_by_pair(item, "structural", "arbitrary_or_expressive") for item in pairs]
        self.assertEqual([item["verdict"] for item in verdicts],
                         [cm.ADJACENCY_TIE, cm.ADJACENCY_TIE],
                         "the carrier and scored graphs no longer agree, and this test only means something "
                         "while they do")
        self.assertEqual(self.graph["indistinguishable_from_chance"]["declared_rule"],
                         ["D2a_acknowledged_population", "D2b_reality_of_others", "D6_temporal_nature",
                          "D7a_speaker_attribution"],
                         "which dimensions get dropped from the band-dropped means is what this comparison turns "
                         "on")
        self.assertNotIn("D6_temporal_nature",
                         self.reported["indistinguishable_from_chance"]["declared_rule"],
                         "the carrier graph keeps D6 in its band-dropped means only while D6 sits outside that "
                         "band, and the whole comparison depends on the two graphs disagreeing about it")

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


class ChanceLineConditionsOnTheScoredPairs(unittest.TestCase):
    """A chance line is only subtractable from the mean it was drawn over the pairs of.

    The scan already named the graph and the statistic for each line; it did not name the pair set, and on the
    scored graph that omission meant the baseline came from the complete graph of the covered works while the
    observation came from the scorable subset. These tests hold the three things that keep the two halves of one
    subtraction in one design: that the line is drawn on exactly the pairs the mean was measured on, that the
    older complete-graph line is still published so the gap between them is a reader's to check rather than the
    author's, and that the gap is computed -- not asserted -- to be small against the band it could move.
    """

    @classmethod
    def setUpClass(cls):
        cls.reported = artifact()
        cls.graph = cls.reported["pair_graph"]
        cls.rows = {row["dimension"]: row for row in cls.graph["dimensions"]}
        cls.conditioning = cls.graph["chance_line_conditioning"]

    def test_the_line_is_drawn_over_the_pairs_the_mean_was_measured_on(self):
        config = json.loads((ROOT / "config" / "model_comparison_v3.json").read_text(encoding="utf-8"))
        per_work, _, _ = scan.load_work_states()
        _, _, _, edges_by_key = scan.scorable_graph(per_work, config, scan.cm.cardinality_map(config))
        for key, row in self.rows.items():
            if not row["declared_rule"]["pairs_compared"]:
                continue
            self.assertTrue(row["declared_rule"]["chance_line_conditions_on_the_scored_pairs"])
            self.assertEqual(len(edges_by_key[key]), row["declared_rule"]["pairs_compared"],
                             f"{key}: the null scores a different pair set than the mean it is subtracted from")

    def test_the_carrier_graph_line_is_still_the_complete_graph_one(self):
        for row in self.reported["dimensions"]:
            for reading in scan.READINGS:
                measured = row[reading]
                if measured["chance_similarity_from_own_marginals"] is None:
                    continue
                self.assertFalse(measured["chance_line_conditions_on_the_scored_pairs"])
                self.assertEqual(measured["conditioning_gap"], 0.0,
                                 "the carrier graph's two lines are the same draw, so a nonzero gap means the "
                                 "edges argument reached the population that must not use it")

    def test_the_published_gap_and_the_two_excesses_are_one_subtraction(self):
        for row in self.graph["dimensions"]:
            for reading in scan.READINGS:
                measured = row[reading]
                if measured["excess_over_the_complete_graph_chance"] is None:
                    continue
                self.assertAlmostEqual(measured["excess_over_chance"]
                                       - measured["excess_over_the_complete_graph_chance"],
                                       -measured["conditioning_gap"], places=5,
                                       msg=f"{row['dimension']}/{reading}: the two published excesses are not "
                                           "the same observation against the two published lines")

    def test_the_band_verdicts_that_move_are_recomputed_from_the_published_excesses(self):
        """A guard against the bug this block shipped with once: a chained comparison that never compared.
        """
        changes = []
        for row in self.graph["dimensions"]:
            for reading in scan.READINGS:
                measured = row[reading]
                if measured["excess_over_chance"] is None:
                    continue
                in_band = abs(measured["excess_over_chance"]) < scan.CHANCE_BAND
                if in_band != (abs(measured["excess_over_the_complete_graph_chance"]) < scan.CHANCE_BAND):
                    changes.append(f"{row['dimension']}/{reading}")
        self.assertEqual(changes, sorted(item["dimension"] + "/" + item["reading"]
                                         for item in self.conditioning
                                         ["band_verdicts_that_change_with_the_chance_line"]))
        self.assertEqual(changes, ["D6_temporal_nature/declared_rule", "D6_temporal_nature/value_sets"])

    def test_the_gap_is_small_against_the_band_it_could_move(self):
        per_measurement = self.conditioning["per_measurement"]
        self.assertEqual(len(per_measurement), 18)
        self.assertEqual(self.conditioning["gaps_beyond_half_the_band"], 0)
        largest = max(abs(item["conditioning_gap"]) for item in per_measurement)
        self.assertEqual(largest, abs(self.conditioning["largest_gap"]["conditioning_gap"]))
        self.assertLess(largest, scan.CHANCE_BAND / 2)
        self.assertEqual(self.conditioning["band_verdicts_that_change_with_the_chance_line"],
                         [item for item in per_measurement if item["band_verdict_changes"]])
        self.assertIn("drawn over the pairs the observed mean was measured on",
                      self.conditioning["primary_line"])

    def test_the_null_model_publishes_its_pair_set_and_the_null_it_rejected(self):
        """The two things a reader cannot infer from a number: what the baseline was drawn on, and why not more.

        A co-occurrence-preserving null is the obvious next request, and this repository promised one for two
        rounds of review before measuring it. The measurement is that it cannot be had this way: the resample's
        expectation is the observation. That belongs in the artifact, not only in a reply to a reviewer.
        """
        null = self.reported["null_model"]
        self.assertIn("same pairs", null["pair_set"])
        self.assertIn("scorable subset", null["pair_set"])
        rejected = null["why_not_a_co_occurrence_preserving_permutation"]
        self.assertIn("expectation equal to the observed complete-graph mean", rejected)
        self.assertIn("zero by construction", rejected)
        self.assertIn("drawn over the pair set of the population it is subtracted from",
                      self.reported["what_this_is_not"])

    def test_a_permutation_of_whole_value_sets_reproduces_the_observation_exactly(self):
        """The arithmetic behind `why_not_a_co_occurrence_preserving_permutation`, on a panel small enough to move.

        A mean over every pair of works is a function of the multiset of value sets, not of which work owns
        which, so permuting whole sets between works gives a null whose every replicate is a rearrangement of the
        observation it is supposed to be subtracted from -- an excess of zero by construction, not a small one. On
        the scored graph the same trick is worse than useless: which work owns which set is what decides whether a
        pair is comparable at all, so the permutation does not preserve the pair set it is meant to be a baseline
        for. A panel and two edges stand in for both halves of that claim.
        """
        panel = [{"alpha"}, {"alpha", "beta"}, {"beta"}, {"alpha"}, {"gamma"}]
        edge_subset = [(0, 3), (1, 4)]
        all_edges = list(combinations(range(len(panel)), 2))
        for statistic in ("exact_match", "jaccard"):
            observed = sorted(scan.score(panel[left], panel[right], statistic)
                              for left, right in all_edges)
            reordered = set()
            for order in permutations(range(len(panel))):
                mapped = sorted(scan.score(panel[order[left]], panel[order[right]], statistic)
                                for left, right in all_edges)
                self.assertEqual(mapped, observed,
                                 f"{statistic}: a permutation of the complete graph changed the multiset of pair "
                                 "scores, which would mean the null is not the observation rearranged")
                reordered.add(tuple(sorted(scan.score(panel[order[left]], panel[order[right]], statistic)
                                           for left, right in edge_subset)))
            self.assertGreater(len(reordered), 1,
                               f"{statistic}: on this edge subset a permutation changes nothing either, so the "
                               "case cannot show that the scored graph is a different design")

    def test_the_gate_reads_the_conditioned_line(self):
        self.assertEqual(self.graph["chance_similarity_per_dimension"],
                         {key: row["declared_rule"]["chance_similarity_from_own_marginals"]
                          for key, row in self.rows.items()
                          if row["declared_rule"]["chance_similarity_from_own_marginals"] is not None})
        for item in self.conditioning["per_measurement"]:
            if item["reading"] == "declared_rule":
                self.assertAlmostEqual(self.graph["chance_similarity_per_dimension"][item["dimension"]]
                                       + item["excess_on_the_scored_pairs"],
                                       self.rows[item["dimension"]]["declared_rule"]["observed_mean_similarity"],
                                       places=5)

    def test_an_enumerated_null_reproduces_the_conditioned_line_on_a_tiny_case(self):
        """Every edge's exact expectation, enumerated, against the sampler the scan actually runs.

        This is the only check in the file that does not read the artifact: the conditioned line is a claim about
        code, and the corpus is too large to enumerate, so a four-work case with hand-set marginals stands in for
        it. The same case also shows the two pair sets are genuinely different designs, which a test that only
        compared the line with itself could not.
        """
        probabilities = {"a": 0.5, "b": 0.3, "c": 0.2}
        sizes = [1, 2, 1, 2]
        edges = [(0, 1), (2, 3)]
        distribution = {position: [(frozenset(combo), _subset_weight(combo, probabilities))
                                   for combo in combinations(sorted(probabilities), sizes[position])]
                        for position in range(len(sizes))}
        for draws in distribution.values():
            self.assertAlmostEqual(sum(weight for _, weight in draws), 1.0, places=9)

        def expectation(left, right):
            return sum(weight_left * weight_right * scan.score(first, second, "jaccard")
                       for first, weight_left in distribution[left]
                       for second, weight_right in distribution[right])

        conditioned = sum(expectation(*edge) for edge in edges) / len(edges)
        all_edges = [(left, right) for left, right in combinations(range(len(sizes)), 2)]
        complete = sum(expectation(*edge) for edge in all_edges) / len(all_edges)
        self.assertNotAlmostEqual(conditioned, complete, places=3,
                                  msg="this case cannot tell the two pair sets apart, so it proves nothing")

        drawn = scan.chance_agreement(probabilities, sizes, random.Random(7), "jaccard", 4000, edges)
        self.assertAlmostEqual(drawn, conditioned, places=2,
                               msg="the edge-conditioned null does not converge on the enumerated expectation")
        wandered = scan.chance_agreement(probabilities, sizes, random.Random(7), "jaccard", 4000)
        self.assertAlmostEqual(wandered, complete, places=2,
                               msg="dropping the edges no longer returns the complete-graph draw")
        self.assertGreater(abs(drawn - wandered), abs(drawn - conditioned),
                           "the published line is closer to the complete-graph expectation than to the one "
                           "it was drawn on")


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


class ChanceBandIsMeasuredAgainstItsOwnNull(unittest.TestCase):
    """The 0.05 band is an analyst-set distance, so the scan publishes how often noise alone crosses it.

    A count of dimensions outside a fixed band cannot be read as a count of discoveries until the band's own
    false-positive rate is on the page, and that rate is not one number: it is set by each measurement's null
    width, which spans an order of magnitude across this panel. These tests re-derive the published figures and
    hold the identities that first caught a bug here -- a per-measurement rate that did not sum to the family
    mean it was supposed to explain, because booleans were being counted as a set rather than a tally.
    """

    @classmethod
    def setUpClass(cls):
        cls.reported = artifact()
        cls.section = cls.reported["chance_band_diagnostics"]
        cls.scored = cls.section["scored_graph"]
        cls.carrier = cls.section["carrier_graph"]

    @staticmethod
    def declared_rows(graph):
        return [row for row in graph["per_measurement"] if row["reading"] == "declared_rule"]

    @staticmethod
    def band_row(graph, dimension, reading="declared_rule"):
        return next(row for row in graph["per_measurement"]
                    if row["dimension"] == dimension and row["reading"] == reading)

    def test_the_band_is_sized_on_both_graphs_with_the_published_null(self):
        for graph in (self.scored, self.carrier):
            self.assertEqual(graph["band"], self.reported["null_model"]["band"])
            self.assertEqual(graph["replicates"], self.reported["null_model"]["draws"])
            self.assertEqual(graph["measurements_tested"], len(graph["per_measurement"]))
            self.assertEqual(graph["dimensions_tested"], len({row["dimension"] for row in graph["per_measurement"]}))
        self.assertIn("not a test level", self.section["why_this_is_here"])
        self.assertIn("it sizes the band", self.scored["what_this_does_not_do"])

    def test_the_per_measurement_rates_add_up_to_the_family_figures(self):
        for graph in (self.scored, self.carrier):
            rates = [row["false_positive_rate_at_band"] for row in graph["per_measurement"]]
            self.assertTrue(all(0.0 <= rate <= 1.0 for rate in rates), rates)
            self.assertAlmostEqual(sum(rates), graph["family"]["mean_measurements_exceeding"], places=4,
                                   msg="the rates and the family mean are the same tally divided two ways")
            self.assertGreaterEqual(graph["family"]["any_measurement_exceeds_rate"], max(rates))
            self.assertEqual(graph["family"]["any_dimension_exceeds_rate"],
                             graph["family"]["any_measurement_exceeds_rate"],
                             "a dimension flags exactly when one of its measurements does")
            self.assertLessEqual(graph["family"]["mean_dimensions_exceeding"],
                                 graph["family"]["mean_measurements_exceeding"])
            self.assertEqual(sum(graph["family"]["distribution_of_dimensions_exceeding"].values()),
                             graph["replicates"])

    def test_the_band_is_a_coin_toss_for_one_dimension_and_silent_for_most(self):
        rates = [row["false_positive_rate_at_band"] for row in self.scored["per_measurement"]]
        self.assertEqual(sum(1 for rate in rates if rate == 0.0), 10)
        widest = self.band_row(self.scored, "D2c_worship_exclusivity")
        self.assertEqual(max(rates), widest["false_positive_rate_at_band"])
        self.assertGreater(widest["false_positive_rate_at_band"], 0.5)
        self.assertGreater(widest["null_excess_sd"], self.scored["band"])

    def test_the_null_widths_span_an_order_of_magnitude_across_the_panel(self):
        declared = self.declared_rows(self.scored)
        widest = max(declared, key=lambda row: row["null_excess_sd"])
        narrowest = min(declared, key=lambda row: row["null_excess_sd"])
        self.assertEqual(widest["dimension"], "D2c_worship_exclusivity")
        self.assertEqual(narrowest["dimension"], "D4_cosmic_function")
        self.assertGreater(widest["null_excess_sd"] / narrowest["null_excess_sd"], 10)
        # a band wider than 95% of a measurement's own noise can only under-flag it
        self.assertGreater(sum(1 for row in declared if row["null_excess_p95_abs"] < self.scored["band"]),
                           len(declared) // 2)
        # the widest null's own 95th percentile sits just under its observed excess, so this measurement is
        # being judged a few draws either side of the point where its own noise becomes "unusual"
        self.assertLess(widest["null_excess_p95_abs"], abs(widest["observed_excess"]))
        self.assertLess(abs(widest["null_excess_p95_abs"] - abs(widest["observed_excess"]))
                        / abs(widest["observed_excess"]), 0.03)
        self.assertLess(abs(widest["null_excess_p95_abs"] - abs(widest["observed_excess"]))
                        / abs(widest["observed_excess"]), 0.03)

    def test_the_leave_one_out_excess_is_centred_on_zero_by_construction(self):
        excesses = scan.leave_one_out_excesses([1.0, 2.0, 3.0, 4.0, 100.0])
        self.assertAlmostEqual(sum(excesses), 0.0, places=9)
        self.assertEqual(excesses[-1], 97.5)
        self.assertEqual(scan.leave_one_out_excesses([7.0] * 5), [0.0] * 5)

    def test_the_replicate_means_are_kept_and_still_average_to_the_published_chance_line(self):
        per_work, _, _ = scan.load_work_states()
        probabilities, sizes = scan.value_marginals(per_work, "D4_cosmic_function")
        means = scan.chance_replicate_means(probabilities, sizes, random.Random(scan.CHANCE_SEED),
                                            "exact_match", 20)
        self.assertEqual(len(means), 20)
        self.assertAlmostEqual(scan.chance_agreement(probabilities, sizes, random.Random(scan.CHANCE_SEED),
                                                     "exact_match", 20),
                               sum(means) / len(means), places=12,
                               msg="splitting the replicate means out moved the published chance line")

    def test_no_published_p_is_below_the_floor_this_many_draws_can_report(self):
        family = self.scored["family"]
        self.assertEqual(family["smallest_resolvable_monte_carlo_p"],
                         round(1 / (scan.CHANCE_REPETITIONS + 1), 8))
        for graph in (self.scored, self.carrier):
            for row in graph["per_measurement"]:
                reported_p = row["monte_carlo_p_two_sided"]
                if reported_p is None:
                    self.assertIsNone(row["observed_excess"])
                    continue
                self.assertLessEqual(reported_p, 1.0)
                scaled = reported_p * (graph["replicates"] + 1)
                self.assertLess(abs(scaled - round(scaled)), 1e-3,
                                f"{row['dimension']}/{row['reading']}: p={reported_p} is not a count over "
                                f"{graph['replicates'] + 1} draws")
                self.assertGreaterEqual(reported_p,
                                        round(graph["family"]["smallest_resolvable_monte_carlo_p"], 6),
                                        f"{row['dimension']}/{row['reading']}: p below the floor that "
                                        f"{graph['replicates']} draws can report")

    def test_the_band_and_the_null_scatter_disagree_on_three_scored_dimensions(self):
        """All three disagreements now point one way: inside the band, yet clear of their own null.

        ``D2c_worship_exclusivity`` used to be the counter-example --- anomalous on the band, unremarkable on its
        own draws. Conditioning the line on the scored pairs moved its excess by 0.004 and its Monte Carlo p by
        more than a factor of four, which on a measurement whose band false-positive rate is 0.555 settles
        nothing. ``D6_temporal_nature`` took the opposite journey and now sits inside the band while still
        clearing its null, which is the case finding (7) of the paper has to describe.
        """
        disagreements = sorted(row["dimension"] for row in self.declared_rows(self.scored)
                               if row["monte_carlo_p_two_sided"] is not None
                               and bool(row["observed_outside_band"]) != (row["monte_carlo_p_two_sided"] <= 0.05))
        self.assertEqual(disagreements, ["D2a_acknowledged_population", "D2b_reality_of_others",
                                         "D6_temporal_nature"])
        for dimension in disagreements:
            row = self.band_row(self.scored, dimension)
            self.assertFalse(row["observed_outside_band"], f"{dimension} is inside the band")
            self.assertLessEqual(row["monte_carlo_p_two_sided"], 0.05, f"{dimension} clears its own null")
        row = self.band_row(self.scored, "D2c_worship_exclusivity")
        self.assertTrue(row["observed_outside_band"])
        self.assertLessEqual(row["monte_carlo_p_two_sided"], 0.05,
                             "the one measurement the band used to over-call now agrees with it, which is the "
                             "instability this class exists to publish rather than hide")

    def test_the_bonferroni_survivors_are_recomputed_from_the_published_p_values(self):
        family = self.scored["family"]
        declared = self.declared_rows(self.scored)
        self.assertEqual(family["declared_rule_panel_size"], len(declared))
        alpha = family["bonferroni_alpha_for_the_declared_rule_panel"]
        self.assertEqual(alpha, round(0.05 / len(declared), 8))
        self.assertEqual(family["dimensions_surviving_bonferroni"],
                         sorted(row["dimension"] for row in declared
                                if row["monte_carlo_p_two_sided"] is not None
                                and row["monte_carlo_p_two_sided"] <= alpha))
        self.assertEqual(len(family["dimensions_surviving_bonferroni"]), 6)
        for row in declared:
            if row["dimension"] in family["dimensions_surviving_bonferroni"]:
                self.assertAlmostEqual(row["monte_carlo_p_two_sided"],
                                       family["smallest_resolvable_monte_carlo_p"], places=5,
                                       msg=f"{row['dimension']} survives at a p the panel did not resolve to")
        self.assertEqual(family["dimensions_surviving_bonferroni"],
                         self.carrier["family"]["dimensions_surviving_bonferroni"])

    def test_the_band_diagnostics_describe_the_measurements_the_dimension_table_published(self):
        scored_by_key = {(row["dimension"], row["reading"]): row for row in self.scored["per_measurement"]}
        checked = 0
        for row in self.reported["pair_graph"]["dimensions"]:
            for reading in scan.READINGS:
                measured = row[reading]
                if not measured["pairs_compared"]:
                    continue
                band_row = scored_by_key[(row["dimension"], reading)]
                checked += 1
                self.assertEqual(band_row["pairs_in_this_population"], measured["pairs_compared"])
                self.assertEqual(band_row["observed_excess"], measured["excess_over_chance"])
                self.assertEqual(band_row["observed_outside_band"], not measured["excess_within_declared_chance_band"])
        self.assertEqual(checked, self.scored["measurements_tested"])
        for reading in scan.READINGS:
            self.assertEqual(self.scored["observed_measurements_outside_band"][reading],
                             sum(1 for row in self.scored["per_measurement"]
                                 if row["reading"] == reading and row["observed_outside_band"]))


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
        conditioning = self.graph["chance_line_conditioning"]
        band = self.reported["chance_band_diagnostics"]["scored_graph"]
        self.assert_quoted(f"drawn over its own \\({self.graph['pairs_scorable']}\\) pairs rather than over every "
                           f"pair of the \\({self.graph['works_covered']}\\) works")
        self.assert_quoted(f"Conditioning moves no chance line by more than "
                           f"\\({abs(conditioning['largest_gap']['conditioning_gap']):.4f}\\)")
        self.assert_quoted(f"and changes \\({len(conditioning['band_verdicts_that_change_with_the_chance_line'])}\\) "
                           f"of the \\({band['measurements_tested']}\\) band verdicts")
        dropped = "declared_rule_chance_corrected_dropping_the_band_keys"
        gaps = []
        for blocks in (self.reported["blocks"], self.graph["blocks"]):
            gaps.append(adjacent_by_pair(blocks["verdicts"][dropped]["adjacent_predictions"],
                                        "structural", "arbitrary_or_expressive")["observed_difference"])
        self.assert_quoted(f"a \\emph{{tie}} on both graphs (\\({gaps[0]:.3f}\\) carrier, \\({gaps[1]:.3f}\\) scored)")
        self.assertEqual(self.graph["adjacency_verdicts_that_change_with_the_graph"], {},
                         "the paper says no adjacency moves with the graph, so this phrase has to go back "
                         "into finding (4)")

    def test_the_abstract_and_the_conclusion_quote_the_same_excess_as_the_table(self):
        """Two sentences outside the anomaly section restate one figure from it, so they are copies too.

        The audit caught the abstract still saying +0.009 after the conditioning moved the quantity to +0.006.
        Nothing about that number is specific to the anomaly subsection, so pinning only the subsection leaves the
        rest of the paper free to drift.
        """
        excess = self.scored["D7a_speaker_attribution"]["declared_rule"]["excess_over_chance"]
        quoted = rf"own base rate by \({excess:+.3f}\)"
        self.assertEqual(self.tex.count(quoted), 2,
                         f"the abstract and the conclusion should both read D7a's excess ({excess}) out of the "
                         f"artifact; the paper contains {self.tex.count(quoted)} such sentences")

    def test_the_chance_band_paragraph_quotes_the_band_diagnostics(self):
        band = self.reported["chance_band_diagnostics"]["scored_graph"]
        family = band["family"]
        rates = [row["false_positive_rate_at_band"] for row in band["per_measurement"]]
        d2c = next(row for row in band["per_measurement"] if row["dimension"] == "D2c_worship_exclusivity"
                   and row["reading"] == "declared_rule")
        d4 = next(row for row in band["per_measurement"] if row["dimension"] == "D4_cosmic_function"
                  and row["reading"] == "declared_rule")
        d2a = next(row for row in band["per_measurement"] if row["dimension"] == "D2a_acknowledged_population"
                   and row["reading"] == "declared_rule")
        d2b = next(row for row in band["per_measurement"] if row["dimension"] == "D2b_reality_of_others"
                   and row["reading"] == "declared_rule")
        d6 = next(row for row in band["per_measurement"] if row["dimension"] == "D6_temporal_nature"
                  and row["reading"] == "declared_rule")
        self.assert_quoted(f"\\(0.000\\) --- \\({sum(1 for rate in rates if rate == 0.0)}\\) of the "
                           f"\\({len(rates)}\\) measurements never leave it --- to "
                           f"\\({d2c['false_positive_rate_at_band']:.3f}\\) on")
        self.assert_quoted(f"standard deviation of \\({d2c['null_excess_sd']:.4f}\\)")
        self.assert_quoted(f"wanders by \\({d4['null_excess_sd']:.4f}\\)")
        self.assert_quoted(f"outside the band in \\({family['any_measurement_exceeds_rate']:.3f}\\) of draws, "
                           f"a mean of \\({family['mean_measurements_exceeding']:.2f}\\) measurements")
        self.assert_quoted(f"The same graph flags \\({band['observed_measurements_outside_band']['declared_rule']}\\) "
                           f"of its \\({band['dimensions_tested']}\\) live dimensions on the declared statistic "
                           f"against a noise-only expectation of \\({family['mean_dimensions_exceeding']:.2f}\\)")
        self.assert_quoted(f"\\dimkey{{{escape(d2a['dimension'])}}} (\\({d2a['observed_excess']:+.3f}\\)) and")
        self.assert_quoted(f"\\dimkey{{{escape(d2b['dimension'])}}} (\\({d2b['observed_excess']:+.3f}\\)) sit")
        self.assert_quoted(f"those two dimensions wander by only \\({d2a['null_excess_sd']:.4f}\\) and "
                           f"\\({d2b['null_excess_sd']:.4f}\\)")
        self.assert_quoted(f"\\dimkey{{{escape(d6['dimension'])}}} (\\({d6['observed_excess']:+.3f}\\)) joins "
                           f"them inside the band by two thousandths")
        self.assert_quoted(f"at the floor of its own null")
        self.assert_quoted(f"calls anomalous at \\({d2c['observed_excess']:+.3f}\\), now clears it "
                           f"(\\(p = {d2c['monte_carlo_p_two_sided']:.3f}\\))")
        self.assert_quoted(f"whose \\(p\\) is \\({round(d2c['monte_carlo_p_two_sided'] * (band['replicates'] + 1)):d}\\) "
                           f"draws in \\({band['replicates'] + 1}\\)")
        survivors = ", ".join(rf"\dimkey{{{escape(name)}}}" for name in family["dimensions_surviving_bonferroni"])
        self.assert_quoted(f"Six dimensions --- {survivors} --- survive a Bonferroni cut")
        self.assert_quoted(f"at \\(0.05/{family['declared_rule_panel_size']} = "
                           f"{family['bonferroni_alpha_for_the_declared_rule_panel']:.6f}\\)")
        self.assert_quoted(f"this many draws can report (\\(p = 1/{band['replicates'] + 1} = "
                           f"{family['smallest_resolvable_monte_carlo_p']:.6f}\\)")

    def test_the_paper_does_not_call_the_band_a_test_level(self):
        band = self.reported["chance_band_diagnostics"]["scored_graph"]
        self.assert_quoted(r"\textbf{(7) The chance band is not a test level")
        self.assertIn(r"\textbf{Seven findings", self.tex)
        self.assertNotIn(r"\textbf{Six findings", self.tex)
        self.assertEqual(band["band"], self.reported["null_model"]["band"])

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
