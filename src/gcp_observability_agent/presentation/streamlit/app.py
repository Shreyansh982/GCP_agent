"""Phase 1 Streamlit presentation for completed investigations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import streamlit as st

from gcp_observability_agent.application.common.events import ProgressEvent, ProgressSink
from gcp_observability_agent.application.investigations.service import (
    InvestigationApplicationService,
    InvestigationSubmission,
)
from gcp_observability_agent.presentation.streamlit.rendering import (
    render_untrusted_text,
    safe_json,
)


ApplicationServiceFactory = Callable[[ProgressSink | None], InvestigationApplicationService]


def render(application_service_factory: ApplicationServiceFactory) -> None:
    """Render a single, application-owned investigation request and its audit record."""
    st.set_page_config(page_title="GCP investigation", page_icon="🔎", layout="wide")
    st.title("GCP observability investigation")
    st.caption("Bounded, evidence-backed investigation using the configured authorized scope.")

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with st.form("investigation-request"):
        question = st.text_area("Investigation question", max_chars=4000, placeholder="Why did a service become slow?")
        project_id = st.text_input("Project ID")
        left, right = st.columns(2)
        with left:
            service = st.text_input("Service (optional)")
            start_date = st.date_input("Start date (UTC)", value=(now - timedelta(hours=1)).date())
            start_clock = st.time_input("Start time (UTC)", value=(now - timedelta(hours=1)).time())
        with right:
            environment = st.text_input("Environment (optional)")
            end_date = st.date_input("End date (UTC)", value=now.date())
            end_clock = st.time_input("End time (UTC)", value=now.time())
        submitted = st.form_submit_button("Investigate")

    if not submitted:
        return
    if not question.strip():
        st.error("Enter an investigation question.")
        return

    submission = InvestigationSubmission(
        question=question,
        project_id=project_id,
        service=service,
        environment=environment,
        start_time=datetime.combine(start_date, start_clock, UTC).isoformat(),
        end_time=datetime.combine(end_date, end_clock, UTC).isoformat(),
    )
    with st.status("Investigation in progress", expanded=True) as status:
        try:
            result = application_service_factory(_progress_renderer(status)).investigate_submission(submission)
        except ValueError:
            status.update(label="Request could not be submitted", state="error")
            st.error("The request is invalid. Check the question and UTC time interval.")
            return
        except Exception:
            status.update(label="Investigation failed", state="error")
            st.error("The investigation could not be completed. Review the configured credentials and scope.")
            return
        status.update(label="Investigation finished", state="complete")
    _render_investigation(result)


def _progress_renderer(status) -> ProgressSink:
    def render_event(event: ProgressEvent) -> None:
        labels = {
            "investigation_started": "Investigation started",
            "step_started": "Validating and executing a tool",
            "tool_completed": "Tool completed",
            "evidence_created": "Evidence recorded",
            "investigation_concluded": "Finding generated",
            "investigation_terminated": "Investigation terminated",
        }
        status.write(labels.get(event.name, "Investigation progress updated"))

    return render_event


def _render_investigation(investigation) -> None:
    outcome = investigation.outcome
    st.subheader("Investigation status")
    status_columns = st.columns(3)
    status_columns[0].metric("Investigation", investigation.status.value)
    status_columns[1].metric("Outcome", outcome.status.value if outcome else "PENDING")
    status_columns[2].metric("Termination", outcome.termination_reason.value if outcome else "PENDING")
    render_untrusted_text(st.caption, f"Investigation ID: {investigation.investigation_id}")

    st.subheader("Findings")
    if investigation.findings:
        for finding in investigation.findings:
            with st.container(border=True):
                render_untrusted_text(st.text, finding.statement)
                st.caption(f"Support: {finding.support_level.value}")
                render_untrusted_text(st.text, f"Evidence: {', '.join(reference.evidence_id for reference in finding.evidence)}")
    else:
        st.info("No supported finding was produced.")

    st.subheader("Evidence")
    if investigation.observations or investigation.analyses:
        for observation in investigation.observations:
            with st.container(border=True):
                render_untrusted_text(st.text, observation.statement)
                render_untrusted_text(st.caption, f"Evidence ID: {observation.evidence_id}")
                st.code(safe_json(dict(observation.provenance)), language="json")
        for analysis in investigation.analyses:
            with st.container(border=True):
                render_untrusted_text(st.text, f"{analysis.operation}: {analysis.result}")
                render_untrusted_text(st.caption, f"Evidence ID: {analysis.evidence_id}")
    else:
        st.info("No evidence was recorded.")

    st.subheader("Uncertainty")
    uncertainty = list(outcome.unresolved_questions if outcome else ())
    uncertainty.extend(
        hypothesis.statement
        for hypothesis in investigation.hypotheses
        if hypothesis.status.value in {"OPEN", "WEAKENED", "REJECTED", "UNRESOLVED"}
    )
    uncertainty.extend(
        finding.statement
        for finding in investigation.findings
        if finding.support_level.value != "SUPPORTED"
    )
    if uncertainty:
        for item in uncertainty:
            render_untrusted_text(st.text, item)
    else:
        st.success("No unresolved questions were recorded.")

    st.subheader("Audit trail")
    for step in investigation.steps:
        with st.expander(f"Step {step.sequence_number}: {step.tool_request.tool_name.value}"):
            st.caption(
                f"Validation: {step.validation_status.value} · Execution: {step.execution_status.value}"
            )
            st.code(safe_json(dict(step.tool_request.arguments)), language="json")
            if step.tool_result:
                st.caption(f"Result: {step.tool_result.status.value}")
                st.code(safe_json(dict(step.tool_result.data)), language="json")
                if step.tool_result.warnings:
                    st.code(safe_json(list(step.tool_result.warnings)), language="json")
                if step.tool_result.error:
                    st.code(safe_json(dict(step.tool_result.error)), language="json")
