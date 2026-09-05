Product Requirements Document

GCP Observability Investigation Agent

Status: Frozen
Version: 0.8
Project Type: Production-oriented engineering project
Initial Environment: Simulated GCP observability environment
Target Environment: Google Cloud Platform

Product Overview

The GCP Observability Investigation Agent is an AI-assisted observability and incident-investigation system that allows an administrator to investigate infrastructure and application problems using natural-language questions.

Instead of requiring an administrator to manually inspect individual metrics, resources, and alerts, the system interprets a problem statement, determines what evidence is required, retrieves that evidence through controlled observability tools, evaluates the collected observations, and produces an evidence-backed explanation.

Example:

"Why did the production payment service become slow yesterday?"

The agent may investigate request latency, request volume, CPU utilization, memory utilization, error rate, alerts, and affected resources.

The initial implementation will use a simulated GCP observability environment because access to a company's production GCP environment is not currently available.

The architecture must nevertheless be designed for eventual production use. The mock environment is an implementation strategy, not a reduced architectural target.

Problem Statement

Modern cloud environments expose large volumes of operational telemetry. Diagnosing an incident often requires an administrator to correlate multiple signals across resources and time periods.

A conventional monitoring workflow may require the administrator to:

Identify the affected service or resource.

Locate relevant metrics.

Select an appropriate time window.

Compare multiple time series.

Inspect alerts and related resources.

Form and test hypotheses.

Determine which observations support the conclusion.

This process can become inefficient as infrastructure grows in size and complexity.

The proposed system aims to provide an investigation layer over existing observability infrastructure. The administrator describes the problem in natural language, and the agent determines what evidence should be collected and how that evidence should be interpreted.

Product Goal

Build a production-oriented, modular AI investigation system capable of:

Planning, executing, and interpreting a bounded sequence of structured observability queries in response to natural-language operational questions, while producing evidence-backed findings with explicit uncertainty.

The system should be designed around:

low coupling

high cohesion

explicit contracts

dependency inversion

replaceable infrastructure adapters

deterministic validation and policy enforcement

observability and auditability

testability

horizontal scalability where appropriate

secure integration with real cloud environments

The first implementation will use mocked GCP-style data, but the core architecture must not be designed as a throwaway prototype.

Target User

Primary User

Cloud / Infrastructure Administrator

The administrator uses natural language to:

inspect metrics

investigate anomalies

correlate multiple signals

understand incidents

inspect relevant alerts

identify likely contributing factors

Example questions:

"What was the CPU utilization of production VMs yesterday?"

"Which production service had the highest latency?"

"Why did the payment service become slow?"

"Was the latency increase associated with a traffic spike?"

"Were there any alerts when the service became unavailable?"

"What changed around the time the error rate increased?"

Product Boundaries

The system is an investigation and reasoning layer, not a replacement for a complete observability platform.

It should consume observability information exposed by an underlying monitoring environment.

The initial underlying environment is simulated GCP monitoring data.

The future underlying environment may be real Google Cloud Monitoring and potentially additional telemetry sources.

Product Goals

6.1 Functional Goals

The system shall:

Accept natural-language investigation questions.

Interpret the user's intent and relevant scope.

Discover available metric definitions when the requested metric is ambiguous, unknown, or potentially provider-specific.

Select from a controlled set of observability tools.

Execute validated tool requests.

Retrieve structured observability data.

Prevent excessive raw telemetry from being passed into the LLM context.

Accumulate evidence during an investigation.

Form and evaluate hypotheses.

Perform deterministic data operations where appropriate.

Distinguish observations from inferences and hypotheses.

Produce evidence-backed natural-language findings.

Expose the investigation trace for audit and debugging.

Handle incomplete, unavailable, contradictory, or erroneous evidence explicitly.

Bound investigation execution.

Support replacement of monitoring, LLM, and persistence providers without changing core domain logic.

6.2 Architectural Goals

The system shall be designed for:

Low Coupling

Changes in one infrastructure concern should not require changes to unrelated domain or application components.

Examples:

changing the LLM provider should not require changing investigation logic

changing persistence technology should not require changing domain logic

replacing the mock monitoring source with GCP should not require changing agent reasoning

changing the presentation layer should not require changing monitoring adapters

High Cohesion

Each module should contain responsibilities that belong together and should have a clear reason to change.

Expected boundaries include:

presentation

application orchestration

investigation domain

telemetry access

LLM integration

persistence

infrastructure configuration

Dependency Inversion

Core investigation logic should depend on stable abstractions rather than provider-specific SDKs or infrastructure implementations.

Candidate abstractions include:

TelemetryProvider

LLMProvider

InvestigationRepository

Explicit Contracts

Major component interactions shall use explicit schemas or interfaces.

Contracts shall be defined for:

tool requests

tool results

telemetry operations

investigation state

persistence

LLM provider interaction where appropriate

Replaceable Infrastructure

Infrastructure implementations should be replaceable without rewriting core investigation logic.

Non-Goals

The initial implementation will not attempt to:

Replace Google Cloud Monitoring.

Build a full observability platform.

Build a Datadog/Grafana-equivalent dashboarding platform.

Collect telemetry from real infrastructure.

Access a company's production environment during initial development.

Perform infrastructure modifications or remediation.

Automatically restart, scale, delete, or modify cloud resources.

Support every GCP service and metric.

Support every possible aggregation or query operation.

Build a generalized multi-cloud platform in the first release.

Introduce multi-agent orchestration without a demonstrated requirement.

Introduce distributed services solely for architectural appearance.

Introduce vector or graph databases without a demonstrated product requirement.

Reproduce the complete Cloud Monitoring API internally.

Optimize prematurely for massive-scale telemetry ingestion.

These are scope boundaries, not necessarily permanent product exclusions.

Core Use Cases

UC-01: Metric Lookup

User:

"What was the average CPU utilization of production VMs yesterday?"

The system should identify the appropriate metric, resources, time range, and aggregation, retrieve the observations, and report the result.

UC-02: Resource Comparison

User:

"Which production VM had the highest CPU utilization yesterday?"

The system should identify relevant resources, retrieve comparable observations, and determine the highest observed value.

UC-03: Multi-Metric Investigation

User:

"Why did the payment service become slow yesterday?"

The system should investigate relevant signals rather than assume a cause.

Potential evidence may include:

request latency

request volume

CPU utilization

memory utilization

error rate

alerts

affected resources

The exact investigation sequence should be determined dynamically within configured policies.

UC-04: Evidence Insufficient

If the available information cannot establish a cause, the system should explicitly state that the evidence is insufficient.

Example:

"The available metrics show increased latency, but there is insufficient evidence to determine whether CPU saturation caused it."

UC-05: No Demonstrable Anomaly

If the data does not support the user's assumption, the system should not manufacture a diagnosis.

Example:

"The available observations do not show a significant latency increase during the requested period."

UC-06: Contradictory Evidence

If observations conflict, the system should preserve the conflict rather than force a single explanation.

Example:

"Latency increased during the requested period, but CPU remained within its normal range. The available evidence therefore does not support CPU saturation as the primary explanation."

The final response should explicitly communicate uncertainty or competing hypotheses where appropriate.

UC-07: Invalid or Unsupported Request

The system should reject or explain unsupported requests without attempting unsafe or undefined operations.

Investigation Model

An investigation is a bounded, stateful process.

For Phase 1, investigations are single-turn: a single user question results in one bounded investigation execution and one final report. Multi-turn conversational context preservation is deferred.

Conceptually:

User Question
↓
Interpretation
↓
Investigation Planning
↓
Structured Tool Request
↓
Validation / Policy Enforcement
↓
Tool Execution
↓
Observation
↓
Deterministic Analysis / Evidence Evaluation
↓
More Evidence Required?
↙             ↘
Yes              No
↓                ↓
Next Tool       Findings
Request            ↓
Response

The LLM may determine what evidence should be investigated next.

The application and domain logic must determine whether the requested operation is valid, permitted, and within execution limits.

The investigation must support partial completion. If limits are reached before sufficient evidence is obtained, the system shall return the strongest findings supported by the evidence collected so far, explicitly identify unresolved questions and missing evidence, and state that the investigation is incomplete.

The system shall not discard previously collected evidence solely because execution terminates.

For relative time expressions such as "last six hours," the application shall provide authoritative temporal context to the investigation. The exact representation of that context is an implementation concern and shall not require unconditional injection into every LLM prompt.

Agent Responsibilities

The LLM-based agent may be responsible for:

natural-language interpretation

investigation planning

metric discovery through the controlled metric-discovery capability

selecting available tools

deciding what evidence may reduce uncertainty

interpreting retrieved observations

forming hypotheses

evaluating evidence

generating the final explanation

The agent must not be responsible for:

database execution

direct cloud API execution

credential management

authorization

security policy enforcement

query-limit enforcement

arbitrary code execution

bypassing tool contracts

deterministic numerical calculations when application code can perform them reliably

The agent should receive authoritative temporal and investigation context when required. The application, rather than the LLM, remains the authority for the actual time range used for queries.

Deterministic Application Responsibilities

Application/domain code must own:

input validation

tool-schema validation

metric validation

resource validation

time-range validation

aggregation validation

authorization boundaries

tool execution

maximum tool-call limits

timeout handling

retry policy

investigation lifecycle

structured error handling

audit logging

The LLM is not considered a security boundary.

Tool Model

The initial tool set will be deliberately small, representing domain-level observability concepts rather than database implementations.

search_metric_descriptors()

Discovers available metric definitions and relevant metadata for a supported monitoring scope.

The capability should help resolve natural-language metric requests to actual available metric types and should reduce the risk of the LLM inventing provider-specific metric names.

The LLM may request semantic search criteria, but the application shall validate the selected metric before it is used for a metric query.

The exact representation of metric descriptors will be defined in TOOL_CONTRACTS.md.

query_metric()

Retrieves time-series observations for a specified metric/resource scope and time interval.

The contract should represent the relevant Cloud Monitoring concepts, including:

metric type

metric-label filters where required

monitored-resource type

monitored-resource-label filters where required

time interval

supported aggregation/alignment options

The tool must not expose raw SQL or provider-specific query syntax to the LLM.

list_resources()

Retrieves monitored resources matching structured filters.

Potential filters include:

project

monitored-resource type

resource labels

service/environment identity represented through the mock resource-label model

get_alerts()

Retrieves relevant alert information using structured filters such as:

resource

time interval

severity/status where supported

Tool Contract Principle

Tool interfaces shall represent domain-level observability concepts, not database implementation details.

The exact request and result schemas will be defined in TOOL_CONTRACTS.md.

Telemetry returned to the LLM shall be treated as untrusted data and shall remain structurally distinguishable from system or developer instructions.

Investigation Limits and Context Protection

Investigations must be bounded.

The system shall support configurable limits for:

maximum tool calls

maximum investigation duration

maximum query time range

maximum result size

repeated or duplicate requests

A preliminary default may be 12 tool calls per investigation, but this value is a configuration decision rather than a permanent product requirement.

Partial Investigation

If an investigation terminates before sufficient evidence has been collected, the system shall return the strongest findings supported by the evidence collected so far, explicitly identify unresolved questions and missing evidence, and state that the investigation is incomplete.

Findings must not be presented as conclusive when the available evidence is insufficient.

When the configured tool-call or execution limit is reached, the system shall not discard previously collected evidence and shall not retry solely to avoid the limit. The investigation record shall retain the evidence collected up to termination and the reason for termination.

The final response shall distinguish between:

established findings supported by collected evidence;

hypotheses that remain unconfirmed;

unresolved questions;

relevant evidence that was not collected, where known;

the reason the investigation terminated.

An inference that is directly supported by collected observations may be reported as a finding, while an inference that remains uncertain or proposes an unverified explanation shall be reported as a hypothesis.

The system shall not retry indefinitely by narrowing the same request merely to avoid the execution limit.

Context Window Protection

The application shall prevent excessive raw telemetry from being passed directly into the LLM context.

The system should use deterministic reduction, aggregation, sampling, or summarization before passing large time-series results to the LLM.

The exact reduction strategy shall depend on the query scope, metric characteristics, requested resolution, and result size rather than a single fixed alignment rule.

If the requested resolution cannot be safely supported within configured result and context limits, the system shall return a structured warning or error rather than silently returning an unsafe or misleadingly reduced result.

Evidence, Hypotheses, and Findings

The system shall maintain a strict semantic distinction between:

Observation

A directly retrieved fact.

Example:

CPU utilization increased from 46% to 91% between 14:15 and 14:25.

Deterministic Analysis

A calculation or comparison performed by application/domain code.

Example:

P95 latency increased by 263%.

Inference

A conclusion derived from observations and deterministic analyses.

Example:

CPU saturation occurred during the same period as the latency increase.

Hypothesis

A possible explanation that remains unverified.

Example:

The traffic increase may have contributed to CPU saturation.

Findings should reference the observations and analyses that support them and avoid presenting hypotheses as established facts.

Temporal correlation alone must not be treated as proof of causation.

When evidence is contradictory, the system should preserve and report the conflict rather than silently selecting one explanation. Contradictory evidence should reduce certainty or result in competing hypotheses where appropriate.

Mock GCP Cloud Monitoring Environment

The initial implementation shall use a simulated monitoring environment based on the conceptual model of Google Cloud Monitoring.

The mock environment should model only the subset required by the product's supported use cases, while preserving the important semantics needed for future GCP integration.

Resources

Examples:

Compute Engine instances

GKE-related resources

Cloud Run services

other resource types only where required by supported use cases

Each monitored resource should conceptually include:

resource type

resource labels

project scope where required

Environment and service identity shall be represented through the resource-label model used by the mock monitored resources. This provides concrete fields for queries such as "production payment service" while keeping those selectors within the monitored-resource model.

Metric Definitions

Examples:

CPU utilization

memory utilization

request count

request latency

error count/rate

network activity where required

Each metric definition should conceptually preserve:

metric type

metric labels

metric metadata required by supported use cases

unit/value semantics where required

Metric labels and monitored-resource labels must remain separate structures in the domain model.

Time Series

A time series should conceptually associate:

Metric
├── type
└── labels

Monitored Resource
├── type
└── labels

Time Series
├── metric reference
├── resource reference
└── points
├── timestamp / interval
└── value

The SQLite implementation may normalize these structures across related tables, but must not collapse metric labels and resource labels into one generic label collection.

Alerts

Alerts should contain enough information to support the investigation scenarios involving:

affected resource

condition

time period

severity/status

The mock environment will include deliberately constructed abnormal scenarios with known expected outcomes.

The mock environment shall represent project scope where required by supported queries so that the future provider contract does not assume a single global resource namespace.

The precise correspondence between the mock schema and real Cloud Monitoring semantics shall be verified against Google's documentation before the GCP adapter contract is finalized.

Monitoring Query and Aggregation Model

The system shall not model Cloud Monitoring aggregation as merely average/min/max/sum.

The domain should preserve the conceptual distinction between:

retrieving time-series data;

aligning points within individual time series;

reducing or combining multiple time series;

grouping results where required.

The MVP will implement only the subset of alignment, reduction, grouping, and aggregation behavior required by supported use cases.

The domain contract must not prevent future support for richer Cloud Monitoring aggregation semantics.

Unsupported aggregation behavior must produce an explicit structured error rather than silently approximating it.

Numerical comparisons, percentage changes, threshold crossings, and temporal overlap calculations that are deterministic should be performed by application/domain code rather than delegated to the LLM.

Persistence Requirements

The system shall abstract persistence of durable domain state.

The initial mock telemetry dataset will use SQLite.

The production-oriented architecture must not make the investigation domain dependent on SQLite.

Potential persistence responsibilities include:

investigation records

evidence

findings

audit records

investigation lifecycle metadata

Active investigation execution state may be maintained in memory for low-latency orchestration.

However, every completed or terminated investigation shall be persisted before the application considers the investigation complete from an audit perspective.

The persisted record shall contain sufficient information to reconstruct the investigation audit trail, including:

investigation ID

original question

scope

tool requests

validation outcomes

tool results

observations

deterministic analyses

hypotheses where applicable

findings

termination reason

relevant model/provider metadata where appropriate

The initial implementation may use SQLite for this persistence as well, provided the repository boundary remains independent of SQLite.

The persistence implementation may later be replaced by a scalable transactional datastore without changing the investigation domain.

LLM Provider Abstraction

The investigation domain should not directly depend on a specific LLM vendor SDK.

A provider abstraction should permit implementations for:

selected primary LLM provider

alternative provider

deterministic/mock provider for testing

Provider-specific concerns such as:

SDK calls

authentication

model configuration

token usage

retries

provider-specific response formats

should remain in the infrastructure/integration layer.

The product does not require multi-provider support in the first release, but the architecture should avoid unnecessary provider lock-in.

Telemetry Provider Abstraction

The investigation domain shall interact with observability data through a provider abstraction.

Conceptually:

Investigation Domain
│
▼
TelemetryProvider
▲
│
┌──────┴─────────────┐
│                    │
MockTelemetry      GCPTelemetry
Provider           Provider
│                    │
SQLite          Cloud Monitoring API

The provider contract must be designed around the observability concepts required by the domain rather than around SQLite query syntax.

The real GCP adapter should be an infrastructure implementation, not a dependency of the domain.

Architecture and Deployment Strategy

The project shall use a modular architecture with independently cohesive components, but modularity must not be equated with microservices.

The initial implementation may be deployed as a modular monolith.

The codebase should maintain clear boundaries such that components can be separated later if scaling or operational requirements justify it.

The project should avoid:

premature microservices

unnecessary network boundaries

duplicated domain logic

infrastructure leakage into domain code

Potential future deployment separation may include:

API/presentation service

investigation execution service

persistence

telemetry integration

LLM gateway

However, such separation should be driven by actual scalability, isolation, or operational requirements.

Production-Grade Requirements

Production readiness is a target of the architecture, not a claim that the initial mock implementation is already production-ready.

Reliability

The architecture should account for:

timeouts

bounded execution

retries where appropriate

graceful failure

structured errors

partial-result handling

idempotent behavior where applicable

protection against runaway tool execution

LLM-provider failures and telemetry-provider failures shall be handled using the same investigation lifecycle rules as other execution failures: the reason shall be recorded, previously collected evidence shall be preserved, and the final result shall accurately indicate whether the investigation completed or terminated early.

Security

The architecture should support:

least-privilege access

credential isolation

authorization outside the LLM

read-only monitoring access initially

project/tenant isolation where required

secrets management

input validation

protection against prompt injection through untrusted telemetry content

Telemetry and logs must be treated as untrusted data. Retrieved content must not be interpreted as instructions to the agent.

Observability

The system itself should expose:

structured logs

request/investigation IDs

investigation execution traces

tool-call records

latency measurements

error metrics

LLM usage/cost metrics where available

investigation outcomes

Scalability

The architecture should permit:

concurrent investigations

horizontal scaling of stateless application components where appropriate

durable shared persistence

controlled access to external telemetry providers

rate limiting

backpressure

configurable concurrency

The initial implementation does not need to operate at production scale, but its architecture must not prevent future scaling.

Presentation Boundary

The Phase 1 Streamlit interface is a presentation choice for initial development and low-concurrency use. Production scaling shall depend on the application/investigation backend rather than on Streamlit process-local state.

Testing Requirements

Testing must exist at multiple levels.

Unit Tests

Test independently:

domain logic

validation

investigation state

termination rules

telemetry adapters

persistence adapters

deterministic analysis functions

tool contracts

Integration Tests

Test:

controller + tools

telemetry provider + mock database

LLM adapter + tool-calling contract

persistence implementation

Scenario Tests

Test complete investigations against known mock scenarios.

Examples:

CPU saturation

traffic surge

memory pressure

latency increase without CPU saturation

error-rate spike

no significant anomaly

missing data

contradictory evidence

ambiguous request

investigation limit reached

Evaluation

Measure:

query correctness

investigation correctness

evidence quality

number of tool calls

unsupported claims

hallucinated observations

termination behavior

failure handling

The evaluation framework should make it possible to compare changes to the agent systematically.

Extensibility Requirements

The architecture should permit future addition of:

additional telemetry providers

logs

traces

additional GCP services

additional LLM providers

persistent investigation history

anomaly detection

richer correlation

human approval workflows

controlled remediation

Adding one provider should not require modification of unrelated domain logic.

Adding a new telemetry capability should require changes primarily within the telemetry contract, adapter, tool definitions, and relevant investigation policies.

Auditability

Every completed or terminated investigation shall have a persisted audit record as defined in §17.

The audit record shall expose the information required to reconstruct how the system reached its findings, including:

investigation ID

original question

scope

tool requests

validation outcomes

tool results

observations

deterministic analyses

hypotheses where applicable

findings

termination reason

relevant model/provider metadata where appropriate

The audit record shall preserve sufficient information for later review without requiring the original investigation process to remain active.

Security Boundary

The architecture must maintain the following boundary:

LLM
│
│ structured request
▼
Application / Domain Policy
│
│ validated operation
▼
Infrastructure Adapter
│
▼
External System

The LLM must never have an unrestricted execution path to:

databases

cloud credentials

arbitrary APIs

operating-system commands

infrastructure modification

This boundary must remain true when replacing mock infrastructure with real GCP infrastructure.

Initial Technology Choices

These are implementation choices for the first development stage, not permanent product requirements.

Concern

Initial Choice

Language

Python

UI

Streamlit

Application architecture

Modular monolith

Agent orchestration

Explicit Python controller/state

LLM

Provider to be selected

Tool calling

Structured function/tool calling

Mock telemetry storage

SQLite

Mock telemetry adapter

Python implementation

Testing

Python testing framework

Version control

Git

The presentation layer shall provide meaningful progress feedback during long-running investigations. The specific mechanism used by the UI is an implementation concern.

Streamlit is appropriate for Phase 1 single-user/low-concurrency use. Before production horizontal scaling, investigation execution shall be separable from the presentation layer and active state shall not depend on process-local UI state.

Additional infrastructure should be introduced only when justified by a concrete requirement.

Architecture Evolution

The intended evolution is:

PHASE 1
Production-oriented modular architecture
+
Mock telemetry
+
SQLite
+
Single deployment

    ↓

PHASE 2
Robust investigation engine
+
Scenario evaluation
+
Persistent investigation history
+
Operational observability

    ↓

PHASE 3
Real GCP telemetry adapter
+
Read-only GCP authentication
+
Cloud Monitoring integration
+
Real API failure handling

    ↓

PHASE 4
Production deployment
+
Scalable persistence
+
Horizontal application scaling
+
Rate limiting
+
Secrets management
+
Operational monitoring

    ↓

PHASE 5
Additional telemetry and investigation capabilities

The architecture should evolve by replacing or adding infrastructure implementations rather than rewriting the core investigation domain.

Success Criteria

The project will be considered technically successful when:

An administrator can submit natural-language investigation questions.

The agent can perform both simple metric lookups and multi-step investigations.

The agent can discover available metric definitions when required instead of relying on invented metric names.

The agent selects evidence dynamically rather than following one permanently hardcoded investigation sequence.

Tool execution is controlled by deterministic application code.

Investigations are bounded and auditable.

Findings are traceable to retrieved evidence and deterministic analyses.

The system handles missing, invalid, contradictory, and incomplete data explicitly.

The system avoids unsupported causal claims.

Large telemetry results are bounded or deterministically summarized before entering the LLM context.

The core investigation logic is independent of SQLite, a specific LLM provider, and GCP SDKs.

The mock telemetry implementation can be replaced by a real GCP adapter without modifying the core investigation domain.

The system can be tested using deterministic mock scenarios.

The architecture can evolve from a modular monolith into independently deployable components if actual scale or operational requirements justify it.

Completed and terminated investigations retain sufficient persisted audit information for later review.

Architectural Principles

The following principles are mandatory design constraints for subsequent architecture and implementation documents.

High Cohesion

A module should contain closely related responsibilities and have a clear reason to change.

Low Coupling

Components should interact through explicit contracts rather than concrete implementation details.

Dependency Inversion

Core business/investigation logic should depend on abstractions rather than infrastructure providers.

Explicit Boundaries

UI, application orchestration, domain logic, and infrastructure concerns must remain separated.

Deterministic Enforcement

Security, validation, authorization, resource limits, query construction, and deterministic calculations must be enforced by application/domain code.

Evidence Before Conclusions

The system should base findings on retrieved observations and deterministic analyses, and explicitly represent uncertainty.

Temporal correlation alone must not be represented as proof of causation.

Provider Independence

LLM, telemetry, and persistence providers should be replaceable without redesigning the investigation domain.

Production-Oriented, Incremental Implementation

The architecture should be production-capable in principle while implementation complexity is introduced only when justified.

No Architecture Theatre

A technology or component must have a demonstrable requirement. Microservices, databases, frameworks, queues, caches, and agent frameworks should not be added merely to make the architecture appear sophisticated.

Design for Evolution

The system should support future growth without unnecessary abstraction today.

Preserve Domain Semantics

Infrastructure adapters may normalize or transform data internally, but domain contracts must preserve distinctions that matter to the underlying observability model.

For GCP Cloud Monitoring, metric labels and monitored-resource labels are distinct concepts and must not be collapsed into one generic label collection.

Untrusted Telemetry

Logs, labels, metadata, and other retrieved telemetry content must be treated as data, not as trusted instructions to the agent.

Bounded Context

The system must control the amount of telemetry supplied to the LLM. Large result sets should be reduced deterministically before model reasoning.

Implementation-Neutral Requirements

Product requirements should describe required behavior rather than unnecessarily prescribing implementation mechanisms. Specific choices such as Streamlit, SQLite, or a particular streaming mechanism are initial implementation decisions unless elevated by a separate architectural requirement.

Documents Derived From This PRD

Once this PRD is frozen, the following documents will define the technical design:

docs/
├── PRD.md
├── SYSTEM_ARCHITECTURE.md
├── DOMAIN_MODEL.md
├── DATA_MODEL.md
├── TOOL_CONTRACTS.md
├── AGENT_BEHAVIOR.md
├── INVESTIGATION_LOGIC.md
├── TESTING_STRATEGY.md
├── SECURITY_ARCHITECTURE.md
├── OBSERVABILITY.md
└── GCP_INTEGRATION.md

Each document must remain consistent with this PRD.

The technical documents may refine implementation details that are intentionally left open here, but they must not silently change product requirements.

If a technical design exposes a requirement that is impossible, contradictory, or materially incomplete, the conflict must be explicitly documented and resolved rather than hidden in implementation.

PRD Review Status

This document is frozen.

Before implementation begins:

Review the final document for genuine contradictions or missing product requirements.

Verify GCP-specific assumptions against official Google Cloud documentation where the technical documents depend on them.

Resolve any remaining material disagreement.

Freeze the approved PRD.

Derive the technical design documents from the frozen requirements.

Do not reopen the PRD for implementation-level preferences unless they reveal a material product or architectural requirement.