"""Compile the paper and check what the compiler reports.

`tools/validate_tex.py` reads this file's structure statically. Only a LaTeX engine can tell whether a
typewriter artifact name fits the table column it was put in: when it does not, TeX emits an overfull hbox
and the name prints on top of the neighbouring column, which is exactly how the data-availability pages of
an earlier edition looked. A reviewer reported that damage from a build of their own, so the claim that the
paper is typeset correctly is checked here rather than asserted in prose.

Where no engine is installed the whole class skips, and the skip is the honest outcome: this file makes no
claim about geometry it cannot test.
"""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/main.tex"
sys.path.insert(0, str(ROOT / "tools"))

from validate_tex import BREAKPOINT_RE  # noqa: E402

ENGINES = ("pdflatex", "xelatex", "lualatex")
MAX_PASSES = 4
# MiKTeX installs per-user outside PATH on some machines, and an engine that is installed but not on PATH
# reads as "no engine", which would let a broken layout pass by silence.
EXTRA_DIRS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/MiKTeX/miktex/bin/x64",
    Path(os.environ.get("PROGRAMFILES", "")) / "MiKTeX/miktex/bin/x64",
    Path("/Library/TeX/texbin"),
    Path("/usr/local/texlive"),
)


def find_engine():
    for name in ENGINES:
        found = shutil.which(name)
        if found:
            return found
    for directory in EXTRA_DIRS:
        for name in ENGINES:
            for suffix in ("", ".exe"):
                candidate = directory / f"{name}{suffix}"
                if candidate.is_file():
                    return str(candidate)
    return None


PAGE_RE = re.compile(r"Outputwritten.*?\.pdf\((\d+)pages", re.S)


def page_count(log_text: str):
    """The page count TeX reported, or None.

    The log wraps at 79 characters and can break inside the path it is printing, so the line is matched
    with its whitespace removed rather than read literally.
    """
    match = PAGE_RE.search(re.sub(r"\s+", "", log_text))
    return match.group(1) if match else None


class TexTypesettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = find_engine()
        if engine is None:
            raise unittest.SkipTest(
                "no pdflatex, xelatex or lualatex on PATH or in a known per-user install; "
                "typesetting geometry is untested on this machine"
            )
        cls.engine = engine
        cls.workdir = Path(tempfile.mkdtemp(prefix="qoder-tex-"))
        # LaTeX reads \jobname.aux from the input search path but writes it to -output-directory, so a
        # compilation that points its output at a temp dir while its source sits in paper/ picks up whatever
        # stale aux an earlier in-tree build left behind. That produced a "Reference undefined on the second
        # pass" failure on a paper with no broken reference: pass 2 was answering a question about a file
        # from a previous edition, not about this source. Compiling a copy in an empty directory makes the
        # aux pass 2 reads the one pass 1 wrote, which is the only two-pass property worth testing.
        source = cls.workdir / "main.tex"
        shutil.copyfile(PAPER, source)
        cls.logs = []
        # Cross-references need a second pass, and a prose edit that changes the length needs a third: LaTeX
        # itself says "Label(s) may have changed. Rerun". Two blind passes would fail on the edit that is most
        # likely to be under review, so the loop runs until the page count repeats and the log stops asking for
        # a rerun, capped so a genuinely unstable document is reported rather than compiled forever.
        for pass_number in range(1, MAX_PASSES + 1):
            result = subprocess.run(
                [engine, "-interaction=nonstopmode", "-output-directory", str(cls.workdir), str(source)],
                cwd=str(cls.workdir), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=900,
            )
            text = cls._log()
            cls.logs.append((result.returncode, text))
            pages = [page_count(entry) for _, entry in cls.logs]
            settled = (
                len(pages) >= 2
                and pages[-1] is not None
                and pages[-1] == pages[-2]
                and "may have changed" not in text
            )
            if settled:
                break
        cls.pages = [page_count(text) for _, text in cls.logs]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)

    @classmethod
    def _log(cls):
        path = Path(cls.workdir) / "main.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def test_the_paper_compiles_and_writes_a_pdf(self):
        for position, (code, text) in enumerate(self.logs, 1):
            self.assertEqual(code, 0, f"pass {position} exited {code}: {text[-1200:]}")
            self.assertIn(".pdf", text, f"pass {position} wrote no PDF: {text[-1200:]}")
        self.assertTrue(all(p is not None for p in self.pages),
                        f"no page count reported in the log; tail: {self.logs[-1][1][-800:]}")
        self.assertGreater(int(self.pages[-1]), 10)

    def test_no_box_overflows_its_column(self):
        code, text = self.logs[-1]
        overfull = [float(w) for w in re.findall(r"Overfull \\hbox \((\d+\.\d+)pt too wide\)", text)]
        underfull = re.findall(r"Underfull \\hbox", text)
        widest = max(overfull, default=0.0)
        self.assertEqual(overfull, [], f"{len(overfull)} overfull box(es), widest {widest:.1f}pt "
                                       f"in a {code}-exit run")
        self.assertEqual(underfull, [], f"{len(underfull)} underfull box(es)")

    def test_every_reference_and_citation_resolves_after_two_passes(self):
        code, text = self.logs[-1]
        for pattern, label in ((r"Reference \S+ on page \d+ undefined", "reference"),
                               (r"Citation \S+ undefined", "citation"),
                               (r"Label\(s\) may have changed", "unstable label set")):
            self.assertNotRegex(text, pattern, f"{label} unresolved on the second pass")
        fatal = [line for line in text.splitlines() if line.startswith("!")]
        self.assertEqual(fatal, [], f"LaTeX errors: {fatal[:3]}")

    def test_the_second_pass_agrees_with_the_first_about_extent(self):
        self.assertTrue(all(p is not None for p in self.pages))
        self.assertEqual(self.pages[0], self.pages[-1],
                         "the document changed length between passes, so the published page "
                         "references are not stable")
        self.assertNotIn("may have changed", self.logs[-1][1],
                         f"the engine still wanted a rerun after {len(self.logs)} passes "
                         f"({MAX_PASSES} allowed): {self.pages}")

    def test_the_page_count_the_paper_states_is_the_one_it_compiles_to(self):
        stated = re.findall(r"the paper sets to (\d+) pages", PAPER.read_text(encoding="utf-8"))
        self.assertEqual(len(stated), 1,
                         f"the page count belongs in the reproducibility statement exactly once, found {stated}")
        self.assertEqual(int(stated[0]), int(self.pages[-1]),
                         "the prose quotes a page count, so it is a measurement and this test owns it")

    def test_the_breakpoint_macro_the_columns_depend_on_is_present(self):
        source = PAPER.read_text(encoding="utf-8")
        self.assertTrue(BREAKPOINT_RE.search(source),
                        "the preamble must give \\_ a breakpoint; without it artifact names cannot wrap "
                        "inside a fixed-width column")


class PaperCoverageFigureTests(unittest.TestCase):
    """The coverage numbers in the paper must be the numbers the graph artifact publishes.

    Every other figure in this repository reaches the page through a run summary that a test re-derives. The
    coverage paragraph was typed, so it is pinned here against `coverage_inventory` in
    `results/ontology_graph.json`: if the frame gains a value or a pattern and the paper is not updated, this
    test fails rather than leaving the page and the artifact disagreeing.
    """

    @classmethod
    def setUpClass(cls):
        graph = json.loads((ROOT / "results/ontology_graph.json").read_text(encoding="utf-8"))
        cls.inventory = graph["coverage_inventory"]
        source = PAPER.read_text(encoding="utf-8")
        flat = re.sub(r"\\field\{([^}]*)\}", r"\1", re.sub(r"\s+", " ", source))
        cls.flattened = flat.replace("\\_", "_")

    def _said(self, pattern):
        match = re.search(pattern, self.flattened)
        self.assertIsNotNone(match, f"the paper no longer says: {pattern!r}")
        return int(match.group(1))

    def test_the_two_decompositions_of_the_declared_count_are_the_published_ones(self):
        self.assertEqual(self._said(r"twelve dimensions carrying (\d+) declared values"),
                         self.inventory["declared_values"])
        self.assertEqual(self._said(r"(\d+) values have an English surface pattern"),
                         self.inventory["with_a_surface_pattern"])
        self.assertEqual(self._said(r"and (\d+) have none"),
                         self.inventory["without_a_surface_pattern"])
        self.assertEqual(self._said(r"(\d+) produced at least one record"),
                         self.inventory["observed_at_least_once"])
        self.assertEqual(self._said(r"while (\d+) produced none"),
                         self.inventory["with_no_matrix_column"])

    def test_the_flagged_set_and_its_overlap_are_the_published_ones(self):
        self.assertEqual(self._said(r"(\d+) are labelled not_yet_instrumented"),
                         self.inventory["flagged_not_yet_instrumented"])
        self.assertEqual(self._said(r"(\d+) of the 9 do carry a pattern"),
                         len(self.inventory["overlaps"]["not_yet_instrumented_that_still_have_a_pattern"]))
        self.assertEqual(self._said(r"the (\d+) values with neither a pattern nor a flag"),
                         self.inventory["overlaps"]["no_pattern_and_not_flagged"])

    def test_the_paper_says_what_the_subtraction_error_is(self):
        self.assertIn("counts nothing", self.flattened)


if __name__ == "__main__":
    unittest.main()