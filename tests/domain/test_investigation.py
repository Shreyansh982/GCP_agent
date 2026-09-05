from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gcp_observability_agent.domain.common.errors import DomainRuleViolation
from gcp_observability_agent.domain.common.ids import (
    AnalysisId,
    FindingId,
    HypothesisId,
    InvestigationStepId,
    ObservationId,
    ToolRequestId,
    ToolResultId,
)
from gcp_observability_agent.domain.evidence.models import (
    DeterministicAnalysis,
    EvidenceReference,
    EvidenceRelationship,
    Finding,
    Hypothesis,
    Observation,
    SupportLevel,
)
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationOutcome,
    InvestigationStatus,
    InvestigationStep,
    OutcomeStatus,
    StepExecutionStatus,
    TerminationReason,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
    ValidationStatus,
)


def _now() -> datetime:
    return datetime(2026, 8, 27, 14, tzinfo=UTC)


def _observation(investigation: Investigation) -> Observation:
    return Observation(
        ObservationId.new(), investigation.investigation_id, "Latency reached 870 ms.", provenance={"source": "metric"}
    )


def test_lifecycle_requires_start_and_keeps_original_question_immutable(investigation: Investigation) -> None:
    assert investigation.status is InvestigationStatus.CREATED
    with pytest.raises(DomainRuleViolation):
        investigation.conclude(InvestigationOutcome(OutcomeStatus.COMPLETED, TerminationReason.SUFFICIENT_EVIDENCE))

    investigation.start()
    with pytest.raises(AttributeError):
        investigation.question = "A replacement question"  # type: ignore[misc]
    assert investigation.question == "Why did payments become slow?"

    investigation.conclude(InvestigationOutcome(OutcomeStatus.COMPLETED, TerminationReason.SUFFICIENT_EVIDENCE))
    assert investigation.status is InvestigationStatus.TERMINAL
    assert investigation.outcome is not None
    with pytest.raises(DomainRuleViolation):
        investigation.record_observation(_observation(investigation))


def test_steps_are_ordered_and_tool_result_must_match_request(investigation: Investigation) -> None:
    investigation.start()
    request = ToolRequest(ToolRequestId.new(), ToolName.QUERY_METRIC, {}, _now())
    step = InvestigationStep(InvestigationStepId.new(), 1, request, _now())
    investigation.record_step(step)

    with pytest.raises(DomainRuleViolation, match="monotonic"):
        investigation.record_step(InvestigationStep(InvestigationStepId.new(), 3, request, _now()))
    wrong_result = ToolResult(ToolResultId.new(), ToolRequestId.new(), ToolName.QUERY_METRIC, ToolResultStatus.SUCCESS)
    with pytest.raises(ValueError, match="belong"):
        step.complete(
            validation_status=ValidationStatus.VALID,
            execution_status=StepExecutionStatus.EXECUTED,
            completed_at=_now(),
            tool_result=wrong_result,
        )


def test_evidence_is_investigation_scoped_unique_and_analysis_is_reproducible(investigation: Investigation) -> None:
    investigation.start()
    observation = _observation(investigation)
    investigation.record_observation(observation)
    with pytest.raises(DomainRuleViolation, match="unique"):
        investigation.record_observation(observation)

    analysis = DeterministicAnalysis(
        AnalysisId.new(), investigation.investigation_id, "maximum", (observation.evidence_id,), 870.0
    )
    investigation.record_analysis(analysis)
    assert investigation.evidence_ids == frozenset({observation.evidence_id, analysis.evidence_id})

    missing_input = DeterministicAnalysis(
        AnalysisId.new(), investigation.investigation_id, "mean", ("obs-missing",), 0.0
    )
    with pytest.raises(DomainRuleViolation, match="inputs"):
        investigation.record_analysis(missing_input)


def test_cross_investigation_evidence_and_fabricated_evidence_are_rejected(investigation: Investigation, interval) -> None:
    investigation.start()
    other = Investigation.create("Other question", investigation.scope, investigation.temporal_context)
    other.start()
    observation = _observation(other)
    other.record_observation(observation)

    finding = Finding(
        FindingId.new(), investigation.investigation_id, "Latency increased.", (EvidenceReference(observation.evidence_id),)
    )
    with pytest.raises(DomainRuleViolation, match="does not exist"):
        investigation.record_finding(finding)

    fabricated = Hypothesis(
        HypothesisId.new(), investigation.investigation_id, "CPU may be involved.", (EvidenceReference("obs-999"),)
    )
    with pytest.raises(DomainRuleViolation, match="does not exist"):
        investigation.record_hypothesis(fabricated)


def test_finding_requires_support_and_preserves_contradictory_evidence(investigation: Investigation) -> None:
    investigation.start()
    supporting = _observation(investigation)
    contradicting = _observation(investigation)
    investigation.record_observation(supporting)
    investigation.record_observation(contradicting)

    unsupported = Finding(FindingId.new(), investigation.investigation_id, "CPU caused latency.", ())
    with pytest.raises(DomainRuleViolation, match="supporting"):
        investigation.record_finding(unsupported)

    partial = Finding(
        FindingId.new(),
        investigation.investigation_id,
        "CPU coincided with latency.",
        (
            EvidenceReference(supporting.evidence_id),
            EvidenceReference(contradicting.evidence_id, EvidenceRelationship.CONTRADICTING),
        ),
    )
    investigation.record_finding(partial)
    assert partial.support_level is SupportLevel.PARTIALLY_SUPPORTED
    assert partial.evidence[1].relationship is EvidenceRelationship.CONTRADICTING

