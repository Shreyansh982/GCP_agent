CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE metric_descriptors (
    metric_type TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    unit TEXT,
    value_type TEXT,
    metric_kind TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE metric_descriptor_labels (
    metric_type TEXT NOT NULL REFERENCES metric_descriptors(metric_type),
    label_key TEXT NOT NULL,
    value_type TEXT,
    description TEXT,
    PRIMARY KEY (metric_type, label_key)
);

CREATE TABLE monitored_resources (
    resource_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    resource_type TEXT NOT NULL,
    display_name TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_monitored_resources_project_type ON monitored_resources(project_id, resource_type);

CREATE TABLE resource_labels (
    resource_id TEXT NOT NULL REFERENCES monitored_resources(resource_id),
    label_key TEXT NOT NULL,
    label_value TEXT NOT NULL,
    PRIMARY KEY (resource_id, label_key)
);
CREATE INDEX idx_resource_labels_key_value ON resource_labels(label_key, label_value);

CREATE TABLE metrics (
    metric_id TEXT PRIMARY KEY,
    metric_type TEXT NOT NULL REFERENCES metric_descriptors(metric_type),
    metadata_json TEXT
);

CREATE TABLE time_series (
    time_series_id TEXT PRIMARY KEY,
    metric_id TEXT NOT NULL REFERENCES metrics(metric_id),
    resource_id TEXT NOT NULL REFERENCES monitored_resources(resource_id),
    metric_labels_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX idx_time_series_metric_resource ON time_series(metric_id, resource_id);

CREATE TABLE data_points (
    data_point_id TEXT PRIMARY KEY,
    time_series_id TEXT NOT NULL REFERENCES time_series(time_series_id),
    timestamp TEXT,
    value_type TEXT NOT NULL,
    numeric_value REAL,
    string_value TEXT,
    boolean_value INTEGER,
    distribution_json TEXT,
    interval_json TEXT,
    CHECK ((timestamp IS NOT NULL) != (interval_json IS NOT NULL))
);
CREATE INDEX idx_data_points_series_timestamp ON data_points(time_series_id, timestamp);

CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    policy_reference TEXT,
    condition_text TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    resource_id TEXT REFERENCES monitored_resources(resource_id),
    metric_id TEXT REFERENCES metrics(metric_id),
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_alerts_project_start ON alerts(project_id, start_time);
CREATE INDEX idx_alerts_resource_start ON alerts(resource_id, start_time);

CREATE TABLE investigations (
    investigation_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED', 'RUNNING', 'TERMINAL')),
    reference_time TEXT NOT NULL,
    timezone TEXT NOT NULL,
    requested_expression TEXT,
    interval_start TEXT NOT NULL,
    interval_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    metadata_json TEXT,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE TABLE investigation_scopes (
    investigation_id TEXT PRIMARY KEY REFERENCES investigations(investigation_id),
    project_id TEXT REFERENCES projects(project_id),
    service TEXT,
    environment TEXT,
    resource_type TEXT,
    resource_id TEXT REFERENCES monitored_resources(resource_id),
    metadata_json TEXT
);

CREATE TABLE investigation_outcomes (
    investigation_id TEXT PRIMARY KEY REFERENCES investigations(investigation_id),
    outcome_status TEXT NOT NULL,
    termination_reason TEXT NOT NULL,
    response_summary TEXT NOT NULL,
    unresolved_questions_json TEXT NOT NULL,
    missing_evidence_json TEXT NOT NULL,
    persisted_at TEXT NOT NULL
);

CREATE TABLE investigation_steps (
    step_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    validation_status TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    metadata_json TEXT,
    UNIQUE (investigation_id, sequence_number)
);
CREATE INDEX idx_investigation_steps_order ON investigation_steps(investigation_id, sequence_number);

CREATE TABLE tool_requests (
    request_id TEXT PRIMARY KEY,
    step_id TEXT NOT NULL REFERENCES investigation_steps(step_id),
    tool_name TEXT NOT NULL,
    contract_version INTEGER NOT NULL DEFAULT 1,
    arguments_json TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    validation_status TEXT NOT NULL
);
CREATE INDEX idx_tool_requests_step_time ON tool_requests(step_id, requested_at);

CREATE TABLE tool_results (
    result_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES tool_requests(request_id),
    status TEXT NOT NULL,
    data_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    error_json TEXT,
    provenance_json TEXT NOT NULL,
    result_metadata_json TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX idx_tool_results_request ON tool_results(request_id);

CREATE TABLE observations (
    observation_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    step_id TEXT REFERENCES investigation_steps(step_id),
    observation_type TEXT NOT NULL DEFAULT 'telemetry',
    metric_type TEXT REFERENCES metric_descriptors(metric_type),
    resource_id TEXT REFERENCES monitored_resources(resource_id),
    time_series_id TEXT REFERENCES time_series(time_series_id),
    statement TEXT NOT NULL,
    numeric_value_json TEXT,
    unit TEXT,
    interval_start TEXT,
    interval_end TEXT,
    source_metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_observations_investigation_time ON observations(investigation_id, created_at);
CREATE INDEX idx_observations_metric_resource_time ON observations(metric_type, resource_id, interval_start);

CREATE TABLE deterministic_analyses (
    analysis_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    step_id TEXT REFERENCES investigation_steps(step_id),
    operation TEXT NOT NULL,
    input_evidence_ids_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    unit TEXT,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_analyses_investigation_time ON deterministic_analyses(investigation_id, created_at);

CREATE TABLE evidence_references (
    evidence_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('OBSERVATION', 'ANALYSIS')),
    observation_id TEXT REFERENCES observations(observation_id),
    analysis_id TEXT REFERENCES deterministic_analyses(analysis_id),
    created_at TEXT NOT NULL,
    CHECK ((observation_id IS NOT NULL) != (analysis_id IS NOT NULL))
);
CREATE INDEX idx_evidence_references_investigation ON evidence_references(investigation_id);

CREATE TABLE hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    support_level TEXT NOT NULL,
    confidence REAL,
    significant_evidence_gap INTEGER NOT NULL,
    causal_claim INTEGER NOT NULL,
    temporal_correlation_only INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_hypotheses_investigation ON hypotheses(investigation_id);

CREATE TABLE hypothesis_evidence (
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_references(evidence_id),
    relationship TEXT NOT NULL CHECK (relationship IN ('SUPPORTING', 'CONTRADICTING')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (hypothesis_id, evidence_id, relationship)
);

CREATE TABLE findings (
    finding_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    statement TEXT NOT NULL,
    support_level TEXT NOT NULL,
    confidence REAL,
    significant_evidence_gap INTEGER NOT NULL,
    causal_claim INTEGER NOT NULL,
    temporal_correlation_only INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_findings_investigation ON findings(investigation_id);

CREATE TABLE finding_evidence (
    finding_id TEXT NOT NULL REFERENCES findings(finding_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_references(evidence_id),
    relationship TEXT NOT NULL CHECK (relationship IN ('SUPPORTING', 'CONTRADICTING')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (finding_id, evidence_id, relationship)
);

CREATE TRIGGER prevent_tool_request_history_change
BEFORE UPDATE ON tool_requests
BEGIN
    SELECT RAISE(ABORT, 'tool requests are append-only');
END;
CREATE TRIGGER prevent_tool_request_history_delete
BEFORE DELETE ON tool_requests
BEGIN
    SELECT RAISE(ABORT, 'tool requests are append-only');
END;
CREATE TRIGGER prevent_tool_result_history_change
BEFORE UPDATE ON tool_results
BEGIN
    SELECT RAISE(ABORT, 'tool results are append-only');
END;
CREATE TRIGGER prevent_tool_result_history_delete
BEFORE DELETE ON tool_results
BEGIN
    SELECT RAISE(ABORT, 'tool results are append-only');
END;
CREATE TRIGGER prevent_observation_history_change
BEFORE UPDATE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations are append-only');
END;
CREATE TRIGGER prevent_observation_history_delete
BEFORE DELETE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations are append-only');
END;
CREATE TRIGGER prevent_analysis_history_change
BEFORE UPDATE ON deterministic_analyses
BEGIN
    SELECT RAISE(ABORT, 'analyses are append-only');
END;
CREATE TRIGGER prevent_analysis_history_delete
BEFORE DELETE ON deterministic_analyses
BEGIN
    SELECT RAISE(ABORT, 'analyses are append-only');
END;
CREATE TRIGGER prevent_evidence_history_change
BEFORE UPDATE ON evidence_references
BEGIN
    SELECT RAISE(ABORT, 'evidence references are append-only');
END;
CREATE TRIGGER prevent_evidence_history_delete
BEFORE DELETE ON evidence_references
BEGIN
    SELECT RAISE(ABORT, 'evidence references are append-only');
END;
