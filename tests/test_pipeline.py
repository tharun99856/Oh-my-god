import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from acquire_corpus import parse_metadata
from build_relevance_graph import aggregate_pairs
from narrative_v2 import classify_passage, segment_narrative
from run_similarity_v2 import build_dependence_index, dependence_between, shuffle_sentences
from text_pipeline import extract_body, segment_text


class TextPipelineTests(unittest.TestCase):
    def test_body_extraction_preserves_raw_offsets(self):
        raw = "Header\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\nStory text.\n\n  *** END OF THE PROJECT GUTENBERG EBOOK X ***  \nLicense"
        body, start, end = extract_body(raw)
        self.assertEqual(body, "Story text.")
        self.assertEqual(raw[start:end], body)

    def test_crlf_boundaries(self):
        raw = "*** START OF X ***\r\nBody\r\n  *** END OF X ***  \r\nLicense"
        self.assertEqual(extract_body(raw)[0], "Body")

    def test_segmentation_merges_short_tail_and_preserves_text(self):
        text = " ".join("word" for _ in range(10))
        passages = segment_text(text, "x", target_words=6, min_words=5)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["word_count"], 10)
        self.assertEqual(text[passages[0]["body_char_start"]:passages[0]["body_char_end"]], text)

    def test_segmentation_offsets_reconstruct_every_passage(self):
        text = "One two three. Four five six! Seven eight nine."
        for passage in segment_text(text, "x", target_words=3, min_words=1):
            reconstructed = text[passage["body_char_start"]:passage["body_char_end"]]
            self.assertEqual(reconstructed, passage["text"])

    def test_metadata_parser_keeps_continuation_lines(self):
        raw = "Title: Example\nAuthor: First Author\n        Second Author\n\n*** START OF X ***"
        self.assertEqual(parse_metadata(raw)["Author"], "First Author Second Author")

    def test_apparatus_classification_preserves_ordinary_narrative(self):
        narrative = "The hero crossed the river and spoke with the king about the coming storm."
        self.assertFalse(classify_passage(narrative)[1])
        editorial = "Page 174. The Praise of Kings. Compare this account with what Samuel says in the Bible."
        self.assertTrue(classify_passage(editorial)[1])

    def test_section_segmentation_retains_headings_and_offsets(self):
        text = "CHAPTER I\n" + " ".join(["alpha"] * 80) + "\nCHAPTER II\n" + " ".join(["beta"] * 80)
        passages = segment_narrative(text, "x")
        self.assertEqual(len(passages), 2)
        self.assertEqual(passages[0]["section_heading"], "CHAPTER I")
        for passage in passages:
            self.assertEqual(text[passage["body_char_start"]:passage["body_char_end"]], passage["text"])

    def test_excluded_heading_applies_to_its_whole_section(self):
        text = "CHAPTER I\n" + " ".join(["narrative"] * 80) + "\nINDEX\n" + " ".join(["entry"] * 80)
        passages = segment_narrative(text, "x")
        index_passages = [passage for passage in passages if passage["section_heading"] == "INDEX"]
        self.assertTrue(index_passages)
        self.assertTrue(all(not passage["eligible_for_similarity"] for passage in index_passages))
        self.assertTrue(all("excluded_heading_index" in passage["content_flags"] for passage in index_passages))

    def test_manifest_identifiers_are_unique(self):
        with (ROOT / "config/corpus_manifest.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len({row["work_id"] for row in rows}))
        self.assertTrue(all(row["gutenberg_id"].isdigit() for row in rows))

    def test_source_dependence_rules_are_symmetric(self):
        config = {
            "work_families": [{"family_id": "family", "work_ids": ["a", "b"], "relationship": "same_translation_family"}],
            "pair_rules": [{"left_work": "c", "right_work": "d", "relationship": "direct_textual_dependence"}],
        }
        works = {work_id: {"overlap_group": ""} for work_id in ["a", "b", "c", "d"]}
        families, pair_rules = build_dependence_index(config)
        self.assertEqual(dependence_between("a", "b", works, families, pair_rules)["relationship"], "same_translation_family")
        self.assertEqual(dependence_between("d", "c", works, families, pair_rules)["relationship"], "direct_textual_dependence")
        self.assertIsNone(dependence_between("a", "c", works, families, pair_rules))

    def test_sentence_shuffle_preserves_sentence_multiset(self):
        import numpy as np

        sentences = ["First sentence.", "Second sentence!", "Third sentence?", "Fourth sentence."]
        shuffled = shuffle_sentences(" ".join(sentences), np.random.default_rng(7))
        self.assertEqual(sorted(shuffled.split()), sorted(" ".join(sentences).split()))

    def test_work_aggregation_preserves_passage_orientation(self):
        passages = {"p1": {"work_id": "z"}, "p2": {"work_id": "a"}}
        record = {
            "left": "p1",
            "right": "p2",
            "score": 0.5,
            "shared_motifs": [],
            "discovery_eligible": True,
            "dependence_relationship": None,
        }
        edge = aggregate_pairs([record], passages)[0]
        self.assertEqual((edge["left_work"], edge["right_work"]), ("a", "z"))
        self.assertEqual((edge["top_left_passage"], edge["top_right_passage"]), ("p2", "p1"))


if __name__ == "__main__":
    unittest.main()
