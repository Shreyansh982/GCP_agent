"""Domain vocabulary for deterministic investigation-quality evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from gcp_observability_agent.domain.common.ids import InvestigationId
from gcp_observability_agent.domain.evidence.models import SupportLevel
from gcp_observability_agent.domain.investigation.models import (
    InvestigationScope,
    OutcomeStatus,
    TemporalContext,
    TerminationReason,
)


def _frozen_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


class EvaluationClassification(StrEnum):
    """Deterministic classification of one evaluation criterion outcome."""

    CORRECT = "CORRECT"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    UNSAFE = "UNSAFE"
    IRRELEVANT = "IRRELEVANT"
    TOOL_MISUSE = "TOOL_MISUSE"
    CONTRADICTION_MISSED = "CONTRADICTION_MISSED"
    NO_DATA = "NO_DATA"


class EvaluationCriterionKind(StrEnum):
    """Scenario expectations that a later deterministic evaluator may assess."""

    MUST_QUERY = "MUST_QUERY"
    MUST_NOT_QUERY = "MUST_NOT_QUERY"
    REQUIRED_EVIDENCE = "REQUIRED_EVIDENCE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    MISSING_DATA = "MISSING_DATA"
    MUST_NOT_CLAIM = "MUST_NOT_CLAIM"
    EXPECTED_SUPPORT_LEVEL = "EXPECTED_SUPPORT_LEVEL"
    EXPECTED_TERMINAL_OUTCOME = "EXPECTED_TERMINAL_OUTCOME"


@dataclass(frozen=True, slots=True)
class ExpectedTerminalOutcome:
    """Existing terminal semantics expected by an evaluation criterion."""

    status: OutcomeStatus
    termination_reason: TerminationReason | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCriterion:
    """One externally defined, deterministic expectation for an investigation."""

    criterion_id: str
    kind: EvaluationCriterionKind
    target: str | None = None
    expected_support_level: SupportLevel | None = None
    expected_terminal_outcome: ExpectedTerminalOutcome | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "criterion_id")
        if self.kind is EvaluationCriterionKind.EXPECTED_TERMINAL_OUTCOME:
            if self.target is not None:
                raise ValueError("expected terminal outcome criteria must not have a target")
            if self.expected_terminal_outcome is None:
                raise ValueError("expected terminal outcome criteria require an expected terminal outcome")
        else:
            if self.target is None:
                raise ValueError("evaluation criteria require a target")
            _require_text(self.target, "target")
            if self.expected_terminal_outcome is not None:
                raise ValueError("only expected terminal outcome criteria may define a terminal outcome")

        if self.kind is EvaluationCriterionKind.EXPECTED_SUPPORT_LEVEL:
            if self.expected_support_level is None:
                raise ValueError("expected support level criteria require a support level")
        elif self.expected_support_level is not None:
            raise ValueError("only expected support level criteria may define a support level")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class EvaluationScenario:
    """External scenario specification for a future deterministic evaluation run."""

    scenario_id: str
    version: str
    question: str
    telemetry_fixture_id: str
    scope: InvestigationScope
    temporal_context: TemporalContext
    criteria: tuple[EvaluationCriterion, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.scenario_id, "scenario_id"),
            (self.version, "version"),
            (self.question, "question"),
            (self.telemetry_fixture_id, "telemetry_fixture_id"),
        ):
            _require_text(value, field_name)
        criteria = tuple(self.criteria)
        if not criteria:
            raise ValueError("an evaluation scenario requires at least one criterion")
        criterion_ids = [criterion.criterion_id for criterion in criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("evaluation scenario criterion IDs must be unique")
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class EvaluationCriterionOutcome:
    """The raw, inspectable result of evaluating one criterion."""

    criterion_id: str
    classification: EvaluationClassification
    passed: bool
    reason: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "criterion_id")
        if self.passed != (self.classification is EvaluationClassification.CORRECT):
            raise ValueError("only CORRECT criterion outcomes may pass")
        if not self.passed:
            _require_text(self.reason, "reason")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Complete deterministic evaluation output for one investigation and scenario."""

    scenario: EvaluationScenario
    investigation_id: InvestigationId
    criterion_outcomes: tuple[EvaluationCriterionOutcome, ...]

    def __post_init__(self) -> None:
        outcomes = tuple(self.criterion_outcomes)
        outcome_ids = [outcome.criterion_id for outcome in outcomes]
        if len(set(outcome_ids)) != len(outcome_ids):
            raise ValueError("evaluation result criterion outcomes must be unique")
        expected_ids = {criterion.criterion_id for criterion in self.scenario.criteria}
        if set(outcome_ids) != expected_ids:
            raise ValueError("evaluation result must contain exactly one outcome for every scenario criterion")
        object.__setattr__(self, "criterion_outcomes", outcomes)

    @property
    def passed(self) -> bool:
        return all(outcome.passed for outcome in self.criterion_outcomes)

    @property
    def classifications(self) -> frozenset[EvaluationClassification]:
        return frozenset(outcome.classification for outcome in self.criterion_outcomes)
