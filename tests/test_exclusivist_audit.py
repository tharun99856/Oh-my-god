"""Tests for the match-level audit of the `exclusivist_monotheism` grammar.

The audit's value is not its headline number, it is that every published count walks back to a printed sentence
at a reported offset, in a named section of a named witness. So these tests hold the published artifact to the
evidence chain: the character span must land on the term, the anthology matches must resolve to the printed part
that makes them reprints, the substring collisions must be labelled collisions, the recall control must name
what it caught, and the correction must be recomputable from the rows rather than asserted above them.

One thing these tests deliberately do not check: agreement between coders. Every verdict in the audit is one
analyst's reading, so the only honest assertions here are that the verdicts are declared, closed and
provenanced -- and that no statistic implying a second reader has been fabricated anywhere in the file.
"""

import csv
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import audit_exclusivist_matches as audit  # noqa: E402
import divinity_terms  # noqa: E402

AUDIT_JSON = ROOT / "results/exclusivist_monotheism_audit.json"
AUDIT_CSV = ROOT / "results/exclusivist_monotheism_audit.csv"

# the two passages the probe counts as doctrine and the printed text does not: 1 Corinthians 6:17 ("is one
# spirit") and 1 Nephi 10:19 ("the course of the Lord is one eternal round"), both reached only by the bare
# `\bthe lord is one\b`, which stops at the first word after the verb
COLLISIONS = ["book_of_mormon:s0012:p001", "kjv_bible:s0017:p033"]


class ExclusivistAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AUDIT_JSON.exists():
            raise unittest.SkipTest("the audit has not been run yet")
        cls.result = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        cls.published_probe = json.loads((ROOT / "results/divinity_terms.json").read_text(encoding="utf-8"))
        cls.matches = cls.result["matches"]
        cls.raws = {}

    def raw(self, work_id):
        path = ROOT / f"corpus/raw/{work_id}.txt"
        if not path.exists():
            raise unittest.SkipTest(
                f"corpus/raw/{work_id}.txt is gitignored and absent here; the audit's offsets can only be "
                "re-read against the text they were taken from, so run tools/acquire_corpus.py first")
        if work_id not in self.raws:
            self.raws[work_id] = path.read_text(encoding="utf-8", newline="")
        return self.raws[work_id]

    def matches_in(self, work_id):
        return [record for record in self.matches if record["work_id"] == work_id]

    def as_is_matches(self):
        return [record for record in self.matches if record["matched_in_as_is_scan"]]

    def probe_hits(self):
        return [hit for item in self.result["missed_formula_probe"]["formulas"].values() for hit in item["hits"]]

    def test_the_audit_reproduces_the_probe_before_it_corrects_it(self):
        consistency = self.result["consistency_with_the_probe"]
        family = self.published_probe["families"]["exclusivist_monotheism"]
        self.assertEqual(consistency["instrument_family_term_hits"], family["term_hits"])
        self.assertEqual(consistency["audit_as_is_match_count"], len(self.as_is_matches()))
        self.assertTrue(consistency["audit_as_is_matches_identical"])
        self.assertTrue(consistency["audit_reproduces_published_json"])
        self.assertEqual(sorted(consistency["published_json_family"]["works"]), sorted(family["works"]))
        self.assertEqual(self.result["correction"]["published"]["term_hits"], family["term_hits"])

    def test_the_patterns_audited_are_the_probes_own_not_a_widened_copy(self):
        self.assertEqual(self.result["patterns_audited"],
                         divinity_terms.FAMILIES["exclusivist_monotheism"]["patterns"])
        self.assertEqual(self.result["pattern_set_imported_from"],
                         "tools/divinity_terms.py FAMILIES['exclusivist_monotheism']['patterns']")

    def test_every_match_lands_on_the_term_it_reports_in_the_raw_file(self):
        for record in self.matches:
            span = self.raw(record["work_id"])[record["match_raw_char_start"]:record["match_raw_char_end"]]
            self.assertTrue(span, f"{record['audit_id']} reports an empty span")
            self.assertEqual(re.sub(r"\s+", " ", span), record["matched_term"],
                             f"{record['audit_id']}: the offset does not hold its term: {span!r}")
            self.assertEqual(record["span_text_as_printed"], span)

    def test_match_offsets_stay_inside_the_cited_passage(self):
        manifest = json.loads((ROOT / "corpus/acquisition_manifest.json").read_text(encoding="utf-8"))
        body_start = {work["work_id"]: work["body_char_start"] for work in manifest["works"]}
        for record in self.matches:
            self.assertEqual(record["match_body_char_start"] + body_start[record["work_id"]],
                             record["match_raw_char_start"], f"{record['audit_id']} coordinates disagree")
            self.assertTrue(record["body_char_start"] <= record["match_body_char_start"]
                            <= record["match_body_char_end"] <= record["body_char_end"],
                            f"{record['audit_id']} match lies outside the passage it cites")
            self.assertIn(record["matched_term"].lower(), record["sentence"].lower())
            self.assertIn(record["matched_term"].lower(), record["context_snippet"].lower())

    def test_whitespace_normalisation_strictly_adds_matches_and_the_work_split_is_published(self):
        totals = self.result["counts"]["totals"]
        self.assertEqual(totals["as_is_matches"], 46)
        self.assertEqual(totals["whitespace_normalised_matches"], 51)
        self.assertGreater(totals["whitespace_normalised_matches"], totals["as_is_matches"])
        self.assertEqual(len(self.matches), totals["whitespace_normalised_matches"])
        self.assertEqual(totals["delta_from_whitespace_normalisation"],
                         sum(row["delta_from_whitespace_normalisation"] for row in self.result["counts"]["per_work"]))
        for row in self.result["counts"]["per_work"]:
            self.assertEqual(row["whitespace_normalised_matches"] - row["as_is_matches"],
                             row["delta_from_whitespace_normalisation"])
            self.assertGreaterEqual(row["whitespace_normalised_matches"], row["as_is_matches"])
            self.assertEqual(row["as_is_matches"], row["whole_work_body_control_as_is"],
                             f"{row['work_id']}: passage segmentation lost a hit")
            self.assertEqual(row["whitespace_normalised_matches"],
                             row["whole_work_body_control_whitespace_normalised"])
        for record in self.matches:
            self.assertEqual(record["new_in_whitespace_normalised_scan"], not record["matched_in_as_is_scan"])
            self.assertEqual(record["counts_as_published_hit"], record["matched_in_as_is_scan"])

    def test_the_recall_gap_sits_at_the_line_wraps_it_claims(self):
        new = [record for record in self.matches if record["new_in_whitespace_normalised_scan"]]
        self.assertEqual(len(new), 5)
        self.assertTrue(all("\n" in record["span_text_as_printed"] for record in new),
                        "a hit the literal patterns miss must show the wrap that hid it")
        locators = sorted(record["canonical_locator"] for record in new)
        self.assertIn("KJV The Book of the Prophet Isaiah 44:6", locators)
        self.assertIn("KJV The Gospel According to Saint Mark 12:29", locators)
        self.assertEqual(len([record for record in new if record["work_id"] == "quran_sale"]), 3)
        for record in new:
            self.assertEqual(record["analyst_verdict"], "genuine_exclusivist_confession",
                             f"{record['canonical_locator']} was caught by normalisation and is not a confession")

    def test_the_anthology_matches_all_resolve_to_its_koran_section_and_none_is_independent(self):
        records = self.matches_in("sacred_books_east")
        self.assertEqual(len(records), 9, "the anthology's published contribution")
        for record in records:
            self.assertEqual("SELECTIONS FROM THE KORAN", record["anthology_section"],
                             f"{record['audit_id']} is not in the anthology's Koran section: "
                             f"{record['resolution_basis']}")
            self.assertFalse(record["counts_as_independent_attestation"])
            self.assertEqual("quran_sale", record["dependent_reprint_of"])
            self.assertIn(record["anthology_voice"], {"reprinted translation", "editorial commentary"})
            self.assertTrue(record["resolution_basis"].startswith(("resolved from the volume's heading sequence",
                                                                   "the anthology's CONTENTS page lists")),
                            f"attribution must come from the printed index, not from an override: "
                            f"{record['resolution_basis']}")
        # nothing lands in the eastern scripture the census's `Multiple` tradition label implies
        self.assertEqual({record["tradition"] for record in records}, {"Multiple"})
        self.assertNotIn("Vedic Hymns", {record["anthology_section"] for record in records})
        self.assertIn("reprinted translation", {record["anthology_voice"] for record in records})

    def test_the_anthologys_one_editorial_match_is_named_and_its_voice_is_printed(self):
        editorial = [record for record in self.matches_in("sacred_books_east")
                     if record["anthology_voice"] == "editorial commentary"]
        self.assertEqual(len(editorial), 1)
        self.assertEqual("editorial_description_of_formula", editorial[0]["analyst_verdict"])
        self.assertEqual("work_level", editorial[0]["dependence_scope"])
        self.assertTrue(editorial[0]["attributed_in_text_to"], "the essay's printed byline must be published")
        reprints = [record for record in self.matches_in("sacred_books_east")
                    if record["anthology_voice"] == "reprinted translation"]
        self.assertEqual(len(reprints), 8)
        for record in reprints:
            self.assertEqual("match_level", record["dependence_scope"])
            self.assertEqual("George Sale", record["attributed_in_text_to"])
            self.assertEqual("genuine_exclusivist_confession", record["analyst_verdict"])

    def test_the_substring_collisions_are_flagged_and_attributed_to_the_bare_pattern(self):
        flagged = sorted(record["passage_id"] for record in self.matches
                         if record["analyst_verdict"] == "non_doctrinal_substring_collision")
        self.assertEqual(flagged, COLLISIONS)
        for record in self.matches:
            if record["passage_id"] in COLLISIONS:
                self.assertEqual([r"\bthe lord is one\b"], record["patterns_matched"],
                                 "the collision must be attributed to the bare pattern alone")
                self.assertNotIn("God", record["matched_term"])
                self.assertTrue(record["counts_as_published_hit"])

    def test_the_worship_prohibitions_are_kept_apart_from_existence_claims(self):
        prohibited = sorted(record["passage_id"] for record in self.matches
                           if record["analyst_verdict"] == "monolatrous_prohibition_presupposing_other_gods")
        self.assertIn("kjv_bible:s0001:p003", prohibited, "Exodus 20:3 must be labelled, not counted")
        for record in self.matches:
            if "no other gods" in record["matched_term"].lower():
                self.assertEqual(record["analyst_verdict"], "monolatrous_prohibition_presupposing_other_gods")

    def test_verdicts_come_from_the_declared_vocabulary_and_every_row_is_provenanced(self):
        vocabulary = set(self.result["verdict_vocabulary"])
        self.assertEqual(vocabulary, set(audit.VERDICTS))
        for required in ("genuine_exclusivist_confession", "monolatrous_prohibition_presupposing_other_gods",
                         "non_doctrinal_substring_collision", "editorial_description_of_formula",
                         "divine_formula_in_non_divine_mouth", "conditional_or_hypothetical",
                         "reported_speech_of_denial", "unresolved_needs_second_coder"):
            self.assertIn(required, vocabulary)
        rules = {name for name, _ in audit.CONTEXT_RULES} | {"analyst_reading_of_context",
                                                             "default_divine_exclusivist_formula"}
        for record in self.matches:
            self.assertIn(record["analyst_verdict"], vocabulary)
            self.assertIn(record["verdict_rule"], rules)
            self.assertTrue(record["verdict_reason"].strip())
            self.assertEqual(audit.ADJUDICATION_PROVENANCE, record["adjudication_provenance"])
            if record["competing_reading"] is not None:
                self.assertIn(record["competing_reading"], vocabulary,
                              "a competing reading is a name from the vocabulary, not a second judgement")
            self.assertFalse([key for key in record if key.startswith("_")],
                             "working fields must not be published")

    def test_verdict_tallies_sum_to_the_match_counts_for_both_scans(self):
        for scan, expected in (("as_is", len(self.as_is_matches())), ("whitespace_normalised", len(self.matches))):
            block = self.result["verdict_counts"]["by_scan"][scan]
            self.assertEqual(block["total_matches"], expected)
            self.assertEqual(sum(block["verdicts"].values()), expected)
            for verdict in block["verdicts"]:
                self.assertIn(verdict, self.result["verdict_vocabulary"])
            for verdict in block["verdicts_with_zero_matches"]:
                self.assertNotIn(verdict, block["verdicts"])

    def test_no_second_coding_or_annotation_is_claimed_anywhere_in_the_file(self):
        joined = json.dumps(self.result).lower()
        for forbidden in ("double_coded", "inter_annotator", "kappa", "annotated_by", "blind_coder",
                          "second coder agreed", "annotation project"):
            self.assertNotIn(forbidden, joined)
        limitations = self.result["limitations"]
        self.assertIn("no second coder", limitations["adjudication"].lower())
        self.assertIn("INPUT TO", limitations["adjudication"])
        self.assertIn("no_human_annotation_was_performed", limitations)
        self.assertIn("I cannot tell", limitations["suspiciously_clean_single_pass"])
        self.assertEqual(limitations["unresolved_records"], [],
                         "an unresolved row here would be a judgement nobody made")

    def test_the_configured_dependence_rules_are_applied_to_both_derived_works(self):
        config = json.loads((ROOT / "config/source_dependence.json").read_text(encoding="utf-8"))
        audited = {record["work_id"] for record in self.matches}
        applied = 0
        for rule in config["pair_rules"]:
            if (rule["right_work"] in audited and rule["left_work"] in audited
                    and rule["exclude_from_independent_analysis"]):
                applied += 1
                for record in self.matches_in(rule["right_work"]):
                    self.assertEqual(rule["left_work"], record["dependent_reprint_of"])
                    self.assertFalse(record["counts_as_independent_attestation"])
                    self.assertIn(record["dependence_scope"], {"match_level", "work_level"})
                    self.assertIn(rule["relationship"], record["source_dependence_basis"])
        self.assertEqual(applied, 2, "quran_sale -> sacred_books_east and kjv_bible -> book_of_mormon")
        for record in self.matches:
            if record["dependent_reprint_of"] is None:
                self.assertTrue(record["counts_as_independent_attestation"])

    def test_attribution_uses_the_witness_the_file_actually_prints(self):
        for record in self.matches_in("quran_sale"):
            self.assertIn("Rodwell", record["original_textual_source"])
            self.assertIn("title page", record["resolution_basis"])
            self.assertIsNotNone(record["internal_chapter"], f"{record['audit_id']} lost its sura")
            self.assertFalse(record["in_translator_notes"])
        self.assertEqual(self.result["attribution"]["quran_sale"]["in_translator_notes"], 0)
        for record in self.matches_in("kjv_bible"):
            self.assertRegex(record["canonical_locator"], r"KJV .+ \d+:\d+")
        self.assertTrue(any(record["canonical_locator"].endswith("Deuteronomy 6:4")
                            for record in self.matches_in("kjv_bible")), "the Shema must be located")

    def test_the_missed_formula_probe_reports_classes_the_family_does_not_carry(self):
        formulas = self.result["missed_formula_probe"]["formulas"]
        self.assertEqual(set(formulas), set(audit.MISSED_FORMULAS))
        for required in ("there is none else", "none else beside", "no saviour beside me",
                         "is there a god beside me", "who is like unto thee among the gods",
                         "I am the LORD and there is none else"):
            self.assertIn(required, formulas)
        for name, item in formulas.items():
            self.assertEqual(item["occurrences"], sum(item["work_counts"].values()), name)
            self.assertEqual(item["uncovered_by_current_pattern_set"], item["occurrences"],
                             f"{name} is listed as missed but reported as already covered")
            for hit in item["hits"]:
                self.assertFalse(hit["covered_by_current_pattern_set"], f"{hit['locator']} is not a missed hit")
                self.assertEqual(audit.ADJUDICATION_PROVENANCE, hit["adjudication_provenance"])
        self.assertEqual(self.result["missed_formula_probe"]["totals"]["occurrences"],
                         self.result["missed_formula_probe"]["totals"]["uncovered_occurrences"])

    def test_the_probe_finds_isaiah_45_5_and_the_rest_of_the_none_else_family(self):
        by_locator = {}
        for hit in self.probe_hits():
            by_locator.setdefault(hit["locator"], []).append(hit)
        isaiah = [hit for locator, hits in by_locator.items() if locator.endswith("Isaiah 45:5") for hit in hits]
        self.assertTrue(isaiah, "the probe must find Isaiah 45:5")
        self.assertTrue(any(hit["formula"] == "I am the LORD and there is none else" for hit in isaiah))
        self.assertTrue(any(hit["formula"] == "there is none else" for hit in isaiah))
        self.assertTrue(any(hit["locator"].endswith("Isaiah 45:22") for hit in self.probe_hits()))
        kjv_none_else = [hit for hit in self.probe_hits()
                         if hit["formula"] == "there is none else" and hit["work_id"] == "kjv_bible"]
        self.assertEqual(len(kjv_none_else), 9,
                         "the `none else` family is nine occurrences in the KJV once line-wraps are collapsed")

    def test_the_probe_finds_the_confession_form_in_the_boasting_city_and_finds_no_jeremiah(self):
        block = self.result["missed_formula_probe"]["divine_formula_in_non_divine_mouth"]
        cases = block["cases"]
        locators = sorted({case["locator"] for case in cases})
        self.assertIn("The Book of the Prophet Isaiah 47:8", locators)
        self.assertIn("The Book of the Prophet Isaiah 47:10", locators)
        self.assertIn("Zephaniah 2:15", locators)
        self.assertEqual(block["occurrences"], len(cases))
        self.assertEqual(block["distinct_verses"], len(locators))
        self.assertLessEqual(block["distinct_verses"], block["occurrences"],
                             "one verse can carry two formula classes, which must not read as two verses")
        for case in cases:
            self.assertEqual("divine_formula_in_non_divine_mouth", case["speaker_frame"])
            self.assertRegex(case["sentence"].lower(), r"(said|sayest|saith) in (thine|her) heart")
        self.assertEqual([hit for hit in self.probe_hits() if "Jeremiah" in (hit["locator"] or "")], [],
                         "the brief's `Jeremiah 51` parallel is not in this text")

    def test_the_correction_is_recomputable_from_the_rows_it_publishes(self):
        correction = self.result["correction"]
        removed = {audit_id for ids in correction["removed_by_this_audit"].values() for audit_id in ids}
        conditional = {record["audit_id"] for record in self.matches
                       if record["analyst_verdict"] == "conditional_or_hypothetical"}
        surviving = {record["audit_id"] for record in self.matches
                     if record["analyst_verdict"] == "genuine_exclusivist_confession"
                     and record["counts_as_independent_attestation"]}
        self.assertFalse(removed & surviving)
        self.assertFalse(conditional & surviving)
        self.assertEqual(removed | conditional | surviving, {record["audit_id"] for record in self.matches})
        self.assertEqual(len(surviving), correction["survives_after_correction"]["matches"])
        self.assertEqual(sum(correction["removed_counts"].values()),
                         sum(len(ids) for ids in correction["removed_by_this_audit"].values()))
        self.assertEqual(correction["published"]["works_attested"], 4)
        self.assertEqual(correction["survives_after_correction"]["works_attested"], 2)
        self.assertEqual(correction["works_no_longer_attested"], ["book_of_mormon", "sacred_books_east"])
        self.assertEqual(sorted(correction["survives_after_correction"]["works"]), ["kjv_bible", "quran_sale"])
        self.assertNotIn("Multiple", correction["survives_after_correction"]["traditions"])
        self.assertEqual(sorted(correction["traditions_no_longer_attested"]), ["Latter-day Saint", "Multiple"])

    def test_the_disposition_table_partitions_every_match_into_exactly_one_row(self):
        table = self.result["disposition_table"]
        rows = table["rows"]
        self.assertEqual(table["total_matches_partitioned"], len(self.matches))
        self.assertEqual(table["sum_of_disposition_rows"], len(self.matches))
        self.assertTrue(table["sum_equals_total"])
        ids = [audit_id for row in rows for audit_id in row["audit_ids"]]
        self.assertEqual(len(ids), len(set(ids)), "a match claimed by two dispositions is a double count")
        self.assertEqual(sorted(ids), sorted(record["audit_id"] for record in self.matches),
                         "the table must cover the whole match set, not a subset of it")
        check = self.result["disposition_check"]
        self.assertTrue(check["every_match_claimed_exactly_once"])
        self.assertTrue(check["rule_predicates_are_pairwise_disjoint"])
        self.assertEqual([], check["overlapping_rule_pairs"])
        self.assertTrue(check["all_rows_reproduced"])
        self.assertTrue(check["confessional_split_is_exhaustive"])
        for row in rows:
            self.assertEqual(row["matches"], len(row["audit_ids"]))
            self.assertEqual(row["matches"], sum(row["works"].values()))
            self.assertEqual(row["matches"], sum(row["verdicts_inside_the_disposition"].values()))

    def test_every_verdict_the_matches_carry_is_covered_by_a_rule(self):
        table = self.result["disposition_table"]
        used = {record["analyst_verdict"] for record in self.matches}
        covered = {verdict for row in table["rows"] for verdict in row["verdicts_inside_the_disposition"]}
        self.assertEqual(used, covered, "a verdict with no row would make the table a subset, not a partition")
        vocabulary = set(self.result["verdict_vocabulary"])
        names = [rule[0] for rule in audit.DISPOSITION_RULES]
        self.assertEqual(len(names), len(set(names)), "two rules with the same name would merge silently")
        self.assertEqual(vocabulary - {"genuine_exclusivist_confession"}
                         | {"confessional_in_a_work_not_marked_dependent", "confessional_in_a_work_marked_dependent"},
                         set(names),
                         "the confession splits into two rows on the dependence marking; every other verdict "
                         "is one row, so the rule list covers the vocabulary exactly")
        for rule in audit.DISPOSITION_RULES:
            self.assertTrue(rule[2].strip(), "a disposition with no definition is a label, not a judgement")
            self.assertTrue(rule[4].strip(), "a disposition must say what its matches evidence")

    def test_the_confessional_count_is_stated_as_not_marked_dependent_and_not_as_independent(self):
        table = self.result["disposition_table"]
        rows = {row["disposition"]: row for row in table["rows"]}
        confessional = rows["confessional_in_a_work_not_marked_dependent"]
        dependent = rows["confessional_in_a_work_marked_dependent"]
        self.assertEqual(confessional["matches"] + dependent["matches"], 42)
        self.assertEqual({"kjv_bible": 4, "quran_sale": 30}, confessional["works"])
        self.assertEqual({"sacred_books_east": 8}, dependent["works"])
        self.assertEqual(
            "34 matches classified as confessional across two works not marked dependent under the currently "
            "configured source-dependence rules. Independence has not been established because dependence "
            "closure remains incomplete.",
            table["headline"])
        self.assertEqual(table["headline"], audit.independence_statement(confessional),
                         "the headline is assembled from the row, so it cannot drift from it")
        self.assertEqual([confessional["disposition"]],
                         table["dispositions_counted_as_evidence_for_the_family"])
        for name, row in rows.items():
            if name != confessional["disposition"]:
                self.assertFalse(row["counts_as_evidence_for_the_family"], f"{name} is not family evidence")

    def test_the_dependence_field_is_documented_as_the_absence_of_a_declared_rule(self):
        independence = self.result["correction"]["independence"]
        self.assertFalse(independence["established"])
        self.assertEqual(34, independence["confessional_matches_in_works_not_marked_dependent"])
        self.assertEqual(8, independence["confessional_matches_in_works_marked_dependent"])
        self.assertEqual(self.result["disposition_table"]["headline"], independence["statement"])
        for phrase in ("absence of a declared edge", "no closure over the whole corpus"):
            self.assertIn(phrase, independence["why_the_first_number_is_not_an_independence_claim"])
        marking = self.result["verdict_counts"]["matches_by_dependence_marking"]
        self.assertEqual(41, marking["true_matches_in_works_not_marked_dependent"])
        self.assertEqual(10, marking["false_matches_in_works_marked_dependent"])
        self.assertIn("not a finding of independent transmission", marking["what_the_field_means"])
        self.assertIn("not marked dependent", self.result["correction"]["survives_after_correction"]["definition"])

    def test_the_csv_published_alongside_the_json_carries_the_same_rows(self):
        with AUDIT_CSV.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(self.matches))
        self.assertEqual(sorted(row["audit_id"] for row in rows),
                         sorted(record["audit_id"] for record in self.matches))
        by_id = {row["audit_id"]: row for row in rows}
        for record in self.matches:
            row = by_id[record["audit_id"]]
            self.assertEqual(row["analyst_verdict"], record["analyst_verdict"])
            self.assertEqual(row["adjudication_provenance"], record["adjudication_provenance"])
            self.assertEqual(int(row["match_raw_char_start"]), record["match_raw_char_start"])
            self.assertEqual("|".join(record["patterns_matched"]), row["patterns_matched"])

    def test_the_published_file_is_fresh_relative_to_every_input_it_names(self):
        reproducibility = self.result["reproducibility"]
        for field, path in (("audit_script_sha256", Path(audit.__file__)),
                            ("divinity_terms_sha256", Path(divinity_terms.__file__)),
                            ("source_dependence_sha256", ROOT / "config/source_dependence.json"),
                            ("acquisition_manifest_sha256", ROOT / "corpus/acquisition_manifest.json")):
            self.assertEqual(reproducibility[field], hashlib.sha256(path.read_bytes()).hexdigest(),
                             f"{field} is stale: {path} changed after the audit ran")
        self.assertEqual(reproducibility["randomness"],
                         "none: sorted iteration, no sampling, no fitted parameters")
        # The two remaining inputs are the gitignored corpus. A clean clone checks everything the
        # repository ships and skips, by name, the part it cannot.
        if not (ROOT / "corpus/derived/passages_v2.jsonl").exists():
            self.skipTest("corpus/derived/passages_v2.jsonl is gitignored and absent here; run "
                          "python tools/build_passages_v2.py before checking passages_sha256")
        self.assertEqual(reproducibility["passages_sha256"],
                         hashlib.sha256((ROOT / "corpus/derived/passages_v2.jsonl").read_bytes()).hexdigest())
        for work_id, digest in reproducibility["raw_text_sha256"].items():
            self.assertEqual(digest, hashlib.sha256((ROOT / f"corpus/raw/{work_id}.txt").read_bytes()).hexdigest())

    def test_collapse_wraps_then_translates_back_to_the_printed_offsets(self):
        text = "there is no\ngod   but God"
        collapsed, mapping = audit.collapse(text)
        self.assertEqual(collapsed, "there is no god but God")
        start = collapsed.index("no god but")
        self.assertEqual(mapping[start], text.index("no"))
        end = start + len("no god but God")
        printed = text[mapping[start]:mapping[end - 1] + 1]
        self.assertEqual(printed, "no\ngod   but God")
        self.assertEqual(re.sub(r"\s+", " ", printed), collapsed[start:end])

    def require_corpus(self):
        if not (ROOT / "corpus/derived/passages_v2.jsonl").exists():
            raise unittest.SkipTest(
                "corpus/derived/ is gitignored and absent here; re-running the audit means reading the same "
                "text it read, so run python tools/build_passages_v2.py first")

    def test_rerunning_the_audit_reproduces_the_published_bytes(self):
        self.require_corpus()
        self.assertEqual(json.dumps(audit.build(), indent=2, ensure_ascii=False) + "\n",
                         AUDIT_JSON.read_text(encoding="utf-8", newline=""))


if __name__ == "__main__":
    unittest.main()
