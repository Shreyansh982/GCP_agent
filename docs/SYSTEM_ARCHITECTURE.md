System Architecture

GCP Observability Investigation Agent

Status: Design Draft
Derived From: PRD v0.8, DOMAIN_MODEL.md
Architecture Style: Modular monolith with explicit domain and infrastructure boundaries
Initial Deployment: Single application
Target Evolution: Independently scalable components where justified by measurable requirements

1. Purpose

This document defines the system architecture of the GCP Observability Investigation Agent.

It translates the frozen product requirements and domain model into an implementable architecture while preserving:

high cohesion

low coupling

dependency inversion

explicit contracts

deterministic enforcement

provider independence

auditability

testability

production-oriented scalability

The first implementation remains simple. The architecture is not a throwaway prototype.

2. Architectural Objectives

2.1 Low Coupling

A change in one concern should not require changes in unrelated concerns.

Examples:

Change LLM provider
    → LLM integration changes
    → investigation domain remains unchanged

Change SQLite to PostgreSQL
    → persistence implementation changes
    → investigation domain remains unchanged

Replace mock telemetry
    → telemetry adapter changes
    → investigation domain remains unchanged

Replace Streamlit
    → presentation changes
    → domain and telemetry remain unchanged

2.2 High Cohesion

Each module should have one coherent responsibility and a limited set of reasons to change.

2.3 Deterministic Control

The LLM handles probabilistic interpretation and investigation reasoning.

Application/domain code handles:

authorization

validation

tool execution

query construction

execution limits

deterministic analysis

persistence guarantees

2.4 Production-Oriented Evolution

The initial deployment may be a modular monolith. Internal boundaries must still support later separation when there is a concrete requirement for:

independent scaling

failure isolation

security isolation

operational ownership

3. Architectural Style

The system uses a layered modular architecture with dependency inversion.

Presentation
     ↓
Application
     ↓
Domain
     ↑
Infrastructure

The intended dependency direction is:

Presentation → Application → Domain
                                ↑
                                │
                         Infrastructure

Infrastructure implements contracts required by the core.

The domain must not import:

Streamlit

GCP SDK clients

SQLite/PostgreSQL drivers

LLM vendor SDKs

4. System Context

                   ┌─────────────────────┐
                   │ Administrator       │
                   └──────────┬──────────┘
                              │
                       Natural-language
                         investigation
                              │
                              ▼
┌────────────────────────────────────────────────────────────┐
│          GCP Observability Investigation Agent             │
│                                                            │
│ Presentation → Application → Domain                        │
│                           ↑                                │
│                           │                                │
│                  Infrastructure adapters                   │
└───────────────┬───────────────────────┬────────────────────┘
                │                       │
                ▼                       ▼
        LLM Provider              Telemetry Provider
                                        │
                                        ▼
                              Mock GCP / Real GCP

The initial environment is simulated GCP monitoring data.

The future environment is real Google Cloud Monitoring.

5. Major Logical Components

The system contains these logical components:

1. Presentation
2. Application
3. Investigation Domain
4. Telemetry Integration
5. LLM Integration
6. Persistence Integration
7. Cross-Cutting Infrastructure

These are logical boundaries, not necessarily separate processes or services.

6. Presentation Layer

Responsibility

Handles communication with the administrator.

It is responsible for:

accepting investigation requests

displaying investigation progress

displaying findings

displaying evidence

displaying warnings/errors

displaying history where supported

It contains no investigation business logic.

Initial Implementation

Streamlit

Streamlit is a Phase 1 implementation choice.

Progress Feedback

Long-running investigations should expose meaningful progress:

Investigation started
↓
Discovering metric
↓
Querying latency
↓
Analyzing request volume
↓
Checking CPU
↓
Evaluating evidence
↓
Generating finding

The exact mechanism for delivering progress is a presentation/infrastructure decision.

Production Boundary

Before production horizontal scaling:

Streamlit / Web UI
        ↓
API boundary
        ↓
Investigation backend

Investigation execution must not depend on Streamlit session-local state.

7. Application Layer

Responsibility

Coordinates application use cases without owning provider-specific logic.

Primary responsibilities:

receive investigation requests

create/load investigation state

invoke investigation execution

validate tool calls

enforce execution policies

coordinate telemetry and LLM providers

coordinate persistence

return application-level results

Key Application Components

InvestigationApplicationService

Coordinates the complete investigation use case.

InvestigationController

Owns bounded investigation execution.

It:

receives structured tool requests

validates them

enforces limits

executes approved operations

records tool results

updates investigation state

determines whether execution can continue

It does not construct provider-specific queries.

8. Domain Layer

The domain is the stable center of the system.

Core concepts are defined in DOMAIN_MODEL.md:

Investigation
InvestigationScope
TemporalContext

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

InvestigationStep
ToolRequest
ToolResult
InvestigationOutcome
TerminationReason

The domain owns:

investigation lifecycle

evidence semantics

hypothesis/finding semantics

deterministic analysis semantics

domain invariants

The domain does not own:

HTTP

Streamlit

SQL

GCP SDK calls

LLM SDK calls

credentials

infrastructure authentication

9. Investigation Aggregate

Investigation is the primary aggregate root.

Investigation
├── Scope
├── TemporalContext
├── Steps
├── Observations
├── DeterministicAnalyses
├── Hypotheses
├── Findings
└── Outcome

The aggregate controls investigation-owned state.

Telemetry objects such as Metric, MonitoredResource, and TimeSeries are represented as external observability data, not mutable children owned by the investigation.

10. Telemetry Integration

Responsibility

Provides structured observability data to the application/domain.

Primary abstraction:

TelemetryProvider

Implementations:

MockTelemetryProvider
GCPTelemetryProvider
FutureTelemetryProvider

Dependency Structure

Investigation/Application
          │
          ▼
TelemetryProvider
          ▲
          │
    ┌─────┴─────┐
    │           │
   Mock         GCP
 Provider     Provider
    │           │
 SQLite      Cloud Monitoring

The domain/application uses the contract.

Infrastructure supplies implementations.

11. Telemetry Capabilities

The initial provider exposes four controlled capabilities:

search_metric_descriptors()
query_metric()
list_resources()
get_alerts()

These operate on domain-level concepts.

They must not expose:

raw SQL

raw GCP filter strings to the LLM

SDK objects

credentials

arbitrary cloud operations

12. Metric Discovery

Metric discovery prevents the agent from relying on invented provider-specific metric names.

Pipeline:

Natural-language metric concept
        ↓
search_metric_descriptors()
        ↓
MetricDescriptor candidates
        ↓
LLM candidate selection
        ↓
Application validation
        ↓
query_metric()

The application validates that the selected metric is actually available and compatible with the requested resource scope before query execution.

13. Query Execution and Result Processing

A telemetry query follows:

LLM ToolRequest
      ↓
Tool Schema Validation
      ↓
Policy / Domain Validation
      ↓
Telemetry Query Construction
      ↓
TelemetryProvider
      ↓
Raw TimeSeries
      ↓
Deterministic Result Processing
      ├── alignment
      ├── reduction
      ├── aggregation
      ├── comparison
      ├── trend analysis
      └── bounded summarization
      ↓
LLM-facing ToolResult
      ↓
LLM

The provider-facing result and LLM-facing result are conceptually distinct.

The system must preserve enough provenance to support auditability.

14. Context Protection

The LLM must never receive unbounded raw telemetry.

Example:

100,000 data points
        ↓
Result-size policy
        ↓
Alignment / aggregation / summarization
        ↓
Bounded evidence representation
        ↓
LLM context

Processing should consider:

time range

metric characteristics

resource count

sampling density

requested resolution

result size

investigation purpose

No single fixed alignment rule applies to every metric.

If the requested resolution cannot safely fit configured limits, the application shall return an explicit warning/error or apply a documented safe reduction policy.

15. Deterministic Analysis Boundary

The following should be performed by application/domain code when applicable:

minimum

maximum

mean

supported percentiles

percentage change

threshold crossing

trend direction

temporal overlap

cross-series comparison

supported alignment/reduction calculations

The LLM interprets the results.

The LLM must not be the sole source of numerical claims when deterministic computation is available.

16. LLM Integration

Responsibility

The LLM performs:

Natural-language interpretation
        ↓
Investigation planning
        ↓
Tool selection
        ↓
Evidence interpretation
        ↓
Hypothesis generation
        ↓
Finding formulation
        ↓
Natural-language response

Provider Abstraction

Core logic depends on:

LLMProvider

Possible implementations:

PrimaryLLMProvider
AlternativeLLMProvider
MockLLMProvider

Provider-specific SDKs, authentication, retry behavior, response formats, and token accounting remain in infrastructure.

17. Tool-Calling Boundary

The LLM communicates with the application through structured requests.

LLM
 │
 │ ToolRequest
 ▼
InvestigationController
 │
 ├── schema validation
 ├── authorization/policy
 ├── execution limits
 └── tool dispatch
 │
 ▼
ToolResult
 │
 ▼
LLM

The LLM never receives direct database or cloud permissions.

18. Observation Creation Boundary

Raw telemetry does not become authoritative evidence merely because the LLM describes it.

The intended path is:

TelemetryProvider
      ↓
Raw TimeSeries
      ↓
Deterministic processing
      ↓
Observation / DeterministicAnalysis
      ↓
LLM interpretation
      ↓
Hypothesis / Finding candidate
      ↓
Evidence-reference validation
      ↓
Authoritative investigation state

This prevents fabricated observations from entering the investigation record.

19. Evidence and Finding Validation

The LLM may propose:

Hypothesis
Finding candidate

The application/domain must verify:

referenced evidence exists

referenced evidence belongs to the investigation

a finding has appropriate support

a hypothesis is not silently promoted to a confirmed fact

contradictory evidence is preserved

Final findings therefore remain traceable to retrieved evidence and deterministic analyses.

20. Persistence Architecture

Responsibility

Stores durable investigation and audit information.

Primary abstraction:

InvestigationRepository

Possible implementations:

SQLiteInvestigationRepository
PostgresInvestigationRepository
FutureRepository

Active vs Durable State

During execution:

Active investigation
        ↓
In-memory execution state

At completion or termination:

Investigation state
        ↓
Persist audit record
        ↓
Complete / terminated

Completed or terminated investigations must not rely on process-local memory for auditability.

21. Failure Handling

Telemetry Failure

Tool request
   ↓
Provider failure
   ↓
Record failure
   ↓
Preserve prior evidence
   ↓
Retry or terminate according to policy

LLM Failure

Investigation state
   ↓
LLM timeout/failure
   ↓
Record failure
   ↓
Preserve prior evidence
   ↓
Persist terminated investigation

Validation Failure

Invalid requests fail before infrastructure execution.

The final result must distinguish:

completed investigation
partial investigation
insufficient evidence
provider failure
system failure

22. Retry and Idempotency

Retry behavior belongs to application/infrastructure code.

The system should distinguish:

Transient provider failure
    → bounded retry may be appropriate

Permanent validation failure
    → no retry

Duplicate request
    → must not create an unbounded loop

Detailed retry policies and duplicate-request behavior belong in TOOL_CONTRACTS.md and INVESTIGATION_LOGIC.md.

23. Security Architecture

Security is enforced outside the LLM.

User Input
    ↓
Application Validation
    ↓
Structured ToolRequest
    ↓
Authorization / Policy
    ↓
Infrastructure Adapter
    ↓
External System

The future GCP integration should use least-privilege, read-only monitoring access.

The LLM must never receive:

cloud credentials

database credentials

unrestricted API access

operating-system execution

infrastructure modification capability

Untrusted Telemetry

Telemetry is data, not instructions.

Potentially attacker-controlled content includes:

labels

metadata

alert descriptions

log-derived text in future extensions

Retrieved content must remain structurally separated from trusted instructions.

24. Audit Architecture

Every completed or terminated investigation must retain an audit record containing enough information to reconstruct:

Question
   ↓
Scope
   ↓
Tool requests
   ↓
Validation results
   ↓
Tool results
   ↓
Observations
   ↓
Deterministic analyses
   ↓
Hypotheses
   ↓
Findings
   ↓
Termination reason

The audit record should also retain relevant model/provider metadata where appropriate.

25. Agent Observability

Every investigation should have:

investigation_id
request_id

System telemetry should capture, where applicable:

investigation duration

tool-call count

tool-call latency

provider latency

LLM latency

error count

termination reason

outcome

LLM usage/cost information

Sensitive data and credentials must not be logged.

26. Deployment Architecture

Phase 1: Modular Monolith

┌──────────────────────────────────────────────┐
│                Application                  │
│                                             │
│ Presentation                                │
│ Application Services                        │
│ Investigation Domain                        │
│ Telemetry Integration                       │
│ LLM Integration                             │
│ Persistence                                 │
└──────────────────────────────────────────────┘
      │              │               │
      ▼              ▼               ▼
   SQLite           LLM         Mock Telemetry

This is a single deployable unit with internal module boundaries.

Future Production Deployment

When justified by actual requirements:

Presentation/API
        │
        ▼
Investigation Backend
     │       │       │
     ▼       ▼       ▼
Persistence LLM    Telemetry

The decomposition should happen only where independent scaling, isolation, or reliability benefits justify the operational cost.

27. Scalability Strategy

The architecture should allow:

concurrent investigations

horizontal scaling of stateless backend instances

shared durable persistence

controlled telemetry-provider concurrency

rate limiting

backpressure

The primary scalability principle is:

Separate state from process-local presentation state before scaling horizontally.

A queue should be introduced only if investigation duration or concurrency demonstrates a need for asynchronous job execution.

28. Performance Strategy

Likely latency sources:

LLM requests
Telemetry-provider requests

Therefore:

provider calls need explicit timeouts;

investigations need execution limits;

telemetry payloads must be bounded;

independent queries may be executed concurrently where safe;

unnecessary tool calls should be avoided;

deterministic processing should happen locally where practical;

long investigations need user-visible progress.

Parallel execution is an optimization to be introduced where it provides measurable benefit and does not compromise investigation ordering or correctness.

29. Typical Investigation Runtime

Example question:

"Why did the production payment service become slow yesterday?"

The runtime architecture is:

User
 ↓
Presentation
 ↓
InvestigationApplicationService
 ↓
InvestigationController
 ↓
LLMProvider
 ↓
search_metric_descriptors()
 ↓
Validated metric
 ↓
query_metric()
 ↓
Raw TimeSeries
 ↓
Deterministic processing
 ↓
Bounded ToolResult
 ↓
LLMProvider
 ↓
Additional evidence requests
 ↓
Evidence evaluation
 ↓
Hypothesis / Findings
 ↓
Persist investigation
 ↓
Presentation

This is an execution sequence, not a component decomposition.

30. Source Structure

The initial codebase should reflect the architectural boundaries without creating unnecessary package complexity.

src/
├── presentation/
│   └── streamlit/
│
├── application/
│   ├── investigations/
│   └── common/
│
├── domain/
│   ├── investigation/
│   ├── telemetry/
│   ├── evidence/
│   └── common/
│
├── infrastructure/
│   ├── llm/
│   ├── telemetry/
│   │   ├── mock/
│   │   └── gcp/
│   ├── persistence/
│   │   └── sqlite/
│   └── configuration/
│
└── bootstrap/

The exact package structure may be refined after DATA_MODEL.md and TOOL_CONTRACTS.md.

A class should not be created merely because a domain noun exists. Packaging should follow cohesive behavior.

31. Dependency Rules

Rule 1

domain/ must not import infrastructure or presentation.

Rule 2

application/ may depend on domain contracts and abstractions, but should not depend directly on concrete provider implementations.

Rule 3

infrastructure/ implements application/domain contracts.

Rule 4

presentation/ invokes application use cases and does not execute domain operations directly.

Rule 5

GCP SDK types must not escape the GCP adapter boundary.

Rule 6

LLM provider SDK types must not escape the LLM adapter boundary.

Rule 7

Database models must not automatically become domain entities through reuse.

These rules should be checked with architecture tests or static tooling where practical.

32. Configuration

Configuration belongs outside domain logic.

Configuration categories include:

LLM settings
Telemetry settings
Persistence settings
Investigation limits
Timeouts
Retry policies
Concurrency limits
Logging
Environment

Secrets must come from secure configuration/secrets mechanisms and must never be committed or passed to the LLM.

33. Architectural Decision Records

Potential ADRs:

ADR-001 Modular monolith for initial deployment
ADR-002 TelemetryProvider abstraction
ADR-003 LLMProvider abstraction
ADR-004 Investigation as aggregate root
ADR-005 Deterministic telemetry result processing
ADR-006 SQLite for initial persistence
ADR-007 GCP adapter boundary

ADR creation should be used for meaningful architectural decisions, not every implementation detail.

34. Architecture Verification

The architecture should be tested against these properties:

Modularity

Can the LLM provider be replaced without changing investigation logic?

Telemetry independence

Can the mock telemetry provider be replaced by the GCP provider without changing the domain?

Persistence independence

Can SQLite be replaced without changing the investigation domain?

Security

Can the LLM bypass validation or directly execute infrastructure operations?

Auditability

Can a completed investigation be reconstructed after the process ends?

Context protection

Can excessive telemetry reach the LLM unchecked?

Failure isolation

Can provider failures terminate or partially complete an investigation without corrupting previously collected evidence?

35. Architecture Evolution Rules

A component should become independently deployable only when one or more of the following is demonstrated:

measurable scaling bottleneck
OR
security isolation requirement
OR
reliability/failure isolation requirement
OR
independent operational ownership
OR
concrete product capability requiring separation

Otherwise, retain the modular-monolith boundary.

Do not introduce:

microservices

message brokers

vector databases

graph databases

distributed caches

agent orchestration frameworks

without a demonstrated requirement.

36. Final Architectural Model

┌──────────────────────────────────────────────────────────────────┐
│                        PRESENTATION                              │
│                                                                  │
│                    Streamlit / Future API                        │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                         APPLICATION                               │
│                                                                  │
│ Investigation Application Service                                │
│ Investigation Controller                                          │
│ Validation / Policy / Lifecycle                                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                            DOMAIN                                │
│                                                                  │
│ Investigation │ Evidence │ Hypothesis │ Finding │ Analysis       │
│                                                                  │
│ Metric │ Resource │ TimeSeries │ Observation │ Outcome            │
│                                                                  │
│ Provider / Repository Contracts                                   │
└───────────────┬──────────────────┬────────────────┬───────────────┘
                │                  │                │
                ▼                  ▼                ▼
┌──────────────────────┐ ┌──────────────────┐ ┌────────────────────┐
│ TELEMETRY            │ │ LLM INTEGRATION  │ │ PERSISTENCE        │
│                      │ │                  │ │                    │
│ Mock Provider        │ │ Primary Provider │ │ SQLite             │
│ GCP Provider         │ │ Alternative      │ │ PostgreSQL future  │
│ Future Providers     │ │ Mock Provider    │ │ Future stores      │
└──────────┬───────────┘ └──────────────────┘ └────────────────────┘
           │
           ▼
┌─────────────────────────┐
│ Monitoring Environment  │
│                         │
│ Mock GCP                │
│        /                │
│ Cloud Monitoring        │
└─────────────────────────┘

The architecture's primary goal is not the number of components. It is the quality of their boundaries:

high cohesion
      +
low coupling
      +
explicit contracts
      +
deterministic enforcement
      +
replaceable infrastructure
      +
evidence-backed reasoning

That combination provides a practical path from mocked development to a production-capable GCP integration without requiring a rewrite of the investigation domain.

37. Derived Technical Documents

The next documents should refine this architecture:

DATA_MODEL.md
TOOL_CONTRACTS.md
INVESTIGATION_LOGIC.md
AGENT_BEHAVIOR.md
SECURITY_ARCHITECTURE.md
OBSERVABILITY.md
TESTING_STRATEGY.md
GCP_INTEGRATION.md

The frozen PRD.md remains the product-level source of truth.

DOMAIN_MODEL.md remains the conceptual source for domain entities and invariants.

This document defines how those concepts are separated and composed into an implementable system.