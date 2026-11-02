"""Locator, state-logic and no-fabrication tests for the Track B v3 ontology instrument.

v3 changed the unit (proposition, not window), the dimensions (twelve, not seven) and
the refusal logic (endorsement withheld, never a record deleted), so these tests check
the things that would make the published counts lies:

- every published span lands on the words it reports, at match, proposition and window
  level;
- the three questions the reviewer separated stay separate -- conceptual presence,
  doctrinal endorsement, historical transmission -- and no record is discarded because
  its endorsement was withheld;
- the composite dimensions really are split, and a single-valued dimension that found
  two values says so instead of choosing one in silence;
- the multilingual claim stays unbuilt, the dates stay empty, and no record claims a
  human coding that has not happened;
- the graph says approximate LSH with a measured recall rather than "exhaustive".
"""

import csv
import gzip
import hashlib
import json
import re
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import divinity_ontology  # noqa: E402

STATES = {"candidate", "candidate_requires_human_disambiguation", "not_yet_instrumented"}
CONCEPT_DIMENSIONS = {"D1_ontological_category", "D2a_acknowledged_population", "D2b_reality_of_others",
                      "D2c_worship_exclusivity", "D3_agency", "D4_cosmic_function",
                      "D5_universe_relationship", "D6_temporal_nature"}
INTERPRETATION_DIMENSIONS = {"D7a_speaker_attribution", "D7b_speech_act",
                             "D7c_discourse_genre", "D7d_epistemic_commitment"}
AFFIRMING_ACTS = {"assert", "deny"}
AFFIRMING_COMMITMENT = {"endorsed_by_text"}


def collapse(text):
    return re.sub(r"\s+", " ", text)


class OntologyInstrumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("results/ontology_attestations.jsonl.gz", "results/ontology_run_summary.json",
                     "results/ontology_graph.json", "results/graph_recall_validation.json"):
            if not (ROOT / name).exists():
                raise unittest.SkipTest(f"{name} has not been produced yet")
        cls.records = [json.loads(line)
                       for line in gzip.open(ROOT / "results/ontology_attestations.jsonl.gz", "rt",
                                             encoding="utf-8")]
        cls.summary = json.loads((ROOT / "results/ontology_run_summary.json").read_text(encoding="utf-8"))
        cls.graph = json.loads((ROOT / "results/ontology_graph.json").read_text(encoding="utf-8"))
        cls.recall = json.loads((ROOT / "results/graph_recall_validation.json").read_text(encoding="utf-8"))
        cls.ontology = json.loads((ROOT / "config/divinity_ontology.json").read_text(encoding="utf-8"))
        cls.rules = json.loads((ROOT / "config/ontology_english_rules.json").read_text(encoding="utf-8"))
        cls.dimensions = cls.ontology["dimensions"]
        cls.passages = {}
        for line in (ROOT / "corpus/derived/passages_v2.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            cls.passages[record["passage_id"]] = record

    # ------------------------------------------------------------------ spans
    def test_every_record_span_lands_on_the_words_it_reports(self):
        for record in self.records:
            passage = self.passages[record["passage_id"]]
            start = record["char_start"] - passage["body_char_start"]
            end = record["char_end"] - passage["body_char_start"]
            self.assertLess(0, end, f"{record['record_id']} has an empty span")
            self.assertLess(start, end, f"{record['record_id']} spans backwards")
            self.assertEqual(collapse(passage["text"][start:end]), record["surface_text"],
                             f"{record['record_id']} does not point at its own surface text")

    def test_every_proposition_span_slices_out_of_the_raw_text_as_published(self):
        for record in self.records:
            passage = self.passages[record["passage_id"]]
            start = record["proposition_char_start"] - passage["body_char_start"]
            end = record["proposition_char_end"] - passage["body_char_start"]
            self.assertLess(start, end, f"{record['record_id']} has an empty proposition")
            self.assertLessEqual(end, len(passage["text"]),
                                 f"{record['record_id']} proposition runs past the passage")
            self.assertEqual(collapse(passage["text"][start:end]).strip(),
                             collapse(record["proposition_text"]).strip(),
                             f"{record['record_id']} proposition span does not hold its proposition text")

    def test_the_proposition_sits_in_the_window_and_the_match_sits_in_the_proposition(self):
        for record in self.records:
            self.assertLessEqual(record["window_char_start"], record["proposition_char_start"])
            self.assertLessEqual(record["proposition_char_end"], record["window_char_end"])
            self.assertLess(record["window_char_start"], record["window_char_end"])
            self.assertLessEqual(record["proposition_char_start"], record["char_start"])
            self.assertLessEqual(record["char_end"], record["proposition_char_end"])

    def test_the_window_span_slices_out_of_the_raw_text_as_published(self):
        for record in self.records:
            passage = self.passages[record["passage_id"]]
            start = record["window_char_start"] - passage["body_char_start"]
            end = record["window_char_end"] - passage["body_char_start"]
            self.assertLess(start, end, f"{record['record_id']} has an empty window")
            self.assertIn(collapse(record["surface_text"]), collapse(passage["text"][start:end]),
                          f"{record['record_id']} window does not hold the words it matched")

    def test_the_normaliser_offset_map_is_exactly_as_long_as_the_text_it_returns(self):
        for text in ["no whitespace trouble", "hard\nwrapped\ttwospaces  here", "\r\nleading and trailing   ",
                     "a\nb"]:
            norm, map_to_raw = divinity_ontology.normalise(text)
            self.assertEqual(len(map_to_raw), len(norm), f"offset map drifted for {text!r}")
            self.assertTrue(all(index < len(text) for index in map_to_raw), f"index past the text for {text!r}")
            self.assertEqual(collapse("".join(text[index] for index in map_to_raw)), norm)

    # ------------------------------------------------------------------ segmentation
    def test_a_window_with_two_claims_becomes_two_propositions(self):
        text = "I am the Lord, and there is none else; I form the light and create darkness"
        split = divinity_ontology.propositions_of(text)
        self.assertGreaterEqual(len(split), 2, "a coordinated multi-claim window was left as one proposition")
        for start, end in split:
            self.assertLess(start, end)
            self.assertGreaterEqual(len(text[start:end].split()), divinity_ontology.MIN_PROPOSITION_WORDS,
                                    f"a bare fragment was published as its own proposition: {text[start:end]!r}")

    def test_a_split_never_leaves_a_coordinator_at_the_head_of_a_proposition(self):
        # A subordinator is kept at the head on purpose: dropping "if" would turn a
        # condition into an assertion, which is the error the endorsement axis exists to avoid.
        text = ("the LORD said that he would gather the people, and he wept because the city "
                "was broken, or the king denied it")
        spans = divinity_ontology.propositions_of(text)
        self.assertGreaterEqual(len(spans), 3)
        for index, (start, end) in enumerate(spans):
            self.assertLess(start, end)
            self.assertNotRegex(text[start:end].strip(), r"\A(and|but|or|nor)\s",
                                f"proposition begins on a coordinator: {text[start:end]!r}")
            if index:
                self.assertGreaterEqual(start, spans[index - 1][1], "propositions overlap")
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], len(text))

    # ------------------------------------------------------------------ dimensions
    def test_the_twelve_dimensions_answer_one_question_each(self):
        self.assertEqual(set(self.dimensions), CONCEPT_DIMENSIONS | INTERPRETATION_DIMENSIONS)
        self.assertEqual(len(self.dimensions), 12)
        for key, spec in self.dimensions.items():
            self.assertTrue(spec["question"].strip(), f"{key} declares no question")
            self.assertIn(spec["cardinality"], ("single", "set"), f"{key} declares no cardinality")
            self.assertIn("undecidable", spec["values"],
                          f"{key} has no residual value, so every reading is forced")
        pluralities = {k for k in self.dimensions if k.startswith("D2")}
        self.assertEqual(len(pluralities), 3, "the plurality composite is not split")
        interpretations = {k for k in self.dimensions if k.startswith("D7")}
        self.assertEqual(len(interpretations), 4, "the interpretation composite is not split")

    def test_record_cardinality_matches_the_dimension_declaration(self):
        for record in self.records:
            self.assertEqual(record["cardinality"], self.dimensions[record["dimension"]]["cardinality"],
                             f"{record['record_id']} carries a cardinality the ontology does not declare")

    def test_a_single_valued_dimension_that_found_two_values_publishes_the_conflict(self):
        clashed = [r for r in self.records if r.get("value_conflict")]
        for record in clashed:
            self.assertEqual(record["cardinality"], "single")
            self.assertGreaterEqual(len(record["value_conflict"]), 2)
            self.assertEqual(record["assertion_state"], "candidate_requires_human_disambiguation",
                             f"{record['record_id']} hides a conflict behind a single label")
        by_proposition = defaultdict(set)
        for record in self.records:
            if record["cardinality"] == "single":
                by_proposition[(record["passage_id"], record["proposition_char_start"],
                                record["dimension"])].add(record["value"])
        multi = {k for k, v in by_proposition.items() if len(v) > 1}
        self.assertEqual(len(multi), len({(r["passage_id"], r["proposition_char_start"], r["dimension"])
                                         for r in clashed}),
                         "two values landed on one proposition without a published conflict")

    def test_the_interpretation_dimensions_are_filled_on_every_record(self):
        for record in self.records:
            for key in INTERPRETATION_DIMENSIONS:
                self.assertIn(record[key], self.dimensions[key]["values"],
                              f"{record['record_id']} has {key}={record[key]!r}, which the ontology does not define")

    # ------------------------------------------------------------------ three questions
    def test_no_record_is_deleted_because_its_endorsement_was_withheld(self):
        for record in self.records:
            self.assertIn(record["conceptual_presence"],
                          ("represented_in_passage", "undecidable_from_available_sources"))
            self.assertIn(record["doctrinal_endorsement"], self._endorsement_values())
            self.assertEqual(record["historical_transmission"], "not_yet_assessable")
            self.assertIsNone(record["date_earliest"])
            self.assertIsNone(record["date_latest"])
        withheld = [r for r in self.records if not r["counts_as_affirmative_doctrine"]
                    and r["conceptual_presence"] == "represented_in_passage"]
        self.assertGreater(len(withheld), 1000,
                           "withholding endorsement has become a deletion again")
        self.assertLess(sum(1 for r in self.records if r["counts_as_affirmative_doctrine"]),
                        len(self.records), "every record is doctrine, which no reading of this corpus supports")

    def _endorsement_values(self):
        return set(self.dimensions["D7d_epistemic_commitment"]["values"])

    def test_affirmative_doctrine_never_escapes_the_conjunction_of_act_and_commitment(self):
        for record in self.records:
            if record["counts_as_affirmative_doctrine"]:
                self.assertIn(record["D7b_speech_act"], AFFIRMING_ACTS,
                              f"{record['record_id']} is doctrine without an asserting or denying act")
                self.assertIn(record["D7d_epistemic_commitment"], AFFIRMING_COMMITMENT,
                              f"{record['record_id']} is doctrine the framing text does not commit to")
                self.assertNotEqual(record["assertion_state"], "not_yet_instrumented")
            elif (record["D7b_speech_act"] in AFFIRMING_ACTS
                  and record["D7d_epistemic_commitment"] in AFFIRMING_COMMITMENT):
                self.assertEqual(record["assertion_state"], "not_yet_instrumented",
                                 f"{record['record_id']} satisfies the conjunction but was not counted")

    def test_a_doctrine_shaped_value_carries_no_affirmative_flag_outside_an_endorsing_voice(self):
        policed = {"sole_existent_others_unreal", "none_acknowledged", "others_denied_unreal"}
        seen = 0
        for record in self.records:
            if record["value"] in policed:
                seen += 1
                if not (record["D7b_speech_act"] in AFFIRMING_ACTS
                        and record["D7d_epistemic_commitment"] in AFFIRMING_COMMITMENT):
                    self.assertFalse(record["counts_as_affirmative_doctrine"],
                                     f"{record['record_id']} reads a doctrine out of "
                                     f"{record['D7b_speech_act']}/{record['D7d_epistemic_commitment']}")
                    self.assertNotEqual(record["doctrinal_endorsement"], "endorsed_by_text")
        self.assertGreater(seen, 0, "the policed value family is absent, so this gate is untested")

    def test_the_published_tally_is_recomputable_from_the_records(self):
        tally = Counter(r["assertion_state"] for r in self.records)
        self.assertEqual(dict(sorted(tally.items())), self.summary["assertion_state_tally"])
        self.assertEqual(sum(tally.values()), self.summary["candidate_records_total"])
        self.assertEqual(len(self.records), self.summary["candidate_records_total"])
        self.assertEqual(sum(1 for r in self.records if r["counts_as_affirmative_doctrine"]),
                         self.summary["affirmative_doctrine_records"])
        self.assertEqual(dict(sorted(Counter(r["conceptual_presence"] for r in self.records).items())),
                         self.summary["conceptual_presence_tally"])
        self.assertEqual(dict(sorted(Counter(r["doctrinal_endorsement"] for r in self.records).items())),
                         self.summary["doctrinal_endorsement_tally"])

    def test_the_three_assertion_states_are_the_only_states(self):
        self.assertEqual(set(Counter(r["assertion_state"] for r in self.records)) - STATES, set())
        for record in self.records:
            self.assertNotIn(record["assertion_state"],
                             {"attested", "not_attested_in_available_sources", "blocked_by_speech_act"},
                             "a machine record must not carry a human, exhaustive-search or deletion state")
            self.assertEqual(record["verification_status"], "machine_candidate_unadjudicated")

    def test_a_value_declared_uninstrumented_never_appears_as_a_candidate(self):
        uninstrumented = set(self.summary["values_not_yet_instrumented"])
        for record in self.records:
            key = f"{record['dimension']}={record['value']}"
            if key in uninstrumented:
                self.assertEqual(record["assertion_state"], "not_yet_instrumented",
                                 f"{record['record_id']} reports a value the frame says it cannot detect")
                self.assertEqual(record["conceptual_presence"], "undecidable_from_available_sources")
        self.assertTrue(uninstrumented, "the run published no coverage limits, which would be a claim of "
                                        "full instrumentation")

    # ------------------------------------------------------------------ honesty
    def test_no_record_claims_a_human_coding_that_has_not_happened(self):
        for record in self.records:
            self.assertIsNone(record["coder_id"])
            self.assertIsNone(record["second_coder_id"])
            self.assertEqual(record["agreement_status"], "not_reviewed")

    def test_the_instrument_calls_itself_multilingual_ready_and_only_reports_english(self):
        self.assertIn("multilingual-ready", self.summary["self_description"])
        self.assertNotIn("language-independent", json.dumps(self.summary))
        self.assertEqual({r["expression_language"] for r in self.records}, {"English (translation)"})
        self.assertIn("unverified_secondary_literature", json.dumps(self.ontology),
                      "the frame no longer says its lexicon is unverified, which is a claim it cannot make")

    def test_the_run_is_fresh_against_the_frame_the_rules_and_the_code(self):
        reproducibility = self.summary["reproducibility"]
        for field, path in (("passages_sha256", "corpus/derived/passages_v2.jsonl"),
                            ("rules_sha256", "config/ontology_english_rules.json"),
                            ("ontology_sha256", "config/divinity_ontology.json"),
                            ("lexicon_sha256", "config/divinity_lexicon.json"),
                            ("code_sha256", "tools/divinity_ontology.py")):
            self.assertEqual(reproducibility[field],
                             hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                             f"{field} is stale: {path} changed after the run")
        self.assertEqual(reproducibility["randomness"],
                         "none: sorted iteration, no sampling, no fitted parameters")

    # ------------------------------------------------------------------ graph
    def test_the_graph_enumerates_exactly_and_never_calls_the_slice_exhaustive(self):
        generation = self.graph["candidate_generation"]
        self.assertEqual(generation["method"], "exact_inverted_index_join")
        self.assertIn("NONE", generation["approximation"].upper())
        self.assertIn("COMPLETE", generation["coverage_of_the_relation"])
        self.assertIn("INCOMPLETE", generation["coverage_of_anything_beyond_the_relation"])
        self.assertIn("NEVER READ AS", json.dumps(generation).upper().replace("_", " "))
        scale = self.graph["scale"]
        # the edge file is a display slice; the complete count is published separately and is larger
        self.assertEqual(scale["passage_pair_edges_written"], self.graph["layers"][2]["edges"])
        self.assertLess(scale["passage_pair_edges_written"], scale["naive_passage_pair_space"])
        self.assertLess(scale["passage_pair_edges_written"], scale["exact_distinct_cross_work_pairs"])
        self.assertEqual(self.graph["layers"][2]["pairs"], scale["exact_distinct_cross_work_pairs"])
        self.assertTrue(scale["edge_file_is_display_slice"])
        self.assertEqual(scale["attestation_records"], self.summary["candidate_records_total"])
        self.assertEqual(scale["passage_matrix_cells"],
                         scale["passage_matrix_rows"] * scale["passage_matrix_value_columns"])

    def test_the_superseded_lsh_recall_is_published_and_bounded(self):
        results = self.recall["results"]
        measured = results["recovered_by_lsh"] / results["exact_sharing_pairs"]
        self.assertAlmostEqual(results["recall"], measured, places=4)
        self.assertLess(results["recall"], 1.0)
        self.assertGreater(results["recall"], 0.0)
        self.assertEqual(results["exact_sharing_pairs"],
                         results["recovered_by_lsh"] + results["lost_to_bucket_cap"] + results["lost_to_banding"],
                         "the loss decomposition does not add up")
        wide = self.recall["corpus_wide"]
        self.assertEqual(wide["exact_distinct_cross_work_pairs"],
                         wide["recovered_by_lsh"] + wide["lost_to_bucket_cap"] + wide["lost_to_banding"])
        self.assertEqual(wide["exact_distinct_cross_work_pairs"],
                         self.graph["scale"]["exact_distinct_cross_work_pairs"])
        published = self.graph["candidate_generation"]["superseded_minhash_recall_measured"]
        self.assertEqual(published["subset"]["recall"], results["recall"],
                         "the graph and the validation artifact disagree")
        self.assertEqual(published["corpus_wide"]["recall"], wide["recall"])
        self.assertEqual(self.recall["inputs"]["attestations_sha256"],
                         hashlib.sha256((ROOT / "results/ontology_attestations.jsonl.gz").read_bytes()).hexdigest(),
                         "the recall figure was measured against a record file this run replaced")
        self.assertEqual(self.graph["reproducibility"]["graph_recall_validation_sha256"],
                         hashlib.sha256((ROOT / "results/graph_recall_validation.json").read_bytes()).hexdigest(),
                         "the graph cites a recall artifact older than itself")

    def test_the_coverage_inventory_is_one_table_and_agrees_with_the_run_summary(self):
        """Five overlapping counts of 93 values were restated in prose in four places; now they are computed.

        The graph layer originally read `coverage_state` where the rules file writes `coverage`, so its gap
        list came out empty and read as "no gaps" -- the worst possible failure of a disclosure field. These
        assertions make that class of mistake a test failure rather than a sentence in a paper.
        """
        inventory = self.graph["coverage_inventory"]
        declared = {f"{d}={v}" for d, specs in self.ontology["dimensions"].items() for v in specs["values"]}
        self.assertEqual(inventory["declared_values"], len(declared))
        # nested sets, not a partition: both decompositions of 93 must hold at once
        self.assertEqual(inventory["with_a_surface_pattern"] + inventory["without_a_surface_pattern"],
                         inventory["declared_values"])
        self.assertEqual(inventory["observed_at_least_once"] + inventory["with_no_matrix_column"],
                         inventory["declared_values"])
        self.assertEqual(sum(inventory["coverage_state_labels"].values()), inventory["declared_values"])
        # and the label counts must be derived from the field the rules file actually uses
        self.assertEqual(inventory["coverage_state_labels"]["not_yet_instrumented"],
                         len(self.summary["values_not_yet_instrumented"]))
        layer5 = next(l for l in self.graph["layers"] if l["name"] == "5_coverage_and_absence")
        self.assertEqual(layer5["values_not_yet_instrumented"],
                         sorted(self.summary["values_not_yet_instrumented"]))
        self.assertGreater(len(layer5["values_not_yet_instrumented"]), 0,
                           "an empty gap list reads as 'no gaps' and is worse than no field at all")
        self.assertEqual(inventory["flagged_not_yet_instrumented"],
                         len(inventory["overlaps"]["not_yet_instrumented_that_still_have_a_pattern"])
                         + len(inventory["overlaps"]["not_yet_instrumented_with_no_pattern"]))
        # the 40 unpatterned values are fully explained: 2 labelled, the rest rule-derived
        overlaps = inventory["overlaps"]
        self.assertEqual(inventory["without_a_surface_pattern"],
                         overlaps["no_pattern_and_not_flagged"]
                         + len(overlaps["not_yet_instrumented_with_no_pattern"]))
        self.assertEqual(overlaps["no_pattern_and_not_flagged"],
                         overlaps["of_which_produced_by_rules_not_patterns"])
        self.assertIn("31", inventory["reading_the_table"])  # the bogus remainder is named and dismissed
        observed = {f"{r['dimension']}={r['value']}" for r in self.records}
        self.assertEqual(inventory["observed_at_least_once"], len(observed))
        self.assertEqual(sorted(inventory["overlaps"]["patterned_but_never_matched"]),
                         sorted({f"{d}={v}" for d, specs in self.rules["dimensions"].items()
                                 for v, spec in specs.get("values", {}).items()
                                 if isinstance(spec, dict) and spec.get("patterns")} - observed))

    def test_the_inheritance_layer_stays_empty_until_dates_exist(self):
        layer = next(l for l in self.graph["layers"] if l["name"] == "4_inheritance_and_transformation")
        self.assertEqual(layer["status"], "unpopulated_by_design")
        self.assertEqual(layer["edges"], 0)
        self.assertTrue(layer["required_fields"])

    def test_no_edge_in_any_layer_is_a_historical_or_resemblance_claim(self):
        kinds = {edge["edge_kind"] for edge in self.graph["edges"]}
        self.assertEqual(kinds, {"SHARED_DIMENSION_STATE_CANDIDATE"})
        text = json.dumps(self.graph)
        for forbidden in ("RESEMBLES", "DESCENDS_FROM", "DERIVES_FROM"):
            self.assertNotIn(forbidden, text)

    def test_configured_dependent_work_pairs_are_not_marked_independent(self):
        dependence = json.loads((ROOT / "config/source_dependence.json").read_text(encoding="utf-8"))
        pairs = {frozenset((rule["left_work"], rule["right_work"])) for rule in dependence["pair_rules"]
                 if rule["exclude_from_independent_analysis"]}
        with (ROOT / "results/ontology_workpair_dimensions.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if frozenset((row["left_work"], row["right_work"])) in pairs:
                    self.assertEqual(row["counts_as_independent"], "no",
                                     f"{row['left_work']}--{row['right_work']} is configured dependent but "
                                     f"the graph offers it as independent evidence")

    def test_the_passage_matrix_covers_eligible_passages_and_no_ineligible_ones(self):
        with gzip.open(ROOT / "results/ontology_passage_matrix.csv.gz", "rt", encoding="utf-8",
                       newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            rows = list(reader)
        self.assertEqual(len(rows), self.graph["scale"]["passage_matrix_rows"])
        self.assertEqual(len(header) - 2, self.graph["scale"]["passage_matrix_value_columns"])
        candidates = defaultdict(set)
        for record in self.records:
            if record["assertion_state"] == "candidate":
                candidates[record["passage_id"]].add(f"{record['dimension']}={record['value']}")
        for row in rows:
            passage = self.passages[row[0]]
            self.assertTrue(passage["eligible_for_similarity"],
                            f"{row[0]} was excluded by cleaning but is coded as evidence")
            live = {header[position] for position, cell in enumerate(row)
                    if position > 1 and int(cell or 0) > 0}
            self.assertEqual(live, candidates[row[0]],
                             f"{row[0]}: the matrix and the record file disagree about what was found")

    # ------------------------------------------------------------------ downstream layers
    def test_the_annotation_packet_codes_propositions_not_windows(self):
        import prepare_annotation_packet
        plan = json.loads((ROOT / "results/annotation_sampling_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["instrument"], "annotation packet v3.1")
        self.assertIn("proposition", plan["unit_of_analysis"])
        self.assertNotIn("windows_in_packet", plan)
        self.assertEqual(set(plan["strata_enforced"]), {"dimension value", "work", "D7b speech act",
                                                        "no-record proposition, cue-negative",
                                                        "no-record proposition, cue-positive"},
                         "the packet's strata changed without the recall-probe design being updated here")
        probe = plan["recall_probe"]
        self.assertEqual(set(probe["strata"]), {"no_candidate_uncued", "no_candidate_cue_positive"})
        for stratum in probe["strata"].values():
            self.assertGreater(stratum["inclusion_probability"], 0)
            self.assertLessEqual(stratum["inclusion_probability"], 1)
            self.assertAlmostEqual(stratum["sampling_weight"],
                                   1 / stratum["inclusion_probability"], places=2)
        universe = probe["universe"]
        self.assertEqual(universe["propositions_in_universe"],
                         universe["hit_by_the_machine"] + universe["no_record_in_universe"])
        self.assertEqual(universe["no_record_in_universe"],
                         universe["of_which_cue_negative"] + universe["of_which_cue_positive"])
        cue_config = json.loads((ROOT / "config/recall_probe_cues.json").read_text(encoding="utf-8"))
        self.assertIs(cue_config["not_a_detector"], True,
                      "the cue list is a sampling instruction; if it can produce a value it is a detector")
        live = {cue.lower() for name in ("divinity_nouns", "divinity_names")
                for cue in cue_config[name]}
        self.assertEqual(len(live), probe["cue_list"]["cues_operative"],
                         "the plan's cue count and the cue file disagree")
        self.assertFalse(live & {cue.lower() for cue in cue_config["excluded_ambiguous_cues"]},
                         "a retired ambiguous cue is still on the list the sampler reads")
        self.assertEqual(plan["dimensions_coded"], 12)
        self.assertEqual({d for d in prepare_annotation_packet.column_cardinalities()
                          if prepare_annotation_packet.column_cardinalities()[d] == "set"},
                         set(plan["set_valued_dimensions"]))
        with (ROOT / "results/annotation_packet_coder_view.csv").open(encoding="utf-8", newline="") as handle:
            header = next(csv.DictReader(handle))
        for key, column in prepare_annotation_packet.coding_columns().items():
            self.assertIn(column, header, f"the coder sheet has no column for {key}")
        self.assertIn("D1_ontological_category_semicolon", header,
                      "a set-valued dimension was given a single-choice column")
        self.assertIn("proposition_text", header)
        self.assertIn("context_window_text", header)
        self.assertNotIn("window_text", header)

    def test_the_packet_key_carries_no_answer_a_coder_could_copy(self):
        with (ROOT / "results/annotation_packet_coder_view.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                for column, value in row.items():
                    if column not in ("token", "proposition_text", "context_window_text", "locator_work",
                                      "locator_passage", "proposition_chars", "window_chars", "tradition",
                                      "region"):
                        self.assertEqual(value, "", f"{column} leaks into the blinded coder view")

    def test_the_work_state_table_publishes_both_the_candidate_and_the_doctrine_count(self):
        with (ROOT / "results/ontology_work_states.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        work_count = len({r["work_id"] for r in rows})
        expected = sum(len(spec["values"]) for spec in self.dimensions.values()) * work_count
        self.assertEqual(len(rows), expected,
                         "every work must carry a row for every declared value of every dimension")
        for row in rows:
            self.assertIn(row["cardinality"], ("single", "set"))
            self.assertLessEqual(int(row["affirmative_doctrine_count"]), int(row["candidate_count"]))
        self.assertLess(sum(int(r["affirmative_doctrine_count"]) for r in rows),
                        sum(int(r["candidate_count"]) for r in rows),
                        "the work-level view counts everything as affirmative doctrine")

    def test_the_interpretation_dimensions_appear_in_the_work_table_without_borrowed_counts(self):
        with (ROOT / "results/ontology_work_states.csv").open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["dimension"].startswith("D7")]
        self.assertTrue(rows, "the interpretation dimensions are missing from the inventory")
        # D7b/c/d are assigned from clause shape, not matched, so they carry no candidate
        # count; the figure that displays them must therefore use its own denominator.
        for key in ("D7b_speech_act", "D7c_discourse_genre", "D7d_epistemic_commitment"):
            self.assertEqual(sum(int(r["candidate_count"]) for r in rows if r["dimension"] == key), 0,
                             f"{key} is not a matched dimension and must not publish matched-term counts")


if __name__ == "__main__":
    unittest.main()
