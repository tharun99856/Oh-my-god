"""Unit tests for the structural narrative-similarity engine.

These target the places where the arithmetic can be silently wrong and still produce a
plausible-looking number: the alignment traceback, gap versus mismatch behaviour, motif
absence semantics, referent-based role matching, and the promise that no composite exists.
"""
import itertools
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from narrative_similarity import (  # noqa: E402
    align_matrix,
    assessed_motifs,
    causal_component,
    compare_versions,
    event_similarity,
    load_context,
    matched_participant_score,
    motif_components,
    permutation_test,
    unrestricted_sequence_score,
)


def part(role, term, referent, kind):
    return {"role": role, "term": term, "referent": referent, "referent_kind": kind}


def narr(event_id, predicate, participants, outcome=""):
    return {"event_id": event_id, "order": 0, "predicate": predicate,
            "participants": participants, "outcome": outcome,
            "evidence_passage": "synthetic:s0000:p000", "quote": "whatever"}


def version(motifs, comparison_class=None, completeness="full", events=(), links=()):
    return {"version_id": "synthetic", "work_id": "synthetic", "region": "Nowhere",
            "comparison_class": comparison_class, "attestation_completeness": completeness,
            "events": list(events), "causal_links": list(links), "motifs": motifs, "symbols": []}


def motif(motif_id, count):
    return {"motif_id": motif_id, "count": count}


REGISTRY = {"M1": {"weight": 0.5, "label": "one motif"}, "M2": {"weight": 0.5, "label": "two motif"},
            "M3": {"weight": 1.0, "label": "three motif"}}
CHECKLISTS = {"class_a": ["M1", "M2"], "class_b": ["M3"]}


class AlignmentTests(unittest.TestCase):
    def test_perfect_diagonal_alignment_scores_one_and_reports_no_gaps(self):
        score, distance, pairs = align_matrix(np.eye(3), 1.0)
        self.assertAlmostEqual(score, 1.0)
        self.assertAlmostEqual(distance, 0.0)
        self.assertEqual([(a, b) for a, b, _ in pairs if a is not None and b is not None],
                         [(0, 0), (1, 1), (2, 2)])

    def test_traceback_replays_the_dp_cost_and_stays_monotone(self):
        rng = np.random.default_rng(7)
        for _ in range(40):
            rows = int(rng.integers(1, 8))
            columns = int(rng.integers(1, 8))
            similarity = np.round(rng.random((rows, columns)), 3)
            gap = float(rng.choice([0.5, 1.0, 1.5]))
            score, distance, pairs = align_matrix(similarity, gap)
            used_rows = [a for a, b, _ in pairs if a is not None]
            used_columns = [b for a, b, _ in pairs if b is not None]
            self.assertEqual(len(used_rows), len(set(used_rows)), "row consumed twice")
            self.assertEqual(len(used_columns), len(set(used_columns)), "column consumed twice")
            self.assertEqual(used_rows, sorted(used_rows), "traceback crossed")
            self.assertEqual(used_columns, sorted(used_columns), "traceback crossed")
            self.assertEqual(len(used_rows), rows)
            self.assertEqual(len(used_columns), columns)
            matched = sum(1 for a, b, _ in pairs if a is not None and b is not None)
            self.assertEqual(len(pairs), rows + columns - matched)
            replayed = sum(1.0 - value for a, b, value in pairs if a is not None and b is not None)
            replayed += gap * sum(1 for a, b, _ in pairs if a is None or b is None)
            self.assertAlmostEqual(replayed, distance, places=9)
            self.assertAlmostEqual(score, max(0.0, min(1.0, 1.0 - distance / max(rows, columns))))

    def test_dp_matches_a_brute_force_search_over_monotone_alignments(self):
        """The DP is the whole engine, so it is checked against enumeration rather than against a
        property I assumed: every order-preserving matching, including the ones that leave several
        events unpaired, is priced explicitly."""
        rng = np.random.default_rng(11)

        def brute_force(similarity, gap):
            rows, columns = similarity.shape
            best = np.inf
            for size in range(min(rows, columns) + 1):
                for used_rows in itertools.combinations(range(rows), size):
                    for used_columns in itertools.combinations(range(columns), size):
                        cost = sum(1.0 - similarity[r, c] for r, c in zip(used_rows, used_columns))
                        cost += gap * (rows + columns - 2 * size)
                        best = min(best, cost)
            return best

        for _ in range(12):
            similarity = np.round(rng.random((4, 4)), 2)
            for gap in (0.5, 1.0, 1.5):
                _, distance, _ = align_matrix(similarity, gap)
                self.assertAlmostEqual(distance, brute_force(similarity, gap), places=9)

    def test_gap_larger_than_a_mismatch_makes_the_model_pair_every_event(self):
        """With g = 1 a mismatch is never more expensive than gapping both events, so the DP keeps
        pairing aggressively; that is why the score is only weakly sensitive to event order. Raising
        g is what restores a real preference for leaving events unpaired."""
        rng = np.random.default_rng(13)
        for _ in range(30):
            similarity = np.round(rng.random((int(rng.integers(2, 7)), int(rng.integers(2, 7)))), 2)
            _, _, pairs = align_matrix(similarity, 2.0)
            matched = sum(1 for a, b, _ in pairs if a is not None and b is not None)
            self.assertEqual(matched, min(similarity.shape))

    def test_cheaper_gap_lets_the_model_decline_a_bad_match(self):
        unrelated = np.zeros((2, 2))
        strict_score, _, strict_pairs = align_matrix(unrelated, 1.0)
        lenient_score, _, lenient_pairs = align_matrix(unrelated, 0.25)
        self.assertEqual(sum(1 for a, b, _ in strict_pairs if a is not None and b is not None), 2)
        self.assertEqual(sum(1 for a, b, _ in lenient_pairs if a is not None and b is not None), 0)
        self.assertGreater(lenient_score, strict_score)

    def test_reversed_event_order_costs_score(self):
        in_order, _, _ = align_matrix(np.eye(3), 1.0)
        reversed_order, _, _ = align_matrix(np.fliplr(np.eye(3)), 1.0)
        self.assertAlmostEqual(in_order, 1.0)
        self.assertAlmostEqual(reversed_order, 1.0 - 2.0 / 3.0)

    def test_order_constraint_loss_is_the_crossing_relaxation_minus_the_monotone_optimum(self):
        """The two best event pairs here cross, so an order-preserving alignment can take only one
        of them. The relaxation takes both, and the difference is exactly the price of order."""
        similarity = np.array([[0.9, 1.0], [1.0, 0.9]])
        monotone, _, _ = align_matrix(similarity, 1.0)
        relaxed = unrestricted_sequence_score(similarity, 1.0)
        self.assertAlmostEqual(monotone, 0.9)
        self.assertAlmostEqual(relaxed, 1.0)

    def test_relaxation_is_never_below_the_monotone_optimum(self):
        rng = np.random.default_rng(3)
        for _ in range(30):
            similarity = rng.random((int(rng.integers(1, 7)), int(rng.integers(1, 7))))
            monotone, _, _ = align_matrix(similarity, 1.0)
            relaxed = unrestricted_sequence_score(similarity, 1.0)
            self.assertGreaterEqual(relaxed + 1e-12, monotone)

    def test_permutation_p_value_is_reported_and_bounded(self):
        rng = np.random.default_rng(5)
        observed, p_value, null_mean = permutation_test(np.eye(4), 1.0, 60, rng)
        self.assertAlmostEqual(observed, 1.0)
        self.assertLessEqual(p_value, 1.0)
        self.assertGreaterEqual(p_value, 1.0 / 61.0)
        self.assertLessEqual(null_mean, observed)


class EventSimilarityTests(unittest.TestCase):
    def setUp(self):
        self.context = load_context()
        self.weights = self.context["weights"]

    def similarity(self, left, right):
        return event_similarity(left, right, self.context["family_of"], self.weights)

    def test_identical_event_scores_one(self):
        event = narr("e1", "divine_flood_sent", [part("agent", "Yahweh", "god_yahweh", "deity")],
                     "waters cover the earth")
        self.assertAlmostEqual(self.similarity(event, event), 1.0)

    def test_same_predicate_family_is_credited_partly(self):
        families = self.context["manual"]["predicate_families"]
        family = next(name for name, members in families.items() if len(members) >= 2)
        first, second = sorted(families[family])[0], sorted(families[family])[1]
        left = narr("e1", first, [part("agent", "a", "x", "deity")])
        right = narr("e2", second, [part("agent", "a", "x", "deity")])
        score = self.similarity(left, right)
        exact = self.similarity(left, left)
        self.assertLess(score, exact)
        self.assertGreater(score, 0.0)

    def test_unknown_predicate_is_not_a_mismatch_by_default(self):
        """A predicate outside the manual must not be silently scored as zero similarity against
        itself; it should still be an exact match, which keeps transcription drift visible."""
        left = narr("e1", "predicate_absent_from_manual", [part("agent", "a", "x", "deity")], "the world ends")
        self.assertAlmostEqual(self.similarity(left, left), 1.0)

    def test_missing_outcome_is_unmeasured_rather_than_maximally_different(self):
        """Both sides leaving the outcome uncoded must not cap an otherwise identical event below 1;
        one side coding an outcome the other omits still counts as a coding difference."""
        coded = narr("e1", "divine_flood_sent", [part("agent", "X", "deity_x", "deity")], "waters rise")
        blank = narr("e2", "divine_flood_sent", [part("agent", "X", "deity_x", "deity")], "")
        self.assertAlmostEqual(self.similarity(coded, coded), 1.0)
        self.assertAlmostEqual(self.similarity(blank, blank), 1.0)
        self.assertLess(self.similarity(coded, blank), self.similarity(coded, coded))

    def test_renaming_participants_does_not_move_event_similarity(self):
        left = narr("e1", "monster_slain",
                    [part("agent", "Marduk", "storm_god_marduk", "deity"),
                     part("patient", "Tiamat", "sea_monster_tiamat", "monster")], "order from chaos")
        right = narr("e2", "monster_slain",
                     [part("agent", "Bel", "storm_god_marduk", "deity"),
                      part("patient", "the Dragon", "sea_monster_tiamat", "monster")], "order from chaos")
        self.assertAlmostEqual(self.similarity(left, right), 1.0)
        self.assertAlmostEqual(self.similarity(left, left), 1.0)


class ParticipantMatchingTests(unittest.TestCase):
    def setUp(self):
        self.credits = load_context()["weights"]["participant_pair_credit"]

    def score(self, left, right):
        return matched_participant_score(left, right, self.credits)

    def test_shared_referent_with_different_surface_names_is_full_credit(self):
        got = self.score([part("agent", "Indra", "storm_god_indra", "deity")],
                         [part("agent", "the Thunderer", "storm_god_indra", "deity")])
        self.assertAlmostEqual(got, 1.0)

    def test_different_referents_are_not_merged_by_a_shared_label(self):
        got = self.score([part("agent", "Thor", "storm_god_thor", "deity")],
                         [part("agent", "Thor", "storm_god_indra", "deity")])
        self.assertAlmostEqual(got, 0.5)

    def test_same_name_different_kind_does_not_leak_identity(self):
        """String equality of a translator's word must never be treated as narrative identity."""
        got = self.score([part("agent", "the eagle", "bird", "animal")],
                         [part("agent", "the eagle", "eagle", "animal")])
        self.assertAlmostEqual(got, 0.5)

    def test_role_mismatch_overrides_shared_referent(self):
        got = self.score([part("agent", "X", "shared", "deity")], [part("patient", "X", "shared", "deity")])
        self.assertAlmostEqual(got, 0.0)

    def test_normalisation_uses_the_larger_participant_set(self):
        shared = part("agent", "X", "flood_hero", "human")
        got = self.score([shared], [shared, part("patient", "Y", "dove", "animal"),
                                    part("instrument", "Z", "ark", "object")])
        self.assertAlmostEqual(got, 1.0 / 3.0)

    def test_empty_participant_sets_are_reported_as_unmeasurable(self):
        self.assertIsNone(self.score([], []))


class MotifSemanticsTests(unittest.TestCase):
    def compare(self, left, right):
        return motif_components(left, right, REGISTRY, 1.0, CHECKLISTS)

    def test_checklist_zero_counts_as_an_adjudicated_absence(self):
        left = version([motif("M1", 1), motif("M2", 1)], "class_a")
        right = version([motif("M1", 1), motif("M2", 0)], "class_a")
        score, matched, domain, matched_ids = self.compare(left, right)
        self.assertEqual(domain, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(matched_ids, ["M1"])
        self.assertAlmostEqual(score, 0.5)

    def test_partial_attestation_turns_absence_into_unassessed_not_zero(self):
        left = version([motif("M1", 1), motif("M2", 1)], "class_a")
        partial = version([motif("M1", 1)], "class_a", completeness="partial")
        score, matched, domain, _ = self.compare(left, partial)
        self.assertEqual(domain, 1, "a motif the fragmentary witness never reached must drop out")
        self.assertEqual(matched, 1)
        self.assertAlmostEqual(score, 1.0)

    def test_asserted_motif_outside_the_checklist_still_counts_when_present(self):
        left = version([motif("M3", 1)], "class_a")
        right = version([motif("M3", 1)], "class_b")
        score, _, domain, _ = self.compare(left, right)
        self.assertEqual(domain, 1)
        self.assertAlmostEqual(score, 1.0)

    def test_no_shared_assessed_domain_is_undecided(self):
        left = version([motif("M1", 1), motif("M2", 1)], "class_a")
        right = version([motif("M3", 1)], "class_b")
        score, matched, domain, matched_ids = self.compare(left, right)
        self.assertIsNone(score)
        self.assertEqual((matched, domain, matched_ids), (0, 0, []))

    def test_repetition_is_damped_rather_than_double_counted(self):
        left = version([motif("M1", 3), motif("M2", 1)], "class_a")
        right = version([motif("M1", 1), motif("M2", 1)], "class_a")
        score, _, _, _ = self.compare(left, right)
        self.assertAlmostEqual(score, (0.5 * 1 + 0.5 * 1) / (0.5 * 3 + 0.5 * 1))

    def test_assessed_domain_size_grows_with_the_checklist(self):
        full = version([motif("M1", 1)], "class_a")
        self.assertEqual(set(assessed_motifs(full, CHECKLISTS)), {"M1", "M2"})
        self.assertEqual(set(assessed_motifs(version([motif("M1", 1)], None), CHECKLISTS)), {"M1"})


class CausalAndContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = load_context()
        cls.versions = cls.context["versions"]

    def pair(self, left_id, right_id):
        return compare_versions(self.versions[left_id], self.versions[right_id], self.context,
                                np.random.default_rng(self.context["weights"]["seed"]))

    def test_causal_component_needs_edges_on_both_sides(self):
        family_of = self.context["family_of"]
        empty = version([], None, events=[narr("e1", "monster_slain", [])])
        filled = version([], None, events=[narr("e1", "monster_slain", []), narr("e2", "world_created", [])],
                         links=[("e1", "e2")])
        self.assertIsNone(causal_component(empty, filled, family_of)[0])
        self.assertIsNone(causal_component(filled, empty, family_of)[0])

    def test_dependent_witness_control_anchors_the_scale(self):
        """The Manu doublet is the same narrative copied between books of one work, so the sequence
        component must reach its ceiling. If this fails the alignment is broken, not the history."""
        row = self.pair("manu_fish_mahabharata", "manu_fish_doublet")
        self.assertAlmostEqual(row["component_vector"]["S_sequence"], 1.0)
        self.assertEqual(row["aligned_event_pairs"], 9)
        self.assertEqual(row["alignment_gaps"], 0)
        self.assertEqual(row["witnesses_not_marked_dependent"], False)

    def test_engine_emits_no_composite_and_no_historical_claim(self):
        for left_id, right_id in [("noah_kjv", "manu_fish_mahabharata"), ("thor_fishing", "indra_vritra_allusive")]:
            row = self.pair(left_id, right_id)
            self.assertIsNone(row["composite_score"])
            self.assertIsNone(row["historical_claim"])
            self.assertNotIn("composite", row["component_vector"])
            self.assertEqual(len(row["component_vector"]), 5)

    def test_cross_comparison_class_pair_reports_motif_as_und_not_zero(self):
        row = self.pair("noah_kjv", "marduk_tiamat")
        self.assertIsNone(row["component_vector"]["S_motif"])
        self.assertEqual(row["motif_domain"], 0)
        self.assertEqual(row["motif_comparison_class"], ["flood_survival", "storm_and_monster_combat"])

    def test_dependent_witnesses_outrank_predicted_unrelated_negatives(self):
        positives = [self.pair("manu_fish_mahabharata", "manu_fish_doublet"),
                     self.pair("taliesin_mabinogion", "taliesin_celtic_myths")]
        negatives = [self.pair("noah_kjv", "pangu_body"), self.pair("popol_vuh_wooden_people", "ymir_body"),
                     self.pair("zeus_typhoeus", "pangu_body")]
        for positive in positives:
            for negative in negatives:
                self.assertGreater(positive["component_vector"]["S_sequence"],
                                   negative["component_vector"]["S_sequence"])

    def test_published_results_are_not_stale_relative_to_the_annotations(self):
        """Same freshness guard validate_results_v2.py applies to the lexical chain: a re-annotated
        file must not be reported as though the published component vectors still came from it."""
        import hashlib
        import json

        summary_path = ROOT / "results/narrative_run_summary.json"
        if not summary_path.exists():
            self.skipTest("the engine has not been run yet")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["reproducibility"]["annotations_sha256"],
                         hashlib.sha256((ROOT / "config/annotated_versions.json").read_bytes()).hexdigest())
        self.assertEqual(summary["reproducibility"]["code_sha256"],
                         hashlib.sha256((ROOT / "tools/narrative_similarity.py").read_bytes()).hexdigest())
        self.assertEqual(summary["versions"], len(self.versions))
        self.assertEqual(summary["alignment_weights"]["gap_penalty"], self.context["weights"]["gap_penalty"])


class PublishedVocabularyTests(unittest.TestCase):
    """The published artefacts must not use a stronger word than the evidence supports. These assertions
    exist because an audit found 'independent' and 'RESEMBLES' doing work the dependence rules cannot do."""

    def setUp(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        pairs_path = root / "results/narrative_component_pairs.jsonl"
        validation_path = root / "results/narrative_validation.json"
        graph_path = root / "results/v2_relevance_graph.json"
        if not pairs_path.exists() or not validation_path.exists() or not graph_path.exists():
            self.skipTest("the engine or graph has not been run yet")
        self.rows = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()]
        self.validation = json.loads(validation_path.read_text(encoding="utf-8"))
        self.graph = json.loads(graph_path.read_text(encoding="utf-8"))

    def test_unmarked_pairs_are_not_called_independent(self):
        for row in self.rows:
            self.assertIn("witnesses_not_marked_dependent", row)
            self.assertNotIn("independent_witnesses", row)
            self.assertIn("independence_basis", row)
            if row["witnesses_not_marked_dependent"]:
                self.assertIn("not a positive independence judgement", row["independence_basis"])

    def test_structural_edges_are_comparisons_rather_than_verdicts(self):
        layers = {layer["name"]: layer for layer in self.graph["layers"]}
        structure = layers["narrative_structure"]
        self.assertEqual(structure["edge_kind"], "COMPARED_WITH")
        self.assertIn("RESEMBLES", structure["explicitly_not"])
        self.assertIn("resemblance_promotion_criterion", structure)
        for name, layer in layers.items():
            self.assertNotIn("RESEMBLES", {edge.get("edge_kind") for edge in layer["edges"]},
                             f"{name} asserts resemblance without a reviewed promotion decision")

    def test_each_comparison_carries_its_own_semantic_guard(self):
        """An edge lifted out of the layer must still state what it is not, and the builder must not be able
        to synthesise the reviewer decision that promotion requires."""
        structure = {layer["name"]: layer for layer in self.graph["layers"]}["narrative_structure"]
        for edge in structure["edges"]:
            self.assertIn("RESEMBLES", edge["explicitly_not"])
            criteria = edge["resemblance_admission"]["criteria"]
            self.assertFalse(edge["resemblance_admission"]["promoted"])
            for name in ("witnesses_independently_attested", "shared_comparison_class",
                         "above_zero_components_on_assessed_domains"):
                self.assertIsInstance(criteria[name], bool)
            for name in ("survives_parameter_sweeps", "reviewer_decision_recorded"):
                self.assertIsNone(criteria[name])
        # Promotion is unreachable in this build: no configured dependence rule asserts independence, so
        # criterion (a) cannot be satisfied by any edge.
        self.assertFalse([edge for edge in structure["edges"]
                          if edge["resemblance_admission"]["criteria"]["witnesses_independently_attested"]])

    def test_correlation_is_reported_as_exploratory_with_a_label_permutation_test(self):
        block = self.validation["structural_vs_lexical"]
        self.assertEqual(block["status"], "exploratory")
        self.assertIn("not admissible", block["independence_p_value_status"])
        qap = block["quadratic_assignment_test"]
        self.assertIsNotNone(qap, "the non-independence of pair observations must be addressed, not assumed away")
        self.assertGreaterEqual(qap["permutation_draws_used"], 50)
        self.assertEqual(qap["versions_permuted"], self.validation["counts"]["versions"])
        expected = round((1 + qap["extreme_draws"]) / (qap["permutation_draws_used"] + 1), 6)
        self.assertEqual(qap["two_tailed_p_value"], expected, "the p-value formula must match the reported counts")

    def test_rank_sensitivity_states_its_scale_and_reports_tau(self):
        variants = self.validation["sensitivity_analysis"]["variants"]
        self.assertGreaterEqual(len(variants), 8)
        for name, variant in variants.items():
            self.assertIn("scale", variant, name)
            self.assertIn("kendall_tau", variant, name)
            self.assertLessEqual(variant["mean_absolute_rank_shift"], 1.0, name)
            if variant["kendall_tau"] is not None:
                self.assertGreaterEqual(variant["kendall_tau"], -1.0, name)
                self.assertLessEqual(variant["kendall_tau"], 1.0, name)
        self.assertLess(variants["gap_penalty_1.0"]["mean_absolute_rank_shift"], 0.01,
                        "the published configuration must reproduce its own ordering")


if __name__ == "__main__":
    unittest.main()
