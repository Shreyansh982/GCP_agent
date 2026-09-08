from __future__ import annotations

from gcp_observability_agent.application.investigations.service import (
    InvestigationApplicationService,
    InvestigationSubmission,
)


class _RecordingController:
    def __init__(self) -> None:
        self.investigation = None

    def run(self, investigation):
        self.investigation = investigation
        return investigation


def test_presentation_submission_is_converted_inside_the_application_layer() -> None:
    controller = _RecordingController()
    service = InvestigationApplicationService(controller)  # type: ignore[arg-type]

    service.investigate_submission(
        InvestigationSubmission(
            question="Why did payments become slow?",
            project_id="project-a",
            service="payments",
            environment="production",
            start_time="2026-08-27T14:00:00Z",
            end_time="2026-08-27T15:00:00Z",
        )
    )

    assert str(controller.investigation.scope.project_id) == "project-a"
    assert controller.investigation.scope.service == "payments"
    assert controller.investigation.temporal_context.resolved_interval.start_time.isoformat() == "2026-08-27T14:00:00+00:00"
