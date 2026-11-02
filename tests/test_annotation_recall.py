"""Tests for the weighted detector-recall estimator added to tools/score_annotation.py.

The reviewer's point was structural, not numerical: a packet whose rows are all
propositions the machine already flagged can measure precision and cannot measure
recall, because a sample of hits contains no misses. These tests pin the fix -- the
Horvitz-Thompson arithmetic, the refusal to run without weights, and the two rules
that keep the two estimands from leaking into each other.

They run against synthetic sheets written to a temporary directory. No human coding
exists, so every agreement figure here is a property of the scorer, not a claim about
coders. The scorer refuses to write the canonical reliability artifact from these
fixtures, and the tests always point --out at their own temporary file.
"""

import contextlib
import csv
import gzip
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import score_annotation as sa  # noqa: E402
from prepare_annotation_packet import (  # noqa: E402
    PROBE_ROLES, REFERENT_COLUMN, UNIT_COLUMN, coding_columns, column_cardinalities)

COLUMNS = coding_columns()
D4 = "D4_cosmic_function"          # set-valued
D2A = "D2a_acknowledged_population"  # single-valued
FIELDNAMES = ["token", "proposition_text", "context_window_text", REFERENT_COLUMN, UNIT_COLUMN,
              *COLUMNS.values(), *sa.QUESTION_COLUMNS]


def blank_row(token, **answers):
    row = {"token": token, "proposition_text": "sample text", "context_window_text": "sample window",
           REFERENT_COLUMN: "", UNIT_COLUMN: ""}
    for column in COLUMNS.values():
        row[column] = ""
    for column in sa.QUESTION_COLUMNS:
        row[column] = ""
    row.update(answers)
    return row


def mundane(token):
    """A probe row both readers code as carrying no divine proposition."""
    return blank_row(token, **{UNIT_COLUMN: "not_a_divine_proposition"})


def candidate_key(token, values_by_dimension, probability):
    return {"token": token, "sample_role": "machine_candidate", "stratum_population": None,
            "inclusion_probability": probability, "sampling_weight": round(1 / probability, 4),
            "machine_values_by_dimension": values_by_dimension}


def probe_key(token, role=PROBE_ROLES[0], population=1000, sampled=10):
    probability = sampled / population
    return {"token": token, "sample_role": role, "stratum_population": population,
            "inclusion_probability": round(probability, 12),
            "sampling_weight": round(1 / probability, 4), "machine_values_by_dimension": {}}


def attestation(work, passage, start, dimension, value):
    return {"work_id": work, "passage_id": passage, "proposition_char_start": start,
            "dimension": dimension, "value": value}


class Harness(unittest.TestCase):
    """Writes a packet, a key and a detector output, then runs the scorer over them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows_a, rows_b, keys, attestations):
        for name, rows in (("a.csv", rows_a), ("b.csv", rows_b)):
            with (self.dir / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row.get(field, "") for field in FIELDNAMES})
        with (self.dir / "key.jsonl").open("w", encoding="utf-8") as handle:
            for record in keys:
                handle.write(json.dumps(record) + "\n")
        with gzip.open(self.dir / "attestations.jsonl.gz", "wt", encoding="utf-8") as handle:
            for record in attestations:
                handle.write(json.dumps(record) + "\n")

    def run_scorer(self, rows_a, rows_b, keys, attestations, same_file=False):
        self.write(rows_a, rows_b, keys, attestations)
        sheet_b = str(self.dir / "a.csv") if same_file else str(self.dir / "b.csv")
        out = self.dir / "reliability.json"
        argv = ["score_annotation.py", "--coder-a", str(self.dir / "a.csv"), "--coder-b", sheet_b,
                "--key", str(self.dir / "key.jsonl"), "--attestations", str(self.dir / "attestations.jsonl.gz"),
                "--out", str(out)]
        stdout = io.StringIO()
        previous, self.stdout = sys.argv, ""
        with contextlib.redirect_stdout(stdout):
            sys.argv = argv
            try:
                sa.main()
            except SystemExit as error:
                self.message = str(error)
                sys.argv = previous
                return None
            sys.argv = previous
        self.stdout = stdout.getvalue()
        return json.loads(out.read_text(encoding="utf-8")) if out.exists() else None

    def run_expecting_exit(self, rows_a, rows_b, keys, attestations, same_file=False):
        result = self.run_scorer(rows_a, rows_b, keys, attestations, same_file=same_file)
        self.assertIsNone(result, "the scorer wrote an artifact it was supposed to refuse")
        return getattr(self, "message", "")


class WeightedRecallTests(Harness):
    def test_the_miss_share_bound_solves_the_defining_equation(self):
        self.assertEqual(sa.binomial_upper_bound_on_p(0, 100), 1 - 0.05 ** (1 / 100))
        p = sa.binomial_upper_bound_on_p(2, 10)
        low_tail = ((1 - p) ** 10 + 10 * p * (1 - p) ** 9
                    + 45 * p ** 2 * (1 - p) ** 8)              # P(X <= 2) at n=10
        self.assertAlmostEqual(low_tail, 0.05, places=3)
        self.assertTrue(0.4 < p < 0.6, p)
        self.assertIsNone(sa.binomial_upper_bound_on_p(0, 0))
        self.assertAlmostEqual(sa.binomial_upper_bound_on_p(10, 10), 1.0)
        self.assertGreater(sa.binomial_upper_bound_on_p(3, 20), 3 / 20)

    def test_two_coders_agreeing_on_a_missed_proposition_contribute_exactly_one_weight(self):
        # 1,000 propositions in the stratum, 20 sampled -> weight 50. One miss found -> 50 estimated.
        missed = blank_row("p1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"})
        keys = [probe_key("p1", PROBE_ROLES[0], 1000, 20), probe_key("p2", PROBE_ROLES[0], 1000, 20)]
        rows = [missed, mundane("p2")]
        result = self.run_scorer(rows, rows, keys,
                                 [attestation("w", "p", 1, D4, "judging_moral_order"),
                                  attestation("w", "p", 2, D4, "judging_moral_order"),
                                  attestation("w", "p", 3, D4, "judging_moral_order")])
        recall = result["detector_recall"]
        stratum = recall["probe_strata"][PROBE_ROLES[0]]
        self.assertEqual(stratum["rows_coded_by_both"], 2)
        self.assertEqual(stratum["sampling_weight"], 50.0)
        self.assertAlmostEqual(stratum["weight_sum_of_coded_rows"], 100.0)
        self.assertEqual(stratum["declined_null"], 1)
        self.assertEqual(stratum["estimated_missed_divine_propositions_weighted"], 50.0)
        entry = recall["by_value"][f"{D4}=judging_moral_order"]
        self.assertEqual(entry["detected_propositions_corpus_wide"], 3)
        self.assertEqual(entry["estimated_missed_propositions_weighted"], 50.0)
        self.assertEqual(entry["recall_hat"], round(3 / 53, 4))

    def test_one_reader_overreading_a_row_does_not_become_a_corpus_miss(self):
        keys = [probe_key("p1"), probe_key("p2")]
        rows_a = [blank_row("p1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"}),
                  mundane("p2")]
        rows_b = [mundane("p1"), mundane("p2")]
        result = self.run_scorer(rows_a, rows_b, keys, [])
        stratum = result["detector_recall"]["probe_strata"][PROBE_ROLES[0]]
        self.assertEqual(stratum["declined_null"], 0)
        self.assertEqual(stratum["estimated_missed_divine_propositions_weighted"], 0.0)
        self.assertEqual(stratum["coders_disagree_on_null"], 1)

    def test_a_stratum_that_found_no_miss_reports_a_bound_not_perfection(self):
        keys = [probe_key("p1", population=1000, sampled=10), probe_key("p2", population=1000, sampled=10)]
        rows = [mundane("p1"), mundane("p2")]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D4, "judging_moral_order")])
        stratum = result["detector_recall"]["probe_strata"][PROBE_ROLES[0]]
        self.assertEqual(stratum["estimated_missed_divine_propositions_weighted"], 0.0)
        self.assertAlmostEqual(stratum["one_sided_95pct_upper_bound_on_miss_share"], round(1 - 0.05 ** 0.5, 6))
        self.assertAlmostEqual(stratum["one_sided_95pct_upper_bound_on_missed_propositions"],
                               1000 * (1 - 0.05 ** 0.5), 2)
        level = result["detector_recall"]["proposition_level"]
        self.assertEqual(level["estimated_missed_divine_propositions_weighted"], 0.0)
        self.assertLess(level["recall_of_divine_propositions_lower_bound_95pct"],
                        level["recall_of_divine_propositions_point"])
        self.assertEqual(level["recall_of_divine_propositions_point"], 1.0)

    def test_both_strata_are_disjoint_and_their_weights_add(self):
        unit = {UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"}
        keys = [probe_key("p1", PROBE_ROLES[0], 1000, 10),      # weight 100
                probe_key("p2", PROBE_ROLES[1], 100, 10)]       # weight 10
        rows = [blank_row("p1", **unit), blank_row("p2", **unit)]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D4, "judging_moral_order")])
        recall = result["detector_recall"]
        entry = recall["by_value"][f"{D4}=judging_moral_order"]
        self.assertEqual(entry["misses_by_probe_stratum"], {PROBE_ROLES[0]: 100.0, PROBE_ROLES[1]: 10.0})
        self.assertEqual(entry["estimated_missed_propositions_weighted"], 110.0)
        self.assertEqual(recall["proposition_level"]["estimated_missed_divine_propositions_weighted"], 110.0)

    def test_a_row_the_segmentation_cutter_disputes_is_still_a_miss(self):
        # too_small_should_join says a divine claim is on the page and only the cut is wrong
        keys = [probe_key("p1", population=1000, sampled=10), probe_key("p2", population=1000, sampled=10)]
        rows_a = [blank_row("p1", **{UNIT_COLUMN: "too_small_should_join", COLUMNS[D4]: "sustaining_order"}),
                  mundane("p2")]
        result = self.run_scorer(rows_a, rows_a, keys, [])
        stratum = result["detector_recall"]["probe_strata"][PROBE_ROLES[0]]
        self.assertEqual(stratum["declined_null"], 1)
        self.assertEqual(stratum["estimated_missed_divine_propositions_weighted"], 100.0)


class EstimandSeparationTests(Harness):
    def test_probe_rows_never_enter_the_machine_versus_human_table(self):
        keys = [candidate_key("c1", {D4: ["judging_moral_order"]}, 0.1),
                candidate_key("c2", {D4: ["judging_moral_order"]}, 0.1),
                probe_key("p1", population=1000, sampled=10)]
        candidate = blank_row("c1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"})
        candidate2 = blank_row("c2", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"})
        probe = blank_row("p1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "guarding_localised"})
        rows = [candidate, candidate2, probe]
        result = self.run_scorer(rows, rows, keys,
                                 [attestation("w", "p", 1, D4, "judging_moral_order")])
        table = result["machine_vs_human_by_value"]
        self.assertEqual(table[f"{D4}=judging_moral_order"]["rows_are_machine_candidate_rows_only"], True)
        self.assertEqual(table[f"{D4}=judging_moral_order"]["human_consensus_in_sampled_candidate_rows"], 2)
        self.assertNotIn(f"{D4}=guarding_localised", table)
        self.assertEqual(result["detector_recall"]["by_value"][f"{D4}=guarding_localised"]
                         ["estimated_missed_propositions_weighted"], 100.0)

    def test_undecidable_is_a_coder_answer_not_a_value_the_detector_can_miss(self):
        keys = [candidate_key("c1", {D4: ["judging_moral_order"]}, 0.5),
                probe_key("p1", population=1000, sampled=10)]
        rows = [blank_row("c1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "undecidable"}),
                blank_row("p1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "undecidable"})]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D4, "judging_moral_order")])
        self.assertNotIn(f"{D4}=undecidable", result["machine_vs_human_by_value"])
        self.assertNotIn(f"{D4}=undecidable", result["detector_recall"]["by_value"])
        # agreement on `undecidable` is still agreement, and agreement is still scored on it
        self.assertEqual(result["set_valued_dimensions"][D4]["mean_jaccard"], 1.0)
        self.assertEqual(result["set_valued_dimensions"][D4]["n_compared"], 2)

    def test_a_value_the_probe_never_produced_gets_no_recall_estimate(self):
        keys = [probe_key("p1"), probe_key("p2")]
        rows = [mundane("p1"), mundane("p2")]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D2A, "one_only")])
        entry = result["detector_recall"]["by_value"][f"{D2A}=one_only"]
        self.assertIsNone(entry["recall_hat"])
        self.assertIn("no_probe_evidence_yet", entry["status"])
        self.assertEqual(entry["detected_propositions_corpus_wide"], 1)

    def test_precision_table_no_longer_calls_a_conditional_recall(self):
        keys = [candidate_key("c1", {D4: ["judging_moral_order"]}, 0.25),
                candidate_key("c2", {D4: ["judging_moral_order"]}, 0.25), probe_key("p1")]
        rows = [blank_row("c1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "sustaining_order"}),
                blank_row("c2", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "sustaining_order"}),
                mundane("p1")]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D4, "judging_moral_order")])
        entry = result["machine_vs_human_by_value"][f"{D4}=sustaining_order"]
        self.assertEqual(entry["label_kind"], "human_only_in_candidate_rows")
        self.assertNotIn("recall", entry)
        self.assertIn("human_confirmation_rate_conditional_on_detection", entry)
        self.assertIsNone(entry["precision_within_sampled_candidates"])
        self.assertIn("it is NOT recall", " ".join(result["reading_rules"]))


class RefusalTests(Harness):
    def test_a_key_without_probe_rows_is_refused_because_it_cannot_measure_recall(self):
        keys = [candidate_key("c1", {D4: ["judging_moral_order"]}, 0.25),
                candidate_key("c2", {D4: ["judging_moral_order"]}, 0.25)]
        rows = [mundane("c1"), mundane("c2")]
        message = self.run_expecting_exit(rows, rows, keys, [])
        self.assertIn("cannot measure recall", message)

    def test_unweighted_probe_rows_are_refused(self):
        keys = [probe_key("p1"), probe_key("p2")]
        keys[1]["sampling_weight"] = None
        rows = [mundane("p1"), mundane("p2")]
        message = self.run_expecting_exit(rows, rows, keys, [])
        self.assertIn("no sampling weight", message)

    def test_one_sheet_supplied_twice_is_still_refused(self):
        keys = [probe_key("p1"), probe_key("p2")]
        rows = [mundane("p1"), mundane("p2")]
        message = self.run_expecting_exit(rows, rows, keys, [], same_file=True)
        self.assertIn("not two independent codings", message)

    def test_a_single_shared_row_is_refused(self):
        keys = [probe_key("p1"), probe_key("p2")]
        message = self.run_expecting_exit([mundane("p1")], [mundane("p1")], keys, [])
        self.assertIn("not a reliability sample", message)


class CoderBehaviourTests(Harness):
    def test_undecidable_tally_accumulates_over_rows_not_the_last_row(self):
        keys = [candidate_key(f"c{i}", {D4: ["judging_moral_order"]}, 0.5) for i in range(3)]
        keys.append(probe_key("p1"))
        rows = [blank_row(f"c{i}", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "undecidable"})
                for i in range(3)]
        rows.append(mundane("p1"))
        result = self.run_scorer(rows, rows, keys, [])
        tally = result["undecidable_selection_rate"]["a"]
        self.assertEqual(tally["total_choices"], 3)          # one filled cell per candidate row
        self.assertEqual(tally["undecidable_choices"], 3)
        self.assertEqual(tally["undecidable_share_of_choices"], 1.0)
        self.assertEqual(tally["candidate_rows_coded"], 3)
        self.assertEqual(tally["probe_rows_coded"], 1)

    def test_row_groups_are_reported_separately_for_every_dimension(self):
        keys = [candidate_key("c1", {D4: ["judging_moral_order"]}, 0.5), probe_key("p1")]
        rows = [blank_row("c1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "judging_moral_order"}),
                blank_row("p1", **{UNIT_COLUMN: "single_proposition", COLUMNS[D4]: "guarding_localised"})]
        result = self.run_scorer(rows, rows, keys, [attestation("w", "p", 1, D4, "judging_moral_order")])
        split = result["set_valued_dimensions"][D4]["agreement_split_by_row_group"]
        self.assertEqual(split["machine_candidate"]["n_compared"], 1)
        self.assertEqual(split["probe"]["n_compared"], 1)
        self.assertEqual(result["rows_by_sample_role"]["probe"]["rows_compared"], 1)
        self.assertEqual(result["rows_by_sample_role"]["machine_candidate"]["rows_compared"], 1)


class ConstructCheckTests(Harness):
    """The D7d / doctrine_endorsed_by_text alias is only testable by a human, so the
    scorer compares one coder's two answers and says so when nobody has answered.

    The machine cannot corroborate the field against itself: `divinity_ontology.py`
    writes the record field as D7d's value, so any machine-side association is 1.0 by
    construction. These tests pin that the reported figure is a coder-side one.
    """

    D7D = "D7d_epistemic_commitment"
    ENDORSE = sa.ENDORSEMENT_COLUMN
    ONTOLOGY = json.loads((ROOT / "config/divinity_ontology.json").read_text(encoding="utf-8"))

    PROBE = "probe1"

    def rows(self, answers):
        """One row per token, with that coder's D7d and endorsement answers.

        The scorer refuses a packet with no no_candidate probe rows, because such a packet
        cannot measure recall, so every fixture carries one -- left blank here so it adds
        nothing to the construct tally.
        """
        return [blank_row(token, **{UNIT_COLUMN: "single_proposition",
                                     COLUMNS[self.D7D]: commitment, self.ENDORSE: endorsement})
                for token, commitment, endorsement in answers] + [blank_row(self.PROBE)]

    def keys(self, tokens):
        return ([candidate_key(token, {self.D7D: ["endorsed_by_text"]}, 0.5) for token in tokens]
                + [probe_key(self.PROBE)])

    def attest(self):
        return [attestation("w", "p", 1, self.D7D, "endorsed_by_text")]

    def test_the_construct_check_compares_one_coders_two_answers_not_two_coders(self):
        tokens = ["t1", "t2", "t3"]
        coder_a = self.rows([("t1", "endorsed_by_text", "endorsed_by_text"),
                             ("t2", "endorsed_by_text", "endorsed_by_text"),
                             ("t3", "rejected_in_text", "attributed_not_endorsed")])
        coder_b = self.rows([("t1", "endorsed_by_text", "suspended_or_held_open"),
                             ("t2", "endorsed_by_text", "not_applicable_non_assertive"),
                             ("t3", "rejected_in_text", "endorsed_by_text")])
        result = self.run_scorer(coder_a, coder_b, self.keys(tokens), self.attest())
        block = result["construct_checks"]["d7d_and_doctrinal_endorsement"]
        self.assertEqual(block["status"], "measured")
        self.assertEqual(block["rows_answering_both_questions"], 6)
        by = block["by_coder_and_row_group"]
        self.assertEqual(sorted(by), ["a.machine_candidate", "b.machine_candidate"],
                         "the unit of comparison is one coder's two columns")
        self.assertEqual(by["a.machine_candidate"]["rows_answering_both_questions"], 3)
        self.assertEqual(by["a.machine_candidate"]["exact_agreement"], round(2 / 3, 4))
        self.assertEqual(by["a.machine_candidate"]["cohen_kappa"], 0.4)
        self.assertEqual(by["a.machine_candidate"]["disagreement_cells"],
                         {"rejected_in_text -> attributed_not_endorsed": 1})
        self.assertEqual(by["b.machine_candidate"]["exact_agreement"], 0.0)
        self.assertEqual(by["b.machine_candidate"]["disagreement_cells"],
                         {"endorsed_by_text -> not_applicable_non_assertive": 1,
                          "endorsed_by_text -> suspended_or_held_open": 1,
                          "rejected_in_text -> endorsed_by_text": 1})
        self.assertEqual(by["a.machine_candidate"]["marginal_distribution_doctrine_endorsed_by_text"],
                         {"attributed_not_endorsed": 1, "endorsed_by_text": 2})

    def test_probes_and_candidates_are_not_pooled_in_the_construct_check(self):
        candidate = blank_row("c1", **{UNIT_COLUMN: "single_proposition",
                                       COLUMNS[self.D7D]: "endorsed_by_text",
                                       self.ENDORSE: "endorsed_by_text"})
        probe = blank_row("p1", **{UNIT_COLUMN: "endorsed_by_text",
                                   COLUMNS[self.D7D]: "endorsed_by_text",
                                   self.ENDORSE: "suspended_or_held_open"})
        result = self.run_scorer([candidate, probe], [candidate, probe],
                                 [candidate_key("c1", {self.D7D: ["endorsed_by_text"]}, 0.5), probe_key("p1")],
                                 self.attest())
        by = result["construct_checks"]["d7d_and_doctrinal_endorsement"]["by_coder_and_row_group"]
        self.assertEqual(sorted(by), ["a.machine_candidate", "a.probe", "b.machine_candidate", "b.probe"])
        self.assertEqual(by["a.machine_candidate"]["exact_agreement"], 1.0)
        self.assertEqual(by["a.probe"]["exact_agreement"], 0.0)

    def test_an_uncoded_packet_reports_no_construct_number_rather_than_a_perfect_one(self):
        tokens = ["t1", "t2"]
        rows = (self.rows([(token, "endorsed_by_text", "") for token in tokens])[:-1]
                + [blank_row(self.PROBE)])
        result = self.run_scorer(rows, rows, self.keys(tokens), self.attest())
        block = result["construct_checks"]["d7d_and_doctrinal_endorsement"]
        self.assertEqual(block["rows_answering_both_questions"], 0)
        self.assertEqual(block["by_coder_and_row_group"], {})
        self.assertTrue(block["status"].startswith("pending_human_coding"))
        self.assertNotIn("1.0", json.dumps(block["by_coder_and_row_group"]))

    def test_the_two_columns_offer_one_vocabulary_so_the_check_compares_like_with_like(self):
        from prepare_annotation_packet import ANSWER_VOCABULARIES
        values = set(self.ONTOLOGY["dimensions"][self.D7D]["values"])
        self.assertEqual(values, set(ANSWER_VOCABULARIES[self.ENDORSE]),
                         "if the vocabularies drift apart the construct check stops being a like-for-like "
                         "comparison and the alias note has to be rewritten with them")
        self.assertEqual(column_cardinalities()[self.D7D], "single")

    def test_the_alias_is_declared_in_the_ontology_config_the_scorer_quotes(self):
        note = self.ONTOLOGY["distinctness_status"]["d7d_epistemic_commitment_and_doctrinal_endorsement"]
        self.assertIn("construct_checks.d7d_and_doctrinal_endorsement", note["what_would_separate_them"])
        self.assertIn("not_yet_instrumented", note["the_relationship_is_not_two_measurements"],
                      "the one place the field and D7d genuinely differ has to be stated, not smoothed over")
        self.assertIn("not_yet_instrumented",
                      self.ONTOLOGY["assertion_logic"]["three_questions_kept_separate"]["doctrinal_endorsement"])

    def test_the_scorer_declines_to_treat_the_alias_as_a_second_measurement(self):
        tokens = ["t1", "t2"]
        rows = self.rows([("t1", "endorsed_by_text", "endorsed_by_text"),
                          ("t2", "endorsed_by_text", "endorsed_by_text")])
        result = self.run_scorer(rows, rows, self.keys(tokens), self.attest())
        block = result["construct_checks"]["d7d_and_doctrinal_endorsement"]
        joined = json.dumps(block).lower()
        self.assertIn("1.0 by construction", joined)
        self.assertIn("not_evidence_of", block)
        self.assertTrue(any("construct check" in line for line in result["not_claimed"]))


class PublishedArtifactTests(unittest.TestCase):
    """The shipped packet must satisfy the properties the estimator depends on."""

    @classmethod
    def setUpClass(cls):
        for name in ("results/annotation_packet_key.jsonl", "results/ontology_attestations.jsonl.gz",
                     "results/annotation_sampling_plan.json"):
            if not (ROOT / name).exists():
                raise unittest.SkipTest(f"{name} has not been produced yet")
        cls.key = sa.key_index(ROOT / "results/annotation_packet_key.jsonl")
        cls.plan = json.loads((ROOT / "results/annotation_sampling_plan.json").read_text(encoding="utf-8"))

    def test_every_probe_row_in_the_shipped_key_carries_an_exact_weight(self):
        probe = sa.require_probe_weights(self.key)
        rows_added = self.plan["recall_probe"]["rows_added"]
        self.assertEqual(len(probe), rows_added[PROBE_ROLES[0]] + rows_added[PROBE_ROLES[1]])
        for record in probe:
            self.assertGreater(record["sampling_weight"], 0)
            self.assertAlmostEqual(record["sampling_weight"], 1 / record["inclusion_probability"], places=3)

    def test_detection_rows_still_carry_their_candidate_weights(self):
        for record in self.key.values():
            if record.get("sample_role") == "machine_candidate":
                self.assertIsNotNone(record["sampling_weight"])

    def test_recall_numerator_counts_the_same_propositions_the_packet_called_hits(self):
        counts, propositions = sa.detected_by_value(ROOT / "results/ontology_attestations.jsonl.gz")
        self.assertEqual(propositions, self.plan["recall_probe"]["universe"]["hit_by_the_machine"])
        self.assertGreater(sum(counts.values()), 0)

    def test_the_probe_universe_is_the_hit_universe_plus_the_missed_population(self):
        universe = self.plan["recall_probe"]["universe"]
        self.assertEqual(universe["propositions_in_universe"],
                         universe["hit_by_the_machine"] + universe["no_record_in_universe"])
        self.assertEqual(universe["no_record_in_universe"],
                         universe["of_which_cue_negative"] + universe["of_which_cue_positive"])

    def test_no_recall_number_exists_yet_because_no_coder_has_coded(self):
        self.assertFalse((ROOT / "results/annotation_reliability.json").exists(),
                         "a reliability artifact would have to be computed from codings that do not exist")


class ImportDriftTests(unittest.TestCase):
    def test_the_scorer_reads_the_roles_the_builder_writes(self):
        importlib.reload(sa)
        from prepare_annotation_packet import PROBE_ROLE_PREFIX, ROLE_CANDIDATE
        self.assertEqual(sa.PROBE_ROLE_PREFIX, PROBE_ROLE_PREFIX)
        self.assertTrue(all(role.startswith(PROBE_ROLE_PREFIX) for role in PROBE_ROLES))
        self.assertFalse(ROLE_CANDIDATE.startswith(PROBE_ROLE_PREFIX))

    def test_the_null_answer_is_a_real_vocabulary_value(self):
        from prepare_annotation_packet import ANSWER_VOCABULARIES
        from prepare_annotation_packet import UNIT_COLUMN as unit_column
        self.assertIn(sa.NULL_UNIT_ANSWER, ANSWER_VOCABULARIES[unit_column])
        self.assertIn(sa.UNDECIDABLE, ANSWER_VOCABULARIES[unit_column])


if __name__ == "__main__":
    unittest.main()
