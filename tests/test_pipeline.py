import argparse
import ast
import csv
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from acquire_corpus import acquire, fetch, merge_rows, parse_metadata  # noqa: E402
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


class PublishedBaselineTests(unittest.TestCase):
    """The paper reports the 42-work baseline as a historical result: the derived passage file its own run
    summary hashed was overwritten by the 65-work rebuild, so two artifacts of that run survive and every figure
    paragraph 5.5 still prints is recomputed from them here. The three false matches it uses as model criticism
    are checked as maxima of named work-pair classes, because a remembered score is exactly the kind of number a
    re-run can quietly invalidate."""

    SOUTH_ASIA = {"ramayana_griffith", "vishnu_purana", "bhagavad_gita_arnold", "jataka_v1",
                  "mahabharata_v1", "mahabharata_v2", "mahabharata_v3", "mahabharata_v4",
                  "mahabharata_7864", "mahabharata_7965", "mahabharata_11894", "mahabharata_12058",
                  "mahabharata_12333"}
    BIBLICAL = {"kjv_bible", "book_of_mormon", "chaldean_genesis", "legends_of_the_jews_v1"}
    SYNTHESIS = {"celtic_myths", "myths_mexico_peru", "myths_north_american", "myths_legends_china",
                 "myths_legends_japan", "chinese_fairy_book", "chinese_folklore", "chinese_wonder_book",
                 "japanese_fairy_tales", "north_american_oral_legends"}

    @classmethod
    def setUpClass(cls):
        import json

        summary_path = ROOT / "results/run_summary.json"
        pairs_path = ROOT / "results/candidate_pairs.jsonl"
        if not summary_path.exists() or not pairs_path.exists():
            raise unittest.SkipTest("the 42-work baseline artifacts are not in this tree")
        cls.summary = json.loads(summary_path.read_text(encoding="utf-8"))
        cls.rows = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()]

    def work_of(self, passage_id):
        return passage_id.split(":")[0]

    def highest_between(self, left_works, right_works):
        candidates = []
        for row in self.rows:
            a, b = self.work_of(row["left"]), self.work_of(row["right"])
            if (a in left_works and b in right_works) or (a in right_works and b in left_works):
                candidates.append(row)
        return max(candidates, key=lambda row: row["score"], default=None)

    def test_the_corpus_and_pair_counts_are_the_runs_own(self):
        corpus = self.summary["corpus"]
        self.assertEqual((corpus["works"], corpus["passages"], corpus["words"]), (42, 21580, 7549234))
        self.assertEqual(corpus["regions"]["South Asia"], 15)
        self.assertEqual(corpus["regions"]["Europe"], 10)
        others = [count for label, count in corpus["regions"].items() if label not in ("South Asia", "Europe")]
        self.assertLess(max(others), 4, "the imbalance the paper describes is no longer the imbalance recorded")
        self.assertEqual(self.summary["candidate_pairs"], len(self.rows))
        self.assertEqual(len(self.rows), 9648)

    def test_the_random_and_order_reference_distributions_are_the_published_ones(self):
        random_pairs = self.summary["random_cross_work_pairs"]
        self.assertEqual(random_pairs["count"], 18963)
        self.assertEqual(round(random_pairs["mean"], 4), 0.0141)
        self.assertEqual(round(random_pairs["p99"], 4), 0.0512)
        shuffled = self.summary["shuffled_sequence_sensitivity"]
        self.assertEqual(shuffled["count"], 256)
        self.assertEqual(round(shuffled["mean"], 4), 0.6740)

    def test_the_known_overlap_controls_score_what_the_paper_says(self):
        controls = self.summary["known_overlap_checks"]
        self.assertEqual(round(controls["sacred_books_east_vs_dhammapada"]["score"], 4), 0.9119)
        self.assertEqual(round(controls["sacred_books_east_vs_quran_sale"]["score"], 4), 0.6022)

    def test_each_published_false_match_is_the_maximum_of_its_work_pair_class(self):
        hindu_biblical = self.highest_between(self.SOUTH_ASIA, self.BIBLICAL)
        self.assertEqual(round(hindu_biblical["score"], 4), 0.5254)
        self.assertEqual({self.work_of(hindu_biblical["left"]), self.work_of(hindu_biblical["right"])},
                         {"kjv_bible", "ramayana_griffith"})
        edda = self.highest_between({"ramayana_griffith"}, {"poetic_edda_bellows"})
        self.assertEqual(round(edda["score"], 4), 0.2207)
        synthesis = self.highest_between({"popol_vuh"}, self.SYNTHESIS)
        self.assertEqual(round(synthesis["score"], 4), 0.5483)

    def test_the_baseline_inputs_are_recorded_and_no_longer_in_the_tree(self):
        """The paragraph calls this a historical result rather than a repeatable run because the 65-work rebuild
        replaced the files the summary hashed. If a rebuild ever reproduces them, the sentence should become a
        reproducibility claim, and this is the test that notices."""
        import hashlib

        recorded = self.summary["reproducibility"]
        manifest = ROOT / "corpus/acquisition_manifest.json"
        self.assertNotEqual(recorded["acquisition_manifest_sha256"],
                            hashlib.sha256(manifest.read_bytes()).hexdigest(),
                            "the shipped manifest is the one the baseline ran on, so 5.5 understates itself")
        passages = ROOT / "corpus/derived/passages.jsonl"
        if not passages.exists():
            self.skipTest("corpus/derived/ is gitignored, so a clean clone cannot check the passage file")
        self.assertNotEqual(recorded["passages_sha256"], hashlib.sha256(passages.read_bytes()).hexdigest())


class ReproductionInventoryTests(unittest.TestCase):
    """`TEST_REPORT.md` §13 promises the reader exactly which commands produce which artifacts.

    The audit found the promise was false in both directions: the list named a file no command writes, and it
    forgot files the commands do write. A reader who follows §13 on a clean machine would have got neither
    warning, so the paragraph is now checked against the directory and against the tool sources it names.
    """

    @classmethod
    def setUpClass(cls):
        section = re.search(r"## 13\. Reproduction(.*)$",
                            (ROOT / "TEST_REPORT.md").read_text(encoding="utf-8"), re.S)
        if section is None:
            raise AssertionError("TEST_REPORT.md no longer carries a numbered §13 Reproduction section; "
                                 "this gate has nothing to check and must not pretend to pass")
        cls.section = section.group(1)
        block = re.search(r"```bash\n(.*?)```", cls.section, re.S)
        if block is None:
            raise unittest.SkipTest("the reproduction section no longer carries a fenced command block")
        cls.commands = [line.strip() for line in block.group(1).splitlines() if line.strip()]
        cls.scripts = [re.search(r"python (tools/\S+\.py)", command).group(1)
                       for command in cls.commands if re.search(r"python (tools/\S+\.py)", command)]
        cls.tool_sources = {script: (ROOT / script).read_text(encoding="utf-8", errors="replace")
                            for script in cls.scripts}
        cls.inventory = set(re.findall(r"`((?:results|corpus|config)/[^`*]+)`", cls.section))

    def test_every_named_artifact_exists(self):
        """Names §13 prints as shipped outputs are real files. corpus/ is exempt: the repository does not ship it."""
        missing = [name for name in self.inventory
                   if not name.startswith("corpus/") and not (ROOT / name).exists()]
        self.assertEqual(missing, [],
                         f"§13 names artifacts that are not in the tree: {missing}")
        corpus_names = [name for name in self.inventory if name.startswith("corpus/")]
        self.assertTrue(corpus_names, "§13 no longer names the corpus inputs, so its exemption is unused")
        self.assertIn("gitignored", self.section,
                      "§13 names corpus/ files without saying the repository does not ship them")

    def test_every_named_artifact_is_known_to_a_command_the_section_prints(self):
        """Every artifact §13 names is a string that appears in the source of a command §13 prints.

        This is deliberately a weaker claim than "that command writes it": the tools emit through several
        helper shapes, and a write-site parser would silently miss one and then fail on an artifact that is
        in fact produced correctly. What this does catch is the defect the audit found -- a file named as an
        output of the reproduction sequence that no tool in the repository knows about at all.
        """
        claimed = set()
        for script in self.scripts:
            claimed |= {name for name in self.inventory
                        if Path(name).name in self.tool_sources[script]}
        # The four frozen baseline artifacts and the human review file are named in the paragraph that
        # explains why the commands above do NOT write them; they are exempt by that paragraph's own terms.
        exempt = {"results/run_summary.json", "results/candidate_pairs.jsonl",
                  "results/motif_candidates.jsonl", "results/top_pairs_for_review.csv",
                  "results/model_comparison.json", "results/v2_manual_review.json"}
        unexplained = sorted(name for name in self.inventory - claimed if name not in exempt)
        self.assertEqual(unexplained, [],
                         f"§13 lists these as outputs but no command it prints knows about them: {unexplained}")
        self.assertTrue(exempt <= self.inventory,
                        "the paragraph exempting the frozen baseline no longer names those artifacts")

    def test_the_readme_repeats_the_same_command_list(self):
        """README.md copies §13, so the two copies are compared rather than trusted."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        blocks = [block for block in re.findall(r"```bash\n(.*?)```", readme, re.S)
                  if "acquire_corpus.py" in block]
        self.assertEqual(len(blocks), 1,
                         "README.md no longer has exactly one reproduction block to compare with §13")
        commands = [line.strip() for line in blocks[0].splitlines() if line.strip()]
        self.assertEqual(commands, self.commands[1:],
                         "README.md and TEST_REPORT.md §13 now print different reproduction sequences")

    def test_the_papers_data_availability_table_names_every_shipped_artifact(self):
        """The reader is told the repository ships these files; the paper's own table has to list them."""
        source = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
        start = source.index(r"\begin{longtable}")
        body = source[start:source.index(r"\end{longtable}", start)]
        named = set()
        for cell in re.findall(r"\\texttt\{([^}]*)\}", body):
            name = cell.replace(r"\_", "_").strip()
            if re.search(r"\.(json|jsonl|csv|html|gz|svg)$", name):
                named.add(Path(name).name)
        self.assertGreater(len(named), 40,
                           f"only {len(named)} artifacts parsed out of the data-availability table; "
                           "the environment or the escaping moved, so this check has stopped checking")
        on_disk = {path.name for path in (ROOT / "results").iterdir() if path.is_file()}
        on_disk |= {path.name for path in (ROOT / "results/figures").iterdir() if path.is_file()}
        unlisted = sorted(on_disk - named)
        self.assertEqual(unlisted, [],
                         f"shipped but absent from the data-availability table: {unlisted}")

    def test_no_file_in_results_is_left_unaccounted_for(self):
        on_disk = {f"results/{path.name}" for path in (ROOT / "results").iterdir() if path.is_file()}
        on_disk |= {f"results/figures/{path.name}"
                    for path in (ROOT / "results/figures").iterdir() if path.is_file()}
        unclaimed = sorted(on_disk - self.inventory)
        self.assertEqual(unclaimed, [],
                         f"these artifacts are shipped but §13 never says where they come from: {unclaimed}")


class CorpusAcquisitionTests(unittest.TestCase):
    """The fetcher writes the provenance artifact every other stage is hashed against.

    A partial re-fetch used to overwrite `corpus/acquisition_manifest.json` with only the rows it touched,
    which destroyed the recorded provenance of the other works and made every published artifact look stale
    by changing the manifest hash. A broken transfer used to surface as a half-written text that hashed and
    segmented like a real one. Both are fixed here, and both are testable without a network.
    """

    DECLARED = [{"work_id": "a", "Title": "A"}, {"work_id": "b", "Title": "B"}, {"work_id": "c", "Title": "C"}]

    def test_a_partial_run_carries_over_the_rows_it_did_not_touch(self):
        previous = {"a": {"work_id": "a", "status": "downloaded", "sha256": "x" * 64},
                    "c": {"work_id": "c", "status": "cached", "sha256": "y" * 64}}
        merged = merge_rows(self.DECLARED, [{"work_id": "b", "status": "downloaded", "sha256": "z" * 64}],
                            previous)
        self.assertEqual([row["work_id"] for row in merged], ["a", "b", "c"],
                         "the manifest order is the config order, so a re-run cannot reorder provenance")
        self.assertEqual(merged[0]["sha256"], "x" * 64, "an untouched row was rewritten")
        self.assertEqual(merged[2]["sha256"], "y" * 64, "an untouched row was rewritten")
        self.assertEqual(merged[1]["status"], "downloaded")

    def test_a_work_with_no_previous_row_is_declared_rather_than_dropped(self):
        merged = merge_rows(self.DECLARED, [], {})
        self.assertEqual(len(merged), len(self.DECLARED), "rows vanished from the manifest")
        self.assertEqual({row["status"] for row in merged}, {"not_fetched"})

    def test_an_unknown_only_selector_refuses_before_any_download(self):
        args = argparse.Namespace(only="kjv_bible,not_a_work", manifest="config/corpus_manifest.csv",
                                  target_words=350, min_words=80)
        with self.assertRaises(SystemExit) as caught:
            acquire(args)
        self.assertIn("not_a_work", str(caught.exception))

    def test_a_broken_transfer_is_retried_instead_of_published(self):
        class Session:
            def __init__(self):
                self.calls = 0

            def get(self, url, timeout):
                self.calls += 1
                if self.calls < 3:
                    raise requests.exceptions.ChunkedEncodingError("Connection broken: InvalidChunkLength")
                response = requests.Response()
                response.status_code = 200
                response._content = b"complete text"
                return response

        session = Session()
        self.assertEqual(fetch(session, "https://example.invalid/book.txt", backoff=0), b"complete text")
        self.assertEqual(session.calls, 3)

    def test_a_transfer_that_never_completes_raises_instead_of_returning_nothing(self):
        class Session:
            def get(self, url, timeout):
                raise requests.exceptions.ChunkedEncodingError("Connection broken")

        with self.assertRaises(requests.exceptions.ChunkedEncodingError):
            fetch(Session(), "https://example.invalid/book.txt", attempts=2, backoff=0)


class LiveCorpusVerificationTests(unittest.TestCase):
    """`results/corpus_live_verification.json` is the only artifact that measures the outside world.

    Every other freshness gate in this repository compares a file with itself: a run summary records the
    SHA-256 of its inputs and a test re-hashes those inputs. That machinery cannot see that the corpus came
    from a website other people can edit, and one work (Gutenberg 3833) has in fact been edited in place
    since it was acquired. This class does not re-download anything; it checks that the published snapshot is
    internally consistent, that it describes the manifest currently in the tree, and that the drift the
    prose reports is the drift the artifact records.
    """

    PATH = ROOT / "results/corpus_live_verification.json"
    STATUSES = {"match", "drifted", "fetch_failed", "acquired_copy_absent",
                "local_copy_does_not_match_the_manifest"}

    @classmethod
    def setUpClass(cls):
        if not cls.PATH.exists():
            raise AssertionError(
                "results/corpus_live_verification.json is missing; publish it with "
                "python tools/verify_corpus_live.py --write-to results/corpus_live_verification.json")
        cls.report = json.loads(cls.PATH.read_text(encoding="utf-8"))
        manifest_path = ROOT / "corpus/acquisition_manifest.json"
        cls.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cls.manifest_rows = {row["work_id"]: row for row in cls.manifest["works"]}

    def test_the_report_covers_every_work_the_manifest_declares(self):
        ids = [record["work_id"] for record in self.report["works"]]
        self.assertEqual(len(ids), len(set(ids)), "a work is checked twice, so the tally double-counts it")
        self.assertEqual(set(ids), set(self.manifest_rows),
                         "the report and the manifest do not describe the same set of works")
        self.assertEqual(self.report["works_checked"], len(ids))

    def test_the_tally_is_the_status_column_recomputed(self):
        recomputed = {}
        for record in self.report["works"]:
            self.assertIn(record["status"], self.STATUSES,
                          f"{record['work_id']} carries a status the tool never emits")
            recomputed[record["status"]] = recomputed.get(record["status"], 0) + 1
        self.assertEqual(self.report["tally"], dict(sorted(recomputed.items())),
                         "the published tally is not the tally of the rows beneath it")
        self.assertEqual(self.report["drifted"],
                         [record["work_id"] for record in self.report["works"]
                          if record["status"] == "drifted"],
                         "the drifted list disagrees with the per-work statuses, in the order the works were "
                         "checked; a second drift made the previous sorted comparison pass by accident")

    def test_the_report_is_pinned_to_the_manifest_bytes_it_checked(self):
        """The same freshness rule every other artifact obeys, applied to a snapshot of the web."""
        digest = hashlib.sha256((ROOT / "corpus/acquisition_manifest.json").read_bytes()).hexdigest()
        self.assertEqual(self.report["manifest_sha256"], digest,
                         "the corpus was re-acquired after this snapshot, so it describes a manifest that "
                         "no longer exists; re-run tools/verify_corpus_live.py")

    def test_every_record_agrees_with_the_hash_the_manifest_recorded(self):
        """A match against a different baseline than the manifest is not a match."""
        for record in self.report["works"]:
            row = self.manifest_rows[record["work_id"]]
            self.assertEqual(record["acquired_sha256"], row["sha256"],
                             f"{record['work_id']} was compared against bytes the manifest does not claim")
            self.assertEqual(record["acquired_bytes"], row["bytes"])
            self.assertEqual(record["source_url"], row["source_url"])
            if record["status"] == "match":
                self.assertEqual(record["live_sha256"], record["acquired_sha256"])
                self.assertNotIn("difference", record, "a match cannot also report a difference")
            if record["status"] == "drifted":
                self.assertNotEqual(record["live_sha256"], record["acquired_sha256"])

    def test_a_drift_record_characterises_the_drift_rather_than_only_counting_it(self):
        drifted = [record for record in self.report["works"] if record["status"] == "drifted"]
        self.assertGreaterEqual(len(drifted), 1,
                                "the prose reports drift and the artifact reports none, or the tool stopped "
                                "recording what it found")
        for record in drifted:
            difference = record["difference"]
            self.assertGreater(difference["differing_bytes_in_common_prefix"], 0)
            self.assertNotEqual(difference["acquired_snippet"], difference["live_snippet"],
                                "the two snippets quoted as evidence are identical")
            self.assertLessEqual(len(difference["acquired_snippet"]), 400,
                                 f"{record['work_id']} quotes a window that runs to the last differing offset, "
                                 "which on a shifted file is the whole text")
            self.assertTrue(difference["explanation"])
            if difference.get("differing_line_blocks") is None:
                continue
            self.assertLessEqual(difference.get("differing_line_blocks"),
                                 difference["differing_bytes_in_common_prefix"],
                                 "aligning the copies cannot find more edits than there are differing bytes")
            self.assertEqual(len(difference.get("line_differences") or []),
                             min(difference.get("differing_line_blocks"), 6),
                             "the blocks published are not the first edits the alignment found")

    def test_a_shifted_drift_is_not_reported_as_a_massive_edit(self):
        """A file whose length changed makes every later byte position disagree, which is not a text change.

        `odyssey` drifted by two bytes in a header line and the positional comparison calls that 685,258
        differing offsets. The artifact has to say so, because a reader who is told the byte count and nothing
        else will read it as a rewritten text and conclude the corpus is not the corpus.
        """
        for record in self.report["works"]:
            if record["status"] != "drifted":
                continue
            difference = record["difference"]
            if not difference["length_change"] or difference.get("differing_line_blocks") is None:
                continue
            self.assertGreater(difference["differing_bytes_in_common_prefix"],
                               20 * difference.get("differing_line_blocks"),
                               "the positional count and the edit count agree, so this sentence is about nothing")
            self.assertIn("shift", difference["explanation"],
                          f"{record['work_id']} reports a length change and a positional count with no note "
                          "that the count is the shift")

    def test_the_line_aligned_edit_count_the_paper_quotes_is_the_artifact_own(self):
        for work_id, name in (("odyssey", r"paper/main.tex"),):
            if not any(record["work_id"] == work_id for record in self.report["works"]):
                self.skipTest(f"{work_id} is not in the current verification snapshot")
            record = next(item for item in self.report["works"] if item["work_id"] == work_id)
            blocks = record["difference"].get("differing_line_blocks")
            self.assertIsNotNone(blocks, f"{name} quotes an edit count for a work the tool did not characterise")
            text = (ROOT / name).read_bytes().decode("utf-8")
            self.assertIn(f"differ at {blocks} sites", " ".join(text.split()),
                          f"{name} quotes an edit count for {work_id} that the artifact does not record")

    def test_the_report_says_what_a_snapshot_cannot_establish(self):
        for key in ("interpretation", "what_it_does_not_establish"):
            self.assertIn(key, self.report)
            self.assertTrue(self.report[key].strip(), f"{key} is empty")
        self.assertIn("manifest", self.report["interpretation"])
        self.assertIn("snapshot", self.report["what_it_does_not_establish"],
                      "a one-time external check must state that it is not a monitoring record")

    def test_the_drift_figures_the_prose_quotes_are_the_artifacts_own(self):
        """The paper, TEST_REPORT and README each quote this snapshot as a number, so all three are checked."""
        matches = self.report["tally"].get("match", 0)
        drift = self.report["tally"].get("drifted", 0)
        total = self.report["works_checked"]
        # Two prose shapes are in use: "64 of 65 still match" and "64 matches and 1 drift". Each pair is
        # compared with the figures that shape actually claims.
        shapes = ((r"(\d+) of (\d+) still match", (matches, total)),
                  (r"(\d+) matches and (\d+) drift", (matches, drift)))
        for name in ("paper/main.tex", "TEST_REPORT.md", "README.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            cited = []
            for pattern, expected in shapes:
                for pair in re.findall(pattern, text):
                    cited.append((pair, expected))
            self.assertTrue(cited, f"{name} no longer quotes the external stability figures")
            for pair, expected in cited:
                self.assertEqual((int(pair[0]), int(pair[1])), expected,
                                 f"{name} quotes {pair} but the artifact records "
                                 f"{expected[0]} of {expected[1]}")


class ToolWritePolicyTests(unittest.TestCase):
    """Every text-mode write in `tools/` has to state the line endings it emits.

    **Why this is a scientific check, not a style rule.** `open(path, "w")` and `Path.write_text` translate
    "\\n" to the platform line separator. On Windows that produced CRLF artifacts, and the SHA-256 of a CRLF
    file is not the SHA-256 of the same content with LF. This study's freshness gates compare a recorded
    hash with the bytes on disk, so an unstated policy meant a reviewer on Linux who re-ran the published
    reproduction sequence would rewrite roughly two dozen artifacts with different bytes and see every
    downstream stage report a stale input --- a reproducibility failure caused by the operating system
    rather than by the data. The fix is to pin each writer to the endings its published artifact already
    carries, which leaves every hash on this machine exactly as it was and makes them platform-independent.

    Binary writes are exempt because they already emit the bytes they are handed.
    """

    def test_no_text_mode_write_leaves_line_endings_to_the_platform(self):
        offenders = []
        for path in sorted((ROOT / "tools").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                kind = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
                if kind == "write_text":
                    mode = "w"
                elif kind == "open":
                    mode = None
                    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                        mode = node.args[1].value
                    for keyword in node.keywords:
                        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                            mode = keyword.value.value
                    if mode is None:
                        continue  # a plain open() reads; it writes nothing
                    if not any(character in str(mode) for character in "wa"):
                        continue  # "r"/"rt"/"rb" read, and a read emits no bytes
                else:
                    continue
                if "b" in str(mode) or "newline" in {keyword.arg for keyword in node.keywords}:
                    continue
                offenders.append(f"tools/{path.name}:{node.lineno} opens for '{mode}' without newline=")
        self.assertEqual(offenders, [],
                         "these writers would produce different bytes, and therefore different published "
                         f"hashes, on Linux than on Windows: {offenders}")

    def test_the_pinned_endings_match_the_artifacts_already_published(self):
        """The pin is not free: it has to name the endings the shipped bytes actually use."""
        for name, expected in (("results/v2_run_summary.json", "\r\n"), ("results/v2_candidate_pairs.jsonl", "\r\n"),
                               ("results/annotation_validation.json", "\r\n"),
                               ("corpus/acquisition_manifest.json", "\r\n"),
                               ("results/ontology_graph.json", "\n"), ("results/pilot_slice.json", "\n"),
                               ("config/recall_probe_cues.json", "\n")):
            data = (ROOT / name).read_bytes()
            endings = "\r\n" if data.count(b"\r\n") == data.count(b"\n") and data.count(b"\r\n") else "\n"
            self.assertEqual(endings, expected,
                             f"{name} is now {endings!r} but the writers were pinned assuming {expected!r}; "
                             "a published hash has moved")


class FingerprintComparisonTests(unittest.TestCase):
    """`results/fingerprint_diff.json` is the evidence behind the claim that re-running the sequence moved no measurement.

    §13 of TEST_REPORT now prints six numbers about a 22.6-minute rebuild that nothing here repeats. The report
    they come from is regenerable, so this class checks its own arithmetic, checks that each status code means
    what the row's two digests show, and checks that the prose quotes the tally rather than a figure carried
    over from an earlier draft -- which is the failure mode that put 239 and 244 in the same document once.
    """

    PATH = ROOT / "results/fingerprint_diff.json"
    STATUSES = {"byte_identical", "stamps_only", "measurement_changed", "opaque_change",
                "added_since_baseline", "removed_since_baseline"}

    @classmethod
    def setUpClass(cls):
        if not cls.PATH.exists():
            raise AssertionError(
                "results/fingerprint_diff.json is missing; publish it with python "
                "tools/compare_published_fingerprints.py --write-to results/fingerprint_diff.json")
        cls.report = json.loads(cls.PATH.read_text(encoding="utf-8"))
        cls.rows = cls.report["files"]

    def test_the_tally_is_the_status_column_recomputed(self):
        recomputed = {}
        for row in self.rows:
            self.assertIn(row["status"], self.STATUSES,
                          f"{row['path']} carries a status the tool never emits: {row['status']}")
            recomputed[row["status"]] = recomputed.get(row["status"], 0) + 1
        self.assertEqual(self.report["files_compared"], len(self.rows))
        self.assertEqual(self.report["tally"], dict(sorted(recomputed.items())))
        self.assertEqual(sum(self.report["tally"].values()), len(self.rows),
                         "the tally counts more or fewer files than the rows describe")

    def test_changed_is_exactly_the_rows_that_are_not_byte_identical(self):
        expected = [row["path"] for row in self.rows if row["status"] != "byte_identical"]
        self.assertEqual([row["path"] for row in self.report["changed"]], expected)

    def test_every_status_means_what_its_row_shows(self):
        for row in self.rows:
            status = row["status"]
            now, base = row["sha256_now"], row["sha256_at_baseline"]
            measured_now, measured_base = row["measured_sha256_now"], row["measured_sha256_at_baseline"]
            if status == "byte_identical":
                self.assertEqual(now, base, f"{row['path']} is called identical but its digests differ")
            elif status == "stamps_only":
                self.assertNotEqual(now, base, f"{row['path']} is called stamp-only but its bytes are equal")
                self.assertIsNotNone(measured_now, f"{row['path']} has no measured digest to compare")
                self.assertEqual(measured_now, measured_base,
                                 f"{row['path']} is called stamp-only while its measured digest differs")
            elif status == "measurement_changed":
                self.assertNotEqual(now, base)
                self.assertIsNotNone(measured_now)
                self.assertNotEqual(measured_now, measured_base,
                                     f"{row['path']} changed bytes but not measurements; it should be stamps_only")
            elif status == "opaque_change":
                self.assertNotEqual(now, base)
                self.assertTrue(measured_now is None or measured_base is None,
                                f"{row['path']} is opaque yet both measured digests exist")
            else:
                self.assertTrue((now is None) != (base is None),
                                f"{row['path']} is {status} but present on both sides or neither")

    def test_the_report_is_not_one_of_the_files_it_classifies(self):
        paths = {row["path"] for row in self.rows}
        self.assertNotIn("results/fingerprint_diff.json", paths,
                         "the report digests itself, so its own bytes would be a changed measurement")

    def test_the_volatile_field_policy_is_published_rather_than_implied(self):
        keys = set(self.report["volatile_fields_stripped_before_the_measured_digest"])
        suffixes = self.report["volatile_suffixes_stripped_before_the_measured_digest"]
        self.assertIn("elapsed_seconds", keys, "wall-clock time is a stamp, and a rebuild always moves it")
        self.assertIn("partial_run", keys)
        self.assertIn("_sha256", suffixes, "input hashes are the majority of what a re-run legitimately moves")
        self.assertIn("_at_utc", suffixes)
        self.assertIn("masked", self.report["non_json_text_digest_policy"],
                      "rendered pages reprint the hashes of what they read; the report must say they are masked")

    def test_the_report_says_that_determinism_is_not_correctness(self):
        self.assertIn("deterministic", self.report["what_this_does_not_establish"])
        self.assertIn("baseline", self.report["what_this_does_not_establish"])

    def test_the_prose_reports_the_same_classification(self):
        text = (ROOT / "TEST_REPORT.md").read_text(encoding="utf-8")
        stated = re.search(r"(\d+) artifacts byte-identical,\s*(\d+) changed in stamps only,\s*(\d+) removed,\s*"
                          r"(\d+) unclassifiable,\s*(\d+) added and\s*(\d+) whose measured content moved", text)
        self.assertIsNotNone(stated, "§13 no longer prints the classification in the form this test can read")
        tally = self.report["tally"]
        self.assertEqual([int(value) for value in stated.groups()],
                         [tally.get("byte_identical", 0), tally.get("stamps_only", 0),
                          tally.get("removed_since_baseline", 0), tally.get("opaque_change", 0),
                          tally.get("added_since_baseline", 0), tally.get("measurement_changed", 0)],
                         "the prose and results/fingerprint_diff.json disagree about what the rebuild moved")
        moved = sorted(row["path"] for row in self.report["changed"] if row["status"] == "measurement_changed")
        for path in moved:
            self.assertIn(path, text, f"{path} changed measured content and the prose does not name it")


if __name__ == "__main__":
    unittest.main()
