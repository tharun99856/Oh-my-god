"""Track B model-comparison layer.

This tool compares the four competing historical models (M1 single ancestral concept then transformation,
M2 multiple independent origins, M3 regional inheritance then mixing, M4 independent development then
convergence) against the licence conditions declared in ``config/model_comparison_v3.json``.

It is a calculator and a gatekeeper, not an historian. Concretely it will not assert that any concept was
inherited, borrowed, restored or invented, and it will not emit a model score or a model ranking while the
dated, route-typed inputs it needs are missing. A refusal is published as a result with
``status: "not_yet_testable"`` and the list of missing inputs, because a silent exit is how an absent
measurement turns into an absent conclusion.

What it does:
  * computes similarity between two divine-concept states over the twelve dimension keys;
  * computes P(A precedes B) from date *ranges* and refuses to orient an edge on a survival date;
  * enforces the four operator conditions conjunctively (all four mandatory, no threshold);
  * keeps vertical inheritance and horizontal transmission as separate, non-interchangeable edge types;
  * prices a candidate derivation with the operator cost matrix and rejects over-long paths;
  * checks the preregistered SHA-256 of the operator cost table before scoring anything;
  * computes the predicted distribution over similarity classes under the probabilistic transformation model
    (which replaces the monotone "greater distance implies greater dissimilarity" prediction) and the
    likelihood of an observed pair under each model;
  * runs stage 1 as a symmetric four-way competition, where the decisive quantity is the leader's margin over
    the runner-up and `no_decisive_winner` is a published outcome, then stage 2 as the separate question of
    whether an inheritance-bearing model has earned licence language against the no-edge null;
  * folds a pair set by work, witness and lineage cluster rather than by pair, publishes the leakage check, and
    estimates the set's Kish effective sample size over its work clusters;
  * derives the pair and effective-sample floors from a power simulation over the decision rule itself
    (``--power``), so the minimum is a measured property of the rule rather than an analyst's number.

``--legacy-lexical`` preserves the v1 lexical diagnostic that this file used to be: TF-IDF cosine sanity
checks over the corpus, written to ``results/model_comparison.json``. It is an instrument diagnostic and
reports no historical finding either.

Usage:
    python tools/compare_models.py                       # model-comparison layer, current data state
    python tools/compare_models.py --derivation path.json # evaluate one candidate derivation
    python tools/compare_models.py --write-to path.json   # publish the JSON instead of printing it
    python tools/compare_models.py --power                # derive the decision-rule floors, publish the artifact
    python tools/compare_models.py --legacy-lexical       # the old lexical diagnostic
"""

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_comparison_v3.json"
SCAFFOLD_PATH = ROOT / "results" / "attestation_scaffold.csv"
POWER_ARTIFACT_PATH = ROOT / "results" / "model_power_simulation.json"
SEED = 20261031
_UNSET = object()
NO_HISTORICAL_CONCLUSION = "none asserted; this layer compares models against licence conditions, it does not settle a historical question"

# States the layer may report. Every one of them is a statement about the instrument.
STATUS_NOT_YET_TESTABLE = "not_yet_testable"
STATUS_NOT_PREREGISTERED = "not_preregistered"
STATUS_REJECTED_DERIVATION = "rejected_derivation"
STATUS_NOT_PREFERRED = "not_preferred_over_independent_origin"
STATUS_MARGIN_MET = "margin_met_no_historical_conclusion"
STATUS_DECISIVE = "decisive"
STATUS_NO_DECISIVE_WINNER = "no_decisive_winner"
STATUS_INSUFFICIENT_PAIRS = "insufficient_pairs"
STATUS_CLUSTER_KEYS_MISSING = "cluster_keys_missing"
STATUS_PROFILE_CONFIRMS = "block_ordering_confirms_declared_propensity"
STATUS_PROFILE_FLAT = "block_profile_flat_the_falsification_hook_fired"
STATUS_PROFILE_CONTRADICTS = "block_ordering_contradicts_declared_propensity"
STATUS_PROFILE_NOT_TESTABLE = "m4_block_profile_not_testable"
STATUS_PROFILE_TIED = "block_profile_did_not_resolve_the_declared_separability"
STATUS_PROFILE_SCALE_DEPENDENT = "block_profile_verdict_depends_on_the_similarity_scale"
# Outcomes that mean the data contradict the one prediction that separates M4 from a second null. A tie is not
# on this list: the registered separability says a gap smaller than it is not a refutation, and a verdict that
# changes with the scale it is read on has not contradicted anything, it has failed to measure.
STATUS_PROFILE_DISCONFIRMED = (STATUS_PROFILE_FLAT, STATUS_PROFILE_CONTRADICTS)
ADJACENCY_TIE = "tie_within_the_declared_separability"
STAGE_ONE_OUTCOMES = (STATUS_DECISIVE, STATUS_NO_DECISIVE_WINNER, STATUS_INSUFFICIENT_PAIRS, STATUS_CLUSTER_KEYS_MISSING)


# --------------------------------------------------------------------------- config


def load_config(path=None):
    path = Path(path) if path else CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def dimension_keys(config):
    return list(config["dimension_keys"]["keys"].keys())


def cardinality_map(config):
    return {key: spec["cardinality"] for key, spec in config["dimension_keys"]["keys"].items()}


def operator_names(config):
    return list(config["operator_cost_matrix"]["operators"].keys())


def operator_spec(config, name):
    return config["operator_cost_matrix"]["operators"][name]


# --------------------------------------------------------------------------- preregistration


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_payload(config):
    """The exact payload the declared hash covers: operator table subset plus path constraints."""
    scope = config["preregistration"]["mechanism"]["hash_scope"]
    operators = {
        name: {field: spec[field] for field in scope["operator_fields"]}
        for name, spec in config["operator_cost_matrix"]["operators"].items()
    }
    constraints = {
        field: config["path_constraints"][field] for field in scope["path_constraints_fields"]
    }
    return {"operators": operators, "path_constraints": constraints}


def operator_cost_table_sha256(config):
    return hashlib.sha256(canonical_json(hash_payload(config)).encode("utf-8")).hexdigest()


def verify_preregistration(config):
    computed = operator_cost_table_sha256(config)
    expected = config["preregistration"]["mechanism"].get("operator_cost_table_sha256")
    registered = config["preregistration"]["mechanism"].get("registered_at")
    problems = []
    if not expected or not isinstance(expected, str) or expected.startswith("TO_BE"):
        problems.append("preregistration.mechanism.operator_cost_table_sha256 is absent")
    elif expected != computed:
        problems.append("operator cost table hash does not match the preregistered value")
    if not registered:
        problems.append("preregistration.mechanism.registered_at is absent")
    return {"ok": not problems, "expected": expected, "computed": computed, "registered_at": registered, "problems": problems}


# --------------------------------------------------------------------------- similarity


def _as_set(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return {str(value)}


def similarity_between(state_a, state_b, config):
    """Similarity over the twelve dimension keys, per dimension_similarity_rules.

    Set-valued keys use Jaccard, single-valued keys exact match, and keys that are `undecidable` or absent on
    either side are skipped and reported as skipped. Below `minimum_comparable_keys` the pair is not scorable
    and similarity is None: no default is substituted, because a defaulted 0.0 would read as evidence for M2
    and a defaulted 1.0 as evidence for M1.

    A key the frame declares single-valued can still arrive carrying several values, and on this corpus most
    of them do. Exact match has no defined answer there, so the comparison is set equality -- identical sets
    score 1, and the order the values were written down in cannot change a score -- and the key is listed under
    `keys_where_the_single_valued_rule_had_no_defined_answer`. Comparing the stringified lists instead would
    have scored the same pair of works differently according to nothing but the order the detector emitted
    their values in.

    The twelve keys are not one kind of thing. D1-D6 say what a text claims is the case; D7a-d say what kind of
    speech act it is, which in this corpus is largely a property of English translation prose and genre
    convention. A single mean over both lets two catechisms score as conceptually alike because they share a
    genre, and lets two genuinely shared concept states score as unlike because one rendering is a hymn and the
    other a narrative. So the score is reported per reading block, and the pair is read as a pattern of the two
    blocks; the overall mean is kept only because the similarity-class grid is defined on it, and it is labelled
    as the mixture it is.
    """
    rules = config["dimension_similarity_rules"]
    card = cardinality_map(config)
    scores = []
    comparable = []
    skipped = []
    outside_the_rule = []
    for key in dimension_keys(config):
        value_a = state_a.get(key, "undecidable")
        value_b = state_b.get(key, "undecidable")
        if value_a in (None, "undecidable") or value_b in (None, "undecidable"):
            skipped.append(key)
            continue
        if card[key] == "set-valued":
            left, right = _as_set(value_a), _as_set(value_b)
            union = left | right
            if not union:
                skipped.append(key)
                continue
            scores.append(len(left & right) / len(union))
        else:
            left, right = _as_set(value_a), _as_set(value_b)
            if len(left) > 1 or len(right) > 1:
                outside_the_rule.append(key)
            scores.append(1.0 if left == right else 0.0)
        comparable.append(key)
    minimum = rules["minimum_comparable_keys"]
    if len(comparable) < minimum:
        return {
            "scorable": False,
            "similarity": None,
            "similarity_class": None,
            "comparable_keys": comparable,
            "skipped_keys": skipped,
            "reason": f"only {len(comparable)} of {len(dimension_keys(config))} keys comparable; minimum is {minimum}",
            "keys_where_the_single_valued_rule_had_no_defined_answer": sorted(outside_the_rule),
            "reading_blocks": reading_block_profile(comparable, scores, config),
        }
    value = sum(scores) / len(scores)
    blocks = reading_block_profile(comparable, scores, config)
    return {
        "scorable": True,
        "similarity": round(value, 6),
        "similarity_is_a_mixture_of_two_reading_blocks": True,
        "similarity_class": similarity_class(value, config),
        "comparable_keys": comparable,
        "skipped_keys": skipped,
        "keys_where_the_single_valued_rule_had_no_defined_answer": sorted(outside_the_rule),
        "block_profile": dimension_block_profile(comparable, scores, config),
        "reading_blocks": blocks,
        "pattern": reading_block_pattern(blocks, config),
    }


def reading_block_profile(comparable, scores, config):
    """Mean similarity within each reading block, with the keys that produced it.

    A block with no comparable key is `null` rather than 0.0 or 1.0: the pair says nothing about that block,
    and substituting either value would turn an absent measurement into evidence for one model or the other.
    """
    blocks = config["dimension_similarity_rules"]["reading_blocks"]
    profile = {}
    for name in ("conceptual", "discourse"):
        keys = blocks[name]
        pairs = [(key, score) for key, score in zip(comparable, scores) if key in keys]
        profile[name] = {
            "keys_declared": len(keys),
            "keys_compared": [key for key, _ in pairs],
            "mean_similarity": round(sum(s for _, s in pairs) / len(pairs), 6) if pairs else None,
            "class": similarity_class(sum(s for _, s in pairs) / len(pairs), config) if pairs else None,
        }
    return profile


def reading_block_pattern(blocks, config):
    """The pair read as a pattern of the two blocks, not as their average."""
    rules = config["dimension_similarity_rules"]["reading_blocks"]
    split = rules["high_low_split"]
    conceptual = blocks["conceptual"]["mean_similarity"]
    discourse = blocks["discourse"]["mean_similarity"]
    if conceptual is None or discourse is None:
        missing = [name for name, value in (("conceptual", conceptual), ("discourse", discourse))
                   if value is None]
        return {"pattern": "indeterminate_missing_block", "missing_blocks": missing,
                "reads_as": rules["patterns"]["indeterminate_missing_block"],
                "high_low_split": split, "conceptual_high": None, "discourse_high": None}
    conceptual_high = conceptual >= split
    discourse_high = discourse >= split
    key = {(True, True): "shared_state_and_shared_speech_situation",
           (True, False): "shared_conceptual_state_differently_spoken",
           (False, True): "shared_genre_without_a_shared_state",
           (False, False): "neither_block_shares"}[(conceptual_high, discourse_high)]
    return {"pattern": key, "high_low_split": split,
            "conceptual_high": conceptual_high, "discourse_high": discourse_high,
            "reads_as": rules["patterns"][key],
            "why_this_is_not_a_verdict": "the pattern names which block moved. It does not license an "
                                        "inheritance claim: `shared_genre_without_a_shared_state` is what two "
                                        "English translations of different compositions look like when the "
                                        "translator's era is the shared variable, and "
                                        "`shared_conceptual_state_differently_spoken` is what inheritance with "
                                        "transformation predicts, so both are consistent with every model in "
                                        "the comparison"}


CLASS_ORDER = ("identical", "near", "partial", "far", "unrelated")


def similarity_class(value, config):
    classes = config["dimension_similarity_rules"]["similarity_classes"]
    if value >= 1.0:
        return "identical"
    if value >= classes["near"]["split"]:
        return "near"
    if value >= classes["partial"]["split"]:
        return "partial"
    if value >= classes["far"]["split"]:
        return "far"
    return "unrelated"


def dimension_block_profile(comparable, scores, config):
    """Per-block means for one pair, with the per-key scores that produced them kept alongside.

    `per_key` is not decoration. The alpha vector declares a concordance propensity per dimension, so a block's
    chance-corrected value is the mean of its dimensions' excesses; pooling pair means first and subtracting a
    per-dimension baseline second would compare a quantity against a number measured on a different conditioning.
    """
    blocks = config["dimension_similarity_rules"]["dimension_blocks"]
    profile = {}
    for name, keys in blocks.items():
        pairs = [(key, score) for key, score in zip(comparable, scores) if key in keys]
        if pairs:
            profile[name] = {"keys_compared": [key for key, _ in pairs],
                             "per_key": {key: round(score, 6) for key, score in pairs},
                             "mean_similarity": round(sum(s for _, s in pairs) / len(pairs), 6)}
    return profile


# --------------------------------------------------------------------------- dates


def date_object_missing_fields(date_obj, config, which="composition"):
    """Which of the declared date fields an expression's date object still lacks."""
    if not isinstance(date_obj, dict):
        return list(config["testability"]["required_dated_fields"]) + ["survival_or_composition", "reference"]
    missing = []
    for field in config["testability"]["required_dated_fields"]:
        if date_obj.get(field) in (None, "", "undated"):
            missing.append(field)
    earliest, latest = date_obj.get("date_earliest"), date_obj.get("date_latest")
    if isinstance(earliest, int) and isinstance(latest, int) and latest < earliest:
        missing.append("date_latest_before_date_earliest")
    basis = date_obj.get("dating_basis")
    if basis and basis not in _dating_bases(config):
        missing.append("dating_basis_not_declared")
    if not date_obj.get("reference"):
        missing.append("reference")
    if not date_obj.get("survival_or_composition"):
        missing.append("survival_or_composition")
    if which == "composition" and date_obj.get("survival_or_composition") in ("witness_survival", "edition_or_translation"):
        missing.append("composition_range_absent_survival_is_not_composition")
    return missing


def _dating_bases(config):
    text = config["date_handling"]["fields_per_expression"]["dating_basis"]
    listing = text.split("One of:")[-1]
    return {part.strip() for part in listing.split("|") if part.strip()}


def ordering_probability(range_a, range_b):
    """Exact enumeration of year pairs under a uniform density over each range.

    Returns P(A compositionally precedes B). The number is a consequence of the two ranges, not a judgement.
    """
    a = list(range(int(range_a["date_earliest"]), int(range_a["date_latest"]) + 1))
    b = list(range(int(range_b["date_earliest"]), int(range_b["date_latest"]) + 1))
    total = len(a) * len(b)
    if not total:
        return {"p_a_before_b": None, "p_b_before_a": None, "pairs": 0}
    before = sum(1 for ta in a for tb in b if ta < tb)
    after = sum(1 for ta in a for tb in b if ta > tb)
    return {"p_a_before_b": before / total, "p_b_before_a": after / total, "pairs": total}


def evaluate_ordering(node_a, node_b, config):
    threshold = config["date_handling"]["ordering_rule"]["threshold"]
    range_a = (node_a.get("dates") or {}).get("composition")
    range_b = (node_b.get("dates") or {}).get("composition")
    survival_only = False
    if not range_a or not range_b:
        if (node_a.get("dates") or {}).get("witness") and (node_b.get("dates") or {}).get("witness"):
            survival_only = True
    if survival_only:
        return {"status": "ordering_undecidable_survival_only", "note": "only witness or recording dates are present; an earlier surviving witness is not evidence of earlier composition"}
    for node, label in ((node_a, "a"), (node_b, "b")):
        missing = date_object_missing_fields((node.get("dates") or {}).get("composition"), config)
        if missing:
            return {"status": "date_inputs_missing", "node": label, "missing": missing}
    order = ordering_probability(range_a, range_b)
    if order["p_a_before_b"] >= threshold:
        direction = "a_before_b"
    elif order["p_b_before_a"] >= threshold:
        direction = "b_before_a"
    else:
        direction = None
    return {"status": "ordered" if direction else "ordering_undecidable", "direction": direction, **order}


# --------------------------------------------------------------------------- edge typing


def edge_type_errors(edge, config):
    """Vertical inheritance and horizontal transmission are separate types with separate evidence.

    A missing, multi-valued or conflated type is rejected, and an edge may not satisfy one type's evidence
    requirement with the other type's evidence.
    """
    typing = config["edge_typing"]
    errors = []
    declared = edge.get("edge_type")
    if declared is None:
        errors.append("edge_type_missing")
    elif isinstance(declared, list):
        if len(declared) > 1:
            errors.append("edge_type_conflated: one edge may not carry both descent and contact")
        else:
            declared = declared[0]
    if isinstance(declared, str):
        if declared not in ("vertical_inheritance", "horizontal_transmission"):
            errors.append(f"edge_type_illegal:{declared}")
            return errors
        block = typing[declared]
        subtype = edge.get("subtype")
        if subtype not in block["subtypes"]:
            errors.append(f"edge_subtype_undeclared:{declared}:{subtype}")
        if declared == "vertical_inheritance":
            if not edge.get("descent_evidence"):
                errors.append("vertical_edge_lacks_descent_evidence_independent_of_the_states_being_explained")
                if edge.get("route_evidence"):
                    errors.append("vertical_edge_argued_from_contact_evidence_alone: horizontal evidence may not satisfy a descent claim")
            else:
                errors.extend(descent_basis_errors(edge, config))
                if edge.get("ambiguous_contact_route"):
                    errors.append("vertical_edge_has_a_documented_contact_route_alone: report it as edge_type_ambiguous, not as descent")
        if declared == "horizontal_transmission":
            if not edge.get("route_evidence"):
                errors.append("horizontal_edge_lacks_route_evidence")
            if not edge.get("direction_argument"):
                errors.append("horizontal_edge_lacks_direction_argument")
            if edge.get("descent_evidence") and not edge.get("route_evidence"):
                errors.append("horizontal_edge_argued_from_descent_evidence_alone: descent is not a contact route")
    return errors


def descent_basis_errors(edge, config):
    """A descent claim must rest on a warrant that exists independently of the similarity being explained."""
    allowed = set(config["edge_typing"]["vertical_inheritance"]["acceptable_descent_bases"])
    errors = []
    for item in edge.get("descent_evidence") or []:
        basis = item.get("basis") if isinstance(item, dict) else None
        if basis is None:
            errors.append("descent_evidence_item_lacks_declared_basis")
        elif basis == "conceptual_similarity":
            errors.append("descent_evidence_from_conceptual_similarity_rejected: that is the thing the edge is supposed to explain")
        elif basis not in allowed:
            errors.append(f"descent_evidence_basis_not_declared:{basis}")
    return errors


def edge_is_ambiguous(edge, config):
    errors = edge_type_errors(edge, config)
    return any(error.startswith(("edge_type_missing", "edge_type_conflated")) for error in errors)


# --------------------------------------------------------------------------- operator conditions


def check_conditions(operator_assertion, edge, nodes_by_id, config):
    """The four conditions, evaluated conjunctively. All four are mandatory; there is no threshold.

    The condition count is reported for transparency and licenses nothing at any count below four. A
    condition whose inputs are absent evaluates to None (`not_evaluable`) rather than False, so that a missing
    measurement is published as a missing input and not silently scored as a failed test.
    """
    conditions = config["operator_discipline"]["conditions"]
    applies_to = operator_assertion.get("applies_to") or []
    left = nodes_by_id.get(applies_to[0]) if len(applies_to) > 0 else None
    right = nodes_by_id.get(applies_to[1]) if len(applies_to) > 1 else None
    out = {}

    def locator_ok(node):
        return bool(node) and bool(node.get("attested")) and bool(node.get("locator")) and bool(node.get("expression_id"))

    out["a"] = bool(locator_ok(left) and locator_ok(right))
    ordering = evaluate_ordering(left, right, config) if (left and right) else {"status": "nodes_missing"}
    if ordering.get("status") in ("date_inputs_missing", "ordering_undecidable_survival_only", "nodes_missing"):
        out["b"] = None
    elif ordering.get("direction") == "a_before_b":
        out["b"] = True
    else:
        out["b"] = False
    out["c"] = not edge_type_errors(edge, config)
    out["d"] = bool(operator_assertion.get("independent_witness")) or bool(edge.get("independent_witness"))
    unmet = [key for key in ("a", "b", "c", "d") if out[key] is False]
    not_evaluable = [key for key in ("a", "b", "c", "d") if out[key] is None]
    return {
        "conditions": out,
        "met_count": sum(1 for value in out.values() if value is True),
        "unmet": unmet,
        "unmet_names": [conditions[key]["name"] for key in unmet],
        "not_evaluable": not_evaluable,
        "ordering": ordering,
        "admissible": all(value is True for value in out.values()),
        "decision_rule": config["operator_discipline"]["decision"]["mode"],
    }


def operator_evidence_gaps(operator_assertion, config):
    name = operator_assertion.get("operator")
    if name not in config["operator_cost_matrix"]["operators"]:
        return [f"unknown_operator:{name}"]
    spec = operator_spec(config, name)
    evidence = operator_assertion.get("evidence") or {}
    gaps = []
    for item in spec["required_evidence"]:
        entry = evidence.get(item)
        if entry in (None, "", [], {}):
            gaps.append(f"{name}: missing required evidence — {item}")
    if spec.get("requires_original_language_evidence") and not (operator_assertion.get("original_language_witness") or evidence.get("original_language_witness")):
        gaps.append(f"{name}: requires original-language evidence, English rendering is inadmissible")
    return gaps


def proposal_is_post_hoc(operator_assertion, config):
    proposal = operator_assertion.get("proposal") or {}
    if not proposal:
        return True, "no operator proposal ledger entry: assertion is unregistered"
    if not proposal.get("proposal_note_sha256"):
        return True, "proposal ledger entry has no note hash"
    proposed, observed = proposal.get("proposed_at"), proposal.get("observed_at")
    if not proposed or not observed:
        return True, "proposal ledger entry lacks proposed_at or observed_at"
    if proposal.get("proposed_before_observation") is not True:
        return True, "proposal does not declare proposed_before_observation"
    if str(proposed) >= str(observed):
        return True, f"proposed_at ({proposed}) is not earlier than observed_at ({observed})"
    seen = set(proposal.get("seen_pairs") or [])
    pair_id = operator_assertion.get("pair_id") or "|".join(operator_assertion.get("applies_to") or [])
    if pair_id in seen:
        return True, "the pair was already in seen_pairs when the operator was proposed"
    return False, None


# --------------------------------------------------------------------------- derivation validation and parsimony


def derivation_errors(derivation, config):
    errors = []
    operators = derivation.get("operators") or []
    edges = {edge.get("edge_id"): edge for edge in derivation.get("edges") or []}
    nodes_by_id = {node.get("node_id"): node for node in derivation.get("nodes") or []}
    constraints = config["path_constraints"]

    used_edge_ids = set()
    for assertion in operators:
        name = assertion.get("operator")
        if name not in config["operator_cost_matrix"]["operators"]:
            errors.append(f"unknown_operator:{name}")
            continue
        spec = operator_spec(config, name)
        edge = edges.get(assertion.get("edge_id"))
        if edge is None:
            errors.append(f"{name}: cites no declared edge_id, so the operator has no typed route")
            continue
        used_edge_ids.add(assertion.get("edge_id"))
        errors.extend(edge_type_errors(edge, config))
        if edge.get("edge_type") not in spec["permitted_edge_types"]:
            errors.append(f"{name}: not permitted on edge_type={edge.get('edge_type')}")
        if edge.get("edge_type") == "horizontal_transmission":
            allowed_subtypes = spec.get("permitted_horizontal_subtypes", "any")
            if allowed_subtypes != "any" and edge.get("subtype") not in allowed_subtypes:
                errors.append(f"{name}: not permitted on horizontal subtype={edge.get('subtype')}; this operator is documented only on {allowed_subtypes}")
        errors.extend(operator_evidence_gaps(assertion, config))
        gate = check_conditions(assertion, edge, nodes_by_id, config)
        if gate["unmet"]:
            errors.append(
                f"{name}: operator conditions are conjunctive, unmet = {','.join(gate['unmet'])} ({'; '.join(gate['unmet_names'])}); three of four is not a transformation claim"
            )
        reported = assertion.get("conditions") or {}
        for key, expected in gate["conditions"].items():
            if expected is None:
                continue
            if key in reported and bool(reported[key]) != expected:
                errors.append(f"{name}: condition {key} reported {reported[key]} but evaluates to {expected}")
        post_hoc, why = proposal_is_post_hoc(assertion, config)
        if post_hoc:
            errors.append(f"{name}: post_hoc_exploratory — {why}")

    applications = [assertion.get("operator") for assertion in operators if assertion.get("operator") in config["operator_cost_matrix"]["operators"]]
    if len(applications) > constraints["max_operator_applications_per_derivation"]:
        errors.append(f"path_length {len(applications)} exceeds max_operator_applications_per_derivation = {constraints['max_operator_applications_per_derivation']}")
    if len(applications) > constraints["max_operator_applications_per_pair_for_a_reported_derivation"]:
        third = applications[constraints["max_operator_applications_per_pair_for_a_reported_derivation"]]
        node = (operators[constraints["max_operator_applications_per_pair_for_a_reported_derivation"]] or {}).get("applies_to", [])
        attested = bool(nodes_by_id.get(node[0], {}).get("attested")) if node else False
        if not attested:
            errors.append(
                f"reported_derivation_length {len(applications)} exceeds {constraints['max_operator_applications_per_pair_for_a_reported_derivation']} and the intermediate node before '{third}' is unattested"
            )
    per_operator = {}
    for name in applications:
        per_operator[name] = per_operator.get(name, 0) + 1
    for name, count in per_operator.items():
        cap = operator_spec(config, name)["max_applications_per_path"]
        if count > cap:
            errors.append(f"{name}: applied {count} times, max_applications_per_path = {cap}")

    unattested = [node.get("node_id") for node in nodes_by_id.values() if node.get("node_id") not in _endpoint_ids(operators) and not node.get("attested")]
    if len(unattested) > constraints["max_unattested_intermediate_nodes"]:
        errors.append(f"unattested intermediate nodes {unattested} exceed max_unattested_intermediate_nodes = {constraints['max_unattested_intermediate_nodes']}")

    discriminating = [name for name in applications if operator_spec(config, name)["may_alone_support_a_derivation"]]
    if applications and not discriminating:
        errors.append("derivation is carried only by attractor-confusable operators (may_alone_support_a_derivation = false)")
    for edge_id, edge in edges.items():
        if edge_id not in used_edge_ids:
            errors.append(f"edge {edge_id} declared but unused by any operator")
    return errors


def _endpoint_ids(operators):
    ids = set()
    for assertion in operators:
        for node in assertion.get("applies_to") or []:
            ids.add(node)
    return ids


def derivation_parsimony(derivation, config):
    """Parsimony is the sum of operator costs plus the unattested-intermediate penalty per unattested node."""
    constraints = config["path_constraints"]
    operator_costs = {}
    total = 0.0
    for assertion in derivation.get("operators") or []:
        name = assertion.get("operator")
        spec = operator_spec(config, name)
        operator_costs[name] = operator_costs.get(name, 0) + spec["cost"]
        total += spec["cost"]
    nodes = derivation.get("nodes") or []
    endpoints = _endpoint_ids(derivation.get("operators") or [])
    unattested = [node for node in nodes if node.get("node_id") not in endpoints and not node.get("attested")]
    penalty = len(unattested) * constraints["unattested_intermediate_penalty_cost"]
    return {
        "total_cost": total + penalty,
        "operator_costs": operator_costs,
        "operator_subtotal": total,
        "unattested_intermediate_nodes": [node.get("node_id") for node in unattested],
        "unattested_intermediate_penalty": penalty,
        "path_length": len(derivation.get("operators") or []),
        "cost_semantics": config["operator_cost_matrix"]["cost_semantics"],
    }


# --------------------------------------------------------------------------- probabilistic transformation model


def _poisson_truncated(lam, k_max):
    pmf = [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(k_max + 1)]
    total = sum(pmf)
    if total <= 0:
        return [1.0] + [0.0] * k_max
    return [value / total for value in pmf]


def predicted_similarity_distribution(config, n_vertical=0, n_horizontal=0, n_restoration=0, monotone_decay=False):
    """Distribution over similarity classes for a pair, given dated edges and contact — not a decay curve.

    Each operator fires on each edge as a thinned Poisson process with its declared rate; an application
    multiplies the retained similarity by its declared retention. Horizontal edges carry a declared rate
    factor; restoration, revival and back-borrowing edges reset similarity toward the archived witness with a
    declared probability, which is what puts mass back at the top of the distribution at large distance and
    is the mechanism the monotone-decay prediction cannot express. Similarity is discretised on the declared
    grid; the result is deterministic arithmetic on the declared parameters, not a measurement.
    """
    grid = config["implementation_grid"]
    step = grid["similarity_grid_step"]
    bins = round(1 / step) + 1
    k_max = grid["operator_application_truncation"]
    params = config["edge_rate_parameters"]
    operators = config["operator_cost_matrix"]["operators"]
    edge_count = n_vertical + params["horizontal_lambda_factor"] * n_horizontal

    if monotone_decay:
        lam_sum = sum(spec["prior_lambda_per_edge"] for spec in operators.values())
        rho_mean = math.exp(sum(math.log(spec["retention_rho"]) for spec in operators.values()) / len(operators))
        total_edges = max(n_vertical + n_horizontal, 1)
        pmf = _poisson_truncated(lam_sum * edge_count, k_max * total_edges)
        dist = {}
        for k, prob in enumerate(pmf):
            if prob <= 0:
                continue
            idx = min(bins - 1, max(0, round((rho_mean ** k) / step)))
            dist[idx] = dist.get(idx, 0.0) + prob
    else:
        dist = {bins - 1: 1.0}
        for spec in operators.values():
            pmf = _poisson_truncated(spec["prior_lambda_per_edge"] * edge_count, k_max)
            nxt = {}
            for idx, prob in dist.items():
                if prob <= 0:
                    continue
                base = idx * step
                for k, event_prob in enumerate(pmf):
                    if event_prob <= 0:
                        continue
                    value = base if k == 0 else base * (spec["retention_rho"] ** k)
                    new_idx = min(bins - 1, max(0, round(value / step)))
                    nxt[new_idx] = nxt.get(new_idx, 0.0) + prob * event_prob
            dist = nxt
        if n_restoration:
            reset = min(params["restoration_reset_probability"] * n_restoration, params["restoration_reset_cap"])
            dist = {idx: prob * (1 - reset) for idx, prob in dist.items()}
            dist[bins - 1] = dist.get(bins - 1, 0.0) + reset
    return _bin_distribution_to_classes(dist, step, bins, config)


def _bin_distribution_to_classes(dist, step, bins, config):
    out = {name: 0.0 for name in CLASS_ORDER}
    for idx, prob in dist.items():
        value = min(round(idx * step, 10), 1.0)
        out[similarity_class(value, config)] += prob
    total = sum(out.values()) or 1.0
    return {name: round(value / total, 8) for name, value in out.items()}


def mean_predicted_similarity(classes, config):
    midpoints = config["implementation_grid"]["class_midpoints"]
    return round(sum(classes.get(name, 0.0) * midpoints[name] for name in midpoints), 6)


def attractor_distribution(config):
    """M4's declared distribution over similarity classes: the exact Poisson-binomial of the twelve keys'
    concordances, each drawn independently at its block's declared propensity, mapped onto the declared
    classes by key count.

    The propensity is `alpha / (alpha + 1)` from the published alpha vector, so a reader can recompute it. No
    data enters this; it is the shape the convergence hypothesis commits to before any pair is scored. Each
    key is treated as concordant or not: on a set-valued key partial overlap counts as concordant, which is a
    declared approximation of the same model that prices similarity in the grid.
    """
    alpha = config["model_likelihoods"]["M4_independent_development_then_convergence"]["attractor_prior_alpha"]["alpha_vector"]
    blocks = config["dimension_similarity_rules"]["dimension_blocks"]
    dist = {0: 1.0}
    for block, keys in blocks.items():
        propensity = alpha[block] / (alpha[block] + 1)
        for _ in keys:
            nxt = {}
            for count, prob in dist.items():
                nxt[count] = nxt.get(count, 0.0) + prob * (1 - propensity)
                nxt[count + 1] = nxt.get(count + 1, 0.0) + prob * propensity
            dist = nxt
    out = {name: 0.0 for name in CLASS_ORDER}
    for count, prob in dist.items():
        value = count / sum(len(keys) for keys in blocks.values())
        out[similarity_class(min(round(value, 10), 1.0), config)] += prob
    total = sum(out.values()) or 1.0
    return {name: round(value / total, 8) for name, value in out.items()}


def declared_block_propensities(config):
    """q(block) = alpha / (alpha + 1) for each dimension block, read back out of the published alpha vector."""
    alpha = config["model_likelihoods"]["M4_independent_development_then_convergence"]["attractor_prior_alpha"]["alpha_vector"]
    return {block: round(value / (value + 1), 6) for block, value in alpha.items()}


def observed_block_profile(observations, chance_similarity=None):
    """Per-block means over a pair set, pooled by dimension, with the chance correction done at the dimension.

    Two weightings, both deliberate. The raw block mean weights by keys compared rather than by pairs, because
    the alpha vector declares a propensity per dimension key: a pair that compared three keys in a block has
    three things to say there and one where it compared one. The excess is averaged over the dimensions the
    block declares, because that is the quantity the model claims and the same quantity the corpus-wide scan
    reports; subtracting a per-dimension chance line from a pair-pooled block mean would set a number measured
    over this pair set against a baseline measured over whichever pairs the scan happened to reach.

    A block no pair reached stays absent rather than 0.0 -- an absent measurement is not evidence of discordance.
    """
    totals = {}
    for observation in observations:
        for name, entry in (observation.get("block_profile") or {}).items():
            per_key = entry.get("per_key") or {}
            keys = entry.get("keys_compared") or sorted(per_key)
            if not keys:
                continue
            bucket = totals.setdefault(name, {"keys": 0, "weighted": 0.0, "pairs": 0, "by_key": {}})
            bucket["keys"] += len(keys)
            bucket["pairs"] += 1
            mean = entry.get("mean_similarity")
            if mean is not None:
                bucket["weighted"] += len(keys) * mean
            for key, score in per_key.items():
                cell = bucket["by_key"].setdefault(key, {"score": 0.0, "pairs": 0})
                cell["score"] += score
                cell["pairs"] += 1
    out = {}
    for name, bucket in sorted(totals.items()):
        if not bucket["keys"]:
            continue
        dimensions = {key: {"mean_similarity": round(cell["score"] / cell["pairs"], 6),
                            "pairs_comparing_this_dimension": cell["pairs"]}
                      for key, cell in sorted(bucket["by_key"].items()) if cell["pairs"]}
        row = {"mean_similarity": round(bucket["weighted"] / bucket["keys"], 6),
               "keys_compared": bucket["keys"], "pairs_contributing": bucket["pairs"],
               "dimensions_measured": sorted(dimensions), "per_dimension": dimensions}
        corrected = []
        for key, cell in dimensions.items():
            line = (chance_similarity or {}).get(key)
            if line is None:
                continue
            cell["chance_similarity"] = line
            cell["excess_over_chance"] = round(cell["mean_similarity"] - line, 6)
            corrected.append(cell["excess_over_chance"])
        if corrected:
            row["mean_excess_over_chance"] = round(sum(corrected) / len(corrected), 6)
            row["dimensions_with_a_chance_line"] = len(corrected)
            row["dimensions_without_a_chance_line"] = sorted(set(dimensions) - {
                key for key, cell in dimensions.items() if "chance_similarity" in cell})
        out[name] = row
    return out


def adjacency_verdicts(means, config):
    """The declared adjacent block predictions read off whatever means are supplied. Three classes, not two.

    `holds` requires a gap of at least `minimum_block_spread` in the predicted direction; a gap smaller than
    that, in either direction, is a tie; only a gap of that size backwards is a reversal. The registered basis
    for that number already says so -- "a reversal smaller than it is a tie, not a refutation" -- and a test
    that scores a 0.0003 gap as a refutation fires on the instrument rather than on the traditions.
    """
    minimum_spread = config["m4_block_profile_test"]["minimum_block_spread"]
    adjacent = []
    for stronger, weaker in config["m4_block_profile_test"]["declared_adjacent_predictions"]:
        if stronger not in means or weaker not in means:
            adjacent.append({"stronger": stronger, "weaker": weaker, "observed_difference": None,
                             "verdict": "unmeasured", "reason": "one of the two blocks carries no comparable key"})
            continue
        difference = round(means[stronger] - means[weaker], 6)
        verdict = ("holds" if difference >= minimum_spread
                   else ADJACENCY_TIE if abs(difference) < minimum_spread
                   else "reversed")
        adjacent.append({"stronger": stronger, "weaker": weaker, "observed_difference": difference,
                         "verdict": verdict})
    return adjacent


def _profile_status(adjacent, spread, minimum_spread):
    """One status from one scale's means: flat, contradicted, tied, confirmed, or nothing measured."""
    judged = [item for item in adjacent if item["verdict"] != "unmeasured"]
    if not judged:
        return STATUS_PROFILE_NOT_TESTABLE
    if spread is not None and spread < minimum_spread:
        return STATUS_PROFILE_FLAT
    if any(item["verdict"] == "reversed" for item in judged):
        return STATUS_PROFILE_CONTRADICTS
    if any(item["verdict"] == ADJACENCY_TIE for item in judged):
        return STATUS_PROFILE_TIED
    return STATUS_PROFILE_CONFIRMS


CHANCE_TABLE_PATH = ROOT / "results/dimension_anomalies.json"


def corpus_chance_similarity(path=CHANCE_TABLE_PATH):
    """The per-dimension chance line from the anomaly scan, with the sha256 of the file it came from.

    Returns None when the scan has not been run, in which case the block-profile test reads raw similarity only
    and says so. The path is deliberately not configurable by the analyst: a gate that changes depending on
    which artifact happens to be on disk is a gate that needs the artifact's identity published with its verdict.
    """
    if not path.exists():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    graph = report.get("pair_graph") or {}
    dimensions = {key: value for key, value in (graph.get("chance_similarity_per_dimension") or {}).items()
                  if value is not None}
    if not dimensions:
        return None
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "dimensions": dimensions,
            "conditioning": graph.get("conditioning"),
            "null_model": report.get("null_model", {})}


def attractor_block_profile_test(observations, config, chance_table=None):
    """Score the single claim that makes M4 a theory rather than a second null.

    M4 admits no edges, so its likelihood is the same function of a pair set that any other no-edge model
    would produce. What separates the two is the alpha vector, and that vector predicts an ordering:
    `functional_or_pressure_prone` most concordant, `structural` middle, `arbitrary_or_expressive` least.
    The per-pair `block_profile` that would test it was computed and published and read by nothing, so M4
    could lose stage 1 without ever being asked whether its distinguishing prediction had come true.

    A flat or reversed profile disqualifies M4 from being *named* the decisive leader. It changes no
    likelihood and removes M4 from no ranking. Under simulation the pair carries no `block_profile` and the
    test reports `m4_block_profile_not_testable`, which is why the published power floors do not move: a
    gate that quietly reshaped a calibrated floor would make the calibration a statement about a different
    rule than the one now in force.

    Two readings are run when a per-dimension chance table is supplied, one on raw mean similarity and one on
    mean excess over that table. They are not two tests of the same claim; they are the same claim on two
    scales, and a block whose dimensions sit on one dominant value is concordant on the first and empty on the
    second. If the readings land on different sides of the disqualification line, no disqualification is
    issued and the status says which scale would have to be chosen to get one. `chance_table` is
    `corpus_chance_similarity()`'s return, and the file's sha256 travels into the published verdict with it,
    because a reading that depends on which artifact is on disk has to say which artifact it read.
    """
    rule = config["m4_block_profile_test"]
    minimum_spread = rule["minimum_block_spread"]
    chance_similarity = (chance_table or {}).get("dimensions")
    declared = declared_block_propensities(config)
    observed = observed_block_profile(observations, chance_similarity)
    predicted_order = list(rule["declared_ordering"])
    scales = {"raw_similarity": {name: row["mean_similarity"] for name, row in observed.items()}}
    corrected = {name: row["mean_excess_over_chance"] for name, row in observed.items()
                 if "mean_excess_over_chance" in row}
    if corrected:
        scales["excess_over_chance"] = corrected
    result = {
        "declared_propensity": declared,
        "declared_ordering": predicted_order,
        "observed_block_means": scales["raw_similarity"],
        "keys_compared_per_block": {name: value["keys_compared"] for name, value in observed.items()},
        "pairs": len(observations),
        "pairs_carrying_a_block_profile": sum(1 for item in observations if item.get("block_profile")),
        "minimum_block_spread_declared": minimum_spread,
        "chance_similarity_table": {
            "used": bool(corrected),
            "dimensions_supplied": len(chance_similarity or {}),
            "path": (chance_table or {}).get("path"),
            "sha256": (chance_table or {}).get("sha256"),
            "conditioning": (chance_table or {}).get("conditioning"),
            "null_model": (chance_table or {}).get("null_model") or None,
            "blocks_corrected": sorted(corrected),
        },
        "disqualifies_m4_from_being_named_leader": False,
    }
    if len(observed) < 2:
        return {**result, "status": STATUS_PROFILE_NOT_TESTABLE,
                "readings": {label: {"block_means": means, "status": STATUS_PROFILE_NOT_TESTABLE}
                             for label, means in scales.items()},
                "blocks_measured": sorted(observed),
                "blocks_without_a_measurement": sorted(set(declared) - set(observed)),
                "reason": "fewer than two dimension blocks carry a comparable key in this pair set, so the "
                          "ordering M4 declares cannot be checked against it. This is a missing input, not a "
                          "pass: a test that reports nothing whenever the data are thin is a test that never runs."}
    readings = {}
    for label, means in scales.items():
        spread = round(max(means.values()) - min(means.values()), 6) if len(means) > 1 else None
        adjacent = adjacency_verdicts(means, config)
        readings[label] = {
            "block_means": means,
            "spread_across_blocks": spread,
            "ordering_observed": sorted(means, key=lambda name: -means[name]),
            "adjacent_predictions": adjacent,
            "status": _profile_status(adjacent, spread, minimum_spread),
        }
    result.update({"observed_block_means": scales["raw_similarity"],
                   "spread_across_blocks": readings["raw_similarity"]["spread_across_blocks"],
                   "adjacent_predictions": readings["raw_similarity"]["adjacent_predictions"],
                   "observed_ordering": readings["raw_similarity"]["ordering_observed"],
                   "observed_block_profile": observed,
                   "readings": readings,
                   "blocks_without_a_measurement": sorted(set(declared) - set(observed))})
    judged = {label: row["status"] for label, row in readings.items()
              if row["status"] != STATUS_PROFILE_NOT_TESTABLE}
    if len(judged) > 1:
        result["readings_that_disconfirm"] = sorted(label for label, read in judged.items()
                                                    if read in STATUS_PROFILE_DISCONFIRMED)
    if not judged:
        return {**result, "status": STATUS_PROFILE_NOT_TESTABLE,
                "reason": "the pair set measures blocks, but never two of the three the alpha vector ranks "
                          "together, so no adjacent prediction has an observable sign"}
    distinct = sorted(set(judged.values()))
    if len(distinct) > 1:
        disconfirming = [label for label, status in judged.items() if status in STATUS_PROFILE_DISCONFIRMED]
        if len(disconfirming) == len(judged):
            status = (STATUS_PROFILE_CONTRADICTS if STATUS_PROFILE_CONTRADICTS in judged.values()
                      else STATUS_PROFILE_FLAT)
            return {**result, "status": status, "disqualifies_m4_from_being_named_leader": True,
                    "reversed_predictions": [item for row in readings.values() for item in row["adjacent_predictions"]
                                             if item["verdict"] == "reversed"],
                    "reason": "every reading available puts the declared block ordering wrong by at least the "
                              "registered separability, so M4's attractor prior is contradicted on both scales and "
                              "the disagreement between them is only about which kind of contradiction this is."}
        return {**result, "status": STATUS_PROFILE_SCALE_DEPENDENT,
                "statuses_by_reading": dict(sorted(judged.items())),
                "reason": "the raw and chance-corrected readings of this pair set fall on different sides of the "
                          "disqualification line, so the line is not being crossed by a fact about the traditions "
                          "but by a choice of scale. Nothing is disqualified and nothing is confirmed: "
                          + " / ".join(f"{label} -> {status}" for label, status in sorted(judged.items())) +
                          ". Whichever reading a reader prefers, the preference has to be stated before the "
                          "verdict is, which is why both are published here."}
    status = distinct[0]
    if status == STATUS_PROFILE_FLAT:
        return {**result, "status": status, "disqualifies_m4_from_being_named_leader": True,
                "reason": f"the blocks differ by {readings['raw_similarity']['spread_across_blocks']} at most, "
                          f"below the declared {minimum_spread}. This is the case the alpha vector's own "
                          "`falsification_hook` named: concordance is flat across the blocks, so the declared "
                          "concentrations are wrong and M4's likelihood moves with them."}
    if status == STATUS_PROFILE_CONTRADICTS:
        return {**result, "status": status, "disqualifies_m4_from_being_named_leader": True,
                "reversed_predictions": [item for row in readings.values() for item in row["adjacent_predictions"]
                                         if item["verdict"] == "reversed"],
                "reason": "the observed block ordering contradicts the declared one by more than the registered "
                          "separability on every reading, so M4's attractor prior is wrong in a directed way: "
                          "the block it says converges most is not the block that agrees most in these pairs."}
    if status == STATUS_PROFILE_TIED:
        return {**result, "status": status,
                "reason": "an adjacent prediction the alpha vector declares is separated by at least "
                          f"{minimum_spread} came out inside that band, on every reading. A gap smaller than the "
                          "registered separability is a tie and the registered basis says so, so this neither "
                          "refutes M4 nor corroborates it: the instrument did not resolve the difference the "
                          "model predicts. Reporting it as a refutation would make the falsification hook fire "
                          "on the measurement rather than on the traditions."}
    return {**result, "status": status,
            "reason": "every adjacent prediction holds, by at least the declared separability, on every reading "
                      "available. This is the weakest of the confirmable outcomes: three blocks admit six "
                      "orderings, so one surviving prediction is not corroboration, it is the absence of the "
                      "refutation M4 was exposed to."}


def pair_log_likelihood(model, observation, config):
    """log likelihood of one observed state pair under one model, per model_likelihoods edge admissions.

    M1 admits vertical edges plus contact_borrowing only; M2 admits no edges and reads similarity off the
    background distribution over `no_known_route` pairs; M3 admits vertical within region plus horizontal and
    restoration between regions; M4 admits no edges and reads similarity off the declared attractor prior.
    `M1_decay` is the nested monotone case, reported so a reader can see whether the transformation model
    earned its extra shape.
    """
    observed_class = observation.get("similarity_class")
    if observed_class is None:
        return None
    if model == "M2":
        source = observation.get("background_distribution")
    elif model == "M4":
        source = observation.get("attractor_distribution") or attractor_distribution(config)
    elif model == "M1":
        source = predicted_similarity_distribution(
            config,
            n_vertical=observation.get("n_vertical", 0),
            n_horizontal=observation.get("n_contact_borrowing", 0),
            n_restoration=0,
        )
    elif model == "M1_decay":
        source = predicted_similarity_distribution(
            config,
            n_vertical=observation.get("n_vertical", 0),
            n_horizontal=observation.get("n_contact_borrowing", 0),
            monotone_decay=True,
        )
    elif model == "M3":
        source = predicted_similarity_distribution(
            config,
            n_vertical=observation.get("n_vertical", 0),
            n_horizontal=observation.get("n_horizontal", 0),
            n_restoration=observation.get("n_restoration", 0),
        )
    else:
        return None
    if not source:
        return None
    probability = source.get(observed_class, 0.0)
    floor = config["implementation_grid"]["likelihood_floor"]
    return math.log(max(probability, floor))


def model_totals(observations, config, models):
    totals = {model: 0.0 for model in models}
    per_pair = []
    for observation in observations:
        row = {"pair_id": observation.get("pair_id")}
        for model in models:
            value = pair_log_likelihood(model, observation, config)
            if value is None:
                return None, None
            row[model] = value
            totals[model] += value
        per_pair.append(row)
    return totals, per_pair


def log10_bayes_factor(totals, baseline, models):
    divisor = math.log(10)
    return {model: round((totals[model] - totals[baseline]) / divisor, 6) for model in models if model != baseline}


# --------------------------------------------------------------------------- cluster structure of a pair set


def cluster_fields(config):
    """The labels a pair must declare for a leakage-safe holdout, and the optional lineage label."""
    block = config["independent_cluster_holdout"]
    return dict(block["cluster_fields"]), dict(block.get("optional_cluster_fields") or {})


def clusters_touched(observation, config):
    """Every cluster label one pair touches, plus the required labels it fails to declare.

    A pair that cannot say which work it sits in cannot be held out leakage-safely, so the caller refuses the
    whole set rather than splitting it by pair -- which is exactly the pair-level split this block replaces.
    """
    required, optional = cluster_fields(config)
    labels, missing = set(), []
    for field, kind in sorted(required.items()):
        value = observation.get(field)
        if value in (None, ""):
            missing.append(field)
        elif kind == "work" and field == "work_b" and value == observation.get("work_a"):
            missing.append(f"{field} (= work_a: a pair of one work with itself is not a cross-work comparison)")
        else:
            labels.add(f"{kind}={value}")
    for field, kind in sorted(optional.items()):
        value = observation.get(field)
        if value not in (None, "", "undeclared"):
            labels.add(f"{kind}={value}")
    return labels, missing


def kish_effective_size(pair_endpoint_labels):
    """Kish's effective sample size over the work clusters of a list of (work_a, work_b) label pairs.

    One implementation, used by the real rule and by the power simulation, so the derived floor cannot be
    calibrated against a formula the tool does not run. Kish takes one cluster per unit and a pair has two
    endpoint works, so a pair is assigned to its more widely shared endpoint, ties broken by label. That is
    label-independent where a fixed-side rule is not: a hub of P pairs lands in one cluster whichever side a
    coder wrote first, and two works joined by P pairs are one comparison repeated P times, not P comparisons.
    """
    degrees = {}
    for left, right in pair_endpoint_labels:
        degrees[left] = degrees.get(left, 0) + 1
        degrees[right] = degrees.get(right, 0) + 1
    counts = {}
    for left, right in pair_endpoint_labels:
        first, second = sorted((left, right))
        chosen = first if degrees[first] >= degrees[second] else second
        counts[chosen] = counts.get(chosen, 0) + 1
    total = sum(counts.values())
    squares = sum(value * value for value in counts.values())
    return {
        "pairs": len(pair_endpoint_labels),
        "pairs_counted": total,
        "clusters": len(counts),
        "cluster_counts": dict(sorted(counts.items())),
        "cluster_pair_degrees": dict(sorted(degrees.items())),
        "sum_cluster_counts": total,
        "sum_squared_cluster_counts": squares,
        "effective_pairs": round(total * total / squares, 6) if squares else 0.0,
    }


def effective_sample_size(observations, config):
    """Kish effective sample size over the work clusters of a pair set, published with its own arithmetic.

    A set of n pairs is not n independent observations: two pairs that share a work share its wording, its
    translator and its manuscript. n_eff is expressed in pairs and never exceeds the pair count, because each
    pair is assigned to exactly one cluster. Nothing here is fitted.
    """
    required, _ = cluster_fields(config)
    labels, unusable = [], []
    for observation in observations:
        pair = []
        for field in ("work_a", "work_b"):
            value = observation.get(field)
            if value in (None, ""):
                continue
            pair.append(f"{required[field]}={value}")
        if len(pair) != 2 or pair[0] == pair[1]:
            unusable.append(observation.get("pair_id"))
            continue
        labels.append((pair[0], pair[1]))
    result = kish_effective_size(labels)
    value = result["effective_pairs"]
    result.update(
        {
            "pairs": len(observations),
            "pairs_without_usable_work_labels": unusable,
            "largest_cluster_pairs": max(result["cluster_counts"].values()) if result["cluster_counts"] else 0,
            "formula": "n_eff = (sum_c n_c)^2 / (sum_c n_c^2), each pair assigned to its more widely shared endpoint work",
            "bounded_by_pair_count": value <= result["pairs_counted"],
            "bounded_by_cluster_count": value <= result["clusters"],
            "reading": "the pair set carries about this many pairs' worth of independent information; the raw count "
                       "overstates it whenever two pairs share a work",
        }
    )
    return result


def holdout_assignment(cluster_sets, seed, test_cluster_fraction):
    """Mark whole clusters held-out until the test fold reaches its declared share of the pairs.

    The split reads labels only, never scores, so it cannot be picked after the result is seen. Clusters are
    sorted by label, shuffled once on the published seed, and taken in that order.
    """
    total = len(cluster_sets)
    universe = sorted({label for labels in cluster_sets for label in labels})
    pairs_by_cluster = {}
    for index, labels in enumerate(cluster_sets):
        for label in labels:
            pairs_by_cluster.setdefault(label, set()).add(index)
    order = list(universe)
    random.Random(seed).shuffle(order)
    held_out, test_indices = set(), set()
    for label in order:
        if total and len(test_indices) / total >= test_cluster_fraction:
            break
        held_out.add(label)
        test_indices |= pairs_by_cluster[label]
    return {
        "seed": seed,
        "test_cluster_fraction_declared": test_cluster_fraction,
        "clusters": len(universe),
        "held_out_clusters": sorted(held_out),
        "discovery_clusters": sorted(set(universe) - held_out),
        "test_indices": sorted(test_indices),
        "discovery_indices": [index for index in range(total) if index not in test_indices],
    }


def split_by_cluster(observations, config):
    """Fold a pair set by cluster, not by pair, and publish the leakage check rather than assume it.

    A pair is in the held-out fold if and only if it touches at least one held-out cluster. The invariant that
    follows and is checked here is that no held-out cluster appears among the discovery fold's pairs. The
    invariant that cannot hold on a connected pair graph -- a discovery work appearing on only one side -- is
    measured and published as `discovery_clusters_spanning_folds`, and the fold whose pairs touch nothing but
    held-out clusters is published separately so a reader can see the strictly clean subset.
    """
    block = config["independent_cluster_holdout"]
    cluster_sets, missing_labels = [], {}
    for observation in observations:
        labels, absent = clusters_touched(observation, config)
        if absent:
            missing_labels[observation.get("pair_id")] = absent
        cluster_sets.append(labels)
    if missing_labels:
        return {
            "ok": False,
            "status": "cluster_keys_missing",
            "pairs_missing_cluster_labels": missing_labels,
            "reason": "a pair without its work, witness and lineage labels cannot be split leakage-safely, so the "
                      "whole set is refused rather than split by pair",
        }
    assignment = holdout_assignment(cluster_sets, block["seed"], block["test_cluster_fraction"])
    held_out = set(assignment["held_out_clusters"])
    test_indices = set(assignment["test_indices"])
    discovery_indices = assignment["discovery_indices"]
    test_fold = [observations[index] for index in sorted(test_indices)]
    discovery_fold = [observations[index] for index in discovery_indices]
    isolated_indices = sorted(
        index for index in test_indices if cluster_sets[index] and cluster_sets[index] <= held_out
    )
    test_labels = {label for index in test_indices for label in cluster_sets[index]}
    discovery_labels = {label for index in discovery_indices for label in cluster_sets[index]}
    spanning = sorted(test_labels & discovery_labels)
    return {
        "ok": True,
        "status": "split",
        "unit": block["unit"],
        "pairs": len(observations),
        "test": test_fold,
        "discovery": discovery_fold,
        "isolated_test": [observations[index] for index in isolated_indices],
        "test_pairs": len(test_fold),
        "discovery_pairs": len(discovery_fold),
        "isolated_test_pairs": len(isolated_indices),
        "test_share_of_pairs": round(len(test_fold) / len(observations), 6) if observations else 0.0,
        "clusters": assignment["clusters"],
        "held_out_clusters": assignment["held_out_clusters"],
        "held_out_cluster_count": len(held_out),
        "seed": assignment["seed"],
        "checks": {
            "no_pair_in_both_folds": len(test_indices & set(discovery_indices)) == 0,
            "no_held_out_cluster_in_discovery_fold": not (held_out & discovery_labels),
            "held_out_clusters_appear_only_in_test_fold": not (held_out & discovery_labels),
        },
        "discovery_clusters_spanning_folds": spanning,
        "discovery_clusters_spanning_folds_count": len(spanning),
        "spanning_note": "every label here is a discovery cluster: a pair joining a discovery work to a held-out "
                         "one is in the test fold and shares its discovery-side wording with the discovery fold. "
                         "No edge-level cluster split can remove this without disconnecting the pair graph, so it "
                         "is published as a measured residual and the isolated fold is reported beside it.",
        "reading": "the held-out margin is earned on pairs whose works were not used to declare the operators; "
                   "the isolated fold is the subset where neither endpoint was",
    }


def holdout_summary(split):
    """The published shape of a cluster split: its counts, checks and labels, without the pair records."""
    withheld = ("test", "discovery", "isolated_test")
    return {key: value for key, value in split.items() if key not in withheld}


def decision_gates(config, power=_UNSET):
    """The floors the decision rule enforces, read from the published power simulation when there is one.

    The config's own `minimum_pairs` is the historical floor and the grid the simulation starts from; it is not
    used as a justification. Which source the run used is published, because a floor that arrived silently is
    indistinguishable from a floor that was chosen.

    `power` defaults to reading the published artifact off disk. Pass `power=None` to ask what the gates would
    be with no artifact published -- the pre-simulation state -- and a dict to score against one in memory.
    Conflating the two would let a test of the fallback silently read the real artifact.
    """
    block = config["power_simulation"]
    floor = config["probabilistic_transformation_model"]["likelihood_of_an_observed_state_pair"]["minimum_pairs"]
    if power is _UNSET and POWER_ARTIFACT_PATH.exists():
        power = json.loads(POWER_ARTIFACT_PATH.read_text(encoding="utf-8"))
    if power is None:
        return {
            "minimum_pairs": floor,
            "minimum_effective_samples": None,
            "source": "config floor: the power simulation has not been published",
            "regenerate_with": block["regenerate_with"],
            "derived_minimum_pairs": None,
            "note": "the historical analyst-set floor is in force only as a placeholder, and this run says so",
        }
    derived = power.get("derived_minimum_pairs")
    derived_eff = power.get("derived_minimum_effective_samples")
    return {
        "minimum_pairs": derived,
        "minimum_effective_samples": derived_eff,
        "source": f"{block['publishes']} (status {power.get('status')})",
        "historical_floor_in_config": floor,
        "derived_minimum_pairs": derived,
        "derived_minimum_effective_samples": derived_eff,
        "target_correct_model_probability": block["target_correct_model_probability"],
        "note": power.get("derivation_rule", "")
                + " | when this artifact exists the config's historical minimum_pairs is not a gate: a null "
                  "derived floor refuses every pair set rather than quietly falling back to 20",
    }


def declared_margin(config):
    """The one margin the layer uses, declared in exactly one place and read by both stages.

    Two numbers both called "the margin" are two tunable knobs, and a reader cannot tell which one a result was
    produced with. The stages ask different questions, so they may use different *denominators* -- the runner-up
    in stage 1, the no-edge null in stage 2 -- but not different severities.
    """
    return config["four_way_decision_rule"]["stage_1_symmetric_competition"]["margin_log10_bayes_factor"]


def _stage_one_from_totals(totals, models, margin, test_totals=None, isolated_totals=None):
    """The symmetric part of stage 1: rank on summed log likelihood, then measure the leader over the runner-up.

    No model is the denominator here. That is the difference between this and a margin against M2: a rule
    written as "inheritance beats null" makes M2 the reference and M4 decorative, which is the asymmetry
    reviewer item 4 names.

    The holdout numbers reuse the whole-set leader and runner-up rather than re-ranking inside the fold: the
    pre-registered contrast is one comparison, and letting the fold pick its own leader would be a second
    search for a winner dressed up as a confirmation of the first.
    """
    divisor = math.log(10)
    ranked = sorted(models, key=lambda model: (-totals[model], model))
    leader, runner_up = ranked[0], ranked[1]
    whole = round((totals[leader] - totals[runner_up]) / divisor, 6)
    on_test = None
    if test_totals:
        on_test = round((test_totals[leader] - test_totals[runner_up]) / divisor, 6)
    isolated = None
    if isolated_totals:
        isolated = round((isolated_totals[leader] - isolated_totals[runner_up]) / divisor, 6)
    ties = [model for model in models if totals[model] == totals[leader]]
    return {
        "ranking": ranked,
        "leader": leader,
        "runner_up": runner_up,
        "tied_at_leader": ties if len(ties) > 1 else [],
        "log10_bayes_factor_leader_over_runner_up": whole,
        "log10_bayes_factor_leader_over_runner_up_on_holdout": on_test,
        "log10_bayes_factor_leader_over_runner_up_isolated_fold": isolated,
        "leader_wins_the_holdout_too": on_test is None or on_test >= margin,
        "margin_declared": margin,
        "decisive": whole >= margin and (on_test is None or on_test >= margin),
        "per_model_log10_vs_leader": {
            model: round((totals[model] - totals[leader]) / divisor, 6) for model in models if model != leader
        },
    }


def decide_four_way(observations, config, gates=None, split=None, chance_table=None):
    """Stage 1 of the decision rule: all four competitors on one footing, with no-decisive-winner reachable.

    The gate (pair count, effective sample size) and the verdict (margin) are computed separately and both
    published: the power simulation measures the verdict, and the gate is what the simulation sets, so a rule
    that folded the gate into the verdict would measure its own placeholder.

    `chance_table` is `corpus_chance_similarity()`'s return. The comparison entry points load it so the block
    profile can be read on both scales; the power simulation reaches stage 1 through the totals, not here.
    """
    rule = config["four_way_decision_rule"]
    models = tuple(rule["competitor_keys"])
    nested = rule["nested_case_key"]
    margin = declared_margin(config)
    gates = gates or decision_gates(config)
    if split is None:
        split = split_by_cluster(observations, config)
    if not split["ok"]:
        return {
            "status": STATUS_CLUSTER_KEYS_MISSING,
            "pairs": len(observations),
            "pairs_missing_cluster_labels": split["pairs_missing_cluster_labels"],
            "reason": split["reason"],
            "model_scores": None,
            "ranking": None,
        }
    totals, per_pair = model_totals(observations, config, models + (nested,))
    if totals is None:
        stalled = next(
            (
                observation
                for observation in observations
                if pair_log_likelihood("M2", observation, config) is None
                or pair_log_likelihood("M4", observation, config) is None
            ),
            observations[0] if observations else {},
        )
        return {
            "status": "inputs_missing",
            "missing": [f"M2 background_distribution or M4 attractor input for pair {stalled.get('pair_id')}"],
            "pairs": len(observations),
            "model_scores": None,
            "ranking": None,
        }
    test_totals, _ = model_totals(split["test"], config, models) if split["test"] else (None, None)
    isolated_totals, _ = model_totals(split["isolated_test"], config, models) if split["isolated_test"] else (None, None)
    verdict = _stage_one_from_totals(totals, models, margin, test_totals, isolated_totals)
    samples = effective_sample_size(observations, config)
    gate_problems = []
    minimum_pairs = gates["minimum_pairs"]
    if minimum_pairs is None:
        gate_problems.append(
            "no grid cell in the published power simulation reaches the target probability, so the rule cannot be "
            "licensed at any pair count on that artifact"
        )
    elif len(observations) < minimum_pairs:
        gate_problems.append(
            f"pair set: {len(observations)} dated, route-typed pairs, gate is {minimum_pairs} from {gates['source']}"
        )
    if gates["minimum_effective_samples"] is not None:
        if samples["effective_pairs"] < gates["minimum_effective_samples"]:
            gate_problems.append(
                f"effective independent samples: n_eff {samples['effective_pairs']} over "
                f"{samples['clusters']} work clusters, gate is {gates['minimum_effective_samples']} from {gates['source']}"
            )
    else:
        gate_problems.append("effective independent samples: no floor published, run the power simulation")
    profile_test = attractor_block_profile_test(observations, config, chance_table)
    disqualified = "M4" if profile_test["disqualifies_m4_from_being_named_leader"] else None
    leader_disqualified = bool(disqualified) and verdict["leader"] == disqualified and verdict["decisive"]
    gated = bool(gate_problems)
    demoted = leader_disqualified and not gated
    status = STATUS_INSUFFICIENT_PAIRS if gate_problems else (
        STATUS_DECISIVE if verdict["decisive"] and not demoted else STATUS_NO_DECISIVE_WINNER
    )
    return {
        "status": status,
        "competitors": list(models),
        "nested_case_reported_not_competing": nested,
        "pairs": len(observations),
        "model_scores": None if gated else {model: round(totals[model], 6) for model in models},
        "nested_case_score": None if gated else round(totals[nested], 6),
        "ranking_by_log_likelihood": None if gated else verdict["ranking"],
        "leader": None if gated else verdict["leader"],
        "runner_up": None if gated else verdict["runner_up"],
        "margin_declared": margin,
        "log10_bayes_factor_leader_over_runner_up": None if gated else verdict["log10_bayes_factor_leader_over_runner_up"],
        "log10_bayes_factor_leader_over_runner_up_on_cluster_holdout": None if gated else verdict["log10_bayes_factor_leader_over_runner_up_on_holdout"],
        "log10_bayes_factor_leader_over_runner_up_on_isolated_fold": None if gated else verdict["log10_bayes_factor_leader_over_runner_up_isolated_fold"],
        "tied_at_leader": [] if gated else verdict["tied_at_leader"],
        "per_model_log10_vs_leader": None if gated else verdict["per_model_log10_vs_leader"],
        "effective_samples": samples,
        "gates": gates,
        "gate_problems": gate_problems,
        "verdict_if_gates_were_met": verdict,
        "scores_are_withheld_because": "the gate is what the power simulation licenses; a ranking printed under "
                                       "a failing gate is a number a reader could quote as a result, so the "
                                       "diagnostic is kept inside `verdict_if_gates_were_met` and labelled as not one",
        "cluster_holdout": {
            "test_pairs": split["test_pairs"],
            "discovery_pairs": split["discovery_pairs"],
            "isolated_test_pairs": split["isolated_test_pairs"],
            "held_out_cluster_count": split["held_out_cluster_count"],
            "clusters": split["clusters"],
            "seed": split["seed"],
            "checks": split["checks"],
            "discovery_clusters_spanning_folds_count": split["discovery_clusters_spanning_folds_count"],
        },
        "per_pair": per_pair,
        "m4_block_profile_test": profile_test,
        "m4_disqualified_from_being_named_leader": bool(disqualified),
        "reason": (
            f"the ranking puts {verdict['leader']} first by at least the margin, but the same pair set "
            f"contradicts the one prediction that separates it from a second no-edge null "
            f"({profile_test['status']}), so no model is named; the ranking is published unchanged"
            if demoted else {
            STATUS_DECISIVE: f"{verdict['leader']} leads {verdict['runner_up']} by at least the declared margin on "
                             "the whole set and on the cluster holdout",
            STATUS_NO_DECISIVE_WINNER: "no model clears the declared margin over the runner-up on both the whole "
                                       "set and the cluster holdout; this is a published result, not a failure to "
                                       "produce one",
            STATUS_INSUFFICIENT_PAIRS: "; ".join(gate_problems),
            STATUS_CLUSTER_KEYS_MISSING: "pair labels missing",
        }[status]),
        "no_decisive_winner_is_expected": rule["stage_1_symmetric_competition"]["no_decisive_winner_is_expected"],
    }


def compare_observations(observations, config):
    """Run both published stages: the symmetric four-way competition, then the inheritance licence.

    Stage 2 keeps its object -- does an inheritance-bearing model beat the no-edge nulls by the margin -- and
    carries it on the cluster holdout instead of a pair split. There are two no-edge nulls and the licence has
    to clear both. The two stages answer different questions and neither implies the other, which is why both
    are emitted on every run.
    """
    models = ("M1", "M2", "M3", "M4")
    reported_alongside = config["four_way_decision_rule"]["nested_case_key"]
    split = split_by_cluster(observations, config)
    chance_table = corpus_chance_similarity()
    if not split["ok"]:
        return {"ok": False, "missing": [f"cluster_keys_missing: {pair} lacks {fields}" for pair, fields in split["pairs_missing_cluster_labels"].items()], "stage_1": decide_four_way(observations, config, split=split, chance_table=chance_table)}
    totals, per_pair = model_totals(observations, config, models + (reported_alongside,))
    if totals is None:
        stalled = next((observation for observation in observations if pair_log_likelihood("M2", observation, config) is None or pair_log_likelihood("M4", observation, config) is None), observations[0])
        return {"ok": False, "missing": [f"M2 background_distribution or M4 attractor input for pair {stalled.get('pair_id')}"]}
    margin = declared_margin(config)
    inheritance_bearing = tuple(config["independent_origin_baseline_and_margin"]["inheritance_bearing_models"])
    baselines = tuple(config["independent_origin_baseline_and_margin"]["baselines"])
    log10_bf_vs_m2 = log10_bayes_factor(totals, "M2", models)
    log10_bf_vs_m4 = log10_bayes_factor(totals, "M4", models)
    test_totals, _ = model_totals(split["test"], config, models) if split["test"] else (None, None)
    held_out_bf = log10_bayes_factor(test_totals, "M2", models) if test_totals else {}
    held_out_bf_vs_m4 = log10_bayes_factor(test_totals, "M4", models) if test_totals else {}
    # The licence is granted against the harder of the two no-edge nulls, not the easier one. Naming M4 a
    # second baseline and then dividing only by M2 left `log10_bayes_factor_vs_M4` published and load-bearing
    # for nothing, which is a model reported rather than tested.
    against = {baseline: log10_bayes_factor(totals, baseline, models) for baseline in baselines}
    held_out_against = {baseline: log10_bayes_factor(test_totals, baseline, models) if test_totals else {}
                        for baseline in baselines}
    licence_whole = {model: min(against[baseline].get(model, float("-inf")) for baseline in baselines)
                     for model in inheritance_bearing}
    licence_held_out = {model: min(held_out_against[baseline].get(model, float("-inf")) for baseline in baselines)
                        for model in inheritance_bearing}
    # The binding baseline is the one the model beats by *least*: the harder of the two no-edge nulls.
    binding = {model: min(baselines, key=lambda baseline: against[baseline][model])
               for model in inheritance_bearing}
    meeting_whole = [model for model, value in licence_whole.items() if value >= margin]
    meeting_held_out = [model for model, value in licence_held_out.items() if value >= margin]
    preferred = [model for model in meeting_whole if model in meeting_held_out] if test_totals else meeting_whole
    ranked = sorted(models, key=lambda model: totals[model], reverse=True)
    stage_one = decide_four_way(observations, config, split=split, chance_table=chance_table)
    return {
        "ok": True,
        "log_likelihoods": {model: round(value, 6) for model, value in totals.items()},
        "log10_bayes_factor_vs_M2": log10_bf_vs_m2,
        "log10_bayes_factor_vs_M4": log10_bf_vs_m4,
        "log10_bayes_factor_vs_M2_held_out": held_out_bf,
        "log10_bayes_factor_vs_M4_held_out": held_out_bf_vs_m4,
        "licence_baselines": list(baselines),
        "licence_min_margin_over_baselines": {model: round(value, 6) for model, value in licence_whole.items()},
        "licence_binding_baseline": {model: baseline for model, baseline in binding.items()},
        "margin_declared": margin,
        "models_meeting_margin_vs_M2": [model for model, value in log10_bf_vs_m2.items()
                                        if value >= margin and model in inheritance_bearing],
        "models_meeting_margin_vs_M4": [model for model, value in log10_bf_vs_m4.items()
                                        if value >= margin and model in inheritance_bearing],
        "models_meeting_the_licence_margin": preferred,
        "models_meeting_margin_on_whole_set": meeting_whole,
        "models_meeting_margin_on_held_out": meeting_held_out,
        "held_out_pairs": split["test_pairs"],
        "discovery_pairs": split["discovery_pairs"],
        "isolated_held_out_pairs": split["isolated_test_pairs"],
        "cluster_holdout": holdout_summary(split),
        "effective_samples": stage_one["effective_samples"],
        "stage_1_symmetric_competition": stage_one,
        "stage_2_inheritance_licence": {
            "status": STATUS_MARGIN_MET if preferred else STATUS_NOT_PREFERRED,
            "models_meeting_the_licence_margin": preferred,
            "baselines": list(baselines),
            "rule": "min(log10 BF over each baseline) >= margin, on the whole set and on the cluster holdout",
            "licence_min_margin_over_baselines": {model: round(value, 6) for model, value in licence_whole.items()},
            "licence_binding_baseline": {model: baseline for model, baseline in binding.items()},
            "held_out": {model: round(licence_held_out[model], 6) for model in meeting_whole},
            "question": "does an inheritance-bearing model beat both no-edge nulls -- independent origin and "
                        "convergence -- by the declared margin",
            "relationship_to_stage_1": config["four_way_decision_rule"]["stage_2_inheritance_licence"]["relationship"],
        },
        "ranking_by_log_likelihood": ranked,
        "monotone_decay_nested_case_reported": reported_alongside in totals,
        "per_pair": per_pair,
        "pairs": len(observations),
    }


# --------------------------------------------------------------------------- power simulation


def _discrete_sampler(distribution):
    total = sum(distribution.get(name, 0.0) for name in CLASS_ORDER) or 1.0
    cumulative, running = [], 0.0
    for name in CLASS_ORDER:
        running += distribution.get(name, 0.0) / total
        cumulative.append((name, running))
    return cumulative


def _draw(cumulative, uniform):
    for name, ceiling in cumulative:
        if uniform <= ceiling:
            return name
    return cumulative[-1][0]


def _synthetic_signature(config, model, edge_models):
    """The typed-edge multiset a pair is generated with under one model, declared rather than drawn.

    M2 and M4 declare none: those models admit no edges, so a pair from them reaches the scorer with every
    count at zero. That is a property of the instrument worth reading in `caveats`, not a modelling choice.
    """
    spec = edge_models.get(model)
    fields = ("n_vertical", "n_horizontal", "n_contact_borrowing", "n_restoration")
    if spec is None:
        return {field: 0 for field in fields}
    return {field: spec.get(field, 0) for field in fields}


def _synthetic_class_distribution(config, model, signature, background):
    if model == "M1":
        return predicted_similarity_distribution(
            config, n_vertical=signature["n_vertical"], n_horizontal=signature["n_contact_borrowing"]
        )
    if model == "M3":
        return predicted_similarity_distribution(
            config,
            n_vertical=signature["n_vertical"],
            n_horizontal=signature["n_horizontal"],
            n_restoration=signature["n_restoration"],
        )
    if model == "M2":
        return dict(background)
    return attractor_distribution(config)


def _score_table(config, models, signature, background):
    """log likelihood of every (model, similarity class) cell for one edge signature, computed once."""
    attractor = attractor_distribution(config)
    table = {model: {} for model in models}
    for name in CLASS_ORDER:
        probe = {
            "similarity_class": name,
            "background_distribution": dict(background),
            "attractor_distribution": attractor,
            **signature,
        }
        for model in models:
            value = pair_log_likelihood(model, probe, config)
            if value is None:
                raise ValueError(f"score table for {model} on class {name} is undefined")
            table[model][name] = value
    return table


def _percentile(values, fraction):
    """The declared percentile of an effective-sample list: sorted, index ceil(fraction * n) - 1."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return round(ordered[index], 6)


def simulate_true_model(
    models, table, sampler, true_model, pairs, replications, work_labels, witnesses_per_work, split_seed,
    test_fraction, margin
):
    """Replications of one cell: generate a pair set, split it by cluster, run the stage-1 verdict.

    The gate is deliberately not applied here. The simulation is what sets the gate, so measuring the verdict
    with the gate in force would measure the previous run's placeholder.
    """
    decisive = 0
    effective_samples, test_shares, leader_counts = [], [], {model: 0 for model in models}
    for replication in range(replications):
        rng = random.Random(f"{split_seed}|{true_model}|{pairs}|{replication}")
        cluster_sets, classes, endpoint_labels = [], [], []
        for _ in range(pairs):
            left = rng.randrange(len(work_labels))
            right = rng.randrange(len(work_labels) - 1)
            if right >= left:
                right += 1
            left_label, right_label = work_labels[left], work_labels[right]
            labels = {left_label, right_label}
            if witnesses_per_work > 1:
                for label in (left_label, right_label):
                    suffix = label.split("=", 1)[1]
                    labels.add(f"witness={suffix}#{rng.randrange(witnesses_per_work)}")
            cluster_sets.append(labels)
            classes.append(_draw(sampler, rng.random()))
            endpoint_labels.append((left_label, right_label))
        assignment = holdout_assignment(cluster_sets, split_seed, test_fraction)
        held_out = set(assignment["test_indices"])
        totals = {model: 0.0 for model in models}
        test_totals = {model: 0.0 for model in models}
        for index, name in enumerate(classes):
            for model in models:
                value = table[model][name]
                totals[model] += value
                if index in held_out:
                    test_totals[model] += value
        endpoint_counts = kish_effective_size(endpoint_labels)
        effective_samples.append(endpoint_counts["effective_pairs"])
        test_shares.append(round(len(assignment["test_indices"]) / pairs, 6))
        verdict = _stage_one_from_totals(totals, models, margin, test_totals)
        leader_counts[verdict["leader"]] += 1
        if verdict["decisive"] and verdict["leader"] == true_model:
            decisive += 1
    return {
        "decisive_and_correct": decisive,
        "power": round(decisive / replications, 6) if replications else None,
        "power_monte_carlo_standard_error": round(
            math.sqrt((decisive / replications) * (1 - decisive / replications) / replications), 6
        ) if replications else None,
        "mean_effective_pairs": round(sum(effective_samples) / len(effective_samples), 6) if effective_samples else None,
        "fifth_percentile_effective_samples": _percentile(effective_samples, 0.05),
        "minimum_effective_samples": min(effective_samples) if effective_samples else None,
        "mean_test_share_of_pairs": round(sum(test_shares) / len(test_shares), 6) if test_shares else None,
        "leader_distribution": dict(sorted(leader_counts.items())),
    }


def grid_values(grid):
    start, stop, step = int(grid["from"]), int(grid["to"]), int(grid["step"])
    return list(range(start, stop + 1, step))


def simulate_scenario(config, scenario, replications=None, cells=None):
    """One full grid over the four generating models under one declared scenario."""
    models = tuple(config["four_way_decision_rule"]["competitor_keys"])
    nested = config["four_way_decision_rule"]["nested_case_key"]
    margin = declared_margin(config)
    block = config["power_simulation"]
    test_fraction = config["independent_cluster_holdout"]["test_cluster_fraction"]
    split_seed = config["independent_cluster_holdout"]["seed"]
    background = scenario["synthetic_background_distribution"]
    structure = scenario["cluster_structure"]
    works = int(structure["works"])
    witnesses = int(structure["witnesses_per_work"])
    repetitions = int(replications or scenario["replications_per_cell"])
    pairs_list = list(cells or grid_values(scenario["grid"]))
    work_labels = [f"work={index:03d}" for index in range(1, works + 1)]
    rows = []
    for model in models:
        signature = _synthetic_signature(config, model, scenario["edge_count_models"])
        distribution = _synthetic_class_distribution(config, model, signature, background)
        table = _score_table(config, models, signature, background)
        sampler = _discrete_sampler(distribution)
        for pairs in pairs_list:
            outcome = simulate_true_model(
                models, table, sampler, model, pairs, repetitions, work_labels, witnesses, split_seed,
                test_fraction, margin
            )
            rows.append(
                {
                    "true_model": model,
                    "pairs": pairs,
                    "replications": repetitions,
                    "declared_edge_signature": signature,
                    "generated_class_distribution": {name: round(distribution.get(name, 0.0), 8) for name in CLASS_ORDER},
                    **outcome,
                }
            )
    target = float(block["target_correct_model_probability"])
    reaching, maximum_power, highest_pairs = {}, {}, max(row["pairs"] for row in rows)
    for model in models:
        model_rows = [row for row in rows if row["true_model"] == model]
        meeting = [row["pairs"] for row in model_rows if row["power"] >= target]
        reaching[model] = min(meeting) if meeting else None
        maximum_power[model] = max(row["power"] for row in model_rows)
    unmet = sorted(model for model, value in reaching.items() if value is None)
    # Every generating model has to clear the target, or the floor is not a floor: a rule licensed at the
    # pair count where three of four truths resolve is a rule that goes silent on the fourth.
    derived_pairs = max(reaching.values()) if reaching and not unmet else None
    binding_model = (
        max(reaching, key=lambda model: (reaching[model], model)) if derived_pairs is not None else None
    )
    binding_row = (
        next((row for row in rows if row["true_model"] == binding_model and row["pairs"] == derived_pairs), None)
        if binding_model
        else None
    )
    derived_samples = binding_row["fifth_percentile_effective_samples"] if binding_row else None
    return {
        "scenario": scenario,
        "rows": rows,
        "target_correct_model_probability": target,
        "smallest_pairs_reaching_target_by_true_model": reaching,
        "maximum_power_by_true_model": maximum_power,
        "true_models_never_reaching_target_on_this_grid": unmet,
        "reached_only_at_the_grid_ceiling": sorted(
            model for model, value in reaching.items() if value == highest_pairs
        ),
        "binding_true_model": binding_model,
        "derived_minimum_pairs": derived_pairs,
        "derived_minimum_effective_samples": derived_samples,
    }


def power_simulation(config=None, write=False, path=None, replications=None, cells=None):
    """Derive the pair and effective-sample floors by running the decision rule against simulated truths.

    This is the replacement for the sentence the reviewer objected to. The floor used to be a number an analyst
    asserted; it is now the smallest simulated pair count at which the published rule names the generating model
    decisively at least `target_correct_model_probability` of the time, for every one of the four models, and it
    is read back out of this artifact by `decision_gates` rather than restated in the config.
    """
    config = config or load_config()
    block = config["power_simulation"]
    competitors = tuple(config["four_way_decision_rule"]["competitor_keys"])
    declared = {
        "seed": block["seed"],
        "target_correct_model_probability": block["target_correct_model_probability"],
        "grid": block["grid"],
        "replications_per_cell": block["replications_per_cell"],
        "synthetic_background_distribution": block["synthetic_background_distribution"],
        "edge_count_models": {
            key: value for key, value in block["edge_count_models"].items() if key in competitors
        },
        "cluster_structure": {
            key: value for key, value in block["cluster_structure"].items() if not key.endswith("_note") and key != "basis"
        },
        "decision_rule": {
            "competitor_keys": config["four_way_decision_rule"]["competitor_keys"],
            "margin_log10_bayes_factor": declared_margin(config),
            "test_cluster_fraction": config["independent_cluster_holdout"]["test_cluster_fraction"],
            "holdout_seed": config["independent_cluster_holdout"]["seed"],
        },
    }
    overrides = {}
    if replications is not None and int(replications) != int(declared["replications_per_cell"]):
        overrides["replications_per_cell"] = {"declared": declared["replications_per_cell"], "used": int(replications)}
        declared["replications_per_cell"] = int(replications)
    if cells is not None and list(cells) != grid_values(declared["grid"]):
        overrides["grid_pairs"] = {"declared": grid_values(declared["grid"]), "used": list(cells)}
        step = int(declared["grid"]["step"])
        declared["grid"] = {"from": min(cells), "to": max(cells), "step": step}
    baseline = simulate_scenario(config, declared, replications=replications, cells=cells)
    scenarios = [
        {
            "label": "declared",
            "change": "the config's own parameters",
            "result": baseline,
        },
        {
            "label": "three_witnesses_per_work",
            "change": "witnesses_per_work 1 -> 3, so witness clusters add dependence on top of the work clusters",
            "result": simulate_scenario(
                config,
                {**declared, "cluster_structure": {**declared["cluster_structure"], "witnesses_per_work": 3}},
                replications=replications,
                cells=cells,
            ),
        },
        {
            "label": "flat_background",
            "change": "M2's synthetic background made uniform over the five classes, so the null predicts less sharply",
            "result": simulate_scenario(
                config,
                {
                    **declared,
                    "synthetic_background_distribution": {name: 0.2 for name in CLASS_ORDER},
                },
                replications=replications,
                cells=cells,
            ),
        },
    ]
    artifact = {
        "schema_version": 1,
        "artifact": "model_power_simulation",
        "produced_by": block["regenerate_with"],
        "status": "derived" if baseline["derived_minimum_pairs"] is not None else "not_derivable_on_declared_grid",
        "question": block["question"],
        "generative_assumption": block["generative_assumption"],
        "what_the_number_is": "the smallest pair count on the declared grid at which the stage-1 rule names the "
                              "generating model decisively in at least the target share of replications, for every "
                              "generating model -- so the binding cell is the hardest of the four to separate",
        "what_the_number_is_not": [
            "a claim that any of the four models is true; a rule can be perfectly powered and still be fed a "
            "world none of the four describes",
            "a measurement of this corpus: every input is a declared parameter of the instrument",
            "independent of the grid: the floor is the first grid point that clears the target, so it is "
            "reported to the grid step and no finer",
        ],
        "gate_is_not_part_of_what_is_measured": "each replication is scored with the pair-count and "
                                               "effective-sample gates switched off, because the simulation is what sets them; "
                                               "measuring the rule with the gate in force would measure the previous run's placeholder",
        "declared_parameters": declared,
        "declared_parameters_sha256": hashlib.sha256(canonical_json(declared).encode("utf-8")).hexdigest(),
        "run_overrides": overrides,
        "provenance": "declared parameters, no overrides" if not overrides else (
            "SMOKE RUN: parameters differ from the config's declared ones as recorded in run_overrides, so the "
            "derived floor in this artifact is provisional and must not be read as the preregistered one"
        ),
        "cells": baseline["rows"],
        "power_by_true_model_declared": baseline["smallest_pairs_reaching_target_by_true_model"],
        "maximum_power_by_true_model_declared": baseline["maximum_power_by_true_model"],
        "true_models_never_reaching_target_on_this_grid": baseline["true_models_never_reaching_target_on_this_grid"],
        "reached_only_at_the_grid_ceiling": baseline["reached_only_at_the_grid_ceiling"],
        "grid_provenance": block.get("grid_provenance", ""),
        "binding_true_model": baseline["binding_true_model"],
        "derived_minimum_pairs": baseline["derived_minimum_pairs"],
        "derived_minimum_effective_samples": baseline["derived_minimum_effective_samples"],
        "derivation_rule": "derived_minimum_pairs = max over the four generating models of the smallest grid pair "
                           "count whose power reaches the declared target, and it is null unless every one of the "
                           "four reaches it somewhere on the grid: a floor licensed where three of four truths "
                           "resolve is a rule that goes silent on the fourth. derived_minimum_effective_samples = "
                           "the 5th percentile (sorted, index ceil(0.05 * replications) - 1) of the Kish effective "
                           "pair count over the replications of that binding cell",
        "sensitivity": [
            {
                "label": item["label"],
                "change": item["change"],
                "derived_minimum_pairs": item["result"]["derived_minimum_pairs"],
                "derived_minimum_effective_samples": item["result"]["derived_minimum_effective_samples"],
                "binding_true_model": item["result"]["binding_true_model"],
                "power_by_true_model": item["result"]["smallest_pairs_reaching_target_by_true_model"],
                "maximum_power_by_true_model": item["result"]["maximum_power_by_true_model"],
                "true_models_never_reaching_target_on_this_grid": item["result"][
                    "true_models_never_reaching_target_on_this_grid"
                ],
            }
            for item in scenarios
        ],
        "caveats": [
            "M1 and M3 predict a point mass at `identical` on a pair declaring no edges, because their likelihood "
            "is conditional on the declared edge multiset. Power against M2- and M4-generated sets is therefore "
            "driven by that collapse rather than by a comparison of distribution shapes, and those cells are easy. "
            "The binding cell is an edge-bearing comparison, which is why the derived floor is what it is.",
            "the floor is reported to the grid step and no finer: a cell one step below the published floor may "
            "reach the target on a different seed, and the power column with its Monte Carlo standard error is "
            "published for every cell so a reader can see the noise rather than trust the crossing",
            "a floor that lands on the grid ceiling is published as reached_only_at_the_grid_ceiling, and a model "
            "that reaches the target nowhere on the grid makes the floor null rather than partial",
            "one witness per work is what the corpus is, and it is the weakest case for the effective-sample gate; "
            "the sensitivity scenario at three witnesses is published beside it rather than argued away",
        ],
        "limitations": [
            "the simulation varies the pair count at a fixed cluster structure, so the two published floors are "
            "calibrated to each other and not independent; a pair set with a different work-per-pair ratio needs a "
            "rerun with that structure declared",
            "power is a property of the decision rule under its own declared parameters, including the analyst-set "
            "background distribution M2 cannot yet supply",
        ],
        "historical_conclusion": NO_HISTORICAL_CONCLUSION,
        "interpretation": "a derived floor is a statement about this rule's resolution, not about the past. It "
                          "changes only by rerunning this file, and the artifact records the parameters it was run under.",
    }
    if write:
        target_path = Path(path) if path else POWER_ARTIFACT_PATH
        target_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return artifact


# --------------------------------------------------------------------------- missing inputs and refusal


def scaffold_diagnostic(path=None):
    """Read-only diagnostic of what the project actually holds, used to ground the refusal."""
    path = Path(path) if path else SCAFFOLD_PATH
    if not path.exists():
        return {"available": False, "note": f"{path.name} not present"}
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"available": False, "note": f"{path.name} is empty"}
    usable = [row for row in rows if (row.get("usable_for_priority_claims") or "").strip().lower() == "yes"]
    filled = [row for row in rows if str(row.get("composition_date_claim", "")).lstrip("-").isdigit()]
    return {
        "available": True,
        "works": len({row.get("work_id") for row in rows}),
        "rows": len(rows),
        "works_with_numeric_composition_date": len(filled),
        "works_usable_for_priority_claims": len(usable),
        "reading": "an earlier surviving witness is not evidence of an earlier composition, and a recording or printing date is not a composition date",
    }


def missing_required_inputs(config, derivation=None, observations=None, scaffold=None):
    missing = []
    verification = verify_preregistration(config)
    if not verification["ok"]:
        missing.extend(f"preregistration: {problem}" for problem in verification["problems"])
    if observations is not None:
        for observation in observations:
            for field in ("date_earliest", "date_latest", "dating_basis"):
                for side in ("a", "b"):
                    dates = (observation.get(f"composition_{side}") or {})
                    if dates.get(field) in (None, "", "undated"):
                        missing.append(f"pair {observation.get('pair_id')}: composition_{side}.{field}")
            if observation.get("similarity_class") is None:
                missing.append(f"pair {observation.get('pair_id')}: similarity_class")
            if observation.get("n_vertical") is None or observation.get("n_horizontal") is None:
                missing.append(f"pair {observation.get('pair_id')}: typed edge counts unstated (a zero must be declared, not defaulted, because it changes what M1 predicts)")
        split = split_by_cluster(observations, config)
        if not split["ok"]:
            for pair_id, fields in sorted(split["pairs_missing_cluster_labels"].items()):
                missing.append(f"pair {pair_id}: cluster labels {', '.join(fields)} undeclared (status cluster_keys_missing; the set is refused rather than split by pair)")
        samples = effective_sample_size(observations, config)
        gates = decision_gates(config)
        minimum_pairs = gates["minimum_pairs"]
        if minimum_pairs is None:
            missing.append(
                "pair set: the published power simulation derives no floor on its declared grid, so no pair count "
                f"licenses a winner (see {gates['source']})"
            )
        elif len(observations) < minimum_pairs:
            missing.append(
                f"pair set: {len(observations)} dated, route-typed pairs supplied, the derived floor is "
                f"{minimum_pairs} ({gates['source']}; the config's historical minimum_pairs of {gates.get('historical_floor_in_config')} "
                "is a superseded analyst-set number and is not the gate)"
            )
        if gates["minimum_effective_samples"] is None:
            missing.append(
                "effective independent samples: no floor published, so the pair set cannot be checked for "
                "dependence; run python tools/compare_models.py --power"
            )
        elif samples["effective_pairs"] < gates["minimum_effective_samples"]:
            missing.append(
                f"effective independent samples: n_eff {samples['effective_pairs']} over {samples['clusters']} work "
                f"clusters for {len(observations)} pairs, floor is {gates['minimum_effective_samples']} "
                f"({gates['source']}) -- pairs that share a work are not independent observations"
            )
        if any(not observation.get("background_distribution") for observation in observations):
            missing.append("background_distribution: empirical similarity-class distribution over pairs with historical_transmission = no_known_route, which only dated route-typed data can supply")
        profile_test = attractor_block_profile_test(observations, config, corpus_chance_similarity())
        if profile_test["status"] == STATUS_PROFILE_NOT_TESTABLE:
            missing.append(
                f"block_profile: M4's alpha vector predicts an ordering over the three dimension blocks and this "
                f"pair set cannot check it ({profile_test['reason']}); a four-way test in which the fourth model's "
                "one distinguishing prediction is never confronted with data is a three-way test with a decoration"
            )
    if derivation is not None:
        for node in derivation.get("nodes") or []:
            for which in ("composition", "witness"):
                date_obj = (node.get("dates") or {}).get(which)
                for field in date_object_missing_fields(date_obj, config, which=which):
                    missing.append(f"node {node.get('node_id')}: dates.{which}.{field}")
    elif not observations:
        missing.append("derivation: no candidate derivation record supplied (config > derivation_record_schema)")
    if scaffold and scaffold.get("available") and not scaffold.get("works_usable_for_priority_claims"):
        missing.append(f"dated attestation: {scaffold.get('works')} works in the scaffold, {scaffold.get('works_with_numeric_composition_date')} with a filled composition range and 0 usable for a priority claim; date_earliest, date_latest and dating_basis are unset at record level")
    seen = set()
    ordered = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def refusal(config, missing, derivation=None, scaffold=None):
    result = {
        "status": STATUS_NOT_YET_TESTABLE,
        "model_scores": None,
        "model_ranking": None,
        "parsimony": derivation_parsimony(derivation, config) if derivation else None,
        "missing_inputs": missing,
        "missing_input_count": len(missing),
        "preregistration": verify_preregistration(config),
        "dated_attestation_diagnostic": scaffold,
        "decision_gates_in_force": decision_gates(config),
        "reason": "the models are compared against evidence; with the dated, route-typed inputs absent there is no evidence to compare, so no score and no ranking are emitted",
        "what_would_close_the_gap": [
            "TRACK_B_METHOD_v2.md > 9.3 gate 'Dated composition and earliest-witness fields populated'",
            "second independent coder and published kappa",
            "dependence closure to chain level",
        ],
        "historical_conclusion": NO_HISTORICAL_CONCLUSION,
        "interpretation": "not_yet_testable is a published result, not a failed run. It is the recorded state of this layer today.",
    }
    return result


# --------------------------------------------------------------------------- top level


def evaluate_derivation(derivation, config, observations=None, scaffold=None):
    errors = derivation_errors(derivation, config)
    verification = verify_preregistration(config)
    missing = missing_required_inputs(config, derivation=derivation, observations=observations, scaffold=scaffold)
    parsimony = derivation_parsimony(derivation, config)
    if not verification["ok"]:
        return {
            "status": STATUS_NOT_PREREGISTERED,
            "model_scores": None,
            "model_ranking": None,
            "parsimony": parsimony,
            "derivation_errors": errors,
            "preregistration": verification,
            "missing_inputs": missing,
            "historical_conclusion": NO_HISTORICAL_CONCLUSION,
        }
    if errors:
        return {
            "status": STATUS_REJECTED_DERIVATION,
            "model_scores": None,
            "model_ranking": None,
            "parsimony": parsimony,
            "derivation_errors": errors,
            "preregistration": verification,
            "licence_violations_named": len(errors),
            "historical_conclusion": NO_HISTORICAL_CONCLUSION,
        }
    if missing or not observations:
        if not observations:
            missing = missing + [
                "pair set: dated, route-typed observations, including M2's background_distribution, which only an observed pair set with historical_transmission = no_known_route can supply"
            ]
        result = refusal(config, missing, derivation=derivation, scaffold=scaffold)
        result["derivation_errors"] = []
        result["preregistration_ok"] = True
        return result
    comparison = compare_observations(observations, config)
    if not comparison.get("ok"):
        return refusal(config, missing + comparison["missing"], derivation=derivation, scaffold=scaffold)
    margin = comparison["margin_declared"]
    licence = comparison["stage_2_inheritance_licence"]
    inheritance_models = licence["models_meeting_the_licence_margin"]
    stage_one = comparison["stage_1_symmetric_competition"]
    status = STATUS_MARGIN_MET if inheritance_models else STATUS_NOT_PREFERRED
    return {
        "status": status,
        "status_is_stage_2": True,
        "model_scores": comparison["log_likelihoods"],
        "model_ranking": comparison["ranking_by_log_likelihood"],
        "log10_bayes_factor_vs_M2": comparison["log10_bayes_factor_vs_M2"],
        "log10_bayes_factor_vs_M4": comparison["log10_bayes_factor_vs_M4"],
        "licence_baselines": licence["baselines"],
        "licence_min_margin_over_baselines": licence["licence_min_margin_over_baselines"],
        "licence_binding_baseline": licence["licence_binding_baseline"],
        "margin_declared": margin,
        "models_meeting_the_licence_margin": inheritance_models,
        "models_meeting_margin_vs_M2": comparison["models_meeting_margin_vs_M2"],
        "models_meeting_margin_vs_M4": comparison["models_meeting_margin_vs_M4"],
        "models_meeting_margin_on_whole_set": comparison["models_meeting_margin_on_whole_set"],
        "models_meeting_margin_on_held_out": comparison["models_meeting_margin_on_held_out"],
        "held_out_pairs": comparison["held_out_pairs"],
        "discovery_pairs": comparison["discovery_pairs"],
        "isolated_held_out_pairs": comparison["isolated_held_out_pairs"],
        "cluster_holdout": comparison["cluster_holdout"],
        "effective_samples": comparison["effective_samples"],
        "stage_1_symmetric_competition": stage_one,
        "m4_block_profile_test": stage_one["m4_block_profile_test"],
        "stage_2_inheritance_licence": licence,
        "both_stages_published": True,
        "stages_answer_different_questions": config["four_way_decision_rule"]["stage_2_inheritance_licence"]["relationship"],
        "monotone_decay_nested_case_reported": comparison["monotone_decay_nested_case_reported"],
        "log10_bayes_factor_vs_M2_held_out": comparison["log10_bayes_factor_vs_M2_held_out"],
        "log10_bayes_factor_vs_M4_held_out": comparison["log10_bayes_factor_vs_M4_held_out"],
        "parsimony": parsimony,
        "pairs": comparison["pairs"],
        "per_pair": comparison["per_pair"],
        "preregistration": verification,
        "historical_conclusion": NO_HISTORICAL_CONCLUSION,
        "reporting_rule": "stage 1 may name a winner only on its own margin rule, and only a winner whose one "
                          "distinguishing prediction the same pair set did not contradict; a derivation may be "
                          "reported as preferred only if it meets the margin against both no-edge baselines -- "
                          "independent origin and convergence -- on the cluster holdout as well as the whole set. "
                          "Neither stage is a historical conclusion.",
    }


def run(config_path=None, derivation_path=None, observations_path=None, scaffold_path=None):
    config = load_config(config_path)
    derivation = None
    observations = None
    if derivation_path:
        derivation = json.loads(Path(derivation_path).read_text(encoding="utf-8"))
    if observations_path:
        observations = json.loads(Path(observations_path).read_text(encoding="utf-8"))
        if isinstance(observations, dict):
            observations = observations.get("observations", [])
    scaffold = scaffold_diagnostic(scaffold_path)
    if derivation is not None:
        return evaluate_derivation(derivation, config, observations=observations, scaffold=scaffold)
    missing = missing_required_inputs(config, derivation=None, observations=observations, scaffold=scaffold)
    if observations and not missing:
        comparison = compare_observations(observations, config)
        if not comparison.get("ok"):
            return refusal(config, missing + comparison.get("missing", []), scaffold=scaffold)
        return {"status": comparison["stage_2_inheritance_licence"]["status"], "status_is_stage_2": True, **comparison, "historical_conclusion": NO_HISTORICAL_CONCLUSION}
    return refusal(config, missing, scaffold=scaffold)


# --------------------------------------------------------------------------- legacy lexical diagnostic


def run_lexical_diagnostics(write=True):
    """The v1-era TF-IDF sanity diagnostic, kept intact. Instrument diagnostics only; no historical finding."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    sys.path.insert(0, str(ROOT / "tools"))
    from text_pipeline import WORD_RE

    passages = [json.loads(line) for line in (ROOT / "corpus/derived/passages.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = [passage["text"] for passage in passages]
    index_by_id = {passage["passage_id"]: index for index, passage in enumerate(passages)}
    overlap_pairs = [
        ("sacred_books_east:p000138", "dhammapada_muller:p000026"),
        ("sacred_books_east:p000245", "quran_sale:p000419"),
    ]
    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(passages), size=256, replace=False)
    shuffled_texts = []
    for index in sample:
        words = [match.group(0) for match in WORD_RE.finditer(texts[index])]
        rng.shuffle(words)
        shuffled_texts.append(" ".join(words))
    work_ids = np.array([passage["work_id"] for passage in passages])
    left_random = rng.integers(0, len(passages), size=5000)
    right_random = rng.integers(0, len(passages), size=5000)
    valid = work_ids[left_random] != work_ids[right_random]
    left_random = left_random[valid]
    right_random = right_random[valid]
    results = {}
    for name, ngrams in {"unigram": (1, 1), "unigram_bigram": (1, 2), "bigram_only": (2, 2)}.items():
        vectorizer = TfidfVectorizer(
            ngram_range=ngrams,
            stop_words="english",
            strip_accents="unicode",
            sublinear_tf=True,
            min_df=2,
            max_df=0.85,
            max_features=120000,
            norm="l2",
            dtype=np.float32,
        )
        matrix = vectorizer.fit_transform(texts)
        shuffled = vectorizer.transform(shuffled_texts)
        shuffled_scores = _cosine_rows(matrix[sample], shuffled)
        random_scores = _cosine_rows(matrix[left_random], matrix[right_random])
        overlap_scores = {}
        for left_id, right_id in overlap_pairs:
            left = index_by_id[left_id]
            right = index_by_id[right_id]
            overlap_scores[f"{left_id}|{right_id}"] = float(_cosine_rows(matrix[left], matrix[right])[0])
        results[name] = {
            "vocabulary_size": len(vectorizer.vocabulary_),
            "shuffled_mean": float(shuffled_scores.mean()),
            "shuffled_median": float(np.median(shuffled_scores)),
            "random_p99": float(np.quantile(random_scores, 0.99)),
            "known_overlap_scores": overlap_scores,
        }
        print(name, results[name])
    output = {
        "seed": SEED,
        "interpretation": "Model diagnostics only. Bigrams capture local wording, not narrative event order.",
        "models": results,
    }
    if write:
        (ROOT / "results/model_comparison.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def _cosine_rows(left, right):
    import numpy as np

    return np.asarray(left.multiply(right).sum(axis=1)).ravel()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Track B model-comparison layer (refuses to rank without dated inputs)")
    parser.add_argument("--derivation", help="path to a candidate derivation record (config > derivation_record_schema)")
    parser.add_argument("--observations", help="path to a dated, route-typed pair set")
    parser.add_argument("--config", help="path to a model comparison config")
    parser.add_argument("--scaffold", help="path to the attestation scaffold csv")
    parser.add_argument("--write-to", help="publish the JSON result to this path instead of stdout")
    parser.add_argument("--power", action="store_true", help="run the decision-rule power simulation and publish results/model_power_simulation.json")
    parser.add_argument("--power-replications", type=int, help="override replications_per_cell for a smoke run; the artifact records the override")
    parser.add_argument("--power-max-pairs", type=int, help="override the grid ceiling for a smoke run; the artifact records the override")
    parser.add_argument("--legacy-lexical", action="store_true", help="run the old TF-IDF diagnostic instead, writing results/model_comparison.json")
    args = parser.parse_args(argv)
    if args.legacy_lexical:
        run_lexical_diagnostics()
        return 0
    if args.power:
        cells = None
        if args.power_max_pairs:
            grid = load_config(args.config)["power_simulation"]["grid"]
            cells = [value for value in range(int(grid["from"]), int(args.power_max_pairs) + 1, int(grid["step"]))]
        artifact = power_simulation(
            config=load_config(args.config),
            replications=args.power_replications,
            cells=cells,
            write=True,
            path=args.write_to,
        )
        print(
            f"wrote {(Path(args.write_to) if args.write_to else POWER_ARTIFACT_PATH).name} "
            f"status={artifact['status']} derived_minimum_pairs={artifact['derived_minimum_pairs']} "
            f"derived_minimum_effective_samples={artifact['derived_minimum_effective_samples']}"
        )
        return 0
    result = run(config_path=args.config, derivation_path=args.derivation, observations_path=args.observations, scaffold_path=args.scaffold)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.write_to:
        Path(args.write_to).write_text(text, encoding="utf-8")
        print(f"wrote {args.write_to} status={result['status']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
