from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gcp_observability_agent.domain.common.ids import InvestigationId
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.evaluation.models import (
    EvaluationClassification,
    EvaluationCriterion,
    EvaluationCriterionKind,
    EvaluationCriterionOutcome,
    EvaluationResult,
    EvaluationScenario,
    ExpectedTerminalOutcome,
)
from gcp_observability_agent.domain.evidence.models import SupportLevel
from gcp_observability_agent.domain.investigation.models import (
    InvestigationScope,
    OutcomeStatus,
    TemporalContext,
    TerminationReason,
)
from gcp_observability_agent.domain.telemetry.models import ProjectId


def _scenario(*criteria: EvaluationCriterion) -> EvaluationScenario:
    interval = TimeInterval(datetime(2026, 8, 27, 14, tzinfo=UTC), datetime(2026, 8, 27, 15, tzinfo=UTC))
    return EvaluationScenario(
        "cpu-saturation", "v1", "Why did payments become slow?", "scenario_cpu_saturation",
        InvestigationScope(project_id=ProjectId("scenario_cpu_saturation"), service="payments"),
        TemporalContext(interval.end_time, interval), criteria,
        {"purpose": "deterministic evaluation"},
    )


def test_evaluation_scenario_represents_the_approved_future_expectation_types() -> None:
    criteria = (
        EvaluationCriterion("query-cpu", EvaluationCriterionKind.MUST_QUERY, "example.googleapis.com/cpu_utilization"),
        EvaluationCriterion("avoid-cause", EvaluationCriterionKind.MUST_NOT_CLAIM, "CPU definitively caused the outage."),
        EvaluationCriterion("cpu-evidence", EvaluationCriterionKind.REQUIRED_EVIDENCE, "cpu-elevated"),
        EvaluationCriterion("mixed-cpu", EvaluationCriterionKind.CONTRADICTORY_EVIDENCE, "cpu-evidence"),
        EvaluationCriterion("memory-missing", EvaluationCriterionKind.MISSING_DATA, "memory-utilization"),
        EvaluationCriterion("cpu-support", EvaluationCriterionKind.EXPECTED_SUPPORT_LEVEL, "CPU was elevated.", SupportLevel.SUPPORTED),
        EvaluationCriterion(
            "terminal", EvaluationCriterionKind.EXPECTED_TERMINAL_OUTCOME,
            expected_terminal_outcome=ExpectedTerminalOutcome(OutcomeStatus.COMPLETED, TerminationReason.SUFFICIENT_EVIDENCE),
        ),
    )

    scenario = _scenario(*criteria)

    assert scenario.criteria == criteria
    assert scenario.telemetry_fixture_id == "scenario_cpu_saturation"
    assert scenario.metadata["purpose"] == "deterministic evaluation"


@pytest.mark.parametrize(
    "build, message",
    [
        (lambda: EvaluationCriterion("query", EvaluationCriterionKind.MUST_QUERY), "require a target"),
        (lambda: EvaluationCriterion("support", EvaluationCriterionKind.EXPECTED_SUPPORT_LEVEL, "CPU"), "require a support level"),
        (lambda: EvaluationCriterion("terminal", EvaluationCriterionKind.EXPECTED_TERMINAL_OUTCOME), "require an expected terminal outcome"),
    ],
)
def test_evaluation_criteria_reject_incomplete_typed_expectations(build, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build()


def test_evaluation_scenario_requires_unique_nonempty_criteria() -> None:
    criterion = EvaluationCriterion("query-cpu", EvaluationCriterionKind.MUST_QUERY, "cpu")

    with pytest.raises(ValueError, match="at least one criterion"):
        _scenario()
    with pytest.raises(ValueError, match="must be unique"):
        _scenario(criterion, criterion)


def test_evaluation_classifications_are_distinct_from_existing_support_levels() -> None:
    unsupported = EvaluationCriterionOutcome(
        "cause", EvaluationClassification.UNSUPPORTED, False, "The causal claim lacks supporting evidence."
    )
    correct = EvaluationCriterionOutcome("query-cpu", EvaluationClassification.CORRECT, True)

    assert EvaluationClassification.UNSUPPORTED is not SupportLevel.UNSUPPORTED
    assert unsupported.classification.value == SupportLevel.UNSUPPORTED.value == "UNSUPPORTED"
    assert correct.passed
    with pytest.raises(ValueError, match="only CORRECT"):
        EvaluationCriterionOutcome("invalid", EvaluationClassification.UNSUPPORTED, True)


def test_evaluation_result_preserves_each_criterion_outcome_without_a_score() -> None:
    scenario = _scenario(
        EvaluationCriterion("query-cpu", EvaluationCriterionKind.MUST_QUERY, "cpu"),
        EvaluationCriterion("avoid-cause", EvaluationCriterionKind.MUST_NOT_CLAIM, "CPU caused the outage."),
    )
    outcomes = (
        EvaluationCriterionOutcome("query-cpu", EvaluationClassification.CORRECT, True),
        EvaluationCriterionOutcome("avoid-cause", EvaluationClassification.UNSUPPORTED, False, "Unsupported causal claim."),
    )

    result = EvaluationResult(scenario, InvestigationId.new(), outcomes)

    assert not result.passed
    assert result.criterion_outcomes == outcomes
    assert result.classifications == {EvaluationClassification.CORRECT, EvaluationClassification.UNSUPPORTED}
    with pytest.raises(ValueError, match="exactly one outcome"):
        EvaluationResult(scenario, InvestigationId.new(), outcomes[:1])
