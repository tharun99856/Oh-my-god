-- Requires PostgreSQL 15 or later: this schema uses UNIQUE ... NULLS NOT DISTINCT (event_participant,
-- statistical_test), which is not valid syntax on earlier releases. It also assumes gen_random_uuid()
-- from pgcrypto for surrogate identifiers.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA narrative;
SET search_path = narrative, public;

CREATE TYPE review_state AS ENUM ('candidate','located','rights_checked','transcribed','source_verified','independently_annotated','adjudicated','analysis_ready');
CREATE TYPE access_class AS ENUM ('public','restricted','embargoed','community_controlled','unknown');
CREATE TYPE claim_status AS ENUM ('proposed','supported','disputed','rejected','superseded');
CREATE TYPE evidence_direction AS ENUM ('supports','contradicts','contextualizes');
-- A relationship between two narrative versions. Translation is deliberately absent: a translation
-- relates two expressions of one work and is recorded in expression_dependency, not inferred between
-- versions. COMPARED_WITH is also absent, because "these two were scored" is an analysis fact and
-- lives in score/statistical_test, not in a relationship table.
CREATE TYPE relation_kind AS ENUM ('RETRIEVED_AS_CANDIDATE','RESEMBLES','DESCENDS_FROM','BORROWS_FROM','INFLUENCES','CONTRADICTS','INDEPENDENT_INVENTION','UNCERTAIN_RELATIONSHIP');
CREATE TYPE confidence_kind AS ENUM ('strong','moderate','weak','mixed','none_identified','unassessed');
CREATE TYPE evidence_grade AS ENUM ('absent','weak','moderate','strong','contradictory','unassessed');

CREATE TABLE actor (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  name text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('human','ai','organization')),
  affiliation text
);

CREATE TABLE community (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  name text NOT NULL,
  self_designation text,
  notes text
);

CREATE TABLE language (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  name text NOT NULL,
  iso_code text,
  glottocode text,
  family_name text,
  parent_id uuid REFERENCES language(id)
);

CREATE TABLE tradition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  name text NOT NULL,
  description text,
  year_start integer,
  year_end integer,
  CHECK (year_start IS NULL OR year_end IS NULL OR year_start <= year_end)
);

CREATE TABLE tradition_community (
  tradition_id uuid REFERENCES tradition(id),
  community_id uuid REFERENCES community(id),
  note text,
  PRIMARY KEY (tradition_id, community_id)
);

CREATE TABLE tradition_language (
  tradition_id uuid REFERENCES tradition(id),
  language_id uuid REFERENCES language(id),
  note text,
  PRIMARY KEY (tradition_id, language_id)
);

CREATE TABLE work (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  original_title text,
  normalized_title text NOT NULL,
  attributed_author text,
  description text
);

-- Documented text families are premises, not findings: two works in one family cannot be counted as
-- independent evidence for each other. This is the schema counterpart of the graph's
-- source_dependency layer, and it is deliberately a work-level grouping rather than a
-- narrative_relationship, because it is not a claim about narratives.
CREATE TABLE work_family (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  relationship text NOT NULL CHECK (relationship IN ('same_epic_or_translation_family','same_anthology','translation_of_work','compilation_of_work','recension_of_work')),
  exclude_from_independent_analysis boolean NOT NULL DEFAULT true,
  rationale text NOT NULL
);

CREATE TABLE work_family_member (
  work_family_id uuid NOT NULL REFERENCES work_family(id),
  work_id uuid NOT NULL REFERENCES work(id),
  note text,
  PRIMARY KEY (work_family_id, work_id)
);

CREATE TABLE expression (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  work_id uuid REFERENCES work(id),
  language_id uuid REFERENCES language(id),
  title text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('original','recension','critical_edition','translation','performance','field_record')),
  editor_or_translator text,
  composition_year_min integer,
  composition_year_max integer,
  dating_rationale text,
  review_state review_state NOT NULL DEFAULT 'candidate',
  CHECK (composition_year_min IS NULL OR composition_year_max IS NULL OR composition_year_min <= composition_year_max)
);

-- An expression can rest on several others at once: a translation may follow one recension while
-- borrowing a reading from another edition. A single based_on_expression_id column cannot say that.
CREATE TABLE expression_dependency (
  from_expression_id uuid NOT NULL REFERENCES expression(id),
  to_expression_id uuid NOT NULL REFERENCES expression(id),
  kind text NOT NULL CHECK (kind IN ('translation_of','revision_of','recension_of','parallel_source_of','quotation_from','compilation_of')),
  note text,
  PRIMARY KEY (from_expression_id, to_expression_id, kind),
  CHECK (from_expression_id <> to_expression_id)
);

CREATE TABLE access_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  access access_class NOT NULL DEFAULT 'unknown',
  copyright_notice text,
  license text,
  community_id uuid REFERENCES community(id),
  protocol text,
  permitted_uses text,
  review_date date
);

CREATE TABLE witness (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  kind text NOT NULL CHECK (kind IN ('manuscript','inscription','printed_copy','recording','field_note','born_digital','archaeological_object')),
  repository text,
  repository_identifier text,
  attestation_year_min integer,
  attestation_year_max integer,
  dating_rationale text,
  access_policy_id uuid REFERENCES access_policy(id),
  CHECK (attestation_year_min IS NULL OR attestation_year_max IS NULL OR attestation_year_min <= attestation_year_max)
);

CREATE TABLE witness_expression (
  witness_id uuid REFERENCES witness(id),
  expression_id uuid REFERENCES expression(id),
  note text,
  PRIMARY KEY (witness_id, expression_id)
);

CREATE TABLE asset (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  expression_id uuid REFERENCES expression(id),
  witness_id uuid REFERENCES witness(id),
  uri text NOT NULL,
  media_type text,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  acquisition_time timestamptz,
  extraction_method text,
  extraction_confidence numeric CHECK (extraction_confidence BETWEEN 0 AND 1),
  access_policy_id uuid REFERENCES access_policy(id),
  supersedes_id uuid REFERENCES asset(id),
  CHECK (expression_id IS NOT NULL OR witness_id IS NOT NULL)
);

CREATE TABLE passage (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  expression_id uuid NOT NULL REFERENCES expression(id),
  witness_id uuid REFERENCES witness(id),
  locator text NOT NULL,
  text_content text,
  script text,
  transliteration_system text,
  restoration_notes text,
  review_state review_state NOT NULL DEFAULT 'candidate',
  UNIQUE (expression_id, locator)
);

CREATE TABLE passage_asset (
  passage_id uuid REFERENCES passage(id),
  asset_id uuid REFERENCES asset(id),
  locator text NOT NULL,
  PRIMARY KEY (passage_id, asset_id, locator)
);

CREATE TABLE passage_alignment (
  source_passage_id uuid REFERENCES passage(id),
  target_passage_id uuid REFERENCES passage(id),
  kind text NOT NULL CHECK (kind IN ('translation','transliteration','parallel_witness')),
  note text,
  PRIMARY KEY (source_passage_id, target_passage_id, kind)
);

CREATE TABLE bibliographic_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  citation text NOT NULL,
  authors text,
  title text NOT NULL,
  publication_year integer,
  doi text,
  url text,
  publisher text,
  peer_reviewed boolean
);

CREATE TABLE narrative_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  tradition_id uuid REFERENCES tradition(id),
  comparison_class_id uuid,
  native_title text,
  normalized_title text NOT NULL,
  summary text,
  context text,
  attestation_completeness text NOT NULL DEFAULT 'full' CHECK (attestation_completeness IN ('full','partial','mention_only')),
  review_state review_state NOT NULL DEFAULT 'candidate'
);

CREATE TABLE narrative_attestation (
  narrative_version_id uuid REFERENCES narrative_version(id),
  passage_id uuid REFERENCES passage(id),
  coverage text NOT NULL CHECK (coverage IN ('whole','episode','mention','iconographic')),
  note text,
  PRIMARY KEY (narrative_version_id, passage_id)
);

CREATE TABLE entity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  kind text NOT NULL CHECK (kind IN ('deity','hero','human','being','animal','object','place','group','abstract')),
  canonical_label text NOT NULL,
  description text
);

CREATE TABLE entity_name (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id uuid NOT NULL REFERENCES entity(id),
  language_id uuid REFERENCES language(id),
  name text NOT NULL,
  script text,
  transliteration text,
  passage_id uuid REFERENCES passage(id)
);

CREATE TABLE event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  narrative_version_id uuid NOT NULL REFERENCES narrative_version(id),
  passage_id uuid NOT NULL REFERENCES passage(id),
  source_char_start integer,
  source_char_end integer,
  local_order numeric NOT NULL,
  episode text,
  predicate text NOT NULL,
  native_description text,
  explicitness text NOT NULL CHECK (explicitness IN ('source_explicit','analyst_inferred')),
  outcome text,
  annotator_certainty confidence_kind NOT NULL DEFAULT 'unassessed',
  evidence_kind text NOT NULL DEFAULT 'passage_text' CHECK (evidence_kind IN ('passage_text','translator_note_about_source','reconstruction')),
  UNIQUE (narrative_version_id, local_order),
  UNIQUE (id, narrative_version_id),
  -- The passage an event is coded from must be a passage that attests that same version. Without
  -- this, an event can quietly borrow a citation from another narrative version of the same work.
  FOREIGN KEY (narrative_version_id, passage_id) REFERENCES narrative_attestation(narrative_version_id, passage_id),
  CHECK (source_char_start IS NULL OR source_char_end IS NULL OR source_char_end > source_char_start),
  CHECK (source_char_start IS NULL OR source_char_start >= 0)
);

-- Every event is anchored to a passage that attests its version, and how directly that passage states
-- the event is carried by explicitness and evidence_kind rather than by leaving the citation empty.
-- A modern reconstruction of a narrative is therefore not an event row at all: it is a claim about the
-- material, which is exactly the distinction the Perun-Veles case turns on.

-- Narrative similarity claims are only falsifiable if the event can be taken back to the exact
-- words it was coded from, so spans are stored relative to passage.text_content rather than
-- inferred from a whole-passage citation.
CREATE TABLE event_participant (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES event(id),
  entity_id uuid REFERENCES entity(id),
  local_label text,
  referent_kind text NOT NULL,
  role text NOT NULL CHECK (role IN ('agent','patient','instrument','recipient','witness','place','product','other')),
  explicitness text NOT NULL CHECK (explicitness IN ('source_explicit','analyst_inferred')),
  CHECK (entity_id IS NOT NULL OR local_label IS NOT NULL),
  UNIQUE NULLS NOT DISTINCT (event_id, role, entity_id, local_label)
);

-- A causal or temporal link inside one narrative version. Reaching across versions is a
-- comparative claim and belongs in narrative_relationship, not here, which is what the composite
-- foreign keys below enforce.
CREATE TABLE event_link (
  narrative_version_id uuid NOT NULL REFERENCES narrative_version(id),
  from_event_id uuid NOT NULL REFERENCES event(id),
  to_event_id uuid NOT NULL REFERENCES event(id),
  kind text NOT NULL CHECK (kind IN ('before','causes','enables','contradicts')),
  explicitness text NOT NULL CHECK (explicitness IN ('source_explicit','analyst_inferred')),
  PRIMARY KEY (from_event_id, to_event_id, kind),
  FOREIGN KEY (from_event_id, narrative_version_id) REFERENCES event(id, narrative_version_id),
  FOREIGN KEY (to_event_id, narrative_version_id) REFERENCES event(id, narrative_version_id),
  CHECK (from_event_id <> to_event_id)
);

CREATE TABLE concept (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  kind text NOT NULL CHECK (kind IN ('motif','theme','symbol','object','role')),
  label text NOT NULL,
  definition text NOT NULL,
  vocabulary_version text NOT NULL,
  external_code text,
  parent_id uuid REFERENCES concept(id),
  UNIQUE (vocabulary_version, kind, label)
);

CREATE TABLE narrative_concept (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  narrative_version_id uuid NOT NULL REFERENCES narrative_version(id),
  concept_id uuid NOT NULL REFERENCES concept(id),
  event_id uuid REFERENCES event(id),
  passage_id uuid REFERENCES passage(id),
  native_label text,
  asserted boolean NOT NULL DEFAULT true,
  assessed boolean NOT NULL DEFAULT true,
  certainty confidence_kind NOT NULL DEFAULT 'unassessed',
  note text,
  UNIQUE NULLS NOT DISTINCT (narrative_version_id, concept_id, event_id, passage_id),
  CHECK (asserted OR certainty <> 'unassessed')
);

-- Absence is only evidence when the coder looked: a version's comparison class fixes the set of
-- concepts that were adjudicated, and anything outside it is NA rather than zero. The engine reads
-- assessed/asserted plus the version's attestation_completeness to make that decision.
CREATE TABLE comparison_class (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  name text NOT NULL UNIQUE,
  definition text NOT NULL
);

CREATE TABLE comparison_class_concept (
  comparison_class_id uuid NOT NULL REFERENCES comparison_class(id),
  concept_id uuid NOT NULL REFERENCES concept(id),
  PRIMARY KEY (comparison_class_id, concept_id)
);

CREATE TABLE annotation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  narrative_version_id uuid NOT NULL REFERENCES narrative_version(id),
  actor_id uuid NOT NULL REFERENCES actor(id),
  layer text NOT NULL CHECK (layer IN ('source','event','participant','comparative_code','interpretation')),
  payload jsonb NOT NULL,
  blinded boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  supersedes_id uuid REFERENCES annotation(id)
);

CREATE TABLE claim (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  statement text NOT NULL,
  kind text NOT NULL,
  status claim_status NOT NULL DEFAULT 'proposed',
  confidence confidence_kind NOT NULL DEFAULT 'unassessed',
  rationale text,
  created_by uuid NOT NULL REFERENCES actor(id),
  reviewed_by uuid REFERENCES actor(id),
  supersedes_id uuid REFERENCES claim(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (reviewed_by IS NULL OR reviewed_by <> created_by)
);

CREATE TABLE evidence_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  passage_id uuid REFERENCES passage(id),
  bibliographic_record_id uuid REFERENCES bibliographic_record(id),
  locator text,
  observation text NOT NULL,
  method text,
  created_by uuid NOT NULL REFERENCES actor(id),
  verified_by uuid REFERENCES actor(id),
  CHECK (passage_id IS NOT NULL OR bibliographic_record_id IS NOT NULL)
);

CREATE TABLE claim_evidence (
  claim_id uuid REFERENCES claim(id),
  evidence_item_id uuid REFERENCES evidence_item(id),
  direction evidence_direction NOT NULL,
  reasoning text NOT NULL,
  PRIMARY KEY (claim_id, evidence_item_id, direction)
);

CREATE TABLE narrative_relationship (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_version_id uuid NOT NULL REFERENCES narrative_version(id),
  to_version_id uuid NOT NULL REFERENCES narrative_version(id),
  kind relation_kind NOT NULL,
  directionality text NOT NULL,
  claim_id uuid UNIQUE NOT NULL REFERENCES claim(id),
  analysis_run_id uuid,
  CHECK (from_version_id <> to_version_id),
  CHECK ((kind IN ('RESEMBLES','RETRIEVED_AS_CANDIDATE','INDEPENDENT_INVENTION','UNCERTAIN_RELATIONSHIP','CONTRADICTS')
          AND directionality = 'symmetric')
      OR (kind IN ('DESCENDS_FROM','BORROWS_FROM','INFLUENCES','TRANSLATED_FROM')
          AND directionality = 'directed')),
  CHECK (directionality <> 'symmetric' OR from_version_id < to_version_id),
  CHECK (kind NOT IN ('RESEMBLES','RETRIEVED_AS_CANDIDATE') OR analysis_run_id IS NOT NULL)
);

ALTER TABLE narrative_version
  ADD CONSTRAINT version_comparison_class_fk FOREIGN KEY (comparison_class_id) REFERENCES comparison_class(id);

CREATE TABLE analysis_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  kind text NOT NULL CHECK (kind IN ('exploratory','confirmatory','null_model','sensitivity')),
  input_manifest jsonb NOT NULL,
  input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
  code_version text NOT NULL,
  vocabulary_version text NOT NULL,
  software_versions jsonb NOT NULL,
  configuration jsonb NOT NULL,
  random_seed bigint,
  output_sha256 text CHECK (output_sha256 IS NULL OR output_sha256 ~ '^[0-9a-f]{64}$'),
  created_by uuid NOT NULL REFERENCES actor(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE narrative_relationship
  ADD CONSTRAINT relationship_analysis_fk FOREIGN KEY (analysis_run_id) REFERENCES analysis_run(id);

-- Scores are descriptive measures only. Nothing in this table may be named or read as an ancestry
-- or transmission probability: those are claims, they live in claim plus evidence_assessment, and
-- they are graded ordinally rather than scored.
CREATE TABLE score (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  from_version_id uuid NOT NULL REFERENCES narrative_version(id),
  to_version_id uuid NOT NULL REFERENCES narrative_version(id),
  measure_id text NOT NULL CHECK (measure_id IN ('S_sequence','S_causal','S_motif','S_role','S_symbol')),
  score_kind text NOT NULL DEFAULT 'descriptive_similarity' CHECK (score_kind = 'descriptive_similarity'),
  value numeric CHECK (value BETWEEN 0 AND 1),
  domain integer CHECK (domain IS NULL OR domain >= 0),
  unavailable_reason text,
  alignment jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (value IS NOT NULL OR unavailable_reason IS NOT NULL),
  CHECK (from_version_id <> to_version_id),
  UNIQUE (analysis_run_id, from_version_id, to_version_id, measure_id)
);

-- Retrieval scores are a different kind of object from narrative comparison scores: they measure
-- word windows inside works, they are produced by an indexing configuration rather than a coding
-- manual, and their unit of analysis is a passage pair, not a version pair. Keeping them in `score`
-- would let a passage cosine be joined to a version-level claim as if the two were comparable.
CREATE TABLE retrieval_score (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  measure_id text NOT NULL CHECK (measure_id IN ('R_lex')),
  left_passage_id uuid NOT NULL REFERENCES passage(id),
  right_passage_id uuid NOT NULL REFERENCES passage(id),
  left_work_id uuid NOT NULL REFERENCES work(id),
  right_work_id uuid NOT NULL REFERENCES work(id),
  value numeric NOT NULL CHECK (value BETWEEN 0 AND 1),
  shared_lexical_terms jsonb,
  discovery_eligible boolean NOT NULL,
  dependence_relationship text,
  dependence_note text,
  CHECK (left_passage_id <> right_passage_id),
  CHECK (left_work_id <> right_work_id),
  CHECK (discovery_eligible OR dependence_relationship IS NOT NULL),
  UNIQUE (analysis_run_id, measure_id, left_passage_id, right_passage_id)
);

-- A work-level aggregate of retrieval scores is an explicit maximum over passage pairs, published as
-- its own object so that its aggregation rule travels with the number instead of being forgotten.
CREATE TABLE retrieval_aggregate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  left_work_id uuid NOT NULL REFERENCES work(id),
  right_work_id uuid NOT NULL REFERENCES work(id),
  aggregation text NOT NULL CHECK (aggregation = 'max'),
  value numeric NOT NULL CHECK (value BETWEEN 0 AND 1),
  passage_pair_count integer NOT NULL CHECK (passage_pair_count >= 0),
  strongest_left_passage_id uuid REFERENCES passage(id),
  strongest_right_passage_id uuid REFERENCES passage(id),
  discovery_eligible boolean NOT NULL,
  dependence_relationship text,
  CHECK (left_work_id <> right_work_id),
  CHECK (left_work_id < right_work_id),
  UNIQUE (analysis_run_id, left_work_id, right_work_id)
);

-- Statistical results are not similarity measures. A permutation p-value answers "how unusual is this
-- score under a stated null", which is a claim about the model and the draws, and must stay separate
-- from the descriptive number it qualifies.
CREATE TABLE statistical_test (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  test_name text NOT NULL,
  unit text NOT NULL CHECK (unit IN ('version_pair','passage','passage_pair','work_pair','corpus')),
  from_version_id uuid REFERENCES narrative_version(id),
  to_version_id uuid REFERENCES narrative_version(id),
  statistic numeric,
  p_value numeric CHECK (p_value IS NULL OR (p_value >= 0 AND p_value <= 1)),
  null_model text NOT NULL,
  draws integer,
  random_seed bigint,
  passed_preregistered_gate boolean,
  note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (statistic IS NOT NULL OR p_value IS NOT NULL),
  CHECK (unit <> 'version_pair' OR (from_version_id IS NOT NULL AND to_version_id IS NOT NULL)),
  -- Corpus-level tests have no version pair, so NULLs must compare equal here or the same test could
  -- be inserted repeatedly under an identical key.
  UNIQUE NULLS NOT DISTINCT (analysis_run_id, test_name, unit, from_version_id, to_version_id)
);

-- A component that could not be measured stays a row with a reason, never a renormalised number.
CREATE TABLE score_component (
  score_id uuid REFERENCES score(id),
  name text NOT NULL,
  value numeric CHECK (value BETWEEN 0 AND 1),
  weight numeric CHECK (weight BETWEEN 0 AND 1),
  domain integer CHECK (domain IS NULL OR domain >= 0),
  unavailable_reason text,
  details jsonb,
  CHECK (value IS NOT NULL OR unavailable_reason IS NOT NULL),
  PRIMARY KEY (score_id, name)
);

-- Ordinal qualitative evidence for a historical claim: geographic and temporal contact, dating
-- order, independent attestation, and the scholar's assessment of each. Deliberately not a number
-- that can be averaged into a probability.
CREATE TABLE evidence_assessment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  claim_id uuid NOT NULL REFERENCES claim(id),
  criterion text NOT NULL,
  grade evidence_grade NOT NULL,
  rationale text NOT NULL,
  evidence_item_id uuid REFERENCES evidence_item(id),
  assessed_by uuid NOT NULL REFERENCES actor(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (claim_id, criterion, assessed_by)
);

CREATE TABLE decision_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text UNIQUE NOT NULL,
  title text NOT NULL,
  decision text NOT NULL,
  reason text NOT NULL,
  affected_objects jsonb NOT NULL,
  approved_by uuid NOT NULL REFERENCES actor(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  supersedes_id uuid REFERENCES decision_record(id)
);

CREATE INDEX passage_expression_idx ON passage(expression_id);
CREATE INDEX attestation_passage_idx ON narrative_attestation(passage_id);
CREATE INDEX event_narrative_order_idx ON event(narrative_version_id, local_order);
CREATE INDEX event_source_span_idx ON event(passage_id, source_char_start);
CREATE INDEX event_participant_entity_idx ON event_participant(entity_id, role);
CREATE INDEX event_link_version_idx ON event_link(narrative_version_id, kind);
CREATE INDEX expression_dependency_from_idx ON expression_dependency(from_expression_id, kind);
CREATE INDEX narrative_concept_assessed_idx ON narrative_concept(narrative_version_id, assessed);
CREATE INDEX comparison_class_concept_idx ON comparison_class_concept(concept_id);
CREATE INDEX concept_narrative_idx ON narrative_concept(narrative_version_id, concept_id);
CREATE INDEX evidence_claim_idx ON claim_evidence(claim_id, direction);
CREATE INDEX evidence_assessment_claim_idx ON evidence_assessment(claim_id, grade);
CREATE INDEX relationship_pair_idx ON narrative_relationship(from_version_id, to_version_id, kind);
CREATE INDEX score_pair_idx ON score(from_version_id, to_version_id);
CREATE INDEX score_measure_idx ON score(measure_id);
CREATE INDEX retrieval_score_work_pair_idx ON retrieval_score(left_work_id, right_work_id);
CREATE INDEX retrieval_score_value_idx ON retrieval_score(analysis_run_id, value DESC);
CREATE INDEX retrieval_aggregate_value_idx ON retrieval_aggregate(analysis_run_id, value DESC);
CREATE INDEX statistical_test_run_idx ON statistical_test(analysis_run_id, test_name);
CREATE INDEX event_attestation_passage_idx ON event(passage_id);
CREATE INDEX annotation_payload_gin ON annotation USING gin(payload);

COMMIT;
