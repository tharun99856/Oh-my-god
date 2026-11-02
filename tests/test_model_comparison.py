"""Licence-condition tests for the Track B model-comparison layer (config/model_comparison_v3.json).

These tests do not check any historical claim. They check the gates the external reviews asked for: that the
four operator conditions are enforced as a conjunction and not as a threshold; that a derivation longer than
the declared path limit is refused; that an operator cannot be asserted without the evidence its own entry
demands; that vertical inheritance and horizontal transmission cannot be conflated into one relation; that the
operator cost table is hash-checked before anything is scored; that no model score or ranking is emitted while
the dated-attestation fields are empty; that stage 1 puts all four models on one footing with
`no_decisive_winner` reachable and M2 allowed to lose; that the holdout folds whole works rather than pairs,
and publishes the leakage check instead of assuming it; that the effective-sample estimate is the Kish count
over work clusters with its worked cases reproduced; and that the pair floor a run enforces comes from the
published power simulation rather than from the number an analyst wrote down.

Every fixture here is synthetic and labelled TEST. No fixture asserts that any real concept was inherited.
"""

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import compare_models as cm  # noqa: E402

CONFIG = cm.load_config()
ONTOLOGY = json.loads((ROOT / "config" / "divinity_ontology.json").read_text(encoding="utf-8"))
GATES = cm.decision_gates(CONFIG)
MINIMUM_PAIRS = GATES["minimum_pairs"] or CONFIG["probabilistic_transformation_model"]["likelihood_of_an_observed_state_pair"]["minimum_pairs"]
MINIMUM_EFFECTIVE_SAMPLES = GATES["minimum_effective_samples"] or 0

DIMENSIONS = [
    "D1_ontological_category",
    "D2a_acknowledged_population",
    "D2b_reality_of_others",
    "D2c_worship_exclusivity",
    "D3_agency",
    "D4_cosmic_function",
    "D5_universe_relationship",
    "D6_temporal_nature",
    "D7a_speaker_attribution",
    "D7b_speech_act",
    "D7c_discourse_genre",
    "D7d_epistemic_commitment",
]

SET_VALUED = {"D1_ontological_category", "D3_agency", "D4_cosmic_function", "D5_universe_relationship", "D6_temporal_nature"}


def state(**overrides):
    base = {}
    for key in DIMENSIONS:
        base[key] = ["TEST_VALUE"] if key in SET_VALUED else "TEST_VALUE"
    base.update(overrides)
    return base


def date_object(earliest, latest, which="composition"):
    return {
        "date_earliest": earliest,
        "date_latest": latest,
        "dating_basis": "critical_edition",
        "date_confidence": "medium",
        "survival_or_composition": which,
        "reference": "TEST FIXTURE reference, not a real edition",
    }


def node(node_id, values, earliest=None, latest=None, attested=True, witness_only=False):
    if witness_only:
        dates = {"witness": date_object(earliest, latest, "witness_survival")}
    elif earliest is None:
        dates = {"composition": {}, "witness": {}}
    else:
        dates = {"composition": date_object(earliest, latest), "witness": date_object(earliest, latest, "witness_survival")}
    return {
        "node_id": node_id,
        "expression_id": node_id + "_expr",
        "attested": attested,
        "locator": {"work": "TEST", "passage": "p000001", "section": "1", "char_start": 0, "char_end": 9, "surface_text": "TEST text"},
        "dates": dates,
        "dimension_values": values,
        "presence": {"conceptual_presence": "present", "doctrinal_endorsement": "endorsed", "historical_transmission": "documented_vertical"},
    }


def evidence(op):
    return {item: "TEST locator for: " + item for item in CONFIG["operator_cost_matrix"]["operators"][op]["required_evidence"]}


def proposal(proposed="2026-01-01", observed="2026-06-01", seen_pairs=()):
    return {
        "proposed_at": proposed,
        "observed_at": observed,
        "proposed_before_observation": proposed < observed,
        "proposal_note_sha256": "0" * 64,
        "seen_pairs": list(seen_pairs),
    }


def vertical_edge(edge_id="e1"):
    return {
        "edge_id": edge_id,
        "edge_type": "vertical_inheritance",
        "subtype": "institutional_succession",
        "descent_evidence": [{"basis": "institutional_records", "note": "TEST succession record"}],
        "independent_witness": [{"note": "TEST witness outside the translator"}],
    }


def horizontal_edge(edge_id="e1", subtype="contact_borrowing"):
    return {
        "edge_id": edge_id,
        "edge_type": "horizontal_transmission",
        "subtype": subtype,
        "route_evidence": [{"note": "TEST dated contact event"}],
        "direction_argument": {"note": "TEST non-conceptual priority argument"},
        "independent_witness": [{"note": "TEST witness"}],
    }


def assertion(op="elevation", applies=("n1", "n2"), edge_id="e1", independent=True):
    item = {
        "operator": op,
        "pair_id": "|".join(applies),
        "applies_to": list(applies),
        "edge_id": edge_id,
        "evidence": evidence(op),
        "proposal": proposal(),
    }
    if independent:
        item["independent_witness"] = [{"note": "TEST independent witness"}]
    return item


def derivation(op="elevation", edge=None, extra_nodes=(), extra_operators=(), witness_only=False, dates=True, independent=True):
    left = node("n1", state(D1_ontological_category=["personal_agent"]), -900, -700, witness_only=witness_only or not dates)
    right = node("n2", state(D1_ontological_category=["personal_agent", "manifestation_or_hypostasis"]), -500, -300, witness_only=witness_only or not dates)
    nodes = [left, right] + list(extra_nodes)
    edges = [edge if edge is not None else vertical_edge()]
    operators = [assertion(op)] + list(extra_operators)
    if not independent:
        edges[0].pop("independent_witness", None)
        operators[0].pop("independent_witness", None)
    return {"derivation_id": "TEST-D", "claim": "TEST hypothesis, asserted nowhere", "nodes": nodes, "edges": edges, "operators": operators}


def nodes_of(derivation):
    return {item["node_id"]: item for item in derivation["nodes"]}


DIMENSION_BLOCKS = CONFIG["dimension_similarity_rules"]["dimension_blocks"]

# The ordering M4's alpha vector declares: functional most concordant, structural middle, arbitrary least.
# Fixtures carry it by default so that a test about margins and gates is not accidentally a test about the
# attractor prior; a test that wants the prior to fail passes its own means.
DECLARED_BLOCK_ORDER = {"functional_or_pressure_prone": 0.70, "structural": 0.50, "arbitrary_or_expressive": 0.30}


def block_profile(means):
    """A pair's per-block means in the shape `similarity_between` writes them.

    `None` for a block means that pair compared no key in it, which is what keeps a block out of the pooled
    profile rather than pulling its mean toward zero. A fixture declares one mean per block, so each key in
    that block carries it; the pooling in `observed_block_profile` then reproduces it exactly.
    """
    if means is None:
        return None
    return {name: {"keys_compared": list(keys), "per_key": {key: means[name] for key in keys},
                   "mean_similarity": means[name]}
            for name, keys in DIMENSION_BLOCKS.items() if means.get(name) is not None}


def observation(pair_id, similarity_class, n_vertical=2, background=None, works=None, witnesses=None, lineage=None,
                block_means=DECLARED_BLOCK_ORDER):
    work_a, work_b = works or (f"work-{pair_id}-a", f"work-{pair_id}-b")
    witness_a, witness_b = witnesses or (f"witness-{pair_id}-a", f"witness-{pair_id}-b")
    record = {
        "pair_id": pair_id,
        "similarity_class": similarity_class,
        "n_vertical": n_vertical,
        "n_horizontal": 0,
        "n_contact_borrowing": 0,
        "n_restoration": 0,
        "work_a": work_a,
        "work_b": work_b,
        "witness_a": witness_a,
        "witness_b": witness_b,
        "background_distribution": background or {"identical": 0.05, "near": 0.15, "partial": 0.3, "far": 0.3, "unrelated": 0.2},
        "composition_a": date_object(-900, -800),
        "composition_b": date_object(-500, -400),
    }
    profile = block_profile(block_means)
    if profile:
        record["block_profile"] = profile
    if lineage:
        record["declared_lineage"] = lineage
    return record


def pair_set(count, similarity_class="identical", **kwargs):
    """A pair set on distinct works, which is the shape the published gates can be met by.

    The gates are a pair count and an effective-sample count, so a test that wants to reach scoring has to
    declare clusters that do not repeat. Work labels are derived from the index, so the set is reproducible.
    """
    return [
        observation(
            "p%03d" % index,
            similarity_class,
            works=(f"work-{index:03d}-a", f"work-{index:03d}-b"),
            witnesses=(f"witness-{index:03d}-a", f"witness-{index:03d}-b"),
            **kwargs,
        )
        for index in range(count)
    ]


class ConfigContractTests(unittest.TestCase):
    def test_twelve_dimension_keys_are_verbatim(self):
        self.assertEqual(sorted(CONFIG["dimension_keys"]["keys"]), sorted(DIMENSIONS))
        self.assertEqual(CONFIG["dimension_keys"]["set_valued"], sorted(SET_VALUED, key=DIMENSIONS.index))
        self.assertEqual(CONFIG["dimension_keys"]["single_valued"], sorted(set(DIMENSIONS) - SET_VALUED, key=DIMENSIONS.index))

    def test_three_presence_fields_replace_the_single_refusal_state(self):
        self.assertEqual(
            sorted(CONFIG["presence_fields"]["fields"]),
            sorted(["conceptual_presence", "doctrinal_endorsement", "historical_transmission"]),
        )
        for spec in CONFIG["presence_fields"]["fields"].values():
            self.assertIn("undecidable", spec["allowed"])

    def test_all_thirteen_operators_are_priced(self):
        ontology_names = set(ONTOLOGY["transformation_operators"]["operators"])
        self.assertEqual(set(CONFIG["operator_cost_matrix"]["operators"]), ontology_names)
        self.assertEqual(len(ontology_names), 13)

    def test_every_operator_carries_cost_evidence_edge_types_and_a_rationale(self):
        hashed = set(CONFIG["preregistration"]["mechanism"]["hash_scope"]["operator_fields"])
        for name, spec in CONFIG["operator_cost_matrix"]["operators"].items():
            self.assertGreater(spec["cost"], 0, name)
            self.assertTrue(0 < spec["prior_lambda_per_edge"] < 1, name)
            self.assertTrue(0 < spec["retention_rho"] <= 1, name)
            self.assertTrue(len(spec["required_evidence"]) >= 2, name)
            self.assertTrue(spec["permitted_edge_types"], name)
            self.assertTrue(set(spec["permitted_edge_types"]) <= {"vertical_inheritance", "horizontal_transmission"}, name)
            self.assertIn("cost_basis", spec, name)
            self.assertIn("notes", spec, name)
            self.assertTrue(hashed <= set(spec), name)

    def test_four_conditions_are_declared_mandatory_not_a_threshold(self):
        decision = CONFIG["operator_discipline"]["decision"]
        self.assertTrue(decision["all_four_mandatory"])
        self.assertEqual(decision["mode"], "conjunction")
        self.assertTrue(decision["threshold_interpretation_rejected"])
        self.assertEqual(len(CONFIG["operator_discipline"]["conditions"]), 4)
        self.assertTrue(CONFIG["operator_discipline"]["waivers"].startswith("none"))

    def test_every_declared_number_is_registered_as_analyst_set(self):
        register = json.dumps(CONFIG["analyst_set_parameters_register"])
        for needle in ("margin_log10_bayes_factor", "max_operator_applications_per_derivation",
                       "ordering_rule threshold", "minimum_block_spread"):
            self.assertIn(needle.split()[-1], register, needle)
        self.assertIn("analyst-set", json.dumps(CONFIG["operator_cost_matrix"]) + json.dumps(CONFIG["edge_rate_parameters"]))

    def test_a_registered_number_still_says_what_the_tool_reads(self):
        """A register entry that has drifted from the live key is a registration of a different rule."""
        registered = {item["parameter"]: item for item in CONFIG["analyst_set_parameters_register"]}
        spread = CONFIG["m4_block_profile_test"]["minimum_block_spread"]
        margin = cm.declared_margin(CONFIG)
        self.assertIn(f"m4_block_profile_test.minimum_block_spread = {spread}", registered,
                      "the register names the number it registers, so editing the key strands the entry")
        self.assertIn(f"margin_log10_bayes_factor = {margin}", registered)
        entry = registered[f"m4_block_profile_test.minimum_block_spread = {spread}"]
        self.assertIn("analyst", entry["basis"], "the spread is a judgement and has to be labelled as one")
        self.assertIn("never after a run", entry["may_be_changed"])

    def test_the_replaced_monotone_prediction_is_named_not_silently_dropped(self):
        replaced = CONFIG["probabilistic_transformation_model"]["replaces"]
        self.assertIn("greater temporal distance implies greater dissimilarity", replaced)


class ConjunctionOfFourConditionsTests(unittest.TestCase):
    def test_four_of_four_is_admissible(self):
        item = derivation()
        gate = cm.check_conditions(item["operators"][0], item["edges"][0], nodes_of(item), CONFIG)
        self.assertTrue(gate["admissible"])
        self.assertEqual(gate["met_count"], 4)
        self.assertEqual(cm.derivation_errors(item, CONFIG), [])

    def test_three_of_four_is_undecidable_not_a_transformation_claim(self):
        item = derivation(independent=False)
        gate = cm.check_conditions(item["operators"][0], item["edges"][0], nodes_of(item), CONFIG)
        self.assertEqual(gate["met_count"], 3)
        self.assertEqual(gate["unmet"], ["d"])
        self.assertFalse(gate["admissible"])
        result = cm.evaluate_derivation(item, CONFIG)
        self.assertEqual(result["status"], cm.STATUS_REJECTED_DERIVATION)
        self.assertIsNone(result["model_scores"])
        self.assertIsNone(result["model_ranking"])

    def test_each_condition_alone_blocks_the_assertion(self):
        cases = {
            "a": lambda item: item["nodes"][1].update(attested=False),
            "b": lambda item: item["nodes"][1]["dates"]["composition"].update(date_earliest=-1200, date_latest=-1100),
            "c": lambda item: item["edges"][0].update(edge_type="untyped"),
            "d": lambda item: (item["operators"][0].pop("independent_witness"), item["edges"][0].pop("independent_witness")),
        }
        for key, break_it in cases.items():
            with self.subTest(condition=key):
                item = derivation()
                break_it(item)
                errors = cm.derivation_errors(item, CONFIG)
                self.assertTrue(any(f"unmet = {key}" in error for error in errors), errors)
                self.assertTrue(any("conjunctive" in error for error in errors), errors)

    def test_no_waiver_or_majority_reading_is_available(self):
        licence = json.dumps({key: CONFIG["operator_discipline"][key] for key in ("decision", "conditions", "waivers", "enforcement")})
        self.assertNotIn("two of the four", licence)
        self.assertNotIn("three of four suffices", licence)
        self.assertIn("if and only if", CONFIG["operator_discipline"]["decision"]["statement"])

    def test_misreported_condition_flags_are_caught(self):
        item = derivation(independent=False)
        item["operators"][0]["conditions"] = {"a": True, "b": True, "c": True, "d": True}
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("condition d reported True but evaluates to False" in error for error in errors), errors)


class PathLimitTests(unittest.TestCase):
    def test_path_longer_than_declared_maximum_is_rejected(self):
        limit = CONFIG["path_constraints"]["max_operator_applications_per_derivation"]
        item = derivation()
        for index, op in enumerate(["absorption", "differentiation", "functional_transfer"]):
            mid = node("m%d" % index, state(), -800 + index, -700 + index)
            mid["dates"]["composition"] = date_object(-800 + 100 * index, -750 + 100 * index)
            item["nodes"].append(mid)
            edge = vertical_edge("e%d" % (index + 2))
            item["edges"].append(edge)
            item["operators"].append(assertion(op, ("m%d" % (index - 1) if index else "n1", "m%d" % index), "e%d" % (index + 2)))
        self.assertGreater(len(item["operators"]), limit)
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("exceeds max_operator_applications_per_derivation" in error for error in errors), errors)

    def test_reported_length_two_limit_needs_an_attested_intermediate(self):
        item = derivation()
        mid = node("m0", state(), attested=False)
        mid["dates"]["composition"] = date_object(-700, -650)
        mid["dates"]["witness"] = date_object(-700, -650, "witness_survival")
        item["nodes"].append(mid)
        item["edges"].append(vertical_edge("e2"))
        item["operators"].append(assertion("absorption", ("n1", "m0"), "e2"))
        item["operators"].append(assertion("functional_transfer", ("m0", "n2"), "e2"))
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("intermediate node" in error and "unattested" in error for error in errors), errors)

    def test_unattested_intermediates_are_capped_and_priced(self):
        item = derivation()
        for index in range(2):
            ghost = node("ghost%d" % index, state(), attested=False)
            ghost["dates"]["composition"] = date_object(-600, -550)
            ghost["dates"]["witness"] = date_object(-600, -550, "witness_survival")
            item["nodes"].append(ghost)
        parsimony = cm.derivation_parsimony(item, CONFIG)
        self.assertEqual(parsimony["unattested_intermediate_penalty"], 2 * CONFIG["path_constraints"]["unattested_intermediate_penalty_cost"])

    def test_repeat_cap_per_operator_is_enforced(self):
        item = derivation()
        item["operators"].append(assertion("elevation", ("n1", "n2"), "e1"))
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("max_applications_per_path" in error for error in errors), errors)

    def test_attractor_confusable_operators_alone_cannot_carry_a_derivation(self):
        item = derivation(op="scope_narrowing")
        item["edges"].append(vertical_edge("e2"))
        item["operators"].append(assertion("functional_transfer", ("n1", "n2"), "e2"))
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("attractor-confusable" in error for error in errors), errors)


class RequiredEvidenceTests(unittest.TestCase):
    def test_operator_without_its_required_evidence_is_rejected(self):
        item = derivation(op="absorption")
        required = item["operators"][0]["evidence"]
        victim = list(required)[0]
        del required[victim]
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("missing required evidence" in error and victim in error for error in errors), errors)
        self.assertEqual(cm.evaluate_derivation(item, CONFIG)["status"], cm.STATUS_REJECTED_DERIVATION)

    def test_nominalisation_demands_original_language_not_english(self):
        item = derivation(op="nominalisation")
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("original-language" in error for error in errors), errors)
        item["operators"][0]["original_language_witness"] = {"note": "TEST morphological argument"}
        self.assertFalse(any("original-language" in error for error in cm.derivation_errors(item, CONFIG)))

    def test_operator_placement_respects_edge_type_and_subtype(self):
        item = derivation(op="abstraction", edge=horizontal_edge(subtype="contact_borrowing"))
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("not permitted on horizontal subtype" in error for error in errors), errors)

    def test_unknown_operator_names_are_rejected(self):
        item = derivation()
        item["operators"][0]["operator"] = "resurrection_of_a_god"
        self.assertTrue(any("unknown_operator" in error for error in cm.derivation_errors(item, CONFIG)))

    def test_declared_but_unused_edge_is_rejected(self):
        item = derivation()
        item["edges"].append(vertical_edge("e9"))
        self.assertTrue(any("declared but unused" in error for error in cm.derivation_errors(item, CONFIG)))


class EdgeTypingTests(unittest.TestCase):
    def test_vertical_and_horizontal_have_separate_evidence_requirements(self):
        vertical = vertical_edge()
        horizontal = horizontal_edge()
        self.assertNotEqual(CONFIG["edge_typing"]["vertical_inheritance"]["evidence_requirements"], CONFIG["edge_typing"]["horizontal_transmission"]["evidence_requirements"])
        self.assertEqual(cm.edge_type_errors(vertical, CONFIG), [])
        self.assertIn("horizontal_edge_lacks_direction_argument", cm.edge_type_errors({k: v for k, v in horizontal.items() if k != "direction_argument"}, CONFIG))

    def test_a_contact_route_does_not_satisfy_a_descent_claim(self):
        edge = vertical_edge()
        edge.pop("descent_evidence")
        edge["route_evidence"] = [{"note": "TEST trade contact"}]
        errors = cm.edge_type_errors(edge, CONFIG)
        self.assertTrue(any("vertical_edge_lacks_descent_evidence" in error for error in errors), errors)
        self.assertTrue(any("horizontal evidence may not satisfy a descent claim" in error for error in errors), errors)

    def test_conflated_edge_type_value_is_illegal(self):
        for bad in ("descent_or_contact", None, ["vertical_inheritance", "horizontal_transmission"]):
            with self.subTest(edge_type=bad):
                edge = {"edge_id": "e1", "descent_evidence": [{"basis": "institutional_records"}], "route_evidence": [{"note": "TEST"}]}
                if bad is not None:
                    edge["edge_type"] = bad
                errors = cm.edge_type_errors(edge, CONFIG)
                self.assertTrue(any(error.startswith(("edge_type_missing", "edge_type_conflated", "edge_type_illegal")) for error in errors), errors)

    def test_descent_may_not_be_argued_from_the_similarity_being_explained(self):
        edge = vertical_edge()
        edge["descent_evidence"] = [{"basis": "conceptual_similarity", "note": "they look alike"}]
        self.assertTrue(any("descent_evidence_from_conceptual_similarity_rejected" in error for error in cm.edge_type_errors(edge, CONFIG)))

    def test_horizontal_descent_only_evidence_is_refused(self):
        edge = horizontal_edge()
        edge.pop("route_evidence")
        edge["descent_evidence"] = [{"basis": "comparative_linguistics"}]
        self.assertTrue(any("horizontal_edge_argued_from_descent_evidence_alone" in error for error in cm.edge_type_errors(edge, CONFIG)))

    def test_the_config_names_m1s_conflation_as_a_finding(self):
        finding = CONFIG["edge_typing"]["m1_conflation_finding"]
        joined = json.dumps(finding)
        self.assertIn("conflates vertical inheritance with horizontal transmission", finding["statement"])
        self.assertIn("condition (c)", joined)
        self.assertIn("edge_type_ambiguous", finding["fix_enforced_by_this_file"])


class PreregistrationTests(unittest.TestCase):
    def test_hash_of_the_registered_cost_table_matches(self):
        verification = cm.verify_preregistration(CONFIG)
        self.assertTrue(verification["ok"], verification["problems"])
        self.assertEqual(verification["expected"], verification["computed"])
        self.assertEqual(verification["registered_at"], CONFIG["preregistration"]["mechanism"]["registered_at"])

    def test_hash_is_reproducible_from_the_declared_scope(self):
        payload = cm.hash_payload(CONFIG)
        self.assertEqual(sorted(payload), sorted(["operators", "path_constraints"]))
        self.assertEqual(
            cm.operator_cost_table_sha256(CONFIG),
            cm.hashlib.sha256(cm.canonical_json(payload).encode("utf-8")).hexdigest(),
        )

    def test_tampered_cost_table_stops_the_run_before_any_score(self):
        tampered = copy.deepcopy(CONFIG)
        tampered["operator_cost_matrix"]["operators"]["elevation"]["cost"] = 1
        self.assertFalse(cm.verify_preregistration(tampered)["ok"])
        result = cm.evaluate_derivation(derivation(), tampered, observations=[observation("p00", "identical")])
        self.assertEqual(result["status"], cm.STATUS_NOT_PREREGISTERED)
        self.assertIsNone(result["model_scores"])
        self.assertIsNone(result["model_ranking"])

    def test_tampered_path_limit_also_stops_the_run(self):
        tampered = copy.deepcopy(CONFIG)
        tampered["path_constraints"]["max_operator_applications_per_derivation"] = 9
        self.assertFalse(cm.verify_preregistration(tampered)["ok"])

    def test_operator_proposed_after_seeing_the_pair_is_excluded(self):
        item = derivation()
        item["operators"][0]["proposal"] = proposal(proposed="2026-06-02", observed="2026-06-01")
        errors = cm.derivation_errors(item, CONFIG)
        self.assertTrue(any("post_hoc_exploratory" in error for error in errors), errors)

    def test_operator_proposed_for_an_already_seen_pair_is_excluded(self):
        item = derivation()
        item["operators"][0]["proposal"] = proposal(seen_pairs=["n1|n2"])
        self.assertTrue(any("seen_pairs" in error for error in cm.derivation_errors(item, CONFIG)))

    def test_missing_proposal_ledger_entry_is_treated_as_post_hoc(self):
        item = derivation()
        item["operators"][0].pop("proposal")
        self.assertTrue(any("post_hoc_exploratory" in error for error in cm.derivation_errors(item, CONFIG)))

    def test_the_config_requires_a_hash_to_exist_before_the_run(self):
        mechanism = CONFIG["preregistration"]["mechanism"]
        self.assertTrue(mechanism["must_exist_before_run"])
        self.assertEqual(len(mechanism["operator_cost_table_sha256"]), 64)


class DateHandlingTests(unittest.TestCase):
    def test_ranges_order_only_past_the_declared_threshold(self):
        threshold = CONFIG["date_handling"]["ordering_rule"]["threshold"]
        early = cm.ordering_probability({"date_earliest": -900, "date_latest": -800}, {"date_earliest": -500, "date_latest": -400})
        self.assertGreaterEqual(early["p_a_before_b"], threshold)
        overlapping = cm.ordering_probability({"date_earliest": -500, "date_latest": -100}, {"date_earliest": -400, "date_latest": 0})
        self.assertLess(overlapping["p_a_before_b"], threshold)
        self.assertLess(overlapping["p_b_before_a"], threshold)

    def test_overlapping_ranges_leave_the_derivation_unadmissible(self):
        item = derivation()
        item["nodes"][1]["dates"]["composition"] = date_object(-950, -100)
        gate = cm.check_conditions(item["operators"][0], item["edges"][0], nodes_of(item), CONFIG)
        self.assertFalse(gate["admissible"])
        self.assertIn("b", gate["unmet"])

    def test_a_surviving_witness_is_not_evidence_of_composition(self):
        item = derivation(witness_only=True)
        ordering = cm.evaluate_ordering(item["nodes"][0], item["nodes"][1], CONFIG)
        self.assertEqual(ordering["status"], "ordering_undecidable_survival_only")
        result = cm.evaluate_derivation(item, CONFIG)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertTrue(any("survival" in text or "composition" in text for text in result["missing_inputs"]), result["missing_inputs"])
        self.assertIsNone(result["model_ranking"])

    def test_date_fields_are_the_declared_uncertainty_range(self):
        self.assertEqual(CONFIG["testability"]["required_dated_fields"], ["date_earliest", "date_latest", "dating_basis"])
        fields = CONFIG["date_handling"]["fields_per_expression"]
        for field in ("date_earliest", "date_latest", "dating_basis"):
            self.assertIn(field, fields)


class RefusalTests(unittest.TestCase):
    def test_no_ranking_while_dates_are_empty(self):
        item = derivation(dates=False)
        result = cm.evaluate_derivation(item, CONFIG)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertIsNone(result["model_scores"])
        self.assertIsNone(result["model_ranking"])
        self.assertTrue(any("date_earliest" in text for text in result["missing_inputs"]), result["missing_inputs"])
        self.assertTrue(any("date_latest" in text for text in result["missing_inputs"]))
        self.assertTrue(any("dating_basis" in text for text in result["missing_inputs"]))
        self.assertGreater(result["missing_input_count"], 0)

    def test_parsimony_is_still_computed_from_the_cost_matrix_without_dates(self):
        result = cm.evaluate_derivation(derivation(op="silencing", dates=False), CONFIG)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertEqual(result["parsimony"]["operator_costs"], {"silencing": CONFIG["operator_cost_matrix"]["operators"]["silencing"]["cost"]})

    def test_default_run_publishes_the_refusal_as_a_result(self):
        result = cm.run()
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertIsNone(result["model_scores"])
        self.assertIsNone(result["model_ranking"])
        self.assertIn("dated attestation", " ".join(result["missing_inputs"]))
        self.assertEqual(result["dated_attestation_diagnostic"]["works_usable_for_priority_claims"], 0)

    def test_cli_refusal_is_printable_and_carries_no_conclusion(self):
        result = cm.run()
        self.assertIn("none asserted", result["historical_conclusion"])
        json.dumps(result)

    def test_pair_needing_more_comparable_keys_is_not_scorable(self):
        thin_a = {"D1_ontological_category": ["personal_agent"], "D2a_acknowledged_population": "many_ranked", "D4_cosmic_function": ["creating_ex_nihilo_or_by_word"], "D7b_speech_act": "confession", "D7c_discourse_genre": "hymn"}
        thin_b = dict(thin_a)
        score = cm.similarity_between(thin_a, thin_b, CONFIG)
        self.assertFalse(score["scorable"])
        self.assertIsNone(score["similarity"])
        self.assertLess(len(score["comparable_keys"]), CONFIG["dimension_similarity_rules"]["minimum_comparable_keys"])

    def test_similarity_uses_jaccard_on_set_valued_and_exact_on_single_keys(self):
        a = state(D4_cosmic_function=["creating_ex_nihilo_or_by_word", "sustaining_order"], D2b_reality_of_others="real")
        b = state(D4_cosmic_function=["creating_ex_nihilo_or_by_word"], D2b_reality_of_others="unreal")
        score = cm.similarity_between(a, b, CONFIG)
        self.assertTrue(score["scorable"])
        # functional block: D3 exact 1.0, D4 Jaccard 1/2, D2c exact 1.0
        self.assertAlmostEqual(score["block_profile"]["functional_or_pressure_prone"]["mean_similarity"], (1.0 + 0.5 + 1.0) / 3, places=6)
        # arbitrary block agrees entirely, structural block loses exactly one key
        self.assertEqual(score["block_profile"]["arbitrary_or_expressive"]["mean_similarity"], 1.0)
        self.assertAlmostEqual(score["block_profile"]["structural"]["mean_similarity"], 4 / 5, places=6)
        self.assertEqual(score["similarity_class"], "near")
        self.assertEqual(len(score["comparable_keys"]), 12)

    def test_a_single_valued_cell_that_carries_several_values_is_compared_as_a_set(self):
        """Exact match has no defined answer there, so the comparison is set equality and the cell is published."""
        key = next(k for k in DIMENSION_BLOCKS["arbitrary_or_expressive"] if k not in SET_VALUED)
        a = state(**{key: ["polytheistic_leaning", "monotheistic_leaning"]})
        b = state(**{key: ["monotheistic_leaning", "polytheistic_leaning"]})
        score = cm.similarity_between(a, b, CONFIG)
        self.assertEqual(score["similarity"], 1.0,
                         "two works carrying the same two values cannot be split by the order they were written in")
        self.assertEqual(score["keys_where_the_single_valued_rule_had_no_defined_answer"], [key])
        c = state(**{key: ["monotheistic_leaning", "something_else"]})
        self.assertLess(cm.similarity_between(a, c, CONFIG)["similarity"], 1.0,
                        "different sets are not identical merely because both carry two values")
        clean = cm.similarity_between(state(), state(), CONFIG)
        self.assertEqual(clean["keys_where_the_single_valued_rule_had_no_defined_answer"], [],
                         "a key that really holds one value is not reported as outside the rule")
        self.assertEqual(clean["block_profile"]["arbitrary_or_expressive"]["per_key"][key], 1.0,
                         "the per-key scores a chance correction needs are published with the block mean")

    def test_undecidable_keys_are_skipped_and_published(self):
        a = state(D6_temporal_nature="undecidable")
        b = state()
        score = cm.similarity_between(a, b, CONFIG)
        self.assertIn("D6_temporal_nature", score["skipped_keys"])


    def test_the_two_reading_blocks_partition_the_twelve_keys_exactly(self):
        blocks = CONFIG["dimension_similarity_rules"]["reading_blocks"]
        conceptual, discourse = blocks["conceptual"], blocks["discourse"]
        self.assertEqual(set(conceptual) & set(discourse), set())
        self.assertEqual(set(conceptual) | set(discourse), set(cm.dimension_keys(CONFIG)))
        self.assertEqual(len(conceptual), 8)
        self.assertEqual(len(discourse), 4)
        self.assertEqual(sorted(conceptual), sorted(ONTOLOGY["distinctness_status"]
                                                    ["conceptual_and_discourse_blocks"]["conceptual"]),
                         "the frame and the scorer must not disagree about which keys are conceptual")
        self.assertEqual(sorted(discourse), sorted(ONTOLOGY["distinctness_status"]
                                                   ["conceptual_and_discourse_blocks"]["discourse"]))
        self.assertIn(blocks["high_low_split"], [rule["split"] for rule in
                                                 CONFIG["dimension_similarity_rules"]["similarity_classes"].values()],
                      "the split reuses a declared class boundary rather than tuning a new one")

    def test_a_shared_state_in_a_different_speech_situation_is_a_pattern_not_a_mean(self):
        split = CONFIG["dimension_similarity_rules"]["reading_blocks"]
        a = state()
        b = state(**{key: "OTHER" for key in split["discourse"]})
        score = cm.similarity_between(a, b, CONFIG)
        self.assertEqual(score["similarity"], round(8 / 12, 6))
        self.assertTrue(score["similarity_is_a_mixture_of_two_reading_blocks"])
        self.assertEqual(score["reading_blocks"]["conceptual"]["mean_similarity"], 1.0)
        self.assertEqual(score["reading_blocks"]["conceptual"]["class"], "identical")
        self.assertEqual(score["reading_blocks"]["discourse"]["mean_similarity"], 0.0)
        self.assertEqual(score["reading_blocks"]["discourse"]["class"], "unrelated")
        self.assertEqual(score["pattern"]["pattern"], "shared_conceptual_state_differently_spoken")
        self.assertIn("not a descent warrant", score["pattern"]["reads_as"])

    def test_two_pairs_with_one_mean_and_opposite_block_shapes_do_not_read_alike(self):
        split = CONFIG["dimension_similarity_rules"]["reading_blocks"]
        four_of_eight = split["conceptual"][:4]
        genre_heavy = cm.similarity_between(state(), state(**{key: "OTHER" for key in split["conceptual"]}),
                                            CONFIG)
        state_heavy = cm.similarity_between(state(), state(**{key: "OTHER" for key in
                                                              list(split["discourse"]) + list(four_of_eight)}),
                                            CONFIG)
        self.assertEqual(genre_heavy["similarity"], state_heavy["similarity"])
        self.assertEqual(genre_heavy["similarity_class"], state_heavy["similarity_class"])
        self.assertEqual(genre_heavy["pattern"]["pattern"], "shared_genre_without_a_shared_state")
        self.assertEqual(state_heavy["pattern"]["pattern"], "shared_conceptual_state_differently_spoken")

    def test_both_blocks_sharing_is_its_own_pattern(self):
        both = cm.similarity_between(state(), state(), CONFIG)
        self.assertEqual(both["pattern"]["pattern"], "shared_state_and_shared_speech_situation")
        self.assertEqual(both["similarity"], 1.0)
        self.assertTrue(both["pattern"]["conceptual_high"])
        self.assertTrue(both["pattern"]["discourse_high"])

    def test_a_block_with_no_comparable_key_is_missing_rather_than_zero(self):
        split = CONFIG["dimension_similarity_rules"]["reading_blocks"]
        score = cm.similarity_between(state(**{key: "undecidable" for key in split["discourse"]}), state(), CONFIG)
        self.assertTrue(score["scorable"], "eight comparable conceptual keys clear the minimum of six")
        self.assertIsNone(score["reading_blocks"]["discourse"]["mean_similarity"])
        self.assertIsNone(score["reading_blocks"]["discourse"]["class"])
        self.assertEqual(score["reading_blocks"]["discourse"]["keys_compared"], [])
        self.assertEqual(score["reading_blocks"]["conceptual"]["mean_similarity"], 1.0)
        self.assertEqual(score["pattern"]["pattern"], "indeterminate_missing_block")
        self.assertEqual(score["pattern"]["missing_blocks"], ["discourse"])
        self.assertEqual(score["pattern"]["conceptual_high"], None)
        self.assertEqual(score["similarity"], 1.0,
                         "the mean is over eight keys and reads as identical; the pattern must not read that as "
                         "a whole-pair verdict")

    def test_an_unscorable_pair_still_publishes_its_block_profile(self):
        thin_a = {"D1_ontological_category": ["personal_agent"], "D2a_acknowledged_population": "many_ranked",
                  "D4_cosmic_function": ["creating_ex_nihilo_or_by_word"], "D7b_speech_act": "confession",
                  "D7c_discourse_genre": "hymn"}
        score = cm.similarity_between(thin_a, dict(thin_a), CONFIG)
        self.assertFalse(score["scorable"])
        blocks = score["reading_blocks"]
        self.assertEqual(blocks["conceptual"]["keys_compared"],
                         ["D1_ontological_category", "D2a_acknowledged_population", "D4_cosmic_function"])
        self.assertEqual(blocks["discourse"]["keys_compared"], ["D7b_speech_act", "D7c_discourse_genre"])
        self.assertEqual(blocks["conceptual"]["keys_declared"], 8)
        self.assertIsNone(score["similarity"])


class TransformationModelTests(unittest.TestCase):
    def test_restoration_breaks_monotone_decay(self):
        near_pair = cm.predicted_similarity_distribution(CONFIG, n_vertical=2)
        far_pair = cm.predicted_similarity_distribution(CONFIG, n_vertical=8)
        far_with_restoration = cm.predicted_similarity_distribution(CONFIG, n_vertical=8, n_restoration=1)
        self.assertLess(far_pair["identical"], near_pair["identical"])
        self.assertGreater(far_with_restoration["identical"], far_pair["identical"])
        self.assertGreater(cm.mean_predicted_similarity(far_with_restoration, CONFIG), cm.mean_predicted_similarity(far_pair, CONFIG))

    def test_the_monotone_nested_case_cannot_predict_the_near_class(self):
        for edges in (1, 2, 4, 8):
            decay = cm.predicted_similarity_distribution(CONFIG, n_vertical=edges, n_restoration=1, monotone_decay=True)
            v3 = cm.predicted_similarity_distribution(CONFIG, n_vertical=edges, n_restoration=1)
            self.assertEqual(decay["near"], 0.0)
            self.assertGreater(v3["near"], 0.0)

    def test_predicted_class_probabilities_are_normalised(self):
        for kwargs in ({"n_vertical": 1}, {"n_vertical": 3, "n_horizontal": 2}, {"n_vertical": 5, "n_restoration": 2}):
            classes = cm.predicted_similarity_distribution(CONFIG, **kwargs)
            self.assertAlmostEqual(sum(classes.values()), 1.0, places=5)

    def test_m4_attractor_prior_is_computed_from_the_published_alpha_vector(self):
        alpha = CONFIG["model_likelihoods"]["M4_independent_development_then_convergence"]["attractor_prior_alpha"]["alpha_vector"]
        declared = CONFIG["model_likelihoods"]["M4_independent_development_then_convergence"]["attractor_prior_alpha"]["block_concordance_propensity"]
        for block, value in alpha.items():
            self.assertAlmostEqual(value / (value + 1), declared[block], places=4)
        classes = cm.attractor_distribution(CONFIG)
        self.assertAlmostEqual(sum(classes.values()), 1.0, places=5)
        self.assertGreater(classes["partial"] + classes["far"], classes["identical"])


class MarginTests(unittest.TestCase):
    def test_the_margin_is_declared_once_and_read_by_both_stages(self):
        margin = cm.declared_margin(CONFIG)
        self.assertGreaterEqual(margin, 1.0)
        source = (ROOT / "config" / "model_comparison_v3.json").read_text(encoding="utf-8")
        self.assertEqual(
            source.count('"margin_log10_bayes_factor":'),
            1,
            "the margin must be declared in exactly one place; two declarations are two knobs",
        )
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["stage_1_symmetric_competition"]["margin_declared"], margin)
        self.assertEqual(result["margin_declared"], margin)
        self.assertEqual(result["stage_2_inheritance_licence"]["status"], result["status"])

    def test_margin_is_declared_and_applied(self):
        margin = cm.declared_margin(CONFIG)
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["status"], cm.STATUS_MARGIN_MET)
        self.assertTrue(result["models_meeting_margin_vs_M2"])
        for model in result["models_meeting_margin_vs_M2"]:
            self.assertGreaterEqual(result["log10_bayes_factor_vs_M2"][model], margin)
        self.assertTrue(result["monotone_decay_nested_case_reported"])
        self.assertEqual(
            result["stage_1_symmetric_competition"]["status"],
            cm.STATUS_NO_DECISIVE_WINNER,
            "this fixture gives M1 and M3 the same prediction, so stage 1 cannot separate the two inheritance "
            "models while stage 2 clears the no-edge null by a wide margin -- the exact case the two stages "
            "exist to keep apart",
        )

    def test_a_derivation_that_does_not_beat_the_baseline_is_not_reported_as_preferred(self):
        pairs = pair_set(MINIMUM_PAIRS, "unrelated")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["status"], cm.STATUS_NOT_PREFERRED)
        self.assertEqual(result["models_meeting_the_licence_margin"], [])
        self.assertIsNotNone(result["model_scores"])
        self.assertIn("none asserted", result["historical_conclusion"])

    def test_the_margin_must_hold_on_the_cluster_holdout_too(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        split = cm.split_by_cluster(pairs, CONFIG)
        self.assertTrue(split["ok"], split)
        self.assertTrue(split["test"])
        self.assertGreaterEqual(split["test_share_of_pairs"], CONFIG["independent_cluster_holdout"]["test_cluster_fraction"])
        for item in split["test"]:
            item["similarity_class"] = "unrelated"
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertTrue(result["models_meeting_margin_on_whole_set"])
        self.assertEqual(result["models_meeting_margin_on_held_out"], [])
        self.assertEqual(result["status"], cm.STATUS_NOT_PREFERRED)
        self.assertEqual(result["models_meeting_the_licence_margin"], [])

    def test_only_inheritance_bearing_models_can_be_preferred(self):
        pairs = pair_set(MINIMUM_PAIRS, "far", n_vertical=1)
        comparison = cm.compare_observations(pairs, CONFIG)
        self.assertTrue(comparison["ok"], comparison)
        for model in comparison["models_meeting_margin_vs_M2"]:
            self.assertIn(model, CONFIG["independent_origin_baseline_and_margin"]["inheritance_bearing_models"])

    def test_comparison_refuses_below_the_minimum_pair_count(self):
        pairs = pair_set(max(MINIMUM_PAIRS - 1, 1), "identical")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertIsNone(result["model_scores"])
        self.assertTrue(
            any("pair set:" in text for text in result["missing_inputs"]),
            result["missing_inputs"],
        )

    def test_refusal_names_the_floor_it_used_and_where_it_came_from(self):
        pairs = pair_set(3, "identical")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        text = " ".join(result["missing_inputs"])
        self.assertIn("results/model_power_simulation.json", text)
        self.assertIn("superseded analyst-set number", text)
        self.assertIn(f"the derived floor is {MINIMUM_PAIRS}", text)
        self.assertNotIn(f"the derived floor is {GATES['historical_floor_in_config']}", text)
        self.assertEqual(result["decision_gates_in_force"]["minimum_pairs"], MINIMUM_PAIRS)

    def test_background_null_cannot_be_invented(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        for pair in pairs:
            pair.pop("background_distribution")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertTrue(any("background_distribution" in text for text in result["missing_inputs"]), result["missing_inputs"])


class ClusterHoldoutTests(unittest.TestCase):
    def test_a_pair_without_cluster_labels_refuses_the_whole_set(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        pairs[7].pop("work_b")
        pairs[11].pop("witness_a")
        split = cm.split_by_cluster(pairs, CONFIG)
        self.assertFalse(split["ok"])
        self.assertEqual(split["status"], cm.STATUS_CLUSTER_KEYS_MISSING)
        self.assertEqual(sorted(split["pairs_missing_cluster_labels"]), ["p007", "p011"])
        self.assertIn("work_b", split["pairs_missing_cluster_labels"]["p007"])
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        self.assertEqual(result["status"], cm.STATUS_NOT_YET_TESTABLE)
        self.assertTrue(any("cluster_keys_missing" in text for text in result["missing_inputs"]), result["missing_inputs"])

    def test_a_work_paired_with_itself_is_not_a_cross_work_comparison(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        pairs[3]["work_b"] = pairs[3]["work_a"]
        split = cm.split_by_cluster(pairs, CONFIG)
        self.assertFalse(split["ok"])
        self.assertTrue(any("work_b (= work_a" in field for field in split["pairs_missing_cluster_labels"]["p003"]))

    def test_the_split_is_by_cluster_and_the_checks_are_run_not_assumed(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        split = cm.split_by_cluster(pairs, CONFIG)
        fraction = CONFIG["independent_cluster_holdout"]["test_cluster_fraction"]
        self.assertGreaterEqual(split["test_share_of_pairs"], fraction)
        self.assertEqual(split["test_pairs"] + split["discovery_pairs"], len(pairs))
        for label, passed in split["checks"].items():
            self.assertTrue(passed, f"{label} failed: the split does not hold the invariant it publishes")
        test_ids = {item["pair_id"] for item in split["test"]}
        discovery_ids = {item["pair_id"] for item in split["discovery"]}
        self.assertFalse(test_ids & discovery_ids)

    def test_the_split_reads_labels_only_and_never_scores(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        first = cm.split_by_cluster(pairs, CONFIG)
        for index, item in enumerate(pairs):
            item["similarity_class"] = "unrelated" if index % 2 else "identical"
        second = cm.split_by_cluster(list(reversed(pairs)), CONFIG)
        self.assertEqual(
            sorted(item["pair_id"] for item in first["test"]),
            sorted(item["pair_id"] for item in second["test"]),
            "the fold assignment must depend on the declared labels, not on the scores or the record order",
        )
        self.assertEqual(first["held_out_clusters"], second["held_out_clusters"])

    def test_a_held_out_work_never_contributes_a_discovery_pair(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        split = cm.split_by_cluster(pairs, CONFIG)
        held_out = set(split["held_out_clusters"])
        for item in split["discovery"]:
            labels, _ = cm.clusters_touched(item, CONFIG)
            self.assertFalse(labels & held_out)

    def test_the_residual_leakage_is_measured_and_published(self):
        hub_pairs = [
            observation("hub%03d" % index, "identical", works=("work-hub", f"work-spoke{index:03d}"))
            for index in range(MINIMUM_PAIRS)
        ]
        split = cm.split_by_cluster(hub_pairs, CONFIG)
        self.assertTrue(split["ok"], split)
        self.assertTrue(split["discovery_clusters_spanning_folds"])
        self.assertLess(split["isolated_test_pairs"], split["test_pairs"])
        isolated_ids = {item["pair_id"] for item in split["isolated_test"]}
        self.assertTrue(isolated_ids <= {item["pair_id"] for item in split["test"]})
        spanning = set(split["discovery_clusters_spanning_folds"])
        self.assertTrue(spanning)
        self.assertFalse(spanning & set(split["held_out_clusters"]))

    def test_a_declared_lineage_is_a_cluster_of_its_own(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        without = cm.split_by_cluster(pairs, CONFIG)
        for item in pairs:
            item["declared_lineage"] = "undeclared"
        same = cm.split_by_cluster(pairs, CONFIG)
        self.assertEqual(without["held_out_clusters"], same["held_out_clusters"], "an undeclared lineage adds no cluster")
        for item in pairs:
            item["declared_lineage"] = "family-of-" + item["work_a"]
        with_lineage = cm.split_by_cluster(pairs, CONFIG)
        self.assertTrue(with_lineage["clusters"] > without["clusters"])

    def test_the_nested_case_competes_in_nothing(self):
        rule = CONFIG["four_way_decision_rule"]
        self.assertNotIn(rule["nested_case_key"], rule["competitor_keys"])
        self.assertEqual(len(rule["competitor_keys"]), 4)
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertNotIn(rule["nested_case_key"], decision["competitors"])
        self.assertIn("nested_case_score", decision)
        self.assertEqual(decision["nested_case_reported_not_competing"], rule["nested_case_key"])


class EffectiveSampleTests(unittest.TestCase):
    def test_the_worked_cases_are_reproduced_by_the_implementation(self):
        distinct = cm.kish_effective_size([(f"w{index}a", f"w{index}b") for index in range(20)])
        self.assertEqual(distinct["effective_pairs"], 20.0)
        self.assertEqual(distinct["clusters"], 20)
        hub = cm.kish_effective_size([("hub", f"s{index}") for index in range(20)])
        self.assertEqual(hub["effective_pairs"], 1.0)
        hub_last_label = cm.kish_effective_size([(f"s{index}", "zzz-hub") for index in range(20)])
        self.assertEqual(hub_last_label["effective_pairs"], 1.0, "the assignment must not depend on which side the hub is written on")
        two_works = cm.kish_effective_size([("a", "b")] * 20)
        self.assertEqual(two_works["effective_pairs"], 1.0, "one comparison repeated is not twenty comparisons")
        spread = cm.kish_effective_size([(f"w{index % 8}", f"w{8 + index % 8}") for index in range(40)])
        self.assertGreater(spread["effective_pairs"], 4)
        self.assertLessEqual(spread["effective_pairs"], spread["clusters"])

    def test_the_published_arithmetic_is_consistent(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        pairs.append(observation("repeat", "identical", works=(pairs[0]["work_a"], "work-extra")))
        samples = cm.effective_sample_size(pairs, CONFIG)
        self.assertEqual(samples["pairs"], len(pairs))
        self.assertEqual(samples["sum_cluster_counts"], samples["pairs_counted"])
        self.assertEqual(sum(samples["cluster_counts"].values()), samples["pairs_counted"])
        self.assertEqual(samples["pairs_counted"], len(pairs))
        recomputed = samples["sum_cluster_counts"] ** 2 / samples["sum_squared_cluster_counts"]
        self.assertAlmostEqual(samples["effective_pairs"], round(recomputed, 6), places=6)
        self.assertTrue(samples["bounded_by_pair_count"])
        self.assertTrue(samples["bounded_by_cluster_count"])

    def test_a_set_of_pairs_on_one_work_does_not_pass_as_many_observations(self):
        pairs = [
            observation("same%03d" % index, "identical", works=("work-shared", f"work-other{index:03d}"))
            for index in range(MINIMUM_PAIRS)
        ]
        samples = cm.effective_sample_size(pairs, CONFIG)
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertEqual(samples["effective_pairs"], 1.0, "220 pairs that all touch one work are one observation")
        self.assertEqual(decision["pairs"], MINIMUM_PAIRS)
        self.assertEqual(decision["status"], cm.STATUS_INSUFFICIENT_PAIRS)
        self.assertTrue(any("effective independent samples" in problem for problem in decision["gate_problems"]))
        self.assertIsNone(decision["model_scores"], "a gated set gets no quotable ranking")
        self.assertIsNone(decision["ranking_by_log_likelihood"])
        verdict = decision["verdict_if_gates_were_met"]
        self.assertIsInstance(verdict, dict, "the withheld diagnostic stays on the record, labelled as not a result")
        self.assertIn(verdict["leader"], CONFIG["four_way_decision_rule"]["competitor_keys"])
        self.assertIsInstance(verdict["decisive"], bool)

    def test_the_floor_is_read_from_the_artifact_not_from_the_config_floor(self):
        self.assertEqual(GATES["source"], "results/model_power_simulation.json (status derived)")
        self.assertEqual(GATES["historical_floor_in_config"], 20)
        self.assertGreater(GATES["minimum_pairs"], 20, "the simulation must earn a floor above the analyst's number")
        self.assertLess(
            GATES["minimum_effective_samples"],
            GATES["minimum_pairs"],
            "the effective-sample floor is a different and smaller count than the pair floor",
        )
        fallback = cm.decision_gates(CONFIG, power=None)
        self.assertEqual(fallback["source"], "config floor: the power simulation has not been published")
        self.assertIsNone(fallback["minimum_effective_samples"])
        unmet = cm.decision_gates(CONFIG, power={"status": "not_derivable_on_declared_grid", "derived_minimum_pairs": None, "derived_minimum_effective_samples": None})
        self.assertIsNone(unmet["minimum_pairs"], "a null derived floor must not fall back to 20")
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        withheld = cm.decide_four_way(pairs, CONFIG, gates=unmet)
        self.assertEqual(withheld["status"], cm.STATUS_INSUFFICIENT_PAIRS)
        self.assertIsNone(withheld["model_scores"], "a grid that derives no floor refuses even a large pair set")
        self.assertTrue(any("no grid cell" in problem for problem in withheld["gate_problems"]), withheld["gate_problems"])
        self.assertTrue(any("no floor published" in problem for problem in withheld["gate_problems"]), withheld["gate_problems"])
        self.assertIsNotNone(cm.decide_four_way(pairs, CONFIG)["model_scores"], "the same set is scored once a floor is derived")


class FourWayCompetitionTests(unittest.TestCase):
    def test_m2_is_allowed_to_lose(self):
        pairs = pair_set(MINIMUM_PAIRS, "unrelated", background={"unrelated": 1.0})
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertEqual(decision["status"], cm.STATUS_DECISIVE)
        self.assertEqual(decision["leader"], "M2")
        self.assertGreaterEqual(decision["log10_bayes_factor_leader_over_runner_up"], cm.declared_margin(CONFIG))
        comparison = cm.compare_observations(pairs, CONFIG)
        self.assertEqual(comparison["stage_2_inheritance_licence"]["status"], cm.STATUS_NOT_PREFERRED)

    def test_m4_is_allowed_to_win(self):
        pairs = pair_set(MINIMUM_PAIRS, "unrelated", background={"identical": 1.0}, n_vertical=0)
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertEqual(decision["leader"], "M4")
        self.assertEqual(decision["status"], cm.STATUS_DECISIVE)
        comparison = cm.compare_observations(pairs, CONFIG)
        self.assertEqual(comparison["models_meeting_the_licence_margin"], [],
                         "convergence is never a demonstrated derivation")

    def test_no_decisive_winner_is_reachable_and_published_as_a_result(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertEqual(decision["status"], cm.STATUS_NO_DECISIVE_WINNER)
        self.assertEqual(decision["leader"], "M1")
        self.assertEqual(decision["runner_up"], "M3")
        self.assertEqual(decision["tied_at_leader"], ["M1", "M3"], "the tie is named, not averaged away")
        self.assertEqual(decision["log10_bayes_factor_leader_over_runner_up"], 0.0)
        self.assertEqual(decision["log10_bayes_factor_leader_over_runner_up_on_cluster_holdout"], 0.0)
        self.assertIn("published result", decision["reason"])
        self.assertIsNotNone(decision["model_scores"], "an inconclusive stage 1 is still scored, unlike a gated one")

    def test_stage_one_can_be_inconclusive_while_stage_two_is_met(self):
        """The two stages answer different questions, and a construction exists where they disagree.

        Two inheritance-bearing models predicting the same profile cannot be separated from each other, yet
        either of them beats the no-edge null by a wide margin. A rule that reported only stage 2 would call
        this a demonstration of vertical transmission; a rule that reported only stage 1 would call it silence.
        """
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        comparison = cm.compare_observations(pairs, CONFIG)
        self.assertEqual(comparison["stage_1_symmetric_competition"]["status"], cm.STATUS_NO_DECISIVE_WINNER)
        self.assertEqual(comparison["stage_2_inheritance_licence"]["status"], cm.STATUS_MARGIN_MET)
        self.assertEqual(
            comparison["stage_2_inheritance_licence"]["relationship_to_stage_1"],
            CONFIG["four_way_decision_rule"]["stage_2_inheritance_licence"]["relationship"],
            "the stage-2 object carries the declared relationship, so a reader cannot merge the two verdicts",
        )

    def test_the_outcome_vocabulary_is_the_declared_one(self):
        self.assertEqual(
            set(cm.STAGE_ONE_OUTCOMES),
            set(CONFIG["four_way_decision_rule"]["stage_1_symmetric_competition"]["outcomes"]),
        )

    def test_a_pair_set_below_the_derived_floor_is_insufficient_not_silently_scored(self):
        pairs = pair_set(max(MINIMUM_PAIRS - 1, 1), "identical")
        decision = cm.decide_four_way(pairs, CONFIG)
        self.assertEqual(decision["status"], cm.STATUS_INSUFFICIENT_PAIRS)
        self.assertIsNone(decision["model_scores"])
        self.assertIsNone(decision["ranking_by_log_likelihood"])
        self.assertIsNone(decision["leader"], "no name is published either, so nothing can be quoted as the winner")
        self.assertIsNone(decision["log10_bayes_factor_leader_over_runner_up"])
        self.assertIsInstance(decision["verdict_if_gates_were_met"]["decisive"], bool)

    def test_both_stages_are_published_on_every_run(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical")
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=pairs)
        for key in ("stage_1_symmetric_competition", "stage_2_inheritance_licence", "both_stages_published"):
            self.assertIn(key, result)
        self.assertTrue(result["both_stages_published"])
        self.assertIn("different", result["stages_answer_different_questions"])
        self.assertTrue(result["status_is_stage_2"], "the headline status is the licence question, and says so")


class M4BlockProfileTests(unittest.TestCase):
    """The fourth model's one distinguishing prediction, confronted with data.

    M4 admits no edges, so its likelihood is the same function of a pair set any other no-edge model would
    produce. What separates the two is the alpha vector, and that vector says something checkable: concordance
    is highest in `functional_or_pressure_prone`, middle in `structural`, lowest in `arbitrary_or_expressive`.
    The per-pair `block_profile` that tests it used to be computed, published and read by nothing.
    """

    FLAT = {"functional_or_pressure_prone": 0.50, "structural": 0.49, "arbitrary_or_expressive": 0.51}
    REVERSED = {"functional_or_pressure_prone": 0.20, "structural": 0.45, "arbitrary_or_expressive": 0.75}

    def m4_leading_set(self, block_means):
        return pair_set(MINIMUM_PAIRS, "unrelated", background={"identical": 1.0}, n_vertical=0,
                        block_means=block_means)

    def test_the_propensity_is_read_back_out_of_the_alpha_vector(self):
        alpha = CONFIG["model_likelihoods"]["M4_independent_development_then_convergence"]["attractor_prior_alpha"]["alpha_vector"]
        declared = cm.declared_block_propensities(CONFIG)
        self.assertEqual(declared, {block: round(value / (value + 1), 6) for block, value in alpha.items()})
        ordering = CONFIG["m4_block_profile_test"]["declared_ordering"]
        self.assertEqual(ordering, sorted(ordering, key=lambda block: -declared[block]),
                         "the declared ordering is the alpha vector's, not a second list that can drift from it")

    def test_the_declared_fixture_confirms_and_disqualifies_nothing(self):
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical"), CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_CONFIRMS)
        self.assertFalse(test["disqualifies_m4_from_being_named_leader"])
        self.assertGreaterEqual(test["spread_across_blocks"], test["minimum_block_spread_declared"])
        self.assertTrue(all(item["verdict"] == "holds" for item in test["adjacent_predictions"]),
                        test["adjacent_predictions"])
        self.assertIn("absence of the refutation", test["reason"],
                      "a surviving prediction is not corroboration, and the reason must say so")

    def test_a_flat_profile_is_the_falsification_hook_the_alpha_vector_declared(self):
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical", block_means=self.FLAT), CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_FLAT)
        self.assertTrue(test["disqualifies_m4_from_being_named_leader"])
        self.assertLess(test["spread_across_blocks"], test["minimum_block_spread_declared"])
        self.assertIn("falsification_hook", test["reason"])

    def test_a_reversed_profile_names_which_prediction_broke(self):
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical", block_means=self.REVERSED),
                                               CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_CONTRADICTS)
        self.assertTrue(test["disqualifies_m4_from_being_named_leader"])
        self.assertEqual(len(test["reversed_predictions"]), 2, "both adjacent predictions point the wrong way")
        self.assertEqual(test["observed_ordering"][0], "arbitrary_or_expressive",
                         "the observed ordering is published, not just a verdict token")

    SUB_BAND_REVERSAL = {"functional_or_pressure_prone": 0.70, "structural": 0.50,
                         "arbitrary_or_expressive": 0.51}
    CONTRADICTS_RAW = {"functional_or_pressure_prone": 0.70, "structural": 0.30,
                       "arbitrary_or_expressive": 0.45}
    TIED_CORRECTED = {"functional_or_pressure_prone": 0.20, "structural": 0.10,
                      "arbitrary_or_expressive": 0.08}

    def chance_table_for(self, raw_means, corrected_means):
        """A chance table that puts each block's mean excess at `corrected_means` for a fixture at `raw_means`.

        The fixtures declare one mean per block, so every key in a block carries it and the gap the table has to
        supply is the same for all of them.
        """
        dimensions = {}
        for name, keys in DIMENSION_BLOCKS.items():
            gap = round(raw_means[name] - corrected_means[name], 6)
            for key in keys:
                dimensions[key] = gap
        return {"path": "tests/fixture_chance_table.json", "sha256": "0" * 64,
                "dimensions": dimensions, "null_model": {"name": "fixture, not the corpus scan"}}

    def test_a_gap_inside_the_registered_separability_is_a_tie_not_a_refutation(self):
        """The registered basis for `minimum_block_spread` promises this; the code used to score a 0.01 gap as a reversal."""
        test = cm.attractor_block_profile_test(
            pair_set(MINIMUM_PAIRS, "identical", block_means=self.SUB_BAND_REVERSAL), CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_TIED)
        self.assertFalse(test["disqualifies_m4_from_being_named_leader"],
                         "a reversal smaller than the declared separability is a tie, and a tie refutes nothing")
        self.assertEqual(test["adjacent_predictions"][0]["verdict"], "holds")
        self.assertEqual(test["adjacent_predictions"][1]["verdict"], cm.ADJACENCY_TIE)
        self.assertGreaterEqual(test["spread_across_blocks"], test["minimum_block_spread_declared"],
                                "the blocks are not flat; one declared adjacency simply did not resolve")
        self.assertIn("registered separability", test["reason"])

    def test_a_tied_profile_leaves_the_name_with_the_model_that_declared_it(self):
        decision = cm.decide_four_way(self.m4_leading_set(self.SUB_BAND_REVERSAL), CONFIG)
        self.assertEqual(decision["status"], cm.STATUS_DECISIVE, "a tie is not a disqualification")
        self.assertEqual(decision["leader"], "M4")
        self.assertFalse(decision["m4_disqualified_from_being_named_leader"])
        self.assertEqual(decision["m4_block_profile_test"]["status"], cm.STATUS_PROFILE_TIED)

    def test_readings_that_disagree_about_disqualification_disqualify_nothing(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical", block_means=self.CONTRADICTS_RAW)
        raw = cm.attractor_block_profile_test(pairs, CONFIG)
        both = cm.attractor_block_profile_test(pairs, CONFIG,
                                               self.chance_table_for(self.CONTRADICTS_RAW, self.TIED_CORRECTED))
        self.assertEqual(raw["status"], cm.STATUS_PROFILE_CONTRADICTS, "one reading alone still calls it a reversal")
        self.assertEqual(both["readings"]["raw_similarity"]["status"], cm.STATUS_PROFILE_CONTRADICTS)
        self.assertEqual(both["readings"]["excess_over_chance"]["status"], cm.STATUS_PROFILE_TIED)
        self.assertEqual(both["status"], cm.STATUS_PROFILE_SCALE_DEPENDENT)
        self.assertFalse(both["disqualifies_m4_from_being_named_leader"],
                         "the disagreement is about the scale, so it is not evidence against the model")
        self.assertIn("choice of scale", both["reason"])
        self.assertTrue(both["chance_similarity_table"]["used"])
        self.assertEqual(both["chance_similarity_table"]["sha256"], "0" * 64,
                         "the table a verdict was reached with is identified, not just mentioned")

    def test_a_disqualification_both_readings_agree_on_still_strips_the_name(self):
        """The two-scale rule can only ever soften a disqualification, never invent one or erase an agreed one."""
        corrected = {"functional_or_pressure_prone": 0.20, "structural": 0.05, "arbitrary_or_expressive": 0.40}
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical", block_means=self.CONTRADICTS_RAW),
                                              CONFIG, self.chance_table_for(self.CONTRADICTS_RAW, corrected))
        self.assertEqual(test["status"], cm.STATUS_PROFILE_CONTRADICTS)
        self.assertTrue(test["disqualifies_m4_from_being_named_leader"])
        self.assertEqual(test["readings_that_disconfirm"], ["excess_over_chance", "raw_similarity"])

    def test_no_chance_table_means_one_reading_and_the_result_says_so(self):
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical"), CONFIG)
        self.assertFalse(test["chance_similarity_table"]["used"])
        self.assertIsNone(test["chance_similarity_table"]["sha256"])
        self.assertEqual(list(test["readings"]), ["raw_similarity"])

    def test_the_spread_and_the_sign_are_two_separate_checks(self):
        """A profile can clear the minimum spread while reversing one adjacency and holding the other."""
        mixed = {"functional_or_pressure_prone": 0.70, "structural": 0.30, "arbitrary_or_expressive": 0.45}
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical", block_means=mixed), CONFIG)
        self.assertGreaterEqual(test["spread_across_blocks"], test["minimum_block_spread_declared"],
                                "a wide spread is not a pass; the ordering is what M4 claims")
        self.assertEqual(test["status"], cm.STATUS_PROFILE_CONTRADICTS)
        self.assertEqual([item["stronger"] for item in test["reversed_predictions"]],
                         ["structural"], "only the broken adjacency is reported as reversed")

    def test_a_disconfirmed_profile_strips_the_name_and_moves_no_score(self):
        confirmed = cm.decide_four_way(self.m4_leading_set(DECLARED_BLOCK_ORDER), CONFIG)
        disconfirmed = cm.decide_four_way(self.m4_leading_set(self.REVERSED), CONFIG)
        self.assertEqual(confirmed["status"], cm.STATUS_DECISIVE)
        self.assertEqual(confirmed["leader"], "M4")
        self.assertEqual(disconfirmed["status"], cm.STATUS_NO_DECISIVE_WINNER,
                         "M4 is not named while the data contradict the claim that made it a model")
        self.assertEqual(disconfirmed["leader"], "M4", "the ranking is published unchanged; the name is withheld")
        self.assertTrue(disconfirmed["m4_disqualified_from_being_named_leader"])
        self.assertIn("no model is named", disconfirmed["reason"])
        self.assertEqual(disconfirmed["model_scores"], confirmed["model_scores"],
                         "the profile test gates a name, it does not edit a likelihood")
        self.assertEqual(disconfirmed["ranking_by_log_likelihood"], confirmed["ranking_by_log_likelihood"])

    def test_a_disconfirmed_profile_is_published_beside_the_verdict_not_buried(self):
        result = cm.evaluate_derivation(derivation(), CONFIG, observations=self.m4_leading_set(self.REVERSED))
        self.assertEqual(result["m4_block_profile_test"]["status"], cm.STATUS_PROFILE_CONTRADICTS)
        self.assertIn("m4_block_profile_test", result)

    def test_a_block_no_pair_reached_is_an_absence_not_a_zero(self):
        sparse = pair_set(MINIMUM_PAIRS, "identical",
                          block_means={"functional_or_pressure_prone": 0.70, "structural": None,
                                       "arbitrary_or_expressive": None})
        test = cm.attractor_block_profile_test(sparse, CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_NOT_TESTABLE)
        self.assertEqual(test["blocks_measured"], ["functional_or_pressure_prone"])
        self.assertEqual(test["observed_block_means"], {"functional_or_pressure_prone": 0.70},
                         "the two unmeasured blocks are absent from the means rather than sitting at 0.0")
        self.assertFalse(test["disqualifies_m4_from_being_named_leader"],
                         "a missing input must not be read as a refutation of M4")

    def test_measuring_the_extremes_without_the_middle_checks_nothing(self):
        """The two adjacent predictions both involve `structural`, so a set that never reaches it judges none."""
        ends_only = {"functional_or_pressure_prone": 0.90, "structural": None, "arbitrary_or_expressive": 0.10}
        test = cm.attractor_block_profile_test(pair_set(MINIMUM_PAIRS, "identical", block_means=ends_only), CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_NOT_TESTABLE)
        self.assertEqual(len(test["adjacent_predictions"]), 2, "both predictions are listed as unjudged")
        self.assertTrue(all(item["verdict"] == "unmeasured" for item in test["adjacent_predictions"]),
                        "a block the pair set never reached is unjudged, not a broken prediction")
        self.assertGreaterEqual(test["spread_across_blocks"], test["minimum_block_spread_declared"],
                                "the spread alone is not what makes the test runnable")

    def test_a_pair_set_with_no_block_profile_at_all_refuses_rather_than_passing(self):
        pairs = pair_set(MINIMUM_PAIRS, "identical", block_means=None)
        test = cm.attractor_block_profile_test(pairs, CONFIG)
        self.assertEqual(test["status"], cm.STATUS_PROFILE_NOT_TESTABLE)
        self.assertEqual(test["pairs_carrying_a_block_profile"], 0)
        refusal = cm.missing_required_inputs(CONFIG, observations=pairs)
        self.assertTrue(any(item.startswith("block_profile:") for item in refusal), refusal)


class InheritanceLicenceBaselinesTests(unittest.TestCase):
    """The licence has two no-edge nulls to clear, and the harder of them is the one that decides."""

    # A background distribution that makes independent origin a poor account of these pairs and convergence a
    # near-equal one: 193 `partial` pairs, which M4 predicts better than M1 does, against 27 `identical` ones,
    # which M1 predicts far better. The two effects cancel to under the margin over M4 while leaving a huge
    # margin over M2 -- which is exactly the case a single-baseline rule used to license on the strength of.
    PARTIAL_WEIGHT = 193
    BACKGROUND = {"identical": 0.01, "near": 0.01, "partial": 0.01, "far": 0.01, "unrelated": 0.96}

    def licence_split_set(self):
        pairs = []
        for index in range(MINIMUM_PAIRS):
            similarity = "partial" if index < self.PARTIAL_WEIGHT else "identical"
            pairs.append(observation(
                "p%03d" % index, similarity,
                works=(f"work-{index:03d}-a", f"work-{index:03d}-b"),
                witnesses=(f"witness-{index:03d}-a", f"witness-{index:03d}-b"),
                background=self.BACKGROUND))
        return pairs

    def test_clearing_the_independent_origin_null_alone_is_not_a_licence(self):
        comparison = cm.compare_observations(self.licence_split_set(), CONFIG)
        self.assertEqual(comparison["models_meeting_margin_vs_M2"], ["M1", "M3"])
        self.assertEqual(comparison["models_meeting_margin_vs_M4"], [])
        self.assertEqual(comparison["models_meeting_the_licence_margin"], [],
                         "a derivation that cannot beat convergence has not earned the word 'inherited'")
        self.assertEqual(comparison["stage_2_inheritance_licence"]["status"], cm.STATUS_NOT_PREFERRED)

    def test_the_binding_baseline_is_the_null_the_model_beats_by_least(self):
        comparison = cm.compare_observations(self.licence_split_set(), CONFIG)
        for model in CONFIG["independent_origin_baseline_and_margin"]["inheritance_bearing_models"]:
            margins = {"M2": comparison["log10_bayes_factor_vs_M2"][model],
                       "M4": comparison["log10_bayes_factor_vs_M4"][model]}
            self.assertEqual(comparison["licence_binding_baseline"][model], min(margins, key=margins.get))
            self.assertAlmostEqual(comparison["licence_min_margin_over_baselines"][model], min(margins.values()))

    def test_the_minimum_over_baselines_is_never_larger_than_either_margin(self):
        for pairs in (pair_set(MINIMUM_PAIRS, "identical"), self.licence_split_set()):
            comparison = cm.compare_observations(pairs, CONFIG)
            for model, value in comparison["licence_min_margin_over_baselines"].items():
                self.assertLessEqual(value, comparison["log10_bayes_factor_vs_M2"][model])
                self.assertLessEqual(value, comparison["log10_bayes_factor_vs_M4"][model])

    def test_a_licence_needs_both_baselines_and_so_m4_can_stop_one(self):
        """M4 cannot win the licence -- convergence is not a demonstrated derivation -- but it can deny one."""
        rule = CONFIG["independent_origin_baseline_and_margin"]
        self.assertEqual(sorted(rule["baselines"]), ["M2", "M4"])
        self.assertNotIn("M4", rule["inheritance_bearing_models"])
        comparison = cm.compare_observations(self.licence_split_set(), CONFIG)
        self.assertNotIn("M4", comparison["models_meeting_the_licence_margin"])
        self.assertEqual(comparison["stage_2_inheritance_licence"]["baselines"], ["M2", "M4"])

    def test_the_licence_still_clears_when_both_nulls_are_beaten(self):
        comparison = cm.compare_observations(pair_set(MINIMUM_PAIRS, "identical"), CONFIG)
        self.assertEqual(comparison["models_meeting_the_licence_margin"], ["M1", "M3"])
        self.assertEqual(comparison["stage_2_inheritance_licence"]["status"], cm.STATUS_MARGIN_MET)


class PowerSimulationTests(unittest.TestCase):
    CELLS = [40, 120]
    REPLICATIONS = 12

    def test_the_artifact_is_the_published_one_and_records_its_parameters(self):
        artifact = json.loads((ROOT / "results" / "model_power_simulation.json").read_text(encoding="utf-8"))
        self.assertEqual(artifact["produced_by"], CONFIG["power_simulation"]["regenerate_with"])
        self.assertEqual(artifact["status"], "derived")
        self.assertIn("no overrides", artifact["provenance"])
        self.assertEqual(artifact["run_overrides"], {})
        recomputed = hashlib.sha256(cm.canonical_json(artifact["declared_parameters"]).encode("utf-8")).hexdigest()
        self.assertEqual(artifact["declared_parameters_sha256"], recomputed, "the published parameters hash to the published digest")
        declared = artifact["declared_parameters"]
        self.assertEqual(declared["grid"], CONFIG["power_simulation"]["grid"])
        self.assertEqual(declared["replications_per_cell"], CONFIG["power_simulation"]["replications_per_cell"])
        self.assertEqual(declared["seed"], CONFIG["power_simulation"]["seed"])
        self.assertEqual(len(artifact["cells"]), 4 * self.declared_cell_count())

    def declared_cell_count(self):
        grid = CONFIG["power_simulation"]["grid"]
        return len(range(int(grid["from"]), int(grid["to"]) + 1, int(grid["step"])))

    def test_the_derivation_requires_every_generating_model_to_reach_the_target(self):
        artifact = json.loads((ROOT / "results" / "model_power_simulation.json").read_text(encoding="utf-8"))
        reaching = artifact["power_by_true_model_declared"]
        self.assertEqual(set(reaching), {"M1", "M2", "M3", "M4"})
        self.assertNotIn(None, reaching.values(), "a floor derived while one truth never resolves would be a partial answer")
        self.assertEqual(artifact["derived_minimum_pairs"], max(reaching.values()))
        self.assertEqual(artifact["binding_true_model"], max(reaching, key=lambda model: reaching[model]))

    def test_the_gates_the_tool_enforces_are_the_ones_the_artifact_derives(self):
        artifact = json.loads((ROOT / "results" / "model_power_simulation.json").read_text(encoding="utf-8"))
        gates = cm.decision_gates(CONFIG)
        self.assertEqual(gates["minimum_pairs"], artifact["derived_minimum_pairs"])
        self.assertEqual(gates["minimum_effective_samples"], artifact["derived_minimum_effective_samples"])

    def test_a_small_run_is_reproducible(self):
        first = cm.power_simulation(config=CONFIG, replications=self.REPLICATIONS, cells=self.CELLS)
        second = cm.power_simulation(config=CONFIG, replications=self.REPLICATIONS, cells=self.CELLS)
        self.assertEqual(first["cells"], second["cells"])
        self.assertEqual(first["declared_parameters_sha256"], second["declared_parameters_sha256"])
        self.assertIn("SMOKE RUN", first["provenance"])
        self.assertEqual(first["run_overrides"]["replications_per_cell"]["declared"], CONFIG["power_simulation"]["replications_per_cell"])

    def test_power_is_a_probability_and_each_row_publishes_its_own_noise(self):
        run = cm.power_simulation(config=CONFIG, replications=self.REPLICATIONS, cells=self.CELLS)
        for row in run["cells"]:
            self.assertGreaterEqual(row["power"], 0.0)
            self.assertLessEqual(row["power"], 1.0)
            self.assertEqual(row["decisive_and_correct"], round(row["power"] * self.REPLICATIONS))
            self.assertLessEqual(row["power_monte_carlo_standard_error"], 0.5)
            self.assertLessEqual(row["minimum_effective_samples"], row["mean_effective_pairs"])
            self.assertGreaterEqual(row["mean_test_share_of_pairs"], CONFIG["independent_cluster_holdout"]["test_cluster_fraction"] - 1e-9)

    def test_a_grid_on_which_no_truth_resolves_derives_no_floor(self):
        run = cm.power_simulation(config=CONFIG, replications=4, cells=[1])
        self.assertEqual(run["status"], "not_derivable_on_declared_grid")
        self.assertIsNone(run["derived_minimum_pairs"])
        self.assertIsNone(run["derived_minimum_effective_samples"])
        self.assertEqual(len(run["true_models_never_reaching_target_on_this_grid"]), 4)

    def test_the_simulation_declares_its_own_limits(self):
        run = cm.power_simulation(config=CONFIG, replications=self.REPLICATIONS, cells=self.CELLS)
        self.assertIn("point mass", " ".join(run["caveats"]))
        self.assertEqual(
            [item["label"] for item in run["sensitivity"]],
            ["declared", "three_witnesses_per_work", "flat_background"],
            "the three published scenarios are the three that were run",
        )
        self.assertIn("fixed cluster structure", " ".join(run["limitations"]))
        self.assertIn("none asserted", run["historical_conclusion"])


if __name__ == "__main__":
    unittest.main()
