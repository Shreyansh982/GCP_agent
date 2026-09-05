Domain Model

GCP Observability Investigation Agent

Status: Design Draft
Derived From: PRD v0.8
Purpose: Define the stable domain concepts, relationships, invariants, and responsibilities of the investigation system independently of UI, database, LLM provider, and telemetry-provider implementations.

Purpose

This document defines the conceptual domain model for the GCP Observability Investigation Agent.

The domain model describes:

what the system fundamentally represents;

which concepts belong to the investigation domain;

how those concepts relate;

what state they may have;

which invariants must hold;

which concepts are provider-independent;

which concepts preserve GCP observability semantics without coupling the domain to a GCP SDK.

The model is intentionally independent of:

Streamlit;

SQLite;

PostgreSQL;

any LLM vendor;

any specific agent framework;

Google Cloud SDK classes;

API request/response objects.

The implementation may map these domain concepts onto infrastructure-specific representations, but the core domain semantics must remain stable.

Domain Scope

The domain is concerned with investigation of observability information.

The domain represents:

Investigation
├── Scope
├── Temporal Context
├── Investigation Steps
├── Observations
├── Deterministic Analyses
├── Hypotheses
├── Findings
└── Termination State

The domain does not own:

telemetry collection;

cloud authentication;

LLM inference;

database access;

user-interface rendering;

execution of arbitrary external commands.

Those belong to application or infrastructure layers.

Domain Design Principles

3.1 Provider Independence

The domain must not depend on GCP SDK types, LLM SDK types, or database-specific types.

3.2 Preserve Observability Semantics

Concepts important to GCP Cloud Monitoring must not be flattened merely for implementation convenience.

In particular:

Metric
├── type
└── labels

MonitoredResource
├── type
└── labels

Metric labels and monitored-resource labels are separate concepts.

3.3 Evidence Before Conclusions

Observations are distinct from analyses, inferences, hypotheses, and findings.

3.4 Deterministic Work Is Deterministic

Calculations that can be performed reliably by application/domain code should not rely on the LLM.

3.5 Bounded Investigation

The investigation domain must support explicit lifecycle and termination states.

3.6 Explicit State

Important investigation state must be represented as structured domain data rather than being hidden entirely inside an LLM conversation.

Core Domain Entities

The initial domain contains the following primary entities:

Investigation
InvestigationScope
TemporalContext

InvestigationStep
ToolRequest
ToolResult

Metric
MetricDescriptor
MonitoredResource
TimeSeries
DataPoint
Alert

Observation
DeterministicAnalysis
Hypothesis
Finding
EvidenceReference

InvestigationOutcome
TerminationReason

Not every item must become a standalone database table or Python class. Some are value objects or structured records. The distinction is established below.

Investigation

5.1 Purpose

Investigation is the central aggregate representing one user's operational question and the system's attempt to answer it.

Example:

"Why did the payment service become slow yesterday?"

An investigation owns the lifecycle and evidence collected for that question.

5.2 Conceptual Structure

Investigation
├── identity
├── question
├── scope
├── temporal_context
├── status
├── steps
├── observations
├── analyses
├── hypotheses
├── findings
├── outcome
└── audit metadata

5.3 Core Attributes

investigation_id

Unique identifier for the investigation.

question

The original natural-language question submitted by the user.

scope

The operational scope inferred or explicitly specified for the investigation.

temporal_context

The authoritative time context used to interpret relative dates/times and establish query intervals.

status

Current lifecycle state.

steps

Ordered record of investigation actions and results.

observations

Facts obtained during investigation.

analyses

Deterministic calculations performed on retrieved data.

hypotheses

Possible explanations considered by the investigation.

findings

Supported conclusions presented by the investigation.

outcome

Summary of how the investigation terminated.

audit metadata

Information required to reconstruct the investigation lifecycle and execution trace.

Investigation Lifecycle

The domain should model an explicit lifecycle.

Recommended states:

CREATED
↓
RUNNING
↓
COMPLETED
│
├── SUFFICIENT_EVIDENCE
├── PARTIAL_LIMIT_REACHED
├── INSUFFICIENT_EVIDENCE
└── TERMINATED_ERROR

A more explicit implementation may represent terminal outcomes separately from lifecycle status.

The important rule is that status and termination reason are not the same concept.

For example:

status = TERMINATED
termination_reason = TOOL_TIMEOUT

or:

status = COMPLETED
outcome = SUFFICIENT_EVIDENCE

The exact enum names can be refined later.

InvestigationScope

7.1 Purpose

Represents the operational scope within which an investigation is allowed to search.

7.2 Conceptual Structure

InvestigationScope
├── project_scope
├── resource_scope
├── service_scope
└── environment_scope

Not every investigation must specify every field.

7.3 Important Principle

Scope is a domain concept, but its concrete filtering representation belongs to the telemetry provider.

For example:

Domain:
service = "payments"
environment = "production"

The GCP adapter may translate that into provider-specific resource labels or filters.

The domain should not contain GCP filter strings.

TemporalContext

8.1 Purpose

Represents time information relevant to the investigation.

It is distinct from a raw timestamp because the system must handle:

explicit time ranges;

relative expressions;

authoritative current time;

query intervals.

8.2 Conceptual Structure

TemporalContext
├── reference_time
├── timezone
├── requested_interval
└── interpretation_metadata

Example:

reference_time = 2026-08-27T19:30:00Z
requested_interval = previous 24 hours
resolved_interval = 2026-08-26T19:30:00Z → 2026-08-27T19:30:00Z

The application is authoritative for the actual resolved query interval.

Metric

9.1 Purpose

Represents the identity and semantics of a metric.

A metric is not the same thing as a time series.

A metric defines what is being measured.

9.2 Conceptual Structure

Metric
├── type
├── labels
└── metadata

9.3 Key Distinction

Metric
↓
defines what is measured

TimeSeries
↓
defines what values were observed for
a particular metric/resource combination

MetricDescriptor

10.1 Purpose

Represents metadata used to discover and validate available metrics.

This supports the search_metric_descriptors() capability.

10.2 Conceptual Structure

MetricDescriptor
├── metric_type
├── description
├── labels
├── metric_kind
├── value_type
├── unit
└── supported_metadata

Only metadata required by supported use cases needs to be implemented initially.

The domain must not assume that a human-friendly name is equivalent to a provider's exact metric type.

MonitoredResource

11.1 Purpose

Represents the resource from which telemetry originates.

11.2 Conceptual Structure

MonitoredResource
├── type
└── labels

Examples may include:

gce_instance
k8s_container
cloud_run_revision

The exact supported resource types are implementation scope, but the domain must allow resource types to differ.

11.3 Project Scope

A resource may belong to a project or equivalent provider scope.

Project scope should remain represented explicitly where required by supported queries.

11.4 Service and Environment

The domain should permit service/environment identity to be expressed through resource metadata or labels.

The representation must remain compatible with provider mappings rather than introducing a separate provider-specific filtering language.

DataPoint

12.1 Purpose

Represents one observed value at a specific time or within a time interval.

12.2 Conceptual Structure

DataPoint
├── timestamp_or_interval
└── value

The value representation must preserve the metric's value semantics.

The exact concrete value type may vary according to the associated metric descriptor.

TimeSeries

13.1 Purpose

Represents a sequence of observations for one fully identified metric/resource combination.

13.2 Conceptual Structure

TimeSeries
├── metric
├── monitored_resource
├── metadata
└── points[]

Where:

metric
├── type
└── labels

monitored_resource
├── type
└── labels

points[]
├── timestamp / interval
└── value

13.3 Domain Invariant

A time series must have enough information to identify:

what metric is being measured;

which monitored resource produced it;

which metric-label values apply;

which resource-label values apply;

what observations occurred over time.

A time series must not merge metric-label and resource-label namespaces.

Alert

14.1 Purpose

Represents alert information relevant to an investigation.

14.2 Conceptual Structure

Alert
├── identity
├── resource_reference
├── condition
├── severity
├── status
├── start_time
├── end_time
└── metadata

The exact structure may expand when the real GCP alerting model is implemented.

The domain should retain only alert semantics required for investigation.

Observation

15.1 Purpose

An Observation is a domain-level representation of a fact retrieved from telemetry.

It is intentionally different from a raw TimeSeries.

A time series is provider-oriented telemetry data.

An observation is investigation-oriented evidence extracted from that telemetry.

15.2 Examples

CPU utilization reached 91% at 14:20.

P95 request latency was 870 ms during the 14:20–14:25 interval.

Request volume increased by 2.4× between two comparison windows.

The first two may directly represent retrieved measurements.

The third may be produced as a deterministic analysis and therefore may instead belong to DeterministicAnalysis.

15.3 Conceptual Structure

Observation
├── observation_id
├── statement / semantic value
├── source_reference
├── temporal_scope
├── resource_scope
├── metric_reference
└── provenance

The observation should retain enough provenance to identify where it came from.

EvidenceReference

16.1 Purpose

Provides traceability between findings/analyses and the observations supporting them.

16.2 Conceptual Structure

EvidenceReference
├── source_type
├── source_id
└── relevance

A finding may reference multiple observations.

Example:

Finding
├── Observation O1: latency increased
├── Observation O2: request volume increased
└── Observation O3: CPU increased

Evidence references should be structured, not merely copied into free-form prose.

DeterministicAnalysis

17.1 Purpose

Represents an analysis performed by application/domain code rather than inferred directly by the LLM.

17.2 Examples

percentage change;

numerical comparison;

max/min/mean;

supported percentile;

threshold crossing;

trend direction;

temporal overlap;

alignment/aggregation result.

17.3 Conceptual Structure

DeterministicAnalysis
├── analysis_id
├── operation
├── inputs
├── parameters
├── result
├── units
└── provenance

17.4 Invariant

A deterministic analysis must be reproducible from its recorded inputs and parameters.

This is important for testing and auditability.

Hypothesis

18.1 Purpose

Represents a possible explanation that has not been established as fact.

18.2 Conceptual Structure

Hypothesis
├── hypothesis_id
├── statement
├── supporting_evidence
├── contradicting_evidence
├── confidence
└── status

Possible statuses may include:

OPEN
SUPPORTED
WEAKENED
REJECTED
UNRESOLVED

These are design candidates and should be validated against actual investigation behavior before implementation.

18.3 Important Rule

A hypothesis may be strengthened or weakened as new evidence is collected.

It should not be silently converted into a confirmed fact merely because the LLM expresses confidence.

Inference

Inference is a reasoning concept rather than necessarily a persistent standalone entity.

An inference is:

a conclusion derived from observations and deterministic analyses.

Example:

Observation:
CPU reached 91%.

Observation:
Latency increased at approximately the same time.

Inference:
CPU saturation coincided with the latency increase.

Whether an inference is stored independently or represented through a finding/hypothesis relationship should be decided in INVESTIGATION_LOGIC.md.

For the current domain model, the semantic distinction must exist even if the implementation uses another representation.

Finding

20.1 Purpose

Represents a conclusion that the system is willing to present as supported by the available evidence.

20.2 Conceptual Structure

Finding
├── finding_id
├── statement
├── support_level
├── supporting_evidence
├── contradicting_evidence
└── confidence

20.3 Finding Requirement

A finding must be traceable to:

one or more observations;

and/or deterministic analyses.

A finding must not exist solely because the LLM generated plausible prose.

Support and Confidence

Confidence should not be treated as an arbitrary emotion score produced by the LLM.

The domain should distinguish:

support_level

from:

confidence

For example:

support_level:
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED

Confidence is informational metadata in Phase 1 and is not an authoritative
measure of evidence support. It must not determine whether a hypothesis or
finding is accepted.

For Phase 1, support_level is determined from validated evidence relationships:

SUPPORTED
One or more valid supporting evidence references exist, with no material
contradictory evidence undermining the claim.

PARTIALLY_SUPPORTED
Supporting evidence exists, but material contradictory evidence or a
significant unresolved evidence gap remains.

UNSUPPORTED
No valid supporting evidence establishes the claim.

Causal claims cannot become SUPPORTED from temporal correlation alone.

InvestigationStep

22.1 Purpose

Represents one ordered unit in the investigation trace.

A step captures what the agent requested and what actually happened.

22.2 Conceptual Structure

InvestigationStep
├── sequence_number
├── timestamp
├── tool_request
├── validation_result
├── tool_result
├── derived_observations
└── execution_status

This makes the investigation auditable.

ToolRequest

23.1 Purpose

Represents a structured request generated by the agent and submitted to the application for validation/execution.

23.2 Properties

A tool request should contain:

ToolRequest
├── tool_name
├── arguments
├── requested_at
└── request_id

The concrete schemas for each tool are defined separately in TOOL_CONTRACTS.md.

The domain must not permit arbitrary executable instructions inside ToolRequest.

ToolResult

24.1 Purpose

Represents the structured result of an attempted tool operation.

24.2 Possible Outcomes

SUCCESS
NO_DATA
INVALID_REQUEST
NOT_FOUND
TIMEOUT
PROVIDER_ERROR
POLICY_REJECTED

The final set of error/status categories belongs in the tool contracts.

24.3 Principle

NO_DATA must remain distinguishable from:

metric does not exist
resource does not exist
query was invalid
provider failed

These states have different meanings for investigation reasoning.

InvestigationOutcome

25.1 Purpose

Represents the final state from the user's perspective.

Conceptually:

InvestigationOutcome
├── outcome_status
├── termination_reason
├── findings
├── unresolved_questions
├── missing_evidence
└── response_summary

Potential outcome statuses include:

COMPLETED
PARTIAL
INSUFFICIENT_EVIDENCE
FAILED

Exact enums should be finalized in INVESTIGATION_LOGIC.md.

TerminationReason

Termination reason is distinct from investigation status.

Examples:

SUFFICIENT_EVIDENCE
MAX_TOOL_CALLS
MAX_DURATION
NO_NEW_EVIDENCE
TOOL_FAILURE
LLM_FAILURE
VALIDATION_FAILURE
SYSTEM_ERROR

This distinction allows the system to report:

Outcome:
PARTIAL

Termination reason:
MAX_TOOL_CALLS

instead of collapsing both concepts into a single ambiguous status.

Relationships

The central domain relationships are:

Investigation
│
├── has one ───────────────► InvestigationScope
├── has one ───────────────► TemporalContext
├── contains many ────────► InvestigationStep
│                              │
│                              ├── contains ToolRequest
│                              ├── contains ToolResult
│                              └── produces Observations
│
├── contains many ────────► Observation
│                              │
│                              └── references Metric / Resource / TimeSeries
│
├── contains many ────────► DeterministicAnalysis
│                              │
│                              └── consumes Observations
│
├── contains many ────────► Hypothesis
│                              │
│                              ├── references supporting Evidence
│                              └── references contradicting Evidence
│
├── contains many ────────► Finding
│                              │
│                              └── references supporting/contradicting Evidence
│
└── has one ───────────────► InvestigationOutcome

Telemetry relationships:

MetricDescriptor
│
└── defines ──► Metric
│
└── participates in ──► TimeSeries
│
MonitoredResource ─────────────────────────────────────┘

The TimeSeries is therefore the relationship between a metric definition/identity and a monitored resource over time.

Aggregate Boundary

For domain-driven design purposes, Investigation is the primary aggregate root.

The investigation controls mutations to:

investigation steps;

evidence references;

hypotheses;

findings;

outcome.

Telemetry entities such as:

MetricDescriptor

Metric

MonitoredResource

TimeSeries

Alert

are not owned by the investigation as mutable child entities in the same sense.

They are external domain data represented for investigation purposes.

This distinction prevents the investigation model from becoming responsible for telemetry lifecycle management.

Immutability and Mutability

Prefer immutable concepts

The following should generally be immutable after creation:

MetricDescriptor

Metric identity

MonitoredResource identity

DataPoint

Observation provenance

ToolResult

DeterministicAnalysis result

Mutable concepts

The following may evolve while an investigation is active:

Investigation status

InvestigationStep execution state

Hypothesis status

Finding support/confidence

InvestigationOutcome

The exact persistence semantics will be specified in DATA_MODEL.md.

Domain Invariants

The following invariants should hold.

Investigation

Every investigation has a unique ID.

Every investigation has an original question.

An investigation cannot execute tools after entering a terminal state.

A completed or terminated investigation must have an outcome.

Terminal investigations retain the evidence collected before termination.

Tool Execution

Only defined tools may be executed.

Tool arguments must satisfy their schema before execution.

Validation must occur before infrastructure execution.

Tool-call limits must be enforced outside the LLM.

Telemetry

Metric labels and resource labels remain distinct.

A time series must identify both metric and monitored resource.

Missing data is distinct from zero-valued data.

Provider errors are distinct from empty results.

Evidence

Observations retain provenance.

Findings require supporting evidence or a deterministic analysis.

Unsupported hypotheses must not be promoted to confirmed findings.

Contradictory evidence must remain representable.

Deterministic Analysis

Deterministic analysis is reproducible from its inputs and parameters.

The LLM must not be the only mechanism producing numerical claims when application logic can calculate them reliably.

Termination

Every terminal investigation has a termination/outcome reason.

Partial investigations retain previously collected evidence.

Reaching a limit does not justify discarding evidence or looping indefinitely.

Domain vs. Application vs. Infrastructure

The following boundary should remain explicit:

Responsibility

Domain

Application

Infrastructure

Investigation lifecycle

✅

coordinates



Hypothesis/finding semantics

✅





Evidence relationships

✅





Numerical analysis rules

✅

executes



Tool selection



coordinates



Tool validation



✅



Tool execution



coordinates

✅

GCP API communication





✅

SQLite/PostgreSQL access





✅

LLM SDK calls





✅

Authentication





✅

UI rendering





✅ / presentation

Rate limiting



✅

possibly infrastructure-level

Logging/telemetry of system



✅

✅

The exact placement of individual mechanisms may be refined in SYSTEM_ARCHITECTURE.md, but the domain must remain free of provider-specific implementations.

Domain Service Candidates

A domain service should be introduced only where behavior does not naturally belong to an entity or value object.

Potential candidates include:

EvidenceEvaluationService

Evaluates relationships between observations, deterministic analyses, and hypotheses.

InvestigationPolicy

Represents domain rules governing whether an investigation may continue.

TimeSeriesAnalysisService

Provides deterministic analysis operations when those operations represent meaningful domain behavior.

These are candidates, not mandatory classes.

The implementation should prefer simple functions or cohesive services where appropriate rather than creating classes solely to mirror every noun in this document.

Value Objects

Likely value-object candidates include:

InvestigationId
InvestigationScope
TemporalContext
MetricType
MetricLabels
ResourceType
ResourceLabels
TimeInterval
ToolName
ToolRequestId
EvidenceReference
TerminationReason
SupportLevel

The purpose of value objects is to enforce meaningful invariants and avoid passing loosely typed primitive values throughout the system.

Not every candidate must become a separate class if the implementation language and complexity do not justify it.

Provider Boundary

The domain should expose abstractions approximately corresponding to:

TelemetryProvider
LLMProvider
InvestigationRepository

These are contracts, not domain data entities.

TelemetryProvider

The domain/application layer should request observability information using domain concepts.

The provider implementation may translate the request to:

SQLite queries;

GCP Cloud Monitoring API filters;

another telemetry provider.

LLMProvider

The provider implementation hides:

model SDK;

authentication;

provider-specific message formats;

provider-specific tool-call response representation.

InvestigationRepository

The repository persists the investigation aggregate without exposing database-specific operations to the domain.

GCP-Specific Knowledge Allowed in the Domain

The domain may preserve concepts that are fundamental to Cloud Monitoring and relevant to the product:

metric type;

metric labels;

monitored-resource type;

monitored-resource labels;

time series;

time interval;

alignment;

reduction;

grouping where supported.

The domain should NOT contain:

GCP REST URLs;

protobuf classes;

SDK client objects;

raw filter strings;

OAuth tokens;

service-account objects.

This maintains provider independence without pretending the domain is ignorant of the semantics it is designed to investigate.

Domain Model Example

For a question:

"Why did the production payment service become slow yesterday?"

the domain state may conceptually become:

Investigation
│
├── question
│   └── "Why did the production payment service become slow yesterday?"
│
├── scope
│   ├── environment = production
│   └── service = payments
│
├── temporal_context
│   └── resolved_interval = previous day
│
├── steps
│   ├── search_metric_descriptors()
│   ├── query_metric(request_latency)
│   ├── query_metric(request_count)
│   ├── query_metric(cpu_utilization)
│   └── query_metric(memory_utilization)
│
├── observations
│   ├── latency increased
│   ├── request volume increased
│   ├── CPU increased
│   └── memory remained stable
│
├── deterministic_analyses
│   ├── latency percentage change
│   ├── request-volume percentage change
│   └── temporal overlap
│
├── hypotheses
│   └── traffic-driven CPU saturation
│
├── findings
│   └── traffic increase coincided with CPU saturation and latency increase
│
└── outcome
└── supported finding / completed

This example demonstrates the domain model without prescribing how any of those operations are implemented.

Open Decisions for Subsequent Documents

The domain model deliberately leaves the following for later technical design:

Exact tool request/result schemas.

Exact repository interface.

Exact LLM provider contract.

Exact investigation state serialization.

Exact hypothesis confidence semantics.

Exact finding support levels.

Exact deterministic analysis operations supported in the MVP.

Exact time-series aggregation API.

Exact SQLite table structure.

Exact GCP adapter mapping.

Exact error hierarchy.

Exact concurrency implementation.

Exact UI representation of investigation progress.

These should be resolved in the appropriate technical documents rather than prematurely embedded here.

Design Constraints for Derived Documents

SYSTEM_ARCHITECTURE.md, DATA_MODEL.md, TOOL_CONTRACTS.md, and INVESTIGATION_LOGIC.md must preserve the following domain decisions:

Metric labels ≠ Resource labels

TimeSeries ≠ Metric

Observation ≠ raw telemetry row

DeterministicAnalysis ≠ LLM inference

Hypothesis ≠ confirmed finding

Investigation status ≠ termination reason

Domain contract ≠ provider-specific API contract

Active investigation state ≠ durable audit record

Any design that violates one of these distinctions must explicitly justify why the domain model should change.

Summary

The domain model centers on one primary aggregate:

Investigation

It gathers:

Question
↓
Scope + Time
↓
Investigation Steps
↓
Observations
↓
Deterministic Analyses
↓
Hypotheses
↓
Findings
↓
Outcome

Telemetry remains conceptually separate:

Metric
+
MonitoredResource
↓
TimeSeries
↓
DataPoints

The domain does not know whether telemetry comes from:

SQLite
GCP Cloud Monitoring
Prometheus
another provider

and does not know whether reasoning comes from:

OpenAI
Gemini
another model provider
mock implementation

The domain is therefore the stable center around which the application and infrastructure can evolve.

Next Derived Documents

After this document is reviewed, the next documents should be:

SYSTEM_ARCHITECTURE.md

DATA_MODEL.md

TOOL_CONTRACTS.md

INVESTIGATION_LOGIC.md

AGENT_BEHAVIOR.md

SECURITY_ARCHITECTURE.md

OBSERVABILITY.md

TESTING_STRATEGY.md

GCP_INTEGRATION.md

The domain model should be treated as the conceptual source for those documents, while the frozen PRD remains the authoritative source for product requirements.