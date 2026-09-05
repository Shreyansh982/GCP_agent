"""SQLite implementation of the investigation repository boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gcp_observability_agent.domain.common.ids import (
    FindingId,
    HypothesisId,
    InvestigationId,
    InvestigationStepId,
)
from gcp_observability_agent.domain.evidence.models import Finding, Hypothesis, HypothesisStatus
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationOutcome,
    InvestigationStatus,
    InvestigationStep,
    OutcomeStatus,
    StepExecutionStatus,
    TerminationReason,
    ValidationStatus,
)
from gcp_observability_agent.domain.ports import InvestigationRepository
from gcp_observability_agent.infrastructure.persistence.sqlite.database import (
    apply_migrations,
    connect,
    transaction,
)
from gcp_observability_agent.infrastructure.persistence.sqlite.errors import ConcurrencyConflict
from gcp_observability_agent.infrastructure.persistence.sqlite.mapper import (
    analysis_from_row,
    as_json,
    as_timestamp,
    evidence_for,
    from_json,
    from_timestamp,
    observation_from_row,
    scope_from_row,
    temporal_context_from_row,
    tool_request_from_row,
    tool_result_from_row,
    utc_now,
)


class SQLiteInvestigationRepository(InvestigationRepository):
    """Persists the aggregate through append-oriented SQLite audit records."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        apply_migrations(self._database_path)

    def save(self, investigation: Investigation, *, expected_version: int | None = None) -> int:
        """Persist a complete aggregate snapshot and return its new durable version."""
        with connect(self._database_path) as connection, transaction(connection):
            row = connection.execute(
                "SELECT version FROM investigations WHERE investigation_id = ?",
                (str(investigation.investigation_id),),
            ).fetchone()
            if row is None:
                if expected_version is not None:
                    raise ConcurrencyConflict("cannot update an investigation that does not exist")
                version = 1
                self._insert_investigation(connection, investigation, version)
            else:
                current_version = row["version"]
                if expected_version != current_version:
                    raise ConcurrencyConflict("investigation version does not match durable state")
                version = current_version + 1
                self._update_investigation(connection, investigation, version)
            self._append_audit_records(connection, investigation)
            return version

    def get(self, investigation_id: InvestigationId) -> Investigation | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT * FROM investigations WHERE investigation_id = ?", (str(investigation_id),)
            ).fetchone()
            if row is None:
                return None
            scope_row = connection.execute(
                "SELECT * FROM investigation_scopes WHERE investigation_id = ?", (str(investigation_id),)
            ).fetchone()
            assert scope_row is not None
            investigation = Investigation(
                InvestigationId(row["investigation_id"]),
                row["question"],
                scope_from_row(scope_row),
                temporal_context_from_row(row),
            )
            if row["status"] != InvestigationStatus.CREATED.value:
                investigation.start()
            self._load_steps(connection, investigation)
            self._load_evidence(connection, investigation)
            self._load_hypotheses_and_findings(connection, investigation)
            if row["status"] == InvestigationStatus.TERMINAL.value:
                outcome_row = connection.execute(
                    "SELECT * FROM investigation_outcomes WHERE investigation_id = ?", (str(investigation_id),)
                ).fetchone()
                assert outcome_row is not None
                investigation.conclude(
                    InvestigationOutcome(
                        OutcomeStatus(outcome_row["outcome_status"]),
                        TerminationReason(outcome_row["termination_reason"]),
                        outcome_row["response_summary"],
                        tuple(from_json(outcome_row["unresolved_questions_json"], [])),
                        tuple(from_json(outcome_row["missing_evidence_json"], [])),
                    )
                )
            return investigation

    def version_for(self, investigation_id: InvestigationId) -> int | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT version FROM investigations WHERE investigation_id = ?", (str(investigation_id),)
            ).fetchone()
            return None if row is None else int(row["version"])

    def _insert_investigation(self, connection: sqlite3.Connection, investigation: Investigation, version: int) -> None:
        now = utc_now()
        started_at = now if investigation.status is not InvestigationStatus.CREATED else None
        completed_at = now if investigation.status is InvestigationStatus.TERMINAL else None
        context = investigation.temporal_context
        connection.execute(
            """
            INSERT INTO investigations(
                investigation_id, question, status, reference_time, timezone, requested_expression,
                interval_start, interval_end, created_at, started_at, completed_at, metadata_json, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(investigation.investigation_id), investigation.question, investigation.status.value,
                as_timestamp(context.reference_time), context.timezone, context.requested_expression,
                as_timestamp(context.resolved_interval.start_time), as_timestamp(context.resolved_interval.end_time),
                now, started_at, completed_at, as_json({}), version,
            ),
        )
        scope = investigation.scope
        connection.execute(
            """
            INSERT INTO investigation_scopes(
                investigation_id, project_id, service, environment, resource_type, resource_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(investigation.investigation_id),
                str(scope.project_id) if scope.project_id else None,
                scope.service, scope.environment,
                str(scope.resource_type) if scope.resource_type else None,
                str(scope.resource_id) if scope.resource_id else None,
                as_json(scope.metadata),
            ),
        )

    def _update_investigation(self, connection: sqlite3.Connection, investigation: Investigation, version: int) -> None:
        now = utc_now()
        connection.execute(
            """
            UPDATE investigations
            SET status = ?, started_at = COALESCE(started_at, ?),
                completed_at = CASE WHEN ? = 'TERMINAL' THEN COALESCE(completed_at, ?) ELSE NULL END,
                version = ?
            WHERE investigation_id = ?
            """,
            (investigation.status.value, now, investigation.status.value, now, version, str(investigation.investigation_id)),
        )

    def _append_audit_records(self, connection: sqlite3.Connection, investigation: Investigation) -> None:
        for step in investigation.steps:
            self._append_step(connection, investigation, step)
        for observation in investigation.observations:
            self._append_observation(connection, observation)
        for analysis in investigation.analyses:
            self._append_analysis(connection, analysis)
        for hypothesis in investigation.hypotheses:
            self._append_hypothesis(connection, hypothesis)
        for finding in investigation.findings:
            self._append_finding(connection, finding)
        if investigation.outcome is not None:
            outcome = investigation.outcome
            connection.execute(
                """
                INSERT OR IGNORE INTO investigation_outcomes(
                    investigation_id, outcome_status, termination_reason, response_summary,
                    unresolved_questions_json, missing_evidence_json, persisted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(investigation.investigation_id), outcome.status.value, outcome.termination_reason.value,
                    outcome.response_summary, as_json(outcome.unresolved_questions), as_json(outcome.missing_evidence), utc_now(),
                ),
            )

    def _append_step(self, connection: sqlite3.Connection, investigation: Investigation, step: InvestigationStep) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO investigation_steps(
                step_id, investigation_id, sequence_number, started_at, completed_at,
                validation_status, execution_status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(step.step_id), str(investigation.investigation_id), step.sequence_number,
                as_timestamp(step.started_at), as_timestamp(step.completed_at) if step.completed_at else None,
                step.validation_status.value, step.execution_status.value, as_json({}),
            ),
        )
        request = step.tool_request
        connection.execute(
            """
            INSERT OR IGNORE INTO tool_requests(
                request_id, step_id, tool_name, arguments_json, requested_at, validation_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(request.request_id), str(step.step_id), request.tool_name.value,
                as_json(request.arguments), as_timestamp(request.requested_at), step.validation_status.value,
            ),
        )
        if step.tool_result is not None:
            result = step.tool_result
            connection.execute(
                """
                INSERT OR IGNORE INTO tool_results(
                    result_id, request_id, status, data_json, warnings_json, error_json,
                    provenance_json, result_metadata_json, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(result.result_id), str(result.request_id), result.status.value,
                    as_json(result.data), as_json(result.warnings), as_json(result.error) if result.error else None,
                    as_json(result.provenance), as_json({}), utc_now(),
                ),
            )

    def _append_observation(self, connection: sqlite3.Connection, observation) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO observations(
                observation_id, investigation_id, step_id, metric_type, resource_id, statement,
                numeric_value_json, unit, interval_start, interval_end, source_metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(observation.observation_id), str(observation.investigation_id),
                str(observation.step_id) if observation.step_id else None,
                str(observation.metric_type) if observation.metric_type else None,
                str(observation.resource_id) if observation.resource_id else None,
                observation.statement, as_json(observation.numeric_value), observation.unit,
                as_timestamp(observation.interval.start_time) if observation.interval else None,
                as_timestamp(observation.interval.end_time) if observation.interval else None,
                as_json(observation.provenance), utc_now(),
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO evidence_references(
                evidence_id, investigation_id, evidence_type, observation_id, analysis_id, created_at
            ) VALUES (?, ?, 'OBSERVATION', ?, NULL, ?)
            """,
            (observation.evidence_id, str(observation.investigation_id), str(observation.observation_id), utc_now()),
        )

    def _append_analysis(self, connection: sqlite3.Connection, analysis) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO deterministic_analyses(
                analysis_id, investigation_id, step_id, operation, input_evidence_ids_json,
                parameters_json, result_json, unit, provenance_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(analysis.analysis_id), str(analysis.investigation_id),
                str(analysis.step_id) if analysis.step_id else None, analysis.operation,
                as_json(analysis.input_evidence_ids), as_json(analysis.parameters), as_json(analysis.result),
                analysis.unit, as_json(analysis.provenance), utc_now(),
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO evidence_references(
                evidence_id, investigation_id, evidence_type, observation_id, analysis_id, created_at
            ) VALUES (?, ?, 'ANALYSIS', NULL, ?, ?)
            """,
            (analysis.evidence_id, str(analysis.investigation_id), str(analysis.analysis_id), utc_now()),
        )

    def _append_hypothesis(self, connection: sqlite3.Connection, hypothesis: Hypothesis) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO hypotheses(
                hypothesis_id, investigation_id, statement, status, support_level, confidence,
                significant_evidence_gap, causal_claim, temporal_correlation_only, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(hypothesis.hypothesis_id), str(hypothesis.investigation_id), hypothesis.statement,
                hypothesis.status.value, hypothesis.support_level.value, hypothesis.confidence,
                int(hypothesis.significant_evidence_gap), int(hypothesis.causal_claim),
                int(hypothesis.temporal_correlation_only), now, now,
            ),
        )
        self._append_evidence_links(connection, "hypothesis_evidence", "hypothesis_id", str(hypothesis.hypothesis_id), hypothesis.evidence)

    def _append_finding(self, connection: sqlite3.Connection, finding: Finding) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO findings(
                finding_id, investigation_id, statement, support_level, confidence,
                significant_evidence_gap, causal_claim, temporal_correlation_only, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(finding.finding_id), str(finding.investigation_id), finding.statement,
                finding.support_level.value, finding.confidence, int(finding.significant_evidence_gap),
                int(finding.causal_claim), int(finding.temporal_correlation_only), now, now,
            ),
        )
        self._append_evidence_links(connection, "finding_evidence", "finding_id", str(finding.finding_id), finding.evidence)

    @staticmethod
    def _append_evidence_links(connection, table: str, owner_column: str, owner_id: str, references) -> None:
        for reference in references:
            connection.execute(
                f"INSERT OR IGNORE INTO {table}({owner_column}, evidence_id, relationship, created_at) VALUES (?, ?, ?, ?)",
                (owner_id, reference.evidence_id, reference.relationship.value, utc_now()),
            )

    @staticmethod
    def _load_steps(connection: sqlite3.Connection, investigation: Investigation) -> None:
        rows = connection.execute(
            """
            SELECT s.*, r.request_id, r.tool_name, r.arguments_json, r.requested_at,
                   tr.result_id, tr.status, tr.data_json, tr.warnings_json,
                   tr.error_json, tr.provenance_json
            FROM investigation_steps s
            JOIN tool_requests r ON r.step_id = s.step_id
            LEFT JOIN tool_results tr ON tr.request_id = r.request_id
            WHERE s.investigation_id = ? ORDER BY s.sequence_number
            """,
            (str(investigation.investigation_id),),
        )
        for row in rows:
            request = tool_request_from_row(row)
            result = tool_result_from_row(row) if row["result_id"] else None
            step = InvestigationStep(
                InvestigationStepId(row["step_id"]), row["sequence_number"], request,
                from_timestamp(row["started_at"]), ValidationStatus(row["validation_status"]),
                StepExecutionStatus(row["execution_status"]), result,
                (), (), from_timestamp(row["completed_at"]) if row["completed_at"] else None,
            )
            investigation.record_step(step)

    @staticmethod
    def _load_evidence(connection: sqlite3.Connection, investigation: Investigation) -> None:
        for row in connection.execute(
            "SELECT * FROM observations WHERE investigation_id = ? ORDER BY created_at", (str(investigation.investigation_id),)
        ):
            investigation.record_observation(observation_from_row(row))
        for row in connection.execute(
            "SELECT * FROM deterministic_analyses WHERE investigation_id = ? ORDER BY created_at", (str(investigation.investigation_id),)
        ):
            investigation.record_analysis(analysis_from_row(row))

    @staticmethod
    def _load_hypotheses_and_findings(connection: sqlite3.Connection, investigation: Investigation) -> None:
        for row in connection.execute(
            "SELECT * FROM hypotheses WHERE investigation_id = ? ORDER BY created_at", (str(investigation.investigation_id),)
        ):
            investigation.record_hypothesis(
                Hypothesis(
                    HypothesisId(row["hypothesis_id"]), investigation.investigation_id, row["statement"],
                    evidence_for(connection, "hypothesis_evidence", row["hypothesis_id"]),
                    HypothesisStatus(row["status"]), row["confidence"], bool(row["significant_evidence_gap"]),
                    bool(row["causal_claim"]), bool(row["temporal_correlation_only"]),
                )
            )
        for row in connection.execute(
            "SELECT * FROM findings WHERE investigation_id = ? ORDER BY created_at", (str(investigation.investigation_id),)
        ):
            investigation.record_finding(
                Finding(
                    FindingId(row["finding_id"]), investigation.investigation_id, row["statement"],
                    evidence_for(connection, "finding_evidence", row["finding_id"]), row["confidence"],
                    bool(row["significant_evidence_gap"]), bool(row["causal_claim"]),
                    bool(row["temporal_correlation_only"]),
                )
            )
