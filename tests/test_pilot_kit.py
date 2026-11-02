"""Tests for the pilot kit: the slice, the handouts, and the scorer that refuses to over-read them.

The kit exists because the project has one coder and needs two. `tools/make_pilot_packet.py` cuts a
300-proposition slice out of the 6,199-row packet, writes the sheet a stranger would fill in and the two
markdown files that stranger needs; `tools/score_annotation.py --pilot` scores two returned sheets and is
not allowed to open the answer key, because a sample drawn for agreement cannot report precision.

No human has coded anything. Every fixture here is synthetic and written to a temporary directory, so every
agreement figure these tests produce is a property of the scorer's arithmetic, not a claim about coders -- and
the pilot scorer refuses to write its canonical artifact without an explicit `--out` for exactly that reason.
"""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_pilot_packet as mk  # noqa: E402
import score_annotation as sa  # noqa: E402
from prepare_annotation_packet import UNIT_COLUMN, coding_columns, column_cardinalities  # noqa: E402

SLICE = ROOT / "results/pilot_slice.json"
SHEET = ROOT / "results/pilot_packet_coder_view.csv"
CODEBOOK_MD = ROOT / "annotation/PILOT_CODEBOOK.md"
INSTRUCTIONS_MD = ROOT / "annotation/CODER_INSTRUCTIONS.md"
COLUMNS = coding_columns()
CARDINALITY = column_cardinalities()
VOCABULARY = mk.codebook_values_by_dimension()


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def slice_tokens(definition):
    return sorted({token for stratum in definition["strata"].values() for token in stratum["tokens"]})


def synthetic_sheet(tokens, coder_id, blank_dimensions=(), drop=(), add=(), alternate=False):
    """A filled sheet shaped like the real one, with values taken from the codebook so the scorer accepts them.

    `alternate` moves every answer to the other end of its value list, which is how the fixtures get a real
    disagreement instead of two identical sheets reporting kappa = 1 and teaching nothing.
    """
    fields, _ = read_csv(SHEET)
    edge = -1 if alternate else 0
    picked = {}
    for dimension in sorted(COLUMNS):
        if dimension in blank_dimensions:
            continue
        allowed = sorted(VOCABULARY[dimension])
        if CARDINALITY[dimension] == "set":
            picked[COLUMNS[dimension]] = ";".join(sorted({allowed[0], allowed[-1]})) if not alternate \
                else allowed[-1]
        else:
            picked[COLUMNS[dimension]] = allowed[edge]
    rows = []
    for index, token in enumerate(tokens):
        row = {name: "" for name in fields}
        row["token"] = token
        row["proposition_text"] = f"synthetic proposition {index}"
        row["coder_id"] = coder_id
        row["coding_date"] = "2026-11-02"
        for column in mk.REQUIRED_COLUMNS:
            row[column] = sorted(VOCABULARY[column])[edge]
        row.update(picked)
        rows.append(row)
    for token in drop:
        rows = [row for row in rows if row["token"] != token]
    for token in add:
        extra = dict(rows[0])
        extra["token"] = token
        rows.append(extra)
    return fields, rows


def write_sheet(directory, name, fields, rows):
    path = Path(directory) / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_pilot(args, cwd=ROOT):
    return subprocess.run([sys.executable, "tools/score_annotation.py", *args],
                          cwd=str(cwd), capture_output=True, text=True)


class TheSliceIsWhatTheSeedSays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = json.loads(SLICE.read_text(encoding="utf-8"))
        cls.fields, cls.sheet_rows = read_csv(SHEET)
        cls.packet_fields, cls.packet_rows = read_csv(ROOT / "results/annotation_packet_coder_view.csv")
        cls.token_to_packet_row = {row["token"]: row for row in cls.packet_rows}

    def test_the_committed_files_are_what_the_builder_produces(self):
        fields, rows, definition = mk.build()
        rendered = mk.render_all(fields, rows, definition)
        for path, payload in rendered.items():
            self.assertEqual(Path(path).read_bytes(), payload,
                             f"{path.name} on disk is not what the builder renders; re-run "
                             "python tools/make_pilot_packet.py or fix the drift, do not leave two versions")

    def test_the_draw_survives_a_different_hash_seed(self):
        script = ("import sys, hashlib; sys.path.insert(0, 'tools'); import make_pilot_packet as mk; "
                  "f, r, d = mk.build(); "
                  "print(hashlib.sha256(mk.render_all(f, r, d)[mk.OUT_SHEET]).hexdigest())")
        for seed in ("0", "1", "7", "12345"):
            result = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT), capture_output=True,
                                    text=True, env={"PYTHONHASHSEED": seed, "SYSTEMROOT": str(Path(sys.prefix).drive)})
            self.assertEqual(result.returncode, 0, result.stderr[-500:])
            self.assertEqual(result.stdout.strip(),
                             hashlib.sha256(SHEET.read_bytes()).hexdigest(),
                             f"the slice moved under PYTHONHASHSEED={seed}, so a stratum is being iterated "
                             "as a set")

    def test_the_packet_strata_all_survive_the_cut(self):
        strata = self.definition["strata"]
        self.assertEqual(sum(row["allocated"] for row in strata.values()), self.definition["pilot_rows"])
        self.assertEqual(sorted(strata), sorted(self.definition["role_names_in_packet"]))
        for role, row in strata.items():
            self.assertGreater(row["allocated"], 0, f"{role} vanished from the pilot")
            self.assertEqual(len(row["tokens"]), row["allocated"])
            self.assertAlmostEqual(row["sampling_weight"], row["packet_rows"] / row["allocated"], places=6)

    def test_the_three_strata_are_disjoint_and_inside_the_packet(self):
        tokens = slice_tokens(self.definition)
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual(len(tokens), self.definition["pilot_rows"])
        for token in tokens:
            self.assertIn(token, self.token_to_packet_row, f"{token} is in the slice but not the packet")

    def test_the_sheet_is_the_packet_rows_unchanged_and_blanked(self):
        self.assertEqual(self.fields, self.packet_fields)
        self.assertEqual(len(self.sheet_rows), self.definition["pilot_rows"])
        for row in self.sheet_rows:
            original = self.token_to_packet_row[row["token"]]
            for name in ("proposition_text", "context_window_text", "locator_work", "locator_passage"):
                self.assertEqual(row[name], original[name], f"{row['token']} differs from the packet in {name}")
            for column in list(COLUMNS.values()) + list(mk.REQUIRED_COLUMNS):
                self.assertEqual(row[column], "",
                                 f"{column} is not blank, so the sheet would leak the machine's answer")

    def test_the_sheet_keeps_the_packets_shuffle_rather_than_a_stratum_order(self):
        packet_position = {row["token"]: index for index, row in enumerate(self.packet_rows)}
        positions = [packet_position[row["token"]] for row in self.sheet_rows]
        self.assertEqual(positions, sorted(positions),
                         "the pilot sheet reordered itself, so the row order is a second thing to reproduce")

    def test_the_derivation_hashes_the_files_it_handed_out_and_not_itself(self):
        for name, entry in self.definition["distributed_files"].items():
            path = ROOT / name
            self.assertTrue(path.exists(), f"{name} is hashed in the derivation but absent from the tree")
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(entry["bytes"], path.stat().st_size)
        self.assertNotIn(SLICE.name, self.definition["distributed_files"],
                         "the derivation claims to hash itself, which is a number no file can carry")

    def test_the_derivation_records_that_nobody_has_coded(self):
        self.assertEqual(self.definition["status"], "pilot_prepared_not_coded")
        self.assertEqual(self.definition["coders_who_have_returned_sheets"], [])
        self.assertEqual(self.definition["seed"], mk.DEFAULT_SEED)
        self.assertEqual(self.definition["source_files"]["packet"]["sha256"],
                         hashlib.sha256((ROOT / "results/annotation_packet_coder_view.csv").read_bytes()).hexdigest(),
                         "the packet changed under the slice, so the pilot is a sample of a different frame")

    def test_the_frame_counts_the_codebooks_two_vocabularies_separately(self):
        dimension_rows, fixed_rows = mk.codebook_partition()
        self.assertEqual(len(dimension_rows), self.definition["dimension_values_in_frame"])
        self.assertEqual(len(fixed_rows), self.definition["fixed_question_answers_in_frame"])
        self.assertEqual(self.definition["dimension_values_in_frame"], 93)
        self.assertEqual(self.definition["dimensions_in_frame"], len(COLUMNS))
        self.assertEqual(self.definition["judgments_per_row"],
                         self.definition["dimensions_in_frame"] + len(mk.REQUIRED_COLUMNS))
        self.assertEqual(self.definition["judgments_total"],
                         self.definition["pilot_rows"] * self.definition["judgments_per_row"])

    def test_a_slice_that_loses_a_stratum_refuses_to_build(self):
        with self.assertRaises(SystemExit) as caught:
            mk.build(size=3)
        self.assertIn("the strata have to survive", str(caught.exception))


class TheHandoutsAreGeneratedNotTyped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codebook_md = CODEBOOK_MD.read_text(encoding="utf-8")
        cls.instructions_md = INSTRUCTIONS_MD.read_text(encoding="utf-8")
        cls.definition = json.loads(SLICE.read_text(encoding="utf-8"))

    def test_check_reports_the_tree_current(self):
        result = subprocess.run([sys.executable, "tools/make_pilot_packet.py", "--check"], cwd=str(ROOT),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "current")

    def test_every_codebook_value_appears_in_the_handout(self):
        missing = [f"{dimension}={value}" for dimension, values in sorted(VOCABULARY.items())
                   if dimension in COLUMNS for value in sorted(values)
                   if f"`{value}`" not in self.codebook_md]
        self.assertEqual(missing, [], f"the coder handout dropped these values: {missing}")

    def test_the_handout_does_not_call_the_coders_answers_frame_values(self):
        total_rows = self.definition["dimension_values_in_frame"] + self.definition["fixed_question_answers_in_frame"]
        self.assertIn(f"{self.definition['dimension_values_in_frame']} values", self.codebook_md)
        self.assertNotIn(f"{total_rows} values", self.codebook_md,
                         "the handout counted the three coder questions' answers as frame values, which is how "
                         "a 93-value vocabulary gets published as 107")

    def test_the_instructions_quote_machine_numbers_and_no_others(self):
        for phrase in (f"{self.definition['pilot_rows']} rows",
                       f"{self.definition['judgments_total']}",
                       f"seed {self.definition['seed']}",
                       f"{self.definition['packet_rows']}"):
            self.assertIn(phrase, self.instructions_md, f"the instructions no longer print {phrase}")
        self.assertIn("never opens the machine's answer key", self.instructions_md)
        self.assertIn("Nobody has returned a sheet", self.instructions_md)

    def test_the_instructions_teach_the_rule_that_makes_agreement_mean_something(self):
        for phrase in ("Two people code this independently", "do not look at the other",
                       "Empty means none applies", "undecidable"):
            self.assertIn(phrase, self.instructions_md, f"the independence rule lost {phrase}")

    def test_the_markdown_is_stored_the_way_the_repo_stores_markdown(self):
        for path in (CODEBOOK_MD, INSTRUCTIONS_MD):
            raw = Path(path).read_bytes()
            self.assertGreater(raw.count(b"\r\n"), 10)
            self.assertEqual(raw.count(b"\n") - raw.count(b"\r\n"), 0, f"{path.name} mixes line endings")


class ThePilotScorerRefusesWhatItCannotSupport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = json.loads(SLICE.read_text(encoding="utf-8"))
        cls.tokens = slice_tokens(cls.definition)

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def sheet(self, name, **kwargs):
        fields, rows = synthetic_sheet(self.tokens, **kwargs)
        return write_sheet(self.dir, name, fields, rows)

    def two_sheets(self):
        """Two sheets that disagree, because two identical sheets would score kappa 1 and prove nothing."""
        return (self.sheet("a.csv", coder_id="coder-alpha"),
                self.sheet("b.csv", coder_id="coder-beta", alternate=True))

    def test_a_finished_pair_reports_agreement_and_nothing_else(self):
        a, b = self.two_sheets()
        out = self.dir / "pilot.json"
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(out)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-800:])
        artifact = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "pilot_agreement_only")
        self.assertFalse(artifact["machine_key_was_read"])
        self.assertEqual(artifact["rows_compared"], len(self.tokens))
        self.assertEqual(set(artifact["single_valued_dimensions"]) | set(artifact["set_valued_dimensions"]),
                         set(COLUMNS), "a dimension in the frame is missing from the pilot report")
        self.assertEqual(len(artifact["single_valued_dimensions"]) + len(artifact["set_valued_dimensions"]),
                         len(COLUMNS))
        below_one = [row["cohen_kappa"] for row in artifact["single_valued_dimensions"].values()
                     if row["cohen_kappa"] is not None and row["cohen_kappa"] < 1]
        self.assertTrue(below_one,
                        "two sheets that disagree produced no kappa below 1, so the fixture is not testing "
                        "the arithmetic")
        text = json.dumps(artifact)
        self.assertNotIn("detector_recall", text)
        names = []

        def walk(node):
            if isinstance(node, dict):
                names.extend(node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(artifact)
        offenders = sorted({name for name in names if "recall" in name or "precision" in name})
        self.assertEqual(offenders, [],
                         "the pilot artifact carries an estimator field, which means it read the key it was "
                         "told not to open")
        self.assertIn("a precision estimate for any value", artifact["what_it_cannot_support"][0])

    def test_the_two_sheets_have_to_be_two_people(self):
        a = self.sheet("a.csv", coder_id="coder-alpha")
        b = self.sheet("b.csv", coder_id="coder-alpha")
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("one person coding twice", result.stderr + result.stdout)

    def test_a_sheet_that_is_not_the_slice_is_refused(self):
        a = self.sheet("a.csv", coder_id="coder-alpha")
        b = self.sheet("b.csv", coder_id="coder-beta", drop=[self.tokens[0]])
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the published slice", result.stderr + result.stdout)

    def test_an_extra_row_is_refused_as_harder_than_a_missing_one(self):
        a = self.sheet("a.csv", coder_id="coder-alpha")
        b = self.sheet("b.csv", coder_id="coder-beta", add=["deadbeefdead"])
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the published slice", result.stderr + result.stdout)

    def test_a_value_that_is_not_on_the_frame_is_refused_not_invented(self):
        fields, rows = synthetic_sheet(self.tokens, "coder-beta")
        rows[0][COLUMNS["D1_ontological_category"]] = "supreme_being;the_one_who_is_not"
        b = write_sheet(self.dir, "b.csv", fields, rows)
        a = self.sheet("a.csv", coder_id="coder-alpha")
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not on the frame's lists", result.stderr + result.stdout)

    def test_a_required_column_left_empty_is_an_unfinished_sheet(self):
        fields, rows = synthetic_sheet(self.tokens, "coder-beta")
        for row in rows[:5]:
            row[UNIT_COLUMN] = ""
        b = write_sheet(self.dir, "b.csv", fields, rows)
        a = self.sheet("a.csv", coder_id="coder-alpha")
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("an unfinished sheet", result.stderr + result.stdout)

    def test_the_key_and_the_attestations_are_refused_on_the_pilot_path(self):
        a, b = self.two_sheets()
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json"),
                            "--key", str(ROOT / "results/annotation_packet_key.jsonl")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--pilot refuses --key", result.stderr + result.stdout)

    def test_the_canonical_file_is_written_only_when_the_run_says_so(self):
        a, b = self.two_sheets()
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an explicit --out", result.stderr + result.stdout)
        self.assertFalse(sa.PILOT_OUT.exists(),
                         "a synthetic run wrote the canonical pilot artifact")

    def test_a_dimension_nobody_coded_does_not_report_perfect_agreement(self):
        blank = [name for name in sorted(COLUMNS) if CARDINALITY[name] == "set"]
        a = self.sheet("a.csv", coder_id="coder-alpha", blank_dimensions=blank)
        fields, rows = synthetic_sheet(self.tokens, "coder-beta", blank_dimensions=blank)
        b = write_sheet(self.dir, "b.csv", fields, rows)
        out = self.dir / "pilot.json"
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(out)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-800:])
        artifact = json.loads(out.read_text(encoding="utf-8"))
        for name in blank:
            block = artifact["set_valued_dimensions"][name]
            self.assertEqual(block["rows_where_either_reader_coded"], 0)
            self.assertIsNone(block["mean_jaccard_on_coded_rows"],
                              "an all-blank column scored as 1.0 agreement, which is the trap the anomaly "
                              "scan found on the machine side")
            self.assertIn("neither_reader_used_this_column", block["flag"])
            self.assertEqual(block["rows_both_left_blank"], len(self.tokens))

    def test_the_agreement_it_reports_is_the_statistic_the_frame_declares(self):
        a, b = self.two_sheets()
        out = self.dir / "pilot.json"
        self.assertEqual(run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(out)]).returncode, 0)
        artifact = json.loads(out.read_text(encoding="utf-8"))
        for name in artifact["single_valued_dimensions"]:
            self.assertEqual(CARDINALITY[name], "single")
            self.assertIn("cohen_kappa over rows", artifact["single_valued_dimensions"][name]["statistic"])
        for name in artifact["set_valued_dimensions"]:
            self.assertEqual(CARDINALITY[name], "set")
            self.assertIn("mean Jaccard over rows", artifact["set_valued_dimensions"][name]["statistic"])
        self.assertEqual(artifact["headline"]["single_valued_dimensions_in_frame"],
                         sum(1 for name, value in CARDINALITY.items() if value == "single"))

    def test_a_slice_file_that_does_not_exist_stops_the_run(self):
        a, b = self.two_sheets()
        result = run_pilot(["--pilot", "--coder-a", str(a), "--coder-b", str(b), "--out", str(self.dir / "o.json"),
                            "--slice", str(self.dir / "nope.json")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist, so there is no pilot to score", result.stderr + result.stdout)


class ThePaperQuotesThePilot(unittest.TestCase):
    """Every figure the paper's pilot subsection prints is re-derived here, because no number is typed by hand."""

    @classmethod
    def setUpClass(cls):
        cls.definition = json.loads(SLICE.read_text(encoding="utf-8"))
        cls.plan = json.loads((ROOT / "results/annotation_sampling_plan.json").read_text(encoding="utf-8"))
        cls.tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
        cls.flat = " ".join(cls.tex.split())

    def escaped(self, name):
        return name.replace("_", "\\_")

    def test_the_table_rows_are_the_strata_in_the_derivation(self):
        roles = self.definition["strata"]
        self.assertEqual(len(roles), 3, "the pilot changed strata and the paper still prints three")
        for role, row in roles.items():
            expected = rf"\texttt{{{self.escaped(role)}}} & {row['packet_rows']} & {row['allocated']} & " \
                       rf"{row['sampling_weight']:.4f} \\"
            self.assertIn(expected, self.tex,
                          f"the paper's table no longer states {role} as {row['allocated']} rows of "
                          f"{row['packet_rows']} at weight {row['sampling_weight']:.4f}")

    def test_the_table_total_is_the_packet_and_the_slice(self):
        d = self.definition
        expected = rf"\textbf{{total}} & \textbf{{{d['packet_rows']}}} & \textbf{{{d['pilot_rows']}}} & \\"
        self.assertIn(expected, self.tex)
        self.assertEqual(d["pilot_rows"], len(slice_tokens(d)),
                         "the derivation's row count and its token list disagree")

    def test_the_prose_figures_match_the_derivation(self):
        d = self.definition
        for phrase in (
            f"One row asks \\({d['judgments_per_row']}\\) answers",
            f"so the pilot asks \\({d['judgments_total']}\\) of them",
            f"against \\({d['packet_judgments_per_coder']}\\) for the full",
            f"carries \\({d['dimension_values_in_frame']}\\) dimension values",
            f"and \\({d['fixed_question_answers_in_frame']}\\)",
            f"a {d['pilot_rows']}-row slice",
            "the twelve dimension columns",
        ):
            self.assertIn(phrase, self.flat, f"the paper no longer prints {phrase!r}")
        self.assertEqual(d["judgments_per_row"], d["dimensions_in_frame"] + len(mk.REQUIRED_COLUMNS))
        self.assertEqual(d["judgments_total"], d["judgments_per_row"] * d["pilot_rows"])
        self.assertEqual(d["dimensions_in_frame"], 12, "the frame changed and 'twelve' in the prose did not")
        self.assertEqual(d["packet_judgments_per_coder"],
                         self.plan["sizing"]["judgments_per_coder"],
                         "the pilot derivation and the packet derivation disagree about the full packet")
        self.assertEqual(d["packet_rows"], len(mk.read_rows(mk.PACKET)[1]),
                         "the paper prints a packet size that is not the packet's size")

    def test_the_refusals_the_paper_describes_are_the_refusals_the_scorer_makes(self):
        scorer = (ROOT / "tools/score_annotation.py").read_text(encoding="utf-8")
        for quoted, literal in ((r"\texttt{-{}-key}", "--key"),
                                (r"\texttt{-{}-attestations}", "--attestations"),
                                (r"neither\_reader\_used\_this\_column", "neither_reader_used_this_column")):
            self.assertIn(quoted, self.tex, f"the paper stopped printing {quoted}")
            self.assertIn(literal, scorer, f"the scorer no longer names {literal}, so the paper describes a refusal "
                                           "that does not exist")

    def test_the_named_files_exist_and_are_cited(self):
        for name in ("tools/make_pilot_packet.py", "results/pilot_slice.json",
                     "annotation/PILOT_CODEBOOK.md", "annotation/CODER_INSTRUCTIONS.md",
                     "results/pilot_packet_coder_view.csv", "results/annotation_codebook.csv"):
            self.assertTrue((ROOT / name).exists(), f"the paper cites {name}, which is not in the tree")
        for citation in (r"tools/make\_pilot\_packet.py", r"tools/score\_annotation.py --pilot",
                         r"results/pilot\_slice.json", r"annotation/PILOT\_CODEBOOK.md",
                         r"annotation/CODER\_INSTRUCTIONS.md", r"results/annotation\_codebook.csv",
                         r"Table~\ref{tab:pilot}", r"\label{sec:pilot}", r"\label{tab:pilot}"):
            self.assertIn(citation, self.tex, f"the paper stopped citing {citation}")

    def test_the_paper_says_no_one_has_coded(self):
        self.assertIn("as of this build nobody has returned a sheet", self.flat.lower())
        self.assertIn("pilot\\_prepared\\_not\\_coded", self.tex)
        self.assertEqual(self.definition["status"], "pilot_prepared_not_coded")
        self.assertEqual(self.definition["coders_who_have_returned_sheets"], [])


if __name__ == "__main__":
    unittest.main()
