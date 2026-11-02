"""Every test count the documentation prints is checked here against the collector's own arithmetic.

**Why this file exists.** The second-round reviewer wrote that this project's suite figures were "reported, not
verified", and the documents proved it: one page carried 239 tests while another page's per-suite breakdown of
the same suite summed to 244. Neither number was wrong because of a code defect. Both were wrong because a human
copied a figure out of an earlier draft, and a copied figure can only be caught by another human -- which is the
one resource this project has already been told it does not have here. So this module runs the collector, runs
the two tests that carry the parameterised subtests, reads the sentences in `paper/main.tex`, `TEST_REPORT.md`,
`ARCHITECTURE.md` and `RESEARCH_PROTOCOL.md`, and fails when prose and measurement disagree.

**What it does not do.** It does not run the suite, so it says nothing about whether any test passes. It asserts
only that the number of tests the documents quote is the number of tests that exist. A green suite with a stale
abstract is the failure mode caught here; a red suite is caught by the suite.

The subprocesses are one `--collect-only` over `tests/` and one run of two named node ids, which together cost a
second or so. Nothing is measured at import time, because the collector collects this file: a module-level call
would spawn a subprocess that imports the module that spawns the subprocess. The environment marker below is
belt-and-braces insurance for the same reason if a child ever runs tests rather than collecting them.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "main.tex"
_CHILD_ENV = "QODER_DOCUMENTED_COUNTS_CHILD"

# The subtests live in exactly these two tests, which loop over the four jointly-mandatory evidence conditions
# and over the conflated edge-type values. The published phrase is "7 parameterised subtests", and the only
# honest way to know that figure is to run the two tests that emit it.
SUBTEST_NODES = (
    "tests/test_model_comparison.py::ConjunctionOfFourConditionsTests::test_each_condition_alone_blocks_the_assertion",
    "tests/test_model_comparison.py::EdgeTypingTests::test_conflated_edge_type_value_is_illegal",
)

# The label each document uses for a suite, and the file that produces it. The paper says "divinity-census" and
# "state-coder" where the files are named for instrument generations, so the mapping is published here rather
# than guessed at read time.
SUITE_LABELS = {
    "pipeline": "tests/test_pipeline.py",
    "structural-engine": "tests/test_narrative_similarity.py",
    "schema": "tests/test_schema.py",
    "divinity-census": "tests/test_divinity_terms.py",
    "exclusivist-audit": "tests/test_exclusivist_audit.py",
    "state-coder": "tests/test_divinity_ontology.py",
    "graph-recall": "tests/test_graph_recall.py",
    "model-comparison": "tests/test_model_comparison.py",
    "anomaly-scan": "tests/test_dimension_anomalies.py",
    "annotation-recall": "tests/test_annotation_recall.py",
    "typesetting": "tests/test_tex_typesetting.py",
    "documented-counts": "tests/test_documented_counts.py",
}

def _refuse_to_recurse():
    if os.environ.get(_CHILD_ENV):
        raise unittest.SkipTest(
            "already inside a measurement subprocess; collecting this module is fine, running it from a child "
            "would spawn a grandchild"
        )


def _run(args):
    env = dict(os.environ)
    env[_CHILD_ENV] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, env=env,
    )
    return result.returncode, result.stdout + result.stderr


_CACHE = {}


def collected_counts():
    """`(total, {file: count})` read from the collector itself, once per run."""
    _refuse_to_recurse()
    if "collect" not in _CACHE:
        code, text = _run(["tests", "--collect-only", "-q"])
        if code != 0:
            raise AssertionError(f"collection failed, so no count can be checked: {text[-800:]}")
        per_file = {}
        for line in text.splitlines():
            match = re.match(r"(tests/\w+\.py)::", line.strip())
            if match:
                per_file[match.group(1)] = per_file.get(match.group(1), 0) + 1
        total_match = re.search(r"(\d+) tests? collected", text)
        if total_match is None:
            raise AssertionError(f"the collector printed no total: {text[-800:]}")
        _CACHE["collect"] = (int(total_match.group(1)), per_file)
    return _CACHE["collect"]


def subtest_count():
    _refuse_to_recurse()
    if "subtests" not in _CACHE:
        code, text = _run(["-q", *SUBTEST_NODES])
        if code != 0:
            raise AssertionError(f"the two subtest-bearing tests did not run clean: {text[-800:]}")
        match = re.search(r"(\d+) subtests passed", text)
        if match is None:
            raise AssertionError(
                f"the short summary reported no subtest total; the quiet flag is what makes pytest count them: "
                f"{text[-800:]}"
            )
        _CACHE["subtests"] = int(match.group(1))
    return _CACHE["subtests"]


def measured():
    """`(total, per_file, subtests)` -- each figure from the tool that actually counts it."""
    total, per_file = collected_counts()
    return total, per_file, subtest_count()


def validated_line_count():
    """The source size `tools/validate_tex.py` prints, i.e. the number a prose quote is copying."""
    _refuse_to_recurse()
    if "texlines" not in _CACHE:
        env = dict(os.environ)
        env[_CHILD_ENV] = "1"
        result = subprocess.run(
            [sys.executable, "tools/validate_tex.py"], cwd=str(ROOT),
            capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"the structural validator failed, so no figure of its can be quoted: "
                f"{(result.stdout + result.stderr)[-600:]}"
            )
        match = re.search(r": (\d+) lines", result.stdout)
        if match is None:
            raise AssertionError(f"the validator printed no line count: {result.stdout[-600:]}")
        _CACHE["texlines"] = int(match.group(1))
    return _CACHE["texlines"]


def paper_text():
    return PAPER.read_text(encoding="utf-8")


class DocumentedTestCounts(unittest.TestCase):
    def test_the_measured_counts_are_plausible_before_any_prose_is_judged(self):
        total, per_file, subtests = measured()
        self.assertGreater(total, 200, "the collector found almost nothing, so a comparison would be meaningless")
        self.assertEqual(
            sum(per_file.values()), total,
            f"the collector's per-file counts ({sum(per_file.values())}) do not sum to its total ({total}); "
            "the parser here is wrong, not the paper",
        )
        self.assertEqual(
            set(per_file), set(SUITE_LABELS.values()),
            "a suite file appeared or vanished, so the published label map no longer covers the directory",
        )
        self.assertGreaterEqual(subtests, 1, "the two named tests emitted no subtest, so the node ids drifted")

    def test_the_abstracts_total_is_the_collected_total(self):
        total, _per_file, subtests = measured()
        stated = re.findall(r"and (\d+) unit tests plus (\d+) parameterised subtests", paper_text())
        self.assertEqual(len(stated), 1, f"the abstract should state one suite total, found {stated}")
        self.assertEqual(
            (int(stated[0][0]), int(stated[0][1])), (total, subtests),
            f"the abstract says {stated[0][0]} tests plus {stated[0][1]} subtests; the collector says {total} "
            f"plus {subtests}. Update the sentence, or fix the suite, but do not leave the two numbers arguing.",
        )

    def test_the_data_availability_breakdown_is_the_collected_per_file_count(self):
        total, per_file, subtests = measured()
        row = re.search(r"(\d+) tests plus (\d+) parameterised subtests[^&]*?:\s*(.*?)\\\\", paper_text(), re.S)
        self.assertIsNotNone(row, "the data-availability row's per-suite breakdown could not be found")
        self.assertEqual(int(row.group(1)), total, "the breakdown's own total is stale")
        self.assertEqual(int(row.group(2)), subtests, "the breakdown's subtest figure is stale")
        pairs = re.findall(r"(\d+) ([a-z-]+)", row.group(3))
        stated = {}
        for count, label in pairs:
            stated[label] = count
        self.assertEqual(len(pairs), len(SUITE_LABELS),
                         f"the row lists {len(pairs)} suites; the published map has {len(SUITE_LABELS)}")
        for label, path in SUITE_LABELS.items():
            self.assertIn(label, stated, f"the row never mentions {label} ({path})")
            self.assertEqual(int(stated[label]), per_file[path],
                             f"the paper says {label} has {stated[label]} tests; {path} collects {per_file[path]}")
        self.assertEqual(
            sum(int(value) for value in stated.values()), total,
            "the per-suite figures do not sum to the stated total, which is how 239 and 244 came to sit in one "
            "document at once",
        )

    def test_the_internal_reports_quote_the_same_total(self):
        total, _per_file, subtests = measured()
        for name, pattern in (
            ("TEST_REPORT.md", r"\*\*(\d+) passed, plus (\d+) subtests\*\*"),
            ("ARCHITECTURE.md", r"(\d+) tests plus (\d+) parameterised subtests"),
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            found = re.findall(pattern, text)
            self.assertTrue(found, f"{name} no longer states a suite total matching {pattern!r}")
            for stated_total, stated_subtests in found:
                self.assertEqual(
                    (int(stated_total), int(stated_subtests)), (total, subtests),
                    f"{name} says {stated_total} tests ({stated_subtests} subtests); the collector says "
                    f"{total} ({subtests})",
                )
        protocol = re.findall(r"([\d,]+) tests \|", (ROOT / "RESEARCH_PROTOCOL.md").read_text(encoding="utf-8"))
        self.assertTrue(protocol, "RESEARCH_PROTOCOL.md no longer states a suite total")
        for stated in protocol:
            self.assertEqual(int(stated.replace(",", "")), total,
                             f"RESEARCH_PROTOCOL.md says {stated} tests; the collector says {total}")

    def test_the_layer_specific_counts_cited_in_prose_are_the_files_own(self):
        """Two documents quote this layer's suite size separately, so those figures are checked separately."""
        _total, per_file, _subtests = measured()
        expected = per_file["tests/test_model_comparison.py"]
        for name in ("TEST_REPORT.md", "RESEARCH_PROTOCOL.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            cited = [
                int(value)
                for line in text.splitlines()
                if "compare_models" in line
                for value in re.findall(r"(\d+) tests\b", line)
            ]
            self.assertTrue(cited, f"{name} no longer cites a test count for the model-comparison layer")
            for value in cited:
                self.assertEqual(
                    value, expected,
                    f"{name} cites {value} tests for a suite that collects {expected}",
                )

    def test_a_quoted_source_line_count_is_the_one_the_validator_prints(self):
        """`TEST_REPORT.md` says the clean copy passes "over N lines", and N moves every time a table row is added."""
        printed = validated_line_count()
        self.assertEqual(
            printed, len(PAPER.read_text(encoding="utf-8").splitlines()),
            "the validator's own count and a plain read of the file disagree, so one of them is misparsing the source",
        )
        stated = re.findall(r"over (\d+) lines", (ROOT / "TEST_REPORT.md").read_text(encoding="utf-8"))
        self.assertTrue(stated, "TEST_REPORT.md no longer quotes a source line count")
        for value in stated:
            self.assertEqual(
                int(value), printed,
                f"TEST_REPORT.md quotes {value} lines; the validator reports {printed}",
            )


if __name__ == "__main__":
    unittest.main()
