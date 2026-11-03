"""Every artifact digest the documentation prints is recomputed here from the file or field it names.

**Why this file exists.** `TRACK_B_METHOD_v2.md` prints three full SHA-256 digests and `TEST_REPORT.md` prints
fifteen abbreviated ones. Section 6.7 of the methodology claims the mechanism that keeps those numbers honest
is that the chance table's hash "is printed inside the verdict rather than beside it in prose" — but the verdict
was stdout-only, so no file in the repository carried it, and no test read the printed literals at all. A
digest quoted in prose is a claim about bytes: when `tools/narrative_similarity.py` is edited, the `engine
code` digest in §9 of the report is wrong, and the only thing that noticed was a reader who happened to hash
the file by hand. That reader is the resource this project has already been told it does not have.

**What it does not do.** It does not check that a documented digest is *fresh* relative to its input — that is
what the `code_sha256` stamps inside the run summaries and `tests/test_pipeline.py` are for. This module owns
the narrower property: the numbers the prose prints are the numbers the shipped artifacts carry, and the
verdict on disk embeds the hash of the chance table that is on disk, which is only true if the published
sequence ran the anomaly scan before the comparison.
"""

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

DOC_FILES = ("TRACK_B_METHOD_v2.md", "TEST_REPORT.md", "RESEARCH_PROTOCOL.md", "ARCHITECTURE.md",
             "README.md", "paper/main.tex")
DIGEST = re.compile(r"\b[0-9a-f]{64}\b")
ABBREVIATED = re.compile(r"`([0-9a-f]{8})…`")

# Files whose bytes are evidence rather than prose: the inventory a printed digest has to be found in.
EVIDENCE_DIRECTORIES = ("results", "config")
EVIDENCE_FILES = ("corpus/acquisition_manifest.json",)

# Each abbreviated digest the report prints: the text that sits immediately in front of it, and where the full
# value lives. A `field` source is a dotted path inside a tracked artifact; a `file` source is the digest of
# that file's own bytes, which is what a report prints when it says a file came out byte-identical.
FIELD, FILE = "field", "file"
DOCUMENTED_ABBREVIATIONS = (
    ("passages", FIELD, "results/v2_run_summary.json", "reproducibility.passages_sha256"),
    ("acquisition manifest", FIELD, "results/v2_run_summary.json",
     "reproducibility.acquisition_manifest_sha256"),
    ("source dependence", FIELD, "results/v2_run_summary.json", "reproducibility.source_dependence_sha256"),
    ("motif lexicon", FIELD, "results/v2_run_summary.json", "reproducibility.motif_lexicon_sha256"),
    ("retrieval code", FIELD, "results/v2_run_summary.json", "reproducibility.analysis_code_sha256"),
    ("annotations", FIELD, "results/narrative_run_summary.json", "reproducibility.annotations_sha256"),
    ("engine code", FIELD, "results/narrative_run_summary.json", "reproducibility.code_sha256"),
    ("narrative pair set", FIELD, "results/v2_relevance_graph.json", "reproducibility.narrative_pairs_sha256"),
    ("candidate set", FIELD, "results/v2_relevance_graph.json", "reproducibility.candidate_pairs_sha256"),
    ("`results/v2_candidate_pairs.jsonl` byte-for-byte (SHA-256", FIELD, "results/v2_relevance_graph.json",
     "reproducibility.candidate_pairs_sha256"),
    ("`corpus/derived/passages_v2.jsonl` unchanged at", FIELD, "results/v2_run_summary.json",
     "reproducibility.passages_sha256"),
    ("`results/model_power_simulation.json` is byte-identical after the change (SHA-256", FILE,
     "results/model_power_simulation.json", None),
    ("`results/pilot_packet_coder_view.csv`", FILE, "results/pilot_packet_coder_view.csv", None),
    ("`annotation/PILOT_CODEBOOK.md`", FILE, "annotation/PILOT_CODEBOOK.md", None),
    ("`annotation/CODER_INSTRUCTIONS.md`", FILE, "annotation/CODER_INSTRUCTIONS.md", None),
)
GAP = r"[\s\S]{0,120}?"
TOKEN = r"`([0-9a-f]{8})…`"
SIZE = r"(?:,\s*([0-9,]{1,15})\s*bytes)?"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digests_inside(data, prefix=""):
    """Every 64-hex string recorded inside an artifact, keyed by where it sits."""
    found = {}
    if isinstance(data, dict):
        for key, value in data.items():
            found.update(digests_inside(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found.update(digests_inside(value, f"{prefix}[{index}]"))
    elif isinstance(data, str) and DIGEST.fullmatch(data):
        found[prefix] = data
    return found


def evidence_inventory():
    """Digests of shipped files, plus digests those files record about their own inputs."""
    inventory = {}
    paths = [ROOT / name for name in EVIDENCE_FILES]
    for directory in EVIDENCE_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file():
                paths.append(path)
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        inventory[digest(path)] = f"sha256 of {relative}"
        if path.suffix == ".json":
            try:
                document = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            for where, value in digests_inside(document).items():
                inventory.setdefault(value, f"{relative} → {where}")
    return inventory


def documented_field(artifact, field):
    document = json.loads((ROOT / artifact).read_text(encoding="utf-8-sig"))
    value = document
    for part in field.split("."):
        value = value[part]
    return value


def chance_table_hashes(verdict):
    """Every `chance_similarity_table.sha256` the verdict carries, however deeply it is nested."""
    found = []
    stack = [verdict]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            table = node.get("chance_similarity_table")
            if isinstance(table, dict) and table.get("sha256"):
                found.append((node, table))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


class PrintedDigestsAreRealDigestsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = evidence_inventory()
        cls.documents = {name: (ROOT / name).read_text(encoding="utf-8") for name in DOC_FILES}

    def test_every_full_digest_the_documents_print_names_a_shipped_artifact(self):
        import compare_models as cm
        registered = cm.load_config()["preregistration"]["mechanism"]["operator_cost_table_sha256"]
        computed = cm.operator_cost_table_sha256(cm.load_config())
        self.inventory.setdefault(registered, "config preregistration.mechanism.operator_cost_table_sha256")
        self.inventory.setdefault(computed, "compare_models.operator_cost_table_sha256 of the registered table")
        problems = []
        for name, text in self.documents.items():
            for line in text.splitlines():
                for value in DIGEST.findall(line):
                    if value not in self.inventory:
                        problems.append(f"{name}: {value} is printed but is the digest of nothing shipped")
        self.assertEqual(problems, [])

    def test_the_three_digests_the_methodology_prints_are_the_three_it_claims(self):
        import compare_models as cm
        text = self.documents["TRACK_B_METHOD_v2.md"]
        self.assertIn(cm.operator_cost_table_sha256(cm.load_config()), text,
                      "§6.7 no longer prints the hash of the table the config registers")
        self.assertIn(digest(ROOT / "results/dimension_anomalies.json"), text,
                      "§6.8 no longer prints the digest of the chance table now on disk")
        self.assertIn(digest(ROOT / "results/model_power_simulation.json"), text,
                      "§6.8 no longer prints the digest of the published power simulation")


class VerdictCarriesItsChanceTableTests(unittest.TestCase):
    VERDICT = ROOT / "results/track_b_verdict.json"

    def setUp(self):
        if not self.VERDICT.exists():
            self.fail("results/track_b_verdict.json is not published. The reproduction sequence runs "
                      "`python tools/compare_models.py --corpus-pairs --write-to results/track_b_verdict.json` "
                      "after `python tools/scan_dimension_anomalies.py --write`, because the verdict embeds the "
                      "digest of the chance table it read and the methodology cites that embedding.")

    def test_the_verdict_embeds_the_digest_of_the_chance_table_shipped_beside_it(self):
        verdict = json.loads(self.VERDICT.read_text(encoding="utf-8-sig"))
        tables = chance_table_hashes(verdict)
        self.assertTrue(tables, "the published verdict carries no chance table, so the block-profile "
                                "readings are raw-similarity only and §6.8's claim needs rewording")
        expected = digest(ROOT / "results/dimension_anomalies.json")
        for _, table in tables:
            self.assertEqual(table["sha256"], expected,
                             "the verdict read a different chance table than the one published; run the "
                             "anomaly scan before the comparison, not after")
            self.assertEqual(table["path"], "results/dimension_anomalies.json")

    def test_the_verdict_reports_both_scales_of_the_block_profile(self):
        verdict = json.loads(self.VERDICT.read_text(encoding="utf-8-sig"))
        tables = chance_table_hashes(verdict)
        used = [table for _, table in tables if table.get("used")]
        self.assertTrue(used, "no chance-corrected reading was produced, so the reversal §6.8 reports "
                              "on the raw scale has no counterpart on the corrected scale")
        for _, table in tables:
            self.assertIsInstance(table["dimensions_supplied"], int)
            self.assertTrue(table.get("conditioning"), "the corrected reading does not say what it "
                                                      "conditions on, so a reader cannot tell which "
                                                      "null it was drawn against")

    def test_the_verdict_states_its_own_status_rather_than_leaving_it_to_be_guessed(self):
        verdict = json.loads(self.VERDICT.read_text(encoding="utf-8-sig"))
        self.assertIn("status", verdict)
        self.assertTrue(verdict.get("interpretation"), "a verdict with no interpretation invites a reader "
                                                      "to supply one")


class PrintedBlockProfileNumbersTests(unittest.TestCase):
    """The block means and adjacency gaps the methodology prints are read back out of the published verdict.

    These are the numbers that used to exist only on a terminal: the gate ran, its figures were transcribed into
    `TRACK_B_METHOD_v2.md` and into the paper's data-availability row, and nothing on disk could be compared
    against the transcription. The verdict is published now, so a figure that drifts away from the artifact -- or
    an artifact that drifts away from the figure -- fails here instead of in a reader's rerun.
    """

    VERDICT = ROOT / "results/track_b_verdict.json"
    SCAN = ROOT / "results/dimension_anomalies.json"

    def setUp(self):
        if not self.VERDICT.exists():
            self.fail("results/track_b_verdict.json is not published, so no artifact holds the block-profile "
                      "figures the documents print")
        verdict = json.loads(self.VERDICT.read_text(encoding="utf-8-sig"))
        gate = verdict.get("m4_block_profile_gate")
        self.assertIsNotNone(gate, "the published verdict carries no M4 block-profile gate, which means the "
                                   "figures in TRACK_B_METHOD_v2.md 6.8 and the paper's Models row come from a "
                                   "run that was never published")
        self.reading = gate["reading"]

    def printed(self, name, value):
        return (name, json.dumps(value), value)

    def test_the_gate_ran_on_the_pair_population_the_chance_table_was_drawn_on(self):
        scan = json.loads(self.SCAN.read_text(encoding="utf-8-sig"))
        self.assertEqual(self.reading["pairs"], scan["pair_graph"]["pairs_scorable"],
                         "the gate scores a different number of pairs than the scan drew its chance line over, "
                         "so the corrected reading is a subtraction of two populations")
        self.assertEqual(self.reading["pairs_carrying_a_block_profile"], self.reading["pairs"],
                         "some scored pairs carry no block profile, so the pooled block means are means over a "
                         "subset the published figure does not name")

    def test_every_block_mean_the_documents_print_is_the_verdict_s_own(self):
        documents = ("TRACK_B_METHOD_v2.md", "paper/main.tex")
        prose = {name: (ROOT / name).read_text(encoding="utf-8") for name in documents}
        missing = []
        for scale, means in self.reading["readings"].items():
            for block, value in means["block_means"].items():
                for name, text in prose.items():
                    if json.dumps(value) not in text:
                        missing.append(f"{name} does not print the {scale} mean of {block} ({value})")
        self.assertEqual(missing, [], "printed block means no longer match the published verdict: "
                                      f"{missing}")

    def test_the_adjacency_gaps_the_methodology_prints_are_the_verdict_s_own(self):
        text = (ROOT / "TRACK_B_METHOD_v2.md").read_text(encoding="utf-8")
        missing = [f"{scale}/{item['stronger']}->{item['weaker']} = {item['observed_difference']}"
                   for scale, row in self.reading["readings"].items()
                   for item in row["adjacent_predictions"]
                   if item["verdict"] != "holds" and json.dumps(item["observed_difference"]) not in text]
        self.assertEqual(missing, [],
                         "TRACK_B_METHOD_v2.md does not quote these adjacency gaps from the published verdict: "
                         f"{missing}")
        self.assertIn(self.reading["status"], text,
                      "the methodology no longer prints the gate's own status beside the numbers")

    def test_the_status_and_pair_count_the_paper_prints_are_the_gate_s_own(self):
        text = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
        self.assertIn(self.reading["status"].replace("_", r"\_"), text,
                      "the paper no longer prints the gate's own status, so the straddle it describes is "
                      "attributable to nothing")
        self.assertIn(f"\\({self.reading['pairs']}\\)", text,
                      f"the paper's Models row does not print the {self.reading['pairs']} pairs the gate ran on")

    def test_the_paper_prose_restates_the_corrected_adjacency_at_its_own_rounding(self):
        """The abstract, the finding and the Models section each write the tie to three places.

        The block means are pinned to six decimals above, but a sentence that says "reverses on raw similarity
        and ties at X" is a copy of the same quantity, and this audit has already collected one abstract that
        kept quoting a superseded value after the artifact moved. Both renderings are therefore read back out of
        the published verdict rather than compared with each other.
        """
        flat = " ".join((ROOT / "paper/main.tex").read_text(encoding="utf-8").split())
        adjacency = next(item for item in self.reading["readings"]["excess_over_chance"]["adjacent_predictions"]
                         if item["stronger"] == "structural"
                         and item["weaker"] == "arbitrary_or_expressive")["observed_difference"]
        self.assertIn(f"raw against \\({adjacency:+.3f}\\) corrected", flat,
                      f"the Models section does not print the verdict's structural->arbitrary gap ({adjacency})")
        self.assertIn(f"base rate is subtracted (\\({adjacency:.3f}\\))", flat,
                      f"the abstract does not print the verdict's structural->arbitrary gap ({adjacency})")


class PrintedAbbreviationsTests(unittest.TestCase):
    """The report's eight-hex digests, each traced to the artifact field or file bytes it claims to abbreviate."""

    @classmethod
    def setUpClass(cls):
        cls.prose = {name: (ROOT / name).read_text(encoding="utf-8") for name in DOC_FILES}

    def expected(self, kind, artifact, field):
        if kind == FILE:
            return digest(ROOT / artifact)
        return documented_field(artifact, field)

    def test_every_abbreviated_digest_matches_the_digest_it_abbreviates(self):
        problems = []
        for before, kind, artifact, field in DOCUMENTED_ABBREVIATIONS:
            pattern = re.compile(re.escape(before) + GAP + TOKEN + SIZE)
            hits = []
            for name, text in self.prose.items():
                for match in pattern.finditer(text):
                    hits.append((name, match))
            self.assertTrue(hits, f"the report no longer prints a digest after `{before}`, so "
                                  f"DOCUMENTED_ABBREVIATIONS names a sentence that is gone")
            expected = self.expected(kind, artifact, field)
            for name, match in hits:
                where = f"{name}: after `{before[:48]}`"
                if match.group(1) != expected[:8]:
                    problems.append(f"{where} prints {match.group(1)}… but {artifact}"
                                    + (f" → {field}" if field else " bytes") + f" is {expected[:8]}…")
                if match.group(2):
                    printed = int(match.group(2).replace(",", ""))
                    actual = (ROOT / artifact).stat().st_size
                    if printed != actual:
                        problems.append(f"{where} prints {printed:,} bytes but {artifact} is {actual:,} bytes")
        self.assertEqual(problems, [])

    def test_the_documents_print_no_abbreviated_digest_this_module_has_not_traced(self):
        claimed = {self.expected(kind, artifact, field)[:8]
                   for before, kind, artifact, field in DOCUMENTED_ABBREVIATIONS}
        unexplained = []
        for name, text in self.prose.items():
            for value in ABBREVIATED.findall(text):
                if value not in claimed:
                    unexplained.append(f"{name}: {value}…")
        self.assertEqual(unexplained, [], "a documented digest with no declared source; add it to "
                                         "DOCUMENTED_ABBREVIATIONS with the artifact field or file that "
                                         "carries it")


if __name__ == "__main__":
    unittest.main()
