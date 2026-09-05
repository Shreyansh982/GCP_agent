from __future__ import annotations

import pytest

from gcp_observability_agent.domain.investigation.models import InvestigationStatus, OutcomeStatus
from gcp_observability_agent.infrastructure.persistence.sqlite.errors import ConcurrencyConflict


def test_repository_round_trips_complete_auditable_investigation(repository, investigation) -> None:
    version = repository.save(investigation)
    loaded = repository.get(investigation.investigation_id)

    assert version == 1
    assert loaded is not None
    assert loaded.status is InvestigationStatus.TERMINAL
    assert loaded.outcome is not None and loaded.outcome.status is OutcomeStatus.COMPLETED
    assert loaded.question == investigation.question
    assert len(loaded.steps) == len(loaded.observations) == len(loaded.analyses) == 1
    assert len(loaded.hypotheses) == len(loaded.findings) == 1
    assert loaded.evidence_ids == investigation.evidence_ids
    assert loaded.steps[0].tool_result is not None


def test_repository_uses_optimistic_versions(repository, investigation) -> None:
    assert repository.save(investigation) == 1
    with pytest.raises(ConcurrencyConflict):
        repository.save(investigation, expected_version=0)
    assert repository.version_for(investigation.investigation_id) == 1
    assert repository.save(investigation, expected_version=1) == 2
    assert repository.version_for(investigation.investigation_id) == 2


def test_missing_investigation_returns_none(repository, investigation) -> None:
    assert repository.get(investigation.investigation_id) is None
    assert repository.version_for(investigation.investigation_id) is None

