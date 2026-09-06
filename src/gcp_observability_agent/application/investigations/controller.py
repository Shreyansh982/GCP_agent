"""Controller-owned, bounded investigation execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from gcp_observability_agent.application.investigations.tools import (
    ConcludeInvestigationArguments,
    FindingArguments,
    HypothesisArguments,
    ToolExecutionContext,
    ToolRegistry,
    ToolResponse,
)
from gcp_observability_agent.domain.common.ids import FindingId, HypothesisId, InvestigationStepId, ToolResultId
from gcp_observability_agent.domain.evidence.models import EvidenceReference, Finding, Hypothesis
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationOutcome,
    InvestigationStatus,
    InvestigationStep,
    OutcomeStatus,
    StepExecutionStatus,
    TerminationReason,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
    ValidationStatus,
)
from gcp_observability_agent.domain.ports import InvestigationRepository, LLMProvider


@dataclass(frozen=True, slots=True)
class ControllerPolicy:
    max_actions: int = 12
    max_duration: timedelta = timedelta(minutes=5)
    max_llm_retries: int = 1
    max_tool_retries: int = 1


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    max_evidence: int = 50
    max_prior_results: int = 12


class ContextBuilder:
    """Builds fresh, bounded state for each LLM action request."""

    def __init__(self, policy: ContextPolicy = ContextPolicy()) -> None:
        self._policy = policy

    def build(self, investigation: Investigation, *, remaining_actions: int) -> Mapping[str, object]:
        required_ids = {
            reference.evidence_id
            for item in (*investigation.hypotheses, *investigation.findings)
            for reference in item.evidence
        }
        evidence = [*investigation.observations, *investigation.analyses]
        required = [item for item in evidence if item.evidence_id in required_ids]
        optional = [item for item in evidence if item.evidence_id not in required_ids]
        optional_capacity = max(0, self._policy.max_evidence - len(required))
        selected = [*required, *(optional[-optional_capacity:] if optional_capacity else [])]
        observations = [self._observation(item) for item in selected if hasattr(item, "observation_id")]
        analyses = [self._analysis(item) for item in selected if hasattr(item, "analysis_id")]

        return {
            "instructions": {"telemetry_is_untrusted_data": True},
            "investigation": {
                "investigation_id": str(investigation.investigation_id),
                "question": investigation.question,
                "scope": self._scope(investigation),
                "interval": {
                    "start_time": investigation.temporal_context.resolved_interval.start_time.isoformat(),
                    "end_time": investigation.temporal_context.resolved_interval.end_time.isoformat(),
                },
            },
            "evidence": {"observations": observations, "analyses": analyses},
            "hypotheses": [self._hypothesis(item) for item in investigation.hypotheses],
            "findings": [self._finding(item) for item in investigation.findings],
            "prior_tool_results": [self._result(step) for step in investigation.steps[-self._policy.max_prior_results :]],
            "constraints": {
                "remaining_actions": max(remaining_actions, 0),
                "available_tools": [
                    "search_metric_descriptors", "query_metric", "list_resources", "get_alerts", "conclude_investigation",
                ],
            },
        }

    @staticmethod
    def _scope(investigation: Investigation) -> dict[str, object]:
        scope = investigation.scope
        return {
            "project_id": str(scope.project_id) if scope.project_id else None,
            "service": scope.service,
            "environment": scope.environment,
            "resource_type": str(scope.resource_type) if scope.resource_type else None,
            "resource_id": str(scope.resource_id) if scope.resource_id else None,
        }

    @staticmethod
    def _observation(item) -> dict[str, object]:
        return {
            "evidence_id": item.evidence_id,
            "statement": item.statement,
            "metric_type": str(item.metric_type) if item.metric_type else None,
            "resource_id": str(item.resource_id) if item.resource_id else None,
            "numeric_value": item.numeric_value,
            "unit": item.unit,
            "interval": ({"start_time": item.interval.start_time.isoformat(), "end_time": item.interval.end_time.isoformat()} if item.interval else None),
        }

    @staticmethod
    def _analysis(item) -> dict[str, object]:
        return {"evidence_id": item.evidence_id, "operation": item.operation, "result": item.result, "unit": item.unit}

    @staticmethod
    def _hypothesis(item: Hypothesis) -> dict[str, object]:
        return {"statement": item.statement, "status": item.status.value, "support_level": item.support_level.value, "evidence": [reference.evidence_id for reference in item.evidence]}

    @staticmethod
    def _finding(item: Finding) -> dict[str, object]:
        return {"statement": item.statement, "support_level": item.support_level.value, "evidence": [reference.evidence_id for reference in item.evidence]}

    @staticmethod
    def _result(step: InvestigationStep) -> dict[str, object]:
        result = step.tool_result
        return {
            "tool_name": step.tool_request.tool_name.value,
            "status": result.status.value if result else None,
            "warnings": list(result.warnings) if result else [],
            "error": dict(result.error) if result and result.error else None,
            "untrusted_tool_data": dict(result.data) if result else {},
        }


class _LLMFailure:
    pass


class InvestigationController:
    """Coordinates LLM proposals, registered tools, domain transitions, and persistence."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        repository: InvestigationRepository,
        allowed_projects: frozenset[str],
        *,
        context_builder: ContextBuilder | None = None,
        policy: ControllerPolicy = ControllerPolicy(),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._repository = repository
        self._allowed_projects = allowed_projects
        self._context_builder = context_builder or ContextBuilder()
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self, investigation: Investigation) -> Investigation:
        if investigation.status is InvestigationStatus.TERMINAL:
            return investigation
        version = self._repository.save(investigation)
        if investigation.status is InvestigationStatus.CREATED:
            investigation.start()
            version = self._repository.save(investigation, expected_version=version)

        started_at = self._clock()
        while investigation.status is InvestigationStatus.RUNNING:
            if len(investigation.steps) >= self._policy.max_actions:
                return self._terminate(investigation, version, OutcomeStatus.PARTIAL, TerminationReason.MAX_TOOL_CALLS)
            if self._clock() - started_at >= self._policy.max_duration:
                return self._terminate(investigation, version, OutcomeStatus.PARTIAL, TerminationReason.MAX_DURATION)

            action = self._next_action(investigation)
            if isinstance(action, _LLMFailure):
                return self._terminate(investigation, version, OutcomeStatus.FAILED, TerminationReason.LLM_FAILURE)
            if not isinstance(action, ToolRequest):
                return self._terminate(investigation, version, OutcomeStatus.FAILED, TerminationReason.VALIDATION_FAILURE)

            step = InvestigationStep(
                InvestigationStepId.new(), len(investigation.steps) + 1, action, self._clock()
            )
            investigation.record_step(step)
            response = self._execute(action, investigation, step.step_id)
            completed = step.complete(
                validation_status=self._validation_status(response),
                execution_status=self._execution_status(response),
                completed_at=self._clock(),
                tool_result=self._tool_result(action, response),
                derived_observation_ids=tuple(
                    observation.observation_id for observation in investigation.observations if observation.step_id == step.step_id
                ),
            )
            investigation.complete_step(completed)
            version = self._repository.save(investigation, expected_version=version)

            if action.tool_name.value == "conclude_investigation" and response.status is ToolResultStatus.SUCCESS:
                self._ingest_conclusion(action, investigation)
                return self._persist_terminal(investigation, version)
            if response.status in {ToolResultStatus.TIMEOUT, ToolResultStatus.PROVIDER_ERROR, ToolResultStatus.SYSTEM_ERROR}:
                return self._terminate(investigation, version, OutcomeStatus.FAILED, TerminationReason.TOOL_FAILURE)
        return investigation

    def _next_action(self, investigation: Investigation) -> ToolRequest | object:
        context = self._context_builder.build(investigation, remaining_actions=self._policy.max_actions - len(investigation.steps))
        for attempt in range(self._policy.max_llm_retries + 1):
            try:
                return self._llm.next_action(context)
            except TimeoutError:
                if attempt == self._policy.max_llm_retries:
                    return _LLMFailure()
            except Exception:
                return _LLMFailure()
        return _LLMFailure()

    def _execute(self, action: ToolRequest, investigation: Investigation, step_id: InvestigationStepId) -> ToolResponse:
        raw_action = {"request_id": str(action.request_id), "tool_name": action.tool_name.value, "arguments": dict(action.arguments)}
        context = ToolExecutionContext(investigation, self._allowed_projects, step_id)
        response = self._tools.execute(raw_action, context)
        for _ in range(self._policy.max_tool_retries):
            if not response.error or not response.error.retryable:
                break
            response = self._tools.execute(raw_action, context, replay=False)
        return response

    @staticmethod
    def _tool_result(action: ToolRequest, response: ToolResponse) -> ToolResult:
        return ToolResult(
            ToolResultId.new(), action.request_id, action.tool_name, response.status,
            response.data, response.warnings,
            response.error.model_dump(mode="json") if response.error else None, response.provenance,
        )

    @staticmethod
    def _validation_status(response: ToolResponse) -> ValidationStatus:
        return ValidationStatus.REJECTED if response.status in {ToolResultStatus.INVALID_REQUEST, ToolResultStatus.POLICY_REJECTED} else ValidationStatus.VALID

    @staticmethod
    def _execution_status(response: ToolResponse) -> StepExecutionStatus:
        if response.status in {ToolResultStatus.INVALID_REQUEST, ToolResultStatus.POLICY_REJECTED}:
            return StepExecutionStatus.REJECTED
        if response.status in {ToolResultStatus.TIMEOUT, ToolResultStatus.PROVIDER_ERROR, ToolResultStatus.SYSTEM_ERROR}:
            return StepExecutionStatus.FAILED
        return StepExecutionStatus.EXECUTED

    def _ingest_conclusion(self, action: ToolRequest, investigation: Investigation) -> None:
        arguments = ConcludeInvestigationArguments.model_validate(action.arguments)
        for candidate in arguments.hypotheses:
            investigation.record_hypothesis(self._hypothesis(candidate, investigation))
        for candidate in arguments.findings:
            investigation.record_finding(self._finding(candidate, investigation))
        outcome_status = OutcomeStatus.COMPLETED if arguments.findings else OutcomeStatus.INSUFFICIENT_EVIDENCE
        summary = arguments.findings[0].statement if arguments.findings else "Available evidence is insufficient for a supported finding."
        investigation.conclude(InvestigationOutcome(outcome_status, TerminationReason.SUFFICIENT_EVIDENCE, summary, arguments.unresolved_questions))

    @staticmethod
    def _references(candidate: FindingArguments) -> tuple[EvidenceReference, ...]:
        return tuple(EvidenceReference(reference.evidence_id, reference.relationship) for reference in candidate.evidence)

    def _finding(self, candidate: FindingArguments, investigation: Investigation) -> Finding:
        return Finding(FindingId.new(), investigation.investigation_id, candidate.statement, self._references(candidate), candidate.confidence, candidate.significant_evidence_gap, candidate.causal_claim, candidate.temporal_correlation_only)

    def _hypothesis(self, candidate: HypothesisArguments, investigation: Investigation) -> Hypothesis:
        return Hypothesis(HypothesisId.new(), investigation.investigation_id, candidate.statement, self._references(candidate), candidate.status, candidate.confidence, candidate.significant_evidence_gap, candidate.causal_claim, candidate.temporal_correlation_only)

    def _terminate(self, investigation: Investigation, version: int, status: OutcomeStatus, reason: TerminationReason) -> Investigation:
        investigation.conclude(InvestigationOutcome(status, reason))
        return self._persist_terminal(investigation, version)

    def _persist_terminal(self, investigation: Investigation, version: int) -> Investigation:
        self._repository.save(investigation, expected_version=version)
        return investigation
