"""Tests for the exact inverted-index graph layer and the recall measurement of the blocking it replaced.

These tests check the claims that make the published counts meaningful: the recall figures must be ratios of
two published counts inside [0, 1] and must say which population they were measured on; the measured subset
must be a real deterministic subset of live-state passages; exact and LSH comparisons must run through the
graph builder's own functions; bucket-cap loss must be reported separately from banding loss and add up, in
both the subset and the corpus-wide form; the candidate set must be complete for the relation it defines,
which means every displayed edge shares a live state and the shipped index regenerates the published pair
count; the edge file must be labelled a display slice and never read as a bound; the gzip artifacts must
carry no per-run header fields, so two builds are byte-identical; the graph artifact must no longer claim
`sampling: NONE`; and the inheritance layer must stay empty.
"""

import gzip
import itertools
import json
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_ontology_graph as bog  # noqa: E402
import validate_graph_recall as vgr  # noqa: E402


class GraphRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("results/ontology_attestations.jsonl.gz", "results/ontology_graph.json",
                     "results/graph_recall_validation.json", "results/ontology_passage_index.json.gz"):
            if not (ROOT / name).exists():
                raise unittest.SkipTest(f"{name} has not been produced yet")
        cls.recall = json.loads((ROOT / "results/graph_recall_validation.json").read_text(encoding="utf-8"))
        cls.graph = json.loads((ROOT / "results/ontology_graph.json").read_text(encoding="utf-8"))
        cls.records = [json.loads(line)
                       for line in gzip.open(ROOT / "results/ontology_attestations.jsonl.gz", "rt",
                                             encoding="utf-8")]
        cls.per_passage = bog.features_of(cls.records)
        cls.members = {(m["work_id"], m["passage_id"]) for m in cls.recall["subset"]["members"]}
        cls.layer = bog.exact_sharing_layer(cls.per_passage, bog.inverted_index(cls.per_passage),
                                            display_per_work_pair=None)

    def test_recall_is_a_ratio_of_two_published_counts_in_unit_interval(self):
        results = self.recall["results"]
        self.assertIsInstance(results["exact_sharing_pairs"], int)
        self.assertIsInstance(results["recovered_by_lsh"], int)
        self.assertGreater(results["exact_sharing_pairs"], 0)
        self.assertLessEqual(results["recovered_by_lsh"], results["exact_sharing_pairs"])
        expected = results["recovered_by_lsh"] / results["exact_sharing_pairs"]
        self.assertAlmostEqual(results["recall"], round(expected, 6), places=6)
        self.assertGreaterEqual(results["recall"], 0.0)
        self.assertLessEqual(results["recall"], 1.0)

    def test_subset_is_a_deterministic_subset_of_live_state_passages(self):
        self.assertLessEqual(self.members, set(self.per_passage))
        self.assertEqual(len(self.members), self.recall["subset"]["passages_in_subset"])
        recomputed, info = vgr.select_subset(self.per_passage)
        self.assertEqual(self.members, set(recomputed))
        self.assertEqual(sorted(self.members), recomputed)  # whole selection is sorted, no random order
        self.assertEqual(info["strata_nonempty"], self.recall["subset"]["strata_nonempty"])
        self.assertEqual(info["quota"], vgr.QUOTA)
        # whole strata up to the quota are kept complete; larger ones keep the sorted first-K, no sampling
        strata = {}
        for key in self.per_passage:
            strata.setdefault((key[0], vgr.band_of(len(self.per_passage[key]))), []).append(key[1])
        for (work, band_label), passages in strata.items():
            kept = {p for (w, p) in self.members
                    if w == work and vgr.band_of(len(self.per_passage[(w, p)])) == band_label}
            self.assertEqual(kept, set(sorted(passages)[:vgr.QUOTA]), f"stratum {work}/{band_label}")

    def test_exact_and_lsh_comparisons_run_over_the_same_subset_via_the_real_path(self):
        vocabulary = {f for features in self.per_passage.values() for f in features}
        keys, signatures = bog.minhash_signatures(self.per_passage, vocabulary)  # full population, as built
        capped = vgr.subset_pair_set(bog.band_candidates(keys, signatures, bucket_cap=bog.BUCKET_CAP),
                                     self.members)
        exact = vgr.exact_sharing_pairs(sorted(self.members), self.per_passage)
        self.assertEqual(len(exact), self.recall["results"]["exact_sharing_pairs"])
        self.assertEqual(len(exact & capped), self.recall["results"]["recovered_by_lsh"])
        # both sides live inside the one published subset
        self.assertTrue(all(k in self.members for pair in exact for k in pair))
        self.assertTrue(all(k in self.members for pair in capped for k in pair))
        # pair definition equals the layer-3 edge meaning: cross-work, >=1 shared live state
        for pair in itertools.islice(exact, 500):
            (k1, k2) = sorted(pair)
            self.assertNotEqual(k1[0], k2[0])
            self.assertTrue(self.per_passage[k1] & self.per_passage[k2])
        reused = self.recall["reuses_the_graph_builders_own_path"]
        for function_name in reused["functions"]:
            self.assertTrue(hasattr(bog, function_name), f"validator must reuse bog.{function_name}")

    def test_bucket_cap_loss_is_reported_separately_from_banding_loss(self):
        results = self.recall["results"]
        self.assertIn("lost_to_bucket_cap", results)
        self.assertIn("lost_to_banding", results)
        self.assertIsInstance(results["lost_to_bucket_cap"], int)
        self.assertIsInstance(results["lost_to_banding"], int)
        self.assertEqual(results["recovered_by_lsh"] + results["lost_to_bucket_cap"] + results["lost_to_banding"],
                         results["exact_sharing_pairs"])
        self.assertGreaterEqual(results["recall_if_bucket_cap_removed"], results["recall"])
        self.assertEqual(self.recall["parameters"]["bucket_cap"], bog.BUCKET_CAP)
        self.assertEqual(self.recall["parameters"]["seed"], bog.SEED)
        self.assertEqual(self.recall["parameters"]["num_hashes"], bog.NUM_HASHES)
        self.assertEqual(self.recall["parameters"]["bands"], bog.NUM_BANDS)
        # the cap is a production behaviour, not a test artefact: the builder defaults to it
        keys, signatures = bog.minhash_signatures(
            self.per_passage, {f for features in self.per_passage.values() for f in features})
        self.assertLessEqual(
            len(vgr.subset_pair_set(bog.band_candidates(keys, signatures), self.members)),
            len(vgr.subset_pair_set(bog.band_candidates(keys, signatures, bucket_cap=None), self.members)))

    def test_the_corpus_wide_measurement_adds_up_and_uses_the_exact_denominator(self):
        """The subset figure needed a caveat; the corpus-wide one takes its denominator from the index."""
        wide = self.recall["corpus_wide"]
        self.assertEqual(wide["recovered_by_lsh"] + wide["lost_to_bucket_cap"] + wide["lost_to_banding"],
                         wide["exact_distinct_cross_work_pairs"])
        self.assertEqual(wide["recovered_by_lsh"], wide["lsh_candidates_with_bucket_cap"])
        self.assertEqual(wide["lost_to_bucket_cap"], wide["lsh_candidates_bucket_cap_removed"]
                         - wide["lsh_candidates_with_bucket_cap"])
        self.assertEqual(wide["exact_distinct_cross_work_pairs"],
                         self.graph["scale"]["exact_distinct_cross_work_pairs"])
        self.assertEqual(wide["exact_pair_multiplicity_by_feature"],
                         self.graph["scale"]["exact_pair_multiplicity_by_feature"])
        self.assertEqual(wide["work_pairs_connected"], self.graph["scale"]["work_pairs_connected"])
        self.assertAlmostEqual(wide["recall"],
                               round(wide["recovered_by_lsh"] / wide["exact_distinct_cross_work_pairs"], 6),
                               places=6)
        self.assertAlmostEqual(wide["recall_if_bucket_cap_removed"],
                               round(wide["lsh_candidates_bucket_cap_removed"]
                                     / wide["exact_distinct_cross_work_pairs"], 6), places=6)
        self.assertGreater(wide["recall_if_bucket_cap_removed"], wide["recall"])
        # the validator's corpus-wide denominator must come from the builder's own join, uncapped
        reused = self.recall["reuses_the_graph_builders_own_path"]
        self.assertIn("exact_sharing_layer", reused["functions"])
        self.assertIn("inverted_index", reused["functions"])
        self.assertIn("display_per_work_pair=None", json.dumps(reused))

    def test_graph_artifact_no_longer_claims_sampling_none(self):
        self.assertNotIn("sampling", self.graph)
        self.assertNotIn('"sampling": "NONE', json.dumps(self.graph))
        block = self.graph["candidate_generation"]
        self.assertEqual(block["method"], "exact_inverted_index_join")
        self.assertNotIn("approximate_minhash_lsh_banding", json.dumps(block))
        text = json.dumps(block).lower()
        self.assertIn("never_read_as", text)
        self.assertIn("missing edge", text)
        self.assertIn("incomplete", block["coverage_of_anything_beyond_the_relation"].lower())
        self.assertIn(str(self.graph["scale"]["exact_distinct_cross_work_pairs"]),
                      block["coverage_of_the_relation"])
        self.assertEqual(block["superseded_minhash_recall_measured"]["corpus_wide"]["recall"],
                         self.recall["corpus_wide"]["recall"])
        self.assertEqual(block["superseded_minhash_recall_measured"]["subset"]["recall"],
                         self.recall["results"]["recall"])

    def test_the_subset_recall_figure_is_never_published_without_its_population(self):
        """0.023214 was quoted as a corpus property in earlier drafts; it is a 1,632-passage measurement."""
        self.assertIn("recall_scope", self.recall["results"])
        self.assertIn("subset", self.recall["results"]["recall_scope"].lower())
        subset_block = self.graph["candidate_generation"]["superseded_minhash_recall_measured"]["subset"]
        self.assertIn("subset", subset_block["measured_on"].lower())
        self.assertIn("subset", subset_block["always_qualify"].lower())
        wide = self.recall["corpus_wide"]
        self.assertIn("exact_distinct_cross_work_pairs", wide)
        self.assertNotEqual(wide["recall"], self.recall["results"]["recall"])  # the two are not one number

    def test_the_exact_layer_counts_are_complete_and_the_edge_file_is_only_a_slice(self):
        scale = self.graph["scale"]
        exact = scale["exact_distinct_cross_work_pairs"]
        self.assertGreater(exact, 0)
        # the display slice is a subset of the enumeration, never a bound on it
        self.assertLess(scale["passage_pair_edges_written"], exact)
        self.assertTrue(scale["edge_file_is_display_slice"])
        self.assertEqual(scale["display_cap_per_work_pair"], bog.EDGES_DISPLAY_PER_WORK_PAIR)
        layer3 = {layer["name"]: layer for layer in self.graph["layers"]}["3_passage_pair_shared_states"]
        self.assertEqual(layer3["pairs"], exact)
        self.assertEqual(layer3["edges"], scale["passage_pair_edges_written"])
        self.assertEqual(layer3["enumeration"], "exact inverted index join; no blocking approximation remains "
                                                "in this layer")
        # complete counts: every connected work pair's published distinct count sums to `exact`
        published = {f"{edge['left_work']}--{edge['right_work']}": edge["distinct_shared_state_pairs"]
                     for edge in self.graph["edges"]}
        self.assertEqual(sum(published.values()), exact)
        recomputed = {(left, right): distinct
                      for (left, right), (distinct, _, _) in self.layer["pair_counts"].items() if distinct}
        self.assertEqual({f"{left}--{right}": distinct for (left, right), distinct in recomputed.items()},
                         published)

    def test_the_shipped_index_regenerates_the_published_relation_without_this_machine(self):
        """The index is the completeness argument: a reader holding it can rebuild every pair we counted.

        Recomputed here from the shipped JSON with plain set arithmetic, with no scipy and no call into the
        builder's join, so it is an independent check of the published totals rather than a restatement.
        """
        with gzip.open(ROOT / "results/ontology_passage_index.json.gz", "rt", encoding="utf-8") as handle:
            shipped = json.loads(handle.read())
        self.assertEqual(shipped["approximation"], "none: this is the join, not a sketch of it")
        index = {feature: [tuple(key) for key in keys] for feature, keys in shipped["features"].items()}
        self.assertEqual(sorted(index), sorted(bog.inverted_index(self.per_passage)))
        self.assertEqual({tuple(key) for keys in index.values() for key in keys}, set(self.per_passage))

        # whole-corpus multiplicity, from posting work-counts alone: ((sum n)^2 - sum n^2) / 2 per feature
        multiplicity = 0
        for keys in index.values():
            per_work = {}
            for work, _passage in keys:
                per_work[work] = per_work.get(work, 0) + 1
            counts = list(per_work.values())
            multiplicity += (sum(counts) ** 2 - sum(value * value for value in counts)) // 2
        self.assertEqual(multiplicity, self.graph["scale"]["exact_pair_multiplicity_by_feature"])

        # distinct pairs, work pair by work pair so no set larger than one block is ever materialised
        features_by_work = {}
        for feature, keys in index.items():
            for work, passage in keys:
                features_by_work.setdefault(work, {}).setdefault(feature, []).append(passage)
        published = {f"{edge['left_work']}--{edge['right_work']}": edge["distinct_shared_state_pairs"]
                     for edge in self.graph["edges"]}
        ranked = sorted(published, key=lambda key: -published[key])
        checked = ranked[:3] + ranked[len(ranked) // 2:len(ranked) // 2 + 2] + ranked[-2:]
        for identity in checked:
            left_work, right_work = identity.split("--")
            shared_states = set(features_by_work[left_work]) & set(features_by_work[right_work])
            pairs = set()
            for feature in shared_states:
                for left in features_by_work[left_work][feature]:
                    for right in features_by_work[right_work][feature]:
                        pairs.add(frozenset(((left_work, left), (right_work, right))))
            self.assertEqual(len(pairs), published[identity], identity)
        # and a displayed edge's shared_states must be exactly what the index says the two passages share
        features_from_index = {}
        for feature, keys in index.items():
            for work, passage in keys:
                features_from_index.setdefault((work, passage), set()).add(feature)
        self.assertEqual(features_from_index, {key: set(value) for key, value in self.per_passage.items()})
        with gzip.open(ROOT / "results/ontology_passage_pairs.jsonl.gz", "rt", encoding="utf-8") as handle:
            for line in itertools.islice(handle, 50):
                edge = json.loads(line)
                left = (edge["left_work_id"], edge["left_passage_id"])
                right = (edge["right_work_id"], edge["right_passage_id"])
                by_feature = sorted(features_from_index[left] & features_from_index[right])
                self.assertEqual(by_feature, edge["shared_states"])
                self.assertTrue(by_feature)

    def test_gzip_artifacts_carry_no_per_run_header_fields(self):
        """mtime and FNAME made two runs of identical content hash differently; the builder now zeroes both."""
        for name in ("results/ontology_passage_pairs.jsonl.gz", "results/ontology_passage_index.json.gz",
                     "results/ontology_passage_matrix.csv.gz"):
            path = ROOT / name
            if not path.exists():
                continue
            header = path.read_bytes()[:18]
            flags = header[3]
            recorded_mtime = struct.unpack("<I", header[4:8])[0]
            self.assertEqual(recorded_mtime, 0, f"{name} stamps a creation time into its gzip header")
            self.assertFalse(flags & 0x08, f"{name} stores its own filename in the gzip header")

    def test_inheritance_layer_is_still_empty_by_design(self):
        layers = {layer["name"]: layer for layer in self.graph["layers"]}
        layer4 = layers["4_inheritance_and_transformation"]
        self.assertEqual(layer4["status"], "unpopulated_by_design")
        self.assertEqual(layer4["edges"], 0)
        for layer in self.graph["layers"]:
            self.assertNotIn("RESEMBLES", json.dumps(layer))
        # and every date field really is null in every v3 record, which is why the layer must stay empty
        for record in self.records:
            self.assertIsNone(record["date_earliest"])
            self.assertIsNone(record["date_latest"])

    def test_edge_file_is_a_labeled_display_slice_and_the_counts_stay_complete(self):
        with gzip.open(ROOT / "results/ontology_passage_pairs.jsonl.gz", "rt", encoding="utf-8") as handle:
            edge_count = sum(1 for _ in handle)
        scale = self.graph["scale"]
        self.assertEqual(edge_count, scale["passage_pair_edges_written"])
        self.assertEqual(edge_count, scale["passage_pair_edges_displayed"])
        self.assertNotIn("passage_pair_candidates_generated", scale)  # the name implied the file was the set
        layers = {layer["name"]: layer for layer in self.graph["layers"]}
        self.assertEqual(layers["3_passage_pair_shared_states"]["edges"], edge_count)
        # no work pair contributes more than the declared cap, so the file size is a property of the cap
        per_work_pair = Counter(f"{edge['left_work']}--{edge['right_work']}" for edge in self.graph["edges"])
        self.assertLessEqual(max(per_work_pair.values()), scale["display_cap_per_work_pair"])
        # every written edge carries at least one shared live state and says which slice it came from
        with gzip.open(ROOT / "results/ontology_passage_pairs.jsonl.gz", "rt", encoding="utf-8") as handle:
            for line in itertools.islice(handle, 200):
                edge = json.loads(line)
                self.assertTrue(edge["shared_states"])
                self.assertNotEqual(edge["left_work_id"], edge["right_work_id"])
                self.assertEqual(edge["edge_kind"], "SHARED_DIMENSION_STATE_CANDIDATE")
                self.assertIn("exact inverted index", edge["edge_is_from"])
                self.assertIn("display_slice", json.dumps(edge))
                self.assertNotIn("RESEMBLES", json.dumps(edge))

    def test_v3_scale_numbers_are_the_ones_the_attestation_file_supports(self):
        scale = self.graph["scale"]
        self.assertEqual(scale["attestation_records"], len(self.records))
        self.assertEqual(len(self.per_passage), scale["passages_with_live_states"])
        self.assertEqual(scale["naive_passage_pair_space"], len(self.per_passage) * (len(self.per_passage) - 1) // 2)
        self.assertEqual(scale["work_state_matrix_cells"], 780)  # 65 works x 12 v3 dimensions
        self.assertNotIn("blocked_by_speech_act", json.dumps(self.graph))


if __name__ == "__main__":
    unittest.main()
