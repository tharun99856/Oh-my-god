#!/usr/bin/env python3
"""One-shot migration of the Track B frame from seven dimensions to twelve.

The reviewer's item 1: orthogonality was claimed but not achieved. D2 folded three
independent questions into one label (how many beings are acknowledged, whether the
others are real, whether they may be worshipped) and D7 folded four (who speaks, what
act is performed, what genre carries it, what the text commits to). D1, D3, D5 and D6
allowed coexistence in the texts while the frame forced a single value.

This script rewrites `config/ontology_english_rules.json` and
`config/divinity_ontology.json` together, and reassigns the existing English patterns to
the new dimensions by named rule, so the correspondence between the old detector and the
new one is auditable rather than implicit. It is idempotent: run it again and it stops,
because the old dimension keys are gone.

Pattern reassignment is deliberately one-to-many. "No god but the LORD" is evidence about
population, about the reality of rivals and about exclusive devotion at the same time;
analytically distinct dimensions mean each question gets its own scan, not that each string is used
once.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "config/divinity_ontology.json"
RULES = ROOT / "config/ontology_english_rules.json"

# --------------------------------------------------------------------------- dimensions

D = lambda cardinality, question, note, coverage, values: {
    "cardinality": cardinality, "question": question, "note": note,
    "coverage_state": coverage, "values": values,
}
V = lambda definition, coverage="instrumented", disambiguation=False: {
    "definition": definition, "coverage": coverage, "disambiguation_needed": disambiguation,
}
INHERIT = lambda *pairs: {"inherit": list(pairs)}
NEW = lambda *patterns: {"new": list(patterns)}
BOTH = lambda pairs, *patterns: {"inherit": list(pairs), "new": list(patterns)}

# D2c asks a normative question. Most of the old "sole existent" strings are existence
# formulas that never mention practice, so they may not be inherited into the worship
# dimension — that would replace one conflation with its mirror image, reading a
# devotion-command out of an ontology-claim. Only patterns carrying devotional language
# pass, and the filter is published in the config so a reader can see what was dropped.
WORSHIP_LANGUAGE = r"worship|serve\b|bow\b|incense|sacrific|no\s+other\s+gods|before\s+me|god\s+but\b|pray"

UNDECIDABLE = V("the proposition does not commit; a reader could not say which value it carries")

DIMENSIONS = {
    "D1_ontological_category": D(
        "set",
        "What kind of thing is divinity taken to be, in this proposition?",
        "Set-valued. A text can hold that the ultimate is a personal being AND the ground in which "
        "other beings subsist; forcing one label invented a contradiction the tradition did not assert.",
        "partially_instrumented",
        {
            "personal_being": V("a being with mind, will and address, capable of being spoken to"),
            "impersonal_order_or_law": V("an order, law, ground or absolute that is not a being and has no mental states"),
            "animating_substance_or_power": V("sacred power as a quantifiable stuff or property that things may contain"),
            "collective_or_class": V("'the divine' names a class of beings; no single member is the referent"),
            "manifestation_or_hypostasis": V("a visible face of a hidden depth; the addressed figure is not the whole"),
            "deified_mortal": V("divinity as an honour a formerly human person received"),
            "unknowable_or_conceptless": V("the ultimate is declared beyond the reach of these predicates",
                                           coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D2a_acknowledged_population": D(
        "single",
        "How many divine beings does this proposition acknowledge?",
        "A counting question only. It carries no claim about worship and none about the reality of the "
        "beings counted; both were split out of the old D2.",
        "instrumented",
        {
            "one_only": V("exactly one divine being is acknowledged in the proposition"),
            "two_polar": V("two complementary terms, neither reducible to the other"),
            "few_or_several": V("a small definite number, without ranking"),
            "many_graded": V("a plurality with ranks, offices, genealogy or a head"),
            "uncountable_or_numeric_scheme": V("plurality expressed as a doctrinal number or as myriads"),
            "none_acknowledged": V("no divine being is conceded"),
            "undecidable": UNDECIDABLE,
        }),
    "D2b_reality_of_others": D(
        "single",
        "What status do other divine beings have, relative to the one in question?",
        "The truth-claim about rivals, separated from the counting question and from the worship question. "
        "A proposition can acknowledge many beings (D2a) while denying they are real, or acknowledge one "
        "while treating the others as real and subordinate.",
        "partially_instrumented",
        {
            "others_denied_unreal": V("other claimed divinities are explicitly not beings: nothing, non-beings, "
                                      "nameless, or the work of human hands"),
            "others_real_but_subordinate": V("others exist and are ordered below the one in question"),
            "others_real_and_not_subordinate": V("others exist and are not ranked under it"),
            "others_not_addressed": V("the proposition is silent about any other being",
                                      coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D2c_worship_exclusivity": D(
        "single",
        "Is devotion or rite restricted to this divinity?",
        "A normative question. 'Thou shalt have no other gods before me' is evidence here, not in D2b: it "
        "commands a practice and says nothing about whether other beings exist. The v1 audit found three "
        "worship prohibitions counted as existence claims; this dimension exists so the frame cannot make "
        "that mistake again.",
        "partially_instrumented",
        {
            "exclusive_devotion_commanded": V("rite, prayer or allegiance is owed to this divinity alone"),
            "devotion_to_others_permitted": V("the text treats devotion to other beings as legitimate, "
                                              "including when it is describing a practice it disapproves of "
                                              "in another voice", disambiguation=True),
            "devotion_mediated_by_hierarchy": V("access runs through subordinate beings, angels, saints or offices"),
            "no_devotional_language": V("the proposition makes no claim about practice at all",
                                       coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D3_agency": D(
        "set",
        "What agency is predicated — personhood, will, manner of acting, delegation?",
        "Set-valued. Deliberating will, delegated execution and reciprocal dependency coexist in ordinary "
        "religious texts; the old single label made them compete.",
        "partially_instrumented",
        {
            "personalhood_mind_and_will": V("the divine is spoken of as having mind, will and the capacity to be addressed"),
            "deliberating_will": V("decides, counsels, debates, commands, repents"),
            "effortless_self_evolution": V("produces without deliberation or labour: emanation, self-differentiation"),
            "law_without_will": V("cosmos runs by an impersonal regularity that is itself sacred"),
            "delegated_execution": V("authorship is nominal; subordinates, angels, fate-figures or offices do the work"),
            "reciprocal_dependency": V("the divine needs human rite, sacrifice or prayer to remain effective"),
            "non_agential": V("the divine is contemplative, immobile, does nothing", coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D4_cosmic_function": D(
        "set",
        "What work is the divinity credited with?",
        "Set-valued, unchanged from the previous release; the values and their detectors are inherited verbatim.",
        "instrumented",
        {
            "creating_ex_nihilo_or_by_word": V("bringing world into being, often by utterance or command"),
            "crafting_from_prior_matter": V("shaping already-existing material, demiurgic"),
            "generating_by_procreation": V("world and gods issued by begetting, birth or union"),
            "sustaining_order": V("maintaining the cosmos against collapse"),
            "judging_moral_order": V("requiring, weighing, punishing, vindicating"),
            "dissolving_or_reabsorbing": V("ending or drawing the world back into itself"),
            "revealing_teaching_lawgiving": V("communicating knowledge or statute to humans"),
            "rescuing_healing_restoring": V("soteriological action toward humans in a damaged condition"),
            "fertilisingWeather_agricultural": V("storm, dew, grain, fertility: the divine as livelihood guarantee"),
            "guarding_localised": V("defence of a place, people, house or cult site"),
            "no_function_attributed": V("invoked but credited with no cosmic or human work",
                                        coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D5_universe_relationship": D(
        "set",
        "What is the relation between divinity and the world?",
        "Set-valued, and the composite value 'other_and_indwelling' is gone: transcendence and immanence are "
        "two labels that may both apply, which is what the texts actually say.",
        "partially_instrumented",
        {
            "wholly_other": V("the divine and the world are distinct kinds; the world does not contain or constitute it"),
            "indwelling_in_world": V("the divine is present within the world or within its worshipers"),
            "identical_with_world": V("the cosmos itself, or its totality, is the divine"),
            "world_in_divine_not_exhausting": V("the world is within the divine but does not exhaust it",
                                                coverage="not_yet_instrumented"),
            "retreated_or_absent": V("a deity made the world and withdrew, was displaced, or is inaccessible"),
            "world_as_appearance": V("the cosmos is unreal, degraded or illusory relative to the divine"),
            "scale_not_claimed": V("the divine is bound to places, animals, lineage or cult; no cosmic-scale claim",
                                   coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D6_temporal_nature": D(
        "set",
        "What is the divinity's relation to time, to beginning and to end?",
        "Set-valued. Eternal existence, cyclic recurrence and an eschatological function are three properties, "
        "not three mutually exclusive answers to one question.",
        "partially_instrumented",
        {
            "uncreated_eternal": V("no beginning; exists necessarily or from ever"),
            "born_in_time": V("has a genealogy, a birth, a youngest generation"),
            "cyclically_recurrent": V("divine acts or ages return on a measurable cycle"),
            "linear_once": V("one creation and one consummation; history does not repeat"),
            "eschatologically_future": V("the decisive divine reality is still to arrive"),
            "from_lost_past": V("the divine walked with humans and has departed", coverage="not_yet_instrumented"),
            "outside_time": V("atemporal: 'beginning' does not apply", coverage="not_yet_instrumented"),
            "undecidable": UNDECIDABLE,
        }),
    "D7a_speaker_attribution": D(
        "single",
        "Who is the utterer this text prints in this proposition?",
        "Attribution only. The previous release mixed the speaker with the act, the genre and the text's stance.",
        "partially_instrumented",
        {
            "divine_self_speech": V("the divine speaks in the first person within the proposition"),
            "praying_or_praising_human_voice": V("a human addresses the divine"),
            "narrator_or_scribe": V("the framing voice of the text reports"),
            "character_within_narrative": V("a figure in the story speaks; the text is not speaking",
                                            disambiguation=True),
            "opponent_or_denier": V("a claimant the text sets itself against speaks", disambiguation=True),
            "editorial_or_ethnographic_frame": V("a compiler, collector or missionary reports what others hold"),
            "undecidable": UNDECIDABLE,
        }),
    "D7b_speech_act": D(
        "single",
        "What act is performed in this proposition?",
        "The illocutionary question, alone: asserting, addressing, commanding, questioning, conditioning, "
        "reporting, denying, boasting, or negating apophatically.",
        "instrumented",
        {
            "assert": V("presented as being so"),
            "address_or_praise": V("spoken to the divine rather than about it"),
            "command": V("statute or prohibition; its force is 'you shall'"),
            "question": V("interrogative; it seeks rather than concludes"),
            "condition": V("holds only inside an 'if'"),
            "report": V("someone's words or a narrative event are relayed"),
            "deny": V("a negation is performed as the act"),
            "boast": V("a claimant exalts themselves; the text may or may not agree"),
            "negate_apophatically": V("denial performed as worship: no attribute reaches it"),
            "undecidable": UNDECIDABLE,
        }),
    "D7c_discourse_genre": D(
        "single",
        "What kind of discourse carries this proposition?",
        "Genre is not a speech act: a hymn contains address and doctrine, a prophetic oracle contains command "
        "and assertion, a commentary contains report and argument.",
        "partially_instrumented",
        {
            "confessional_formula": V("a fixed creed or shorthand of belief"),
            "hymn_or_prayer": V("praise, petition or lament"),
            "mythic_narrative": V("told as event"),
            "legal_statute": V("regulation of practice"),
            "philosophical_argument": V("inferred from premises"),
            "prophetic_oracle": V("declared as message, often with a messenger formula"),
            "commentary_or_description": V("an outsider or editor describing a belief",
                                           coverage="partially_instrumented"),
            "doubt_or_inquiry": V("questioning that seeks"),
            "undecidable": UNDECIDABLE,
        }),
    "D7d_epistemic_commitment": D(
        "single",
        "Does the framing text commit to the proposition, attribute it, reject it, or hold it open?",
        "Commitment is neither speaker nor act. An opponent may assert; a narrator may report; whether the text "
        "means the proposition to be so is answered by the frame around the clause. This is the question the "
        "previous release silently merged into speech act, and the reason a conditional could be read as an "
        "atheist confession.",
        "instrumented",
        {
            "endorsed_by_text": V("the framing voice presents the proposition as so"),
            "attributed_not_endorsed": V("the text relays the proposition without committing to it",
                                         disambiguation=True),
            "rejected_in_text": V("the framing voice sets the proposition against what it holds to be true"),
            "suspended_or_held_open": V("question or condition: the text leaves it open"),
            "not_applicable_non_assertive": V("the proposition is address, praise or command, so 'does the text "
                                              "assert it' has no application"),
            "undecidable": UNDECIDABLE,
        }),
}

# ------------------------------------------------------------------------ pattern routing
# new value -> where its English patterns come from
PATTERNS = {
    "D1_ontological_category": {
        "personal_being": INHERIT(("D1_divine_ontology", "personal_agent")),
        "impersonal_order_or_law": INHERIT(("D1_divine_ontology", "impersonal_principle")),
        "animating_substance_or_power": INHERIT(("D1_divine_ontology", "animating_substance")),
        "collective_or_class": INHERIT(("D1_divine_ontology", "collective_or_class")),
        "manifestation_or_hypostasis": INHERIT(("D1_divine_ontology", "manifestation_or_hypostasis")),
        "deified_mortal": INHERIT(("D1_divine_ontology", "deified_mortal")),
        "unknowable_or_conceptless": INHERIT(("D1_divine_ontology", "unknowable_or_conceptless")),
    },
    "D2a_acknowledged_population": {
        "one_only": INHERIT(("D2_plurality", "sole_existent_others_unreal"),
                            ("D2_plurality", "sole_worshipable_others_acknowledged")),
        "two_polar": INHERIT(("D2_plurality", "dyadic_polar")),
        "few_or_several": INHERIT(("D2_plurality", "many_co_equal")),
        "many_graded": INHERIT(("D2_plurality", "many_ranked"),
                               ("D2_plurality", "supreme_head_with_assembly")),
        "uncountable_or_numeric_scheme": INHERIT(("D2_plurality", "numeric_scheme")),
        "none_acknowledged": INHERIT(("D2_plurality", "none")),
    },
    "D2b_reality_of_others": {
        "others_denied_unreal": INHERIT(("D2_plurality", "sole_existent_others_unreal"),
                                        ("D2_plurality", "none")),
        "others_real_but_subordinate": INHERIT(("D2_plurality", "sole_worshipable_others_acknowledged"),
                                               ("D2_plurality", "supreme_head_with_assembly"),
                                               ("D2_plurality", "many_ranked")),
        "others_real_and_not_subordinate": INHERIT(("D2_plurality", "many_co_equal"),
                                                   ("D2_plurality", "dyadic_polar")),
    },
    "D2c_worship_exclusivity": {
        "exclusive_devotion_commanded": {
            "inherit": [("D2_plurality", "sole_existent_others_unreal"),
                        ("D2_plurality", "sole_worshipable_others_acknowledged")],
            "require": WORSHIP_LANGUAGE,
            "new": [r"\bthou\s+shalt\s+have\s+no\s+other\s+gods\b",
                    r"\bno\s+other\s+gods\b",
                    r"\bworship\s+(?:the\s+)?(?:LORD|him)\s+only\b",
                    r"\bserve\s+him\s+only\b"]},
        "devotion_to_others_permitted": NEW(
            r"\bsacrific\w*\s+to\s+the\s+gods\b",
            r"\bworship\w*\s+(?:the\s+)?(?:idols?|images?|baalim)\b",
            r"\bburn\s+incense\s+to\b",
            r"\bmake\s+mention\s+of\s+other\s+gods\b"),
        "devotion_mediated_by_hierarchy": NEW(
            r"\bangel\s+of\s+the\s+(?:LORD|Lord)\b",
            r"\b(?:intercess|mediat)\w+\b",
            r"\bthrough\s+(?:his|the)\s+(?:son|angels|ministers|priests)\b"),
    },
    "D3_agency": {
        "personalhood_mind_and_will": INHERIT(("D1_divine_ontology", "personal_agent")),
        "deliberating_will": INHERIT(("D3_agency", "deliberating_will")),
        "effortless_self_evolution": INHERIT(("D3_agency", "effortless_self_evolution")),
        "law_without_will": INHERIT(("D3_agency", "law_without_will")),
        "delegated_execution": INHERIT(("D3_agency", "delegated_execution")),
        "reciprocal_dependency": INHERIT(("D3_agency", "reciprocal_dependency")),
        "non_agential": INHERIT(("D3_agency", "non_agential")),
    },
    "D4_cosmic_function": {name: INHERIT(("D4_cosmic_function", name)) for name in [
        "creating_ex_nihilo_or_by_word", "crafting_from_prior_matter", "generating_by_procreation",
        "sustaining_order", "judging_moral_order", "dissolving_or_reabsorbing",
        "revealing_teaching_lawgiving", "rescuing_healing_restoring",
        "fertilisingWeather_agricultural", "guarding_localised", "no_function_attributed"]},
    "D5_universe_relationship": {
        "wholly_other": INHERIT(("D5_universe_relationship", "wholly_other")),
        "indwelling_in_world": INHERIT(("D5_universe_relationship", "other_and_indwelling")),
        "identical_with_world": INHERIT(("D5_universe_relationship", "identical_with_world")),
        "world_in_divine_not_exhausting": INHERIT(("D5_universe_relationship", "world_in_divine_not_exhausting")),
        "retreated_or_absent": INHERIT(("D5_universe_relationship", "retreated_or_absent")),
        "world_as_appearance": INHERIT(("D5_universe_relationship", "world_as_appearance")),
        "scale_not_claimed": INHERIT(("D5_universe_relationship", "scale_not_claimed")),
    },
    "D6_temporal_nature": {name: INHERIT(("D6_temporal_nature", name)) for name in [
        "uncreated_eternal", "born_in_time", "cyclically_recurrent", "linear_once",
        "eschatologically_future", "from_lost_past", "outside_time"]},
    # D7a-d are assigned from window and clause shape by the marker machinery, not from a term.
    # Only two D7a values have term detectors at all, and they are narrow on purpose: the
    # messenger formula and the first-person divine claim. Everything else needs a reader.
    "D7a_speaker_attribution": {
        "divine_self_speech": NEW(
            r"\bI\s+am\s+the\s+LORD\b", r"\bI\s+(?:am|was)\s+(?:god|God)\b", r"\bI\s+myself\b",
            r"\bsaith\s+the\s+LORD\b", r"\bthe\s+LORD\s+said\b", r"\bthus\s+saith\s+the\s+LORD\b"),
        "praying_or_praising_human_voice": NEW(
            r"\bO\s+(?:god|God|Lord)\b", r"\bmy\s+god\b", r"\bwe\s+(?:praise|thank|beseech|call\s+upon)\b",
            r"\bhear\s+(?:me|thou)\b"),
    },
}

MIGRATION_NOTE = {
    "old_D7_human_interpretation": (
        "Not inherited as a dimension. Its twelve labels distributed across four questions: "
        "asserted_doctrine -> D7b=assert plus D7d=endorsed_by_text; doxology_or_address -> D7b=address_or_praise "
        "plus D7c=hymn_or_prayer; mythic_narration -> D7b=report plus D7c=mythic_narrative; "
        "philosophical_argument -> D7c=philosophical_argument; prescriptive_command -> D7b=command plus "
        "D7c=legal_statute; conditional_hypothetical -> D7b=condition plus D7d=suspended_or_held_open; "
        "reported_speech_of_opponent -> D7a=opponent_or_denier plus D7b=report; polemic_denial -> D7b=deny; "
        "editorial_or_ethnographic_description -> D7a=editorial_or_ethnographic_frame plus D7d=attributed_not_endorsed; "
        "boast_of_non_divine_claimant -> D7b=boast plus D7d=rejected_in_text; apophatic_negation -> "
        "D7b=negate_apophatically; doubt_or_inquiry -> D7b=question plus D7c=doubt_or_inquiry. The old labels "
        "were not a mutually exclusive classification, which is why a hymn containing doctrine and a conditional "
        "containing a reported statement each had to be forced into one slot."),
    "old_D2_plurality": (
        "Split three ways. Every pattern in the old value set is now attached to the dimension whose question it "
        "actually answers; the sole_existent and sole_worshipable sets appear in all three D2 dimensions because "
        "those strings do carry all three claims, and the frame now records that separately instead of choosing one."),
}


def old_values(old_rules, dimension):
    return old_rules["dimensions"][dimension]["values"]


def old_patterns(old_rules, dimension, value):
    spec = old_values(old_rules, dimension).get(value)
    return list(spec.get("patterns") or []) if isinstance(spec, dict) else []


def migrate_rules(old_rules):
    dimensions = {}
    for key, spec in DIMENSIONS.items():
        routing = PATTERNS.get(key, {})
        values = {}
        for value, definition in spec["values"].items():
            entry = dict(definition)
            source = routing.get(value)
            if source:
                patterns, origins, dropped = [], [], []
                require = source.get("require")
                for dimension, old_value in source.get("inherit", []):
                    origins.append(f"{dimension}={old_value}")
                    for pattern in old_patterns(old_rules, dimension, old_value):
                        if require and not re.search(require, pattern.replace("\\b", " ").replace("\\s+", " "),
                                                     re.IGNORECASE):
                            dropped.append(pattern)
                            continue
                        patterns.append(pattern)
                patterns.extend(source.get("new", []))
                if patterns:
                    entry["patterns"] = sorted(set(patterns))
                    entry["inherited_from"] = origins
                if require:
                    entry["inheritance_filter"] = {
                        "require": require,
                        "reason": "D2c asks whether devotion is restricted; an existence formula says nothing "
                                  "about practice and may not be scored as a worship claim",
                        "patterns_dropped_from_inheritance": sorted(dropped)}
                if source.get("new"):
                    entry["new_in_v3"] = sorted(set(source["new"]))
            values[value] = entry
        dimensions[key] = {"cardinality": spec["cardinality"], "question": spec["question"],
                           "note": spec["note"], "coverage_state": spec["coverage_state"],
                           "assigned_by": ("clause and window shape (speech_act_markers), evaluated before "
                                           "the term dimensions" if key.startswith("D7")
                                           else "term patterns"),
                           "values": values}
    rules = dict(old_rules)
    rules["schema_version"] = "3.0.0"
    rules["frame"] = "twelve analytically distinct dimensions, proposition-level"
    rules["purpose"] = ("English-detector patterns for the twelve-dimension Track B frame. Patterns were "
                        "reassigned from the seven-dimension release by named rule "
                        "(tools/migrate_rules_to_v3.py); one surface string may be evidence on several "
                        "dimensions, because the dimensions ask different questions.")
    rules["distinctness_note"] = (
        "Set-valued dimensions (D1, D3, D4, D5, D6) may carry several values for one proposition. Single-valued "
        "dimensions (D2a, D2b, D2c, D7a, D7b, D7c, D7d) may not: when two of their values fire on one proposition "
        "the instrument records a conflict and asks a reader, instead of choosing by precedence.")
    rules["migration_from_seven_dimensions"] = MIGRATION_NOTE
    rules["dimensions"] = dimensions
    return rules


def migrate_ontology(old_ontology, old_rules, new_rules):
    ontology = dict(old_ontology)
    ontology["schema_version"] = "3.0.0"
    ontology["instrument"] = "Track B divinity-concept frame, v3 (twelve dimensions, proposition-level)"
    ontology["replaces"] = ["Track B v2 seven-dimension frame", "the ten grammars of tools/divinity_terms.py"]
    ontology["design_motivation"] = (
        "v2 claimed seven orthogonal dimensions but delivered two composite ones. D2 answered three questions at "
        "once — how many beings, whether the others are real, whether they may be worshipped — and D7 answered four "
        "— who speaks, what act, what genre, what commitment. Five further dimensions forced a single value where "
        "the texts plainly hold several at once. v3 splits D2 into D2a/D2b/D2c and D7 into D7a/D7b/D7c/D7d, makes "
        "D1, D3, D4, D5 and D6 set-valued, and moves the unit of analysis from the utterance window to the "
        "proposition, with the window retained as context. It also replaces the single refusal state with three "
        "separate fields, so that a record the frame will not count as affirmed doctrine is still available as "
        "evidence that a concept is represented in the text.")
    ontology["distinctness_status"] = {
        "claim": "twelve analytically distinct dimensions, each answering exactly one question",
        "set_valued": [k for k, s in DIMENSIONS.items() if s["cardinality"] == "set"],
        "single_valued": [k for k, s in DIMENSIONS.items() if s["cardinality"] == "single"],
        "residual_risk": (
            "Distinctness is a property of the questions, not of the English detectors. Several values are "
            "detected by the same surface string (a confession of exclusive devotion populates D2a, D2b and D2c "
            "together), so the dimensions are correlated in observation while remaining independent in definition. "
            "A reader who treats a co-occurrence as three independent attestations has reintroduced the error this "
            "split was designed to remove."),
        "migration_record_note": (
            "The shipped config carries four fields this migration did not write, added after it ran: "
            "`status_of_the_claim` and `what_would_test_it` (why the word is `analytically distinct` and not "
            "`orthogonal`, which is an empirical property no coding has measured yet), "
            "`conceptual_and_discourse_blocks` (D1-D6 against D7a-D7d, reported as two similarities rather than "
            "averaged into one), and `d7d_epistemic_commitment_and_doctrinal_endorsement` (the two are one "
            "detector reading published twice, not two measurements). Re-running this migration from the "
            "pre-v3 backup produces a config missing them, and the freshness assertions in "
            "`tests/test_divinity_ontology.py` fail on the resulting hash change rather than passing quietly."),
    }
    ontology["unit_of_analysis"] = {
        "record": "one dimension value predicated of one identified referent in one proposition",
        "proposition": "the minimal clause that carries a subject and a predicate about a divine referent; the "
                       "utterance window is retained as context because a proposition read without its window "
                       "cannot be assigned a speaker or a commitment",
        "why_not_the_window": "a window can carry three distinct claims — that a creator made the world, that other "
                              "beings existed before it, that those beings were subordinate — and coding them as "
                              "one state produced one ambiguous conceptual reading per paragraph",
        "fields": ["referent_surface", "referent_kind", "proposition_text", "proposition_char_start",
                   "proposition_char_end", "window_text", "window_char_start", "window_char_end",
                   "speaker_attribution", "assertion_mode"],
    }
    ontology["assertion_logic"] = {
        "three_questions_kept_separate": {
            "conceptual_presence": "Is this concept represented in the passage at all? Values: represented, "
                                   "not_represented_in_available_sources, undecidable_from_available_sources.",
            "doctrinal_endorsement": "Does the framing voice affirm the proposition? This is not a thirteenth "
                                     "question: tools/divinity_ontology.py writes the field as "
                                     "D7d_epistemic_commitment's own value, so it carries that dimension's six values "
                                     "(endorsed_by_text, attributed_not_endorsed, rejected_in_text, "
                                     "suspended_or_held_open, not_applicable_non_assertive, undecidable) and cannot "
                                     "disagree with it except on a `not_yet_instrumented` row, where the "
                                     "record forces this field to `undecidable`. See distinctness_status."
                                     "d7d_epistemic_commitment_and_doctrinal_endorsement.",
            "historical_transmission": "Is there evidence that this concept travelled from an earlier source? "
                                       "Values: not_yet_assessable until dated original-language attestations and "
                                       "documented contact routes exist.",
        },
        "rule": (
            "These three are never collapsed into one another and never merged into one field. A withheld endorsement "
            "is not an absence of the concept: the records the previous release refused are retained and are available "
            "for conceptual analysis, and are excluded only from the count of affirmative doctrinal claims."),
        "machine_states": ["candidate", "candidate_requires_human_disambiguation", "not_yet_instrumented"],
        "removed_state": {
            "blocked_by_speech_act": "dropped in v3. It answered two questions with one label and caused 54 records "
                                     "representing a concept to be treated as though they represented nothing."},
        "coverage_states": ["instrumented", "partially_instrumented", "not_yet_instrumented"],
    }
    ontology["coding_record"] = {
        "dimensions": {key: {"cardinality": spec["cardinality"], "question": spec["question"],
                             "coverage_state": spec["coverage_state"],
                             "note": spec["note"],
                             "values": {value: aspec["definition"] for value, aspec in spec["values"].items()}}
                       for key, spec in DIMENSIONS.items()},
        "three_question_fields": ["conceptual_presence", "doctrinal_endorsement", "historical_transmission"],
    }
    # `dimensions` is the frame the instrument reads; leaving it on the old seven keys while
    # coding_record carried twelve would have made the two sections disagree silently.
    ontology["dimensions"] = ontology["coding_record"]["dimensions"]
    ontology["multilingual_status"] = {
        "self_description": "multilingual-ready framework, not an operational multilingual instrument",
        "operational_detectors": "English translations only",
        "source_language_detection": "not operational; no lexicon entry has been verified against an original-language "
                                     "source or a critical edition",
        "consequence": "the records this release publishes are evidence about English translation vocabulary, not "
                       "about the concepts a tradition expressed in its own language",
    }
    ontology["english_detectors"] = {key: spec["values"] for key, spec in new_rules["dimensions"].items()}
    return ontology


def main():
    old_rules = json.loads(RULES.read_text(encoding="utf-8"))
    if "D2_plurality" not in old_rules["dimensions"]:
        print(f"{RULES.name} already carries the v3 dimension set; nothing to migrate")
        return 0
    old_ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    new_rules = migrate_rules(old_rules)
    new_ontology = migrate_ontology(old_ontology, old_rules, new_rules)
    RULES.write_text(json.dumps(new_rules, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ONTOLOGY.write_text(json.dumps(new_ontology, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("migrated both configs to the twelve-dimension frame")
    detector_total = 0
    for key, spec in new_rules["dimensions"].items():
        with_patterns = [v for v, s in spec["values"].items() if s.get("patterns")]
        detector_total += len(with_patterns)
        print(f"  {key:32s} {spec['cardinality']:6s} {len(with_patterns):2d}/{len(spec['values'])} values detected")
    print(f"  total values carrying an English detector: {detector_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
