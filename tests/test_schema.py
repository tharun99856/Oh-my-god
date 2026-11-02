"""Structural checks on schema.sql.

There is no Postgres in this environment, so the DDL cannot be executed here. What can be checked
without a server is the class of defect that actually bites when the schema is edited: a table
referencing one that is created later, a foreign key aimed at a column that does not exist, a join
table with no primary key, or an enum value used by a check but never declared. These tests cover
those; applying the schema to a real server remains a separate step.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "schema.sql").read_text(encoding="utf-8")


def split_top_level(text):
    parts, depth, current = [], 0, []
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


def parse_tables(sql):
    tables = {}
    for match in re.finditer(r"CREATE TABLE (\w+) \(", sql):
        name = match.group(1)
        start = match.end() - 1
        depth = 0
        for index in range(start, len(sql)):
            if sql[index] == "(":
                depth += 1
            elif sql[index] == ")":
                depth -= 1
                if depth == 0:
                    break
        else:
            raise AssertionError(f"Unbalanced parentheses in table {name}")
        tables[name] = {"position": match.start(), "body": sql[start + 1:index],
                        "columns": split_top_level(sql[start + 1:index])}
    return tables


TABLES = parse_tables(SQL)
DECLARATION_ORDER = {name: info["position"] for name, info in TABLES.items()}


def column_names(clause):
    first = re.split(r"\s+", clause.strip(), maxsplit=2)[0]
    return first


CONSTRAINT_CLAUSES = ("primary key", "foreign key", "unique", "check", "constraint", "exclude")


class SchemaStructureTests(unittest.TestCase):
    def test_file_wraps_the_schema_in_one_transaction(self):
        # Leading comment lines are allowed; what must hold is that the first statement opens the
        # transaction and the last statement closes it, so a failure mid-schema cannot leave a
        # half-created schema behind.
        self.assertRegex(SQL, r"\A(?:--[^\n]*\n|\s)*BEGIN;")
        self.assertTrue(SQL.rstrip().endswith("COMMIT;"))

    def test_every_table_has_a_primary_key(self):
        missing = [name for name, info in TABLES.items() if "primary key" not in info["body"].lower()]
        self.assertEqual(missing, [], "join tables without a primary key can silently duplicate rows")

    def test_referenced_tables_are_created_before_they_are_referenced(self):
        violations = []
        for name, info in TABLES.items():
            for clause in info["columns"]:
                for target in re.findall(r"REFERENCES (\w+)", clause):
                    if target not in TABLES:
                        violations.append(f"{name} references unknown table {target}")
                    elif target != name and DECLARATION_ORDER[target] > DECLARATION_ORDER[name]:
                        violations.append(f"{name} references {target}, which is created later")
        self.assertEqual(violations, [], "Postgres resolves foreign keys at creation time")

    def test_foreign_keys_without_a_deferred_alter_all_resolve(self):
        """A forward reference is legal only when it is added by ALTER TABLE after both tables exist."""
        deferred = set()
        for match in re.finditer(r"ALTER TABLE (\w+)\s+ADD CONSTRAINT \w+ FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\((\w+)\)", SQL):
            alter_table, columns, target, target_column = match.groups()
            self.assertIn(target, TABLES, f"ALTER on {alter_table} targets unknown table {target}")
            self.assertLess(DECLARATION_ORDER[target], match.start(), f"{target} is referenced before it exists")
            self.assertTrue(re.search(rf"\b{re.escape(column_names(columns))}\b", TABLES[alter_table]["body"]),
                            f"ALTER adds a foreign key on a column {alter_table} does not have")
            self.assertIn(target_column, TABLES[target]["body"], f"{target} has no column {target_column}")
            deferred.add(alter_table)
        self.assertTrue(deferred, "expected at least the deferred comparison_class foreign key")

    def test_referenced_columns_exist(self):
        problems = []
        for name, info in TABLES.items():
            for clause in info["columns"]:
                match = re.search(r"FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\((\w+)\)", clause)
                if match:
                    _, target, target_column = match.groups()
                    if target_column not in TABLES[target]["body"]:
                        problems.append(f"{name} -> {target}.{target_column}")
                    continue
                for target, column in re.findall(r"REFERENCES (\w+)\((\w+)\)", clause):
                    if column not in TABLES[target]["body"]:
                        problems.append(f"{name} -> {target}.{column}")
        self.assertEqual(problems, [])

    def test_composite_foreign_key_targets_need_a_matching_unique_key(self):
        """A composite foreign key can only point at a composite unique key, which is why event
        carries UNIQUE (id, narrative_version_id) rather than only a primary key."""
        for name, info in TABLES.items():
            for clause in info["columns"]:
                match = re.search(r"FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\(([^)]+)\)", clause)
                if not match:
                    continue
                source_columns = [part.strip() for part in match.group(1).split(",")]
                target_columns = [part.strip() for part in match.group(3).split(",")]
                target = match.group(2)
                self.assertEqual(len(source_columns), len(target_columns), f"{name}: arity mismatch")
                if len(target_columns) == 1:
                    continue
                keys = [key for key in re.findall(r"UNIQUE \(([^)]+)\)|PRIMARY KEY \(([^)]+)\)", TABLES[target]["body"])]
                covered = [tuple(sorted(part.strip() for part in (a or b).split(","))) for a, b in keys]
                self.assertIn(tuple(sorted(target_columns)), covered,
                              f"{name} -> {target} composite key has no unique target")

    def test_enum_types_used_by_tables_are_declared(self):
        declared = set(re.findall(r"CREATE TYPE (\w+) AS ENUM", SQL))
        used = set()
        for info in TABLES.values():
            for clause in info["columns"]:
                head = column_names(clause)
                if head in declared:
                    used.add(head)
        self.assertEqual(used - declared, set())
        for enum_name in ("relation_kind", "review_state", "evidence_grade", "confidence_kind"):
            self.assertIn(enum_name, declared)

    def test_layered_graph_vocabulary_has_a_home(self):
        """Each graph layer needs a place in the schema, and the work-level premise layer must not be
        filed as a narrative relationship, because it is not a claim about narratives."""
        values = re.search(r"CREATE TYPE relation_kind AS ENUM \(([^)]+)\)", SQL).group(1)
        for kind in ("RETRIEVED_AS_CANDIDATE", "RESEMBLES", "DESCENDS_FROM", "BORROWS_FROM", "INDEPENDENT_INVENTION"):
            self.assertIn(f"'{kind}'", values)
        self.assertNotIn("SOURCE_DEPENDENCE", values)
        self.assertNotIn("TRANSLATED_FROM", values, "translation relates expressions, not narrative versions")
        self.assertIn("work_family", TABLES)
        self.assertIn("work_family_member", TABLES)

    def test_score_is_confined_to_descriptive_measures(self):
        body = TABLES["score"]["body"]
        self.assertNotIn("linguistic_evidence", body)
        self.assertNotIn("transmission_evidence", body)
        self.assertIn("CHECK (value BETWEEN 0 AND 1)", body)
        self.assertIn("unavailable_reason", body)
        measures = re.search(r"measure_id text NOT NULL CHECK \(measure_id IN \(([^)]+)\)\)", body).group(1)
        for allowed in ("S_sequence", "S_causal", "S_motif", "S_role", "S_symbol"):
            self.assertIn(f"'{allowed}'", measures)
        for forbidden in ("R_lex", "permutation_p_value"):
            self.assertNotIn(f"'{forbidden}'", measures, f"{forbidden} is not a version-level descriptive score")

    def test_retrieval_scores_are_not_stored_with_narrative_scores(self):
        """A passage cosine and a version-pair component have different units of analysis; mixing them in
        one table is how a retrieval artifact becomes a narrative conclusion by join alone."""
        self.assertIn("retrieval_score", TABLES)
        self.assertIn("retrieval_aggregate", TABLES)
        body = TABLES["retrieval_score"]["body"]
        self.assertIn("REFERENCES passage(id)", body)
        self.assertIn("discovery_eligible boolean NOT NULL", body)
        self.assertIn("dependence_relationship", body)
        aggregate = TABLES["retrieval_aggregate"]["body"]
        self.assertIn("CHECK (aggregation = 'max')", aggregate, "the aggregation rule must travel with the number")
        self.assertIn("passage_pair_count integer NOT NULL", aggregate)

    def test_a_p_value_is_not_a_similarity_score(self):
        self.assertIn("statistical_test", TABLES)
        body = TABLES["statistical_test"]["body"]
        self.assertIn("null_model text NOT NULL", body)
        self.assertIn("random_seed bigint", body)
        self.assertIn("passed_preregistered_gate boolean", body)
        self.assertIn("CHECK (p_value IS NULL OR (p_value >= 0 AND p_value <= 1))", body)
        self.assertNotIn("BETWEEN 0 AND 100", body)

    def test_event_citation_must_attest_its_own_version(self):
        """Otherwise an event can borrow a passage from another version of the same work."""
        body = TABLES["event"]["body"]
        self.assertIn("passage_id uuid NOT NULL REFERENCES passage(id)", body)
        self.assertIn("FOREIGN KEY (narrative_version_id, passage_id) REFERENCES narrative_attestation(narrative_version_id, passage_id)", body)

    def test_historical_evidence_is_graded_rather_than_scored(self):
        self.assertIn("evidence_assessment", TABLES)
        body = TABLES["evidence_assessment"]["body"]
        self.assertIn("grade evidence_grade", body)
        self.assertNotIn("numeric", body, "an ordinal assessment must not offer a probability")

    def test_event_link_is_restricted_to_one_narrative_version(self):
        body = TABLES["event_link"]["body"]
        self.assertIn("narrative_version_id uuid NOT NULL", body)
        self.assertEqual(len(re.findall(r"FOREIGN KEY \((?:from|to)_event_id, narrative_version_id\) REFERENCES event\(id, narrative_version_id\)", body)), 2)

    def test_symmetric_relationships_cannot_be_stored_twice(self):
        body = TABLES["narrative_relationship"]["body"]
        self.assertIn("CHECK (directionality <> 'symmetric' OR from_version_id < to_version_id)", body)

    def test_expression_dependencies_are_many_to_many(self):
        self.assertIn("expression_dependency", TABLES)
        self.assertIsNone(re.search(r"^\s*based_on_expression_id\s+uuid", SQL, re.MULTILINE),
                          "a single-valued dependency column is back")

    def test_annotations_are_attributed_and_replaceable(self):
        body = TABLES["annotation"]["body"]
        self.assertIn("actor_id uuid NOT NULL", body)
        self.assertIn("supersedes_id", body)
        self.assertIn("blinded", body)

    def test_indexes_point_at_real_tables_and_columns(self):
        for match in re.finditer(r"CREATE INDEX \w+ ON (\w+)(?: USING \w+)? \(([^)]+)\)", SQL):
            table, columns = match.groups()
            self.assertIn(table, TABLES, f"index on unknown table {table}")
            for column in re.findall(r"\w+", columns):
                if column in ("gin", "btree"):
                    continue
                self.assertIn(column, TABLES[table]["body"], f"{table} has no column {column}")

    def test_no_table_is_declared_twice(self):
        names = re.findall(r"CREATE TABLE (\w+)", SQL)
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
