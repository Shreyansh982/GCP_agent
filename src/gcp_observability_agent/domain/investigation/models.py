"""The investigation aggregate, lifecycle, and provider-neutral tool records."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from gcp_observability_agent.domain.common.errors import DomainRuleViolation
from gcp_observability_agent.domain.common.ids import (
    AnalysisId,
    FindingId,
    HypothesisId,
    InvestigationId,
    InvestigationStepId,
    ObservationId,
    ToolRequestId,
    ToolResultId,
)
from gcp_observability_agent.domain.common.time import TimeInterval, normalized_utc
from gcp_observability_agent.domain.evidence.models import (
    DeterministicAnalysis,
    Finding,
    Hypothesis,
    Observation,
    SupportLevel,
)
from gcp_observability_agent.domain.telemetry.models import ProjectId, ResourceId, ResourceType


def _frozen_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


class InvestigationStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    TERMINAL = "TERMINAL"


class OutcomeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class TerminationReason(StrEnum):
    SUFFICIENT_EVIDENCE = "SUFFICIENT_EVIDENCE"
    MAX_TOOL_CALLS = "MAX_TOOL_CALLS"
    MAX_DURATION = "MAX_DURATION"
    NO_NEW_EVIDENCE = "NO_NEW_EVIDENCE"
    TOOL_FAILURE = "TOOL_FAILURE"
    LLM_FAILURE = "LLM_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class ToolName(StrEnum):
    SEARCH_METRIC_DESCRIPTORS = "search_metric_descriptors"
    QUERY_METRIC = "query_metric"
    LIST_RESOURCES = "list_resources"
    GET_ALERTS = "get_alerts"
    CONCLUDE_INVESTIGATION = "conclude_investigation"


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    NO_DATA = "no_data"
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    POLICY_REJECTED = "policy_rejected"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    SYSTEM_ERROR = "system_error"


class ValidationStatus(StrEnum):
    PENDING = "PENDING"
    VALID = "VALID"
    REJECTED = "REJECTED"


class StepExecutionStatus(StrEnum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class InvestigationScope:
    """Authorized operational scope, without provider-specific filter syntax."""

    project_id: ProjectId | None = None
    service: str | None = None
    environment: str | None = None
    resource_type: ResourceType | None = None
    resource_id: ResourceId | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("service", "environment"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TemporalContext:
    """Application-authoritative time context for an investigation."""

    reference_time: datetime
    resolved_interval: TimeInterval
    timezone: str = "UTC"
    requested_expression: str | None = None

    def __post_init__(self) -> None:
        if not self.timezone.strip():
            raise ValueError("timezone must not be blank")
        if self.requested_expression is not None and not self.requested_expression.strip():
            raise ValueError("requested_expression must not be blank")
        object.__setattr__(self, "reference_time", normalized_utc(self.reference_time))


@dataclass(frozen=True, slots=True)
class ToolRequest:
    request_id: ToolRequestId
    tool_name: ToolName
    arguments: Mapping[str, object]
    requested_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _frozen_mapping(self.arguments))
        object.__setattr__(self, "requested_at", normalized_utc(self.requested_at))


@dataclass(frozen=True, slots=True)
class ToolResult:
    result_id: ToolResultId
    request_id: ToolRequestId
    tool_name: ToolName
    status: ToolResultStatus
    data: Mapping[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: Mapping[str, object] | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _frozen_mapping(self.data))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.error is not None:
            object.__setattr__(self, "error", _frozen_mapping(self.error))
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class InvestigationStep:
    step_id: InvestigationStepId
    sequence_number: int
    tool_request: ToolRequest
    started_at: datetime
    validation_status: ValidationStatus = ValidationStatus.PENDING
    execution_status: StepExecutionStatus = StepExecutionStatus.PENDING
    tool_result: ToolResult | None = None
    derived_observation_ids: tuple[ObservationId, ...] = ()
    derived_analysis_ids: tuple[AnalysisId, ...] = ()
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if self.tool_result is not None and self.tool_result.request_id != self.tool_request.request_id:
            raise ValueError("tool result must belong to the step's tool request")
        object.__setattr__(self, "started_at", normalized_utc(self.started_at))
        if self.completed_at is not None:
            completed_at = normalized_utc(self.completed_at)
            if completed_at < self.started_at:
                raise ValueError("completed_at must not precede started_at")
            object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(self, "derived_observation_ids", tuple(self.derived_observation_ids))
        object.__setattr__(self, "derived_analysis_ids", tuple(self.derived_analysis_ids))

    def complete(
        self,
        *,
        validation_status: ValidationStatus,
        execution_status: StepExecutionStatus,
        completed_at: datetime,
        tool_result: ToolResult | None = None,
        derived_observation_ids: tuple[ObservationId, ...] = (),
        derived_analysis_ids: tuple[AnalysisId, ...] = (),
    ) -> "InvestigationStep":
        return replace(
            self,
            validation_status=validation_status,
            execution_status=execution_status,
            completed_at=completed_at,
            tool_result=tool_result,
            derived_observation_ids=derived_observation_ids,
            derived_analysis_ids=derived_analysis_ids,
        )


@dataclass(frozen=True, slots=True)
class InvestigationOutcome:
    status: OutcomeStatus
    termination_reason: TerminationReason
    response_summary: str = ""
    unresolved_questions: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "unresolved_questions", tuple(self.unresolved_questions))
        object.__setattr__(self, "missing_evidence", tuple(self.missing_evidence))


class Investigation:
    """The mutable aggregate that enforces investigation lifecycle and evidence ownership."""

    __slots__ = (
        "_investigation_id",
        "_question",
        "_scope",
        "_temporal_context",
        "_status",
        "_steps",
        "_observations",
        "_analyses",
        "_hypotheses",
        "_findings",
        "_outcome",
    )

    def __init__(
        self,
        investigation_id: InvestigationId,
        question: str,
        scope: InvestigationScope,
        temporal_context: TemporalContext,
    ) -> None:
        if not question.strip():
            raise ValueError("investigation question must not be empty")
        self._investigation_id = investigation_id
        self._question = question
        self._scope = scope
        self._temporal_context = temporal_context
        self._status = InvestigationStatus.CREATED
        self._steps: list[InvestigationStep] = []
        self._observations: dict[str, Observation] = {}
        self._analyses: dict[str, DeterministicAnalysis] = {}
        self._hypotheses: dict[HypothesisId, Hypothesis] = {}
        self._findings: dict[FindingId, Finding] = {}
        self._outcome: InvestigationOutcome | None = None

    @classmethod
    def create(
        cls,
        question: str,
        scope: InvestigationScope,
        temporal_context: TemporalContext,
    ) -> "Investigation":
        return cls(InvestigationId.new(), question, scope, temporal_context)

    @property
    def investigation_id(self) -> InvestigationId:
        return self._investigation_id

    @property
    def question(self) -> str:
        return self._question

    @property
    def scope(self) -> InvestigationScope:
        return self._scope

    @property
    def temporal_context(self) -> TemporalContext:
        return self._temporal_context

    @property
    def status(self) -> InvestigationStatus:
        return self._status

    @property
    def steps(self) -> tuple[InvestigationStep, ...]:
        return tuple(self._steps)

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._observations.values())

    @property
    def analyses(self) -> tuple[DeterministicAnalysis, ...]:
        return tuple(self._analyses.values())

    @property
    def hypotheses(self) -> tuple[Hypothesis, ...]:
        return tuple(self._hypotheses.values())

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings.values())

    @property
    def outcome(self) -> InvestigationOutcome | None:
        return self._outcome

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset((*self._observations, *self._analyses))

    def start(self) -> None:
        if self._status is not InvestigationStatus.CREATED:
            raise DomainRuleViolation("only a created investigation can start")
        self._status = InvestigationStatus.RUNNING

    def record_step(self, step: InvestigationStep) -> None:
        self._require_running()
        if step.sequence_number != len(self._steps) + 1:
            raise DomainRuleViolation("investigation steps must have monotonic sequence numbers")
        self._steps.append(step)

    def complete_step(self, step: InvestigationStep) -> None:
        """Finalize the most recently recorded action without rewriting history."""
        self._require_running()
        if not self._steps or self._steps[-1].step_id != step.step_id:
            raise DomainRuleViolation("only the current investigation step can be completed")
        if self._steps[-1].completed_at is not None:
            raise DomainRuleViolation("an investigation step cannot be completed twice")
        if step.completed_at is None or step.tool_result is None:
            raise DomainRuleViolation("a completed step requires a result and completion time")
        self._steps[-1] = step

    def record_observation(self, observation: Observation) -> None:
        self._require_running()
        if observation.investigation_id != self.investigation_id:
            raise DomainRuleViolation("observation belongs to a different investigation")
        if observation.evidence_id in self.evidence_ids:
            raise DomainRuleViolation("evidence IDs must be unique within an investigation")
        self._observations[observation.evidence_id] = observation

    def record_analysis(self, analysis: DeterministicAnalysis) -> None:
        self._require_running()
        if analysis.investigation_id != self.investigation_id:
            raise DomainRuleViolation("analysis belongs to a different investigation")
        if any(evidence_id not in self.evidence_ids for evidence_id in analysis.input_evidence_ids):
            raise DomainRuleViolation("analysis inputs must be existing investigation evidence")
        if analysis.evidence_id in self.evidence_ids:
            raise DomainRuleViolation("evidence IDs must be unique within an investigation")
        self._analyses[analysis.evidence_id] = analysis

    def record_hypothesis(self, hypothesis: Hypothesis) -> None:
        self._require_running()
        if hypothesis.investigation_id != self.investigation_id:
            raise DomainRuleViolation("hypothesis belongs to a different investigation")
        self._validate_evidence_references(hypothesis.evidence)
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    def record_finding(self, finding: Finding) -> None:
        self._require_running()
        if finding.investigation_id != self.investigation_id:
            raise DomainRuleViolation("finding belongs to a different investigation")
        self._validate_evidence_references(finding.evidence)
        if finding.support_level is SupportLevel.UNSUPPORTED:
            raise DomainRuleViolation("a finding requires valid supporting evidence")
        self._findings[finding.finding_id] = finding

    def conclude(self, outcome: InvestigationOutcome) -> None:
        self._require_running()
        self._outcome = outcome
        self._status = InvestigationStatus.TERMINAL

    def _validate_evidence_references(self, references: tuple) -> None:
        for reference in references:
            if reference.evidence_id not in self.evidence_ids:
                raise DomainRuleViolation(
                    f"evidence reference {reference.evidence_id!r} does not exist in this investigation"
                )

    def _require_running(self) -> None:
        if self._status is not InvestigationStatus.RUNNING:
            raise DomainRuleViolation("investigation is not running")
