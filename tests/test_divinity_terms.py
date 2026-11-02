"""Provenance and self-consistency tests for the divinity-terms probe.

The probe's whole value is that a reader can check a claim about a concept against the exact words in the
corpus, so these tests verify the locators rather than the counts: a record is only admissible if its
character span lands on the term it reports, inside the passage it cites.
"""

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import divinity_terms  # noqa: E402


def published():
    return json.loads((ROOT / "results/divinity_terms.json").read_text(encoding="utf-8"))


class DivinityTermsProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "results/divinity_terms.json").exists():
            raise unittest.SkipTest("the probe has not been run yet")
        cls.result = published()
        cls.passages = {json.loads(line)["passage_id"]: json.loads(line)
                        for line in (ROOT / "corpus/derived/passages_v2.jsonl")
                        .read_text(encoding="utf-8").splitlines()}

    def all_records(self):
        for family in self.result["families"].values():
            for record in family["examples"]:
                yield record
        for record in self.result["skepticism_evidence"]["records"]:
            yield record
        for records in self.result["skepticism_evidence"]["excluded_matches"].values():
            for record in records:
                yield record

    def test_every_record_points_at_the_term_it_reports(self):
        for record in self.all_records():
            passage = self.passages[record["passage_id"]]
            self.assertTrue(passage["eligible_for_similarity"],
                            f"{record['passage_id']} was excluded by cleaning but is quoted as evidence")
            local_start = record["char_start"] - passage["body_char_start"]
            local_end = record["char_end"] - passage["body_char_start"]
            self.assertLessEqual(0, local_start)
            self.assertLess(local_start, local_end)
            self.assertEqual(passage["text"][local_start:local_end], record["term"])
            self.assertIn(record["term"].lower(), passage["text"].lower())

    def test_regions_and_traditions_come_from_the_manifest_not_from_the_text(self):
        manifest = divinity_terms.work_attributes()
        for record in self.all_records():
            self.assertEqual(record["region"], manifest[record["work_id"]]["region"])
            self.assertEqual(record["tradition"], manifest[record["work_id"]]["tradition"])

    def test_the_motive_claim_is_stated_as_a_testable_precondition_and_its_limits_are_published(self):
        self.assertIn("precondition", self.result["purpose"])
        self.assertGreaterEqual(len(self.result["cannot_support"]), 5)
        joined = " ".join(self.result["cannot_support"])
        for boundary in ("monolingual", "existence or non-existence", "dated"):
            self.assertIn(boundary, joined)

    def test_no_family_is_allowed_to_look_like_a_universality_proof(self):
        """The verdict must follow from attestation, and an empty universal set must say so plainly."""
        test = self.result["one_concept_test"]
        self.assertEqual(test["families_attested_in_every_work"], [])
        for family in self.result["families"].values():
            self.assertLessEqual(family["works_attested"], self.result["corpus"]["works_in_passage_index"])
        self.assertIn("vocabulary observation", test["verdict"])

    def test_exclusion_of_the_monotheistic_formula_is_published_not_silent(self):
        evidence = self.result["skepticism_evidence"]
        self.assertGreater(evidence["excluded_count"], 0)
        for records in evidence["excluded_matches"].values():
            for record in records:
                self.assertIn("excluded_because", record)
        for record in evidence["records"]:
            self.assertEqual(record["review_state"], "unreviewed_machine_match")

    def test_non_theism_and_exclusivist_monotheism_are_kept_apart(self):
        families = self.result["families"]
        self.assertIn("exclusivist_monotheism", families)
        oneness = self.result["oneness_claim_distribution"]
        self.assertTrue(set(oneness["works_attested"]) <= set(families["exclusivist_monotheism"]["works"]))
        self.assertLess(oneness["term_hits"], families["plural_or_council_deities"]["term_hits"])

    def test_published_output_is_fresh_relative_to_the_corpus_and_the_probe_code(self):
        self.assertEqual(self.result["reproducibility"]["passages_sha256"],
                         hashlib.sha256((ROOT / "corpus/derived/passages_v2.jsonl").read_bytes()).hexdigest())
        self.assertEqual(self.result["reproducibility"]["code_sha256"],
                         hashlib.sha256(Path(divinity_terms.__file__).read_bytes()).hexdigest())

    def test_rerunning_the_probe_reproduces_the_published_bytes(self):
        self.assertEqual(json.dumps(divinity_terms.build(), indent=2, ensure_ascii=False) + "\n",
                         (ROOT / "results/divinity_terms.json").read_text(encoding="utf-8", newline=""))


if __name__ == "__main__":
    unittest.main()
