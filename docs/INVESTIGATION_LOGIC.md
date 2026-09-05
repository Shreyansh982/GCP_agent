Investigation Logic

GCP Observability Investigation Agent

Status: Design Draft
Derived From: PRD v0.8, DOMAIN_MODEL.md, SYSTEM_ARCHITECTURE.md, TOOL_CONTRACTS v0.3, DATA_MODEL.md
Purpose: Define deterministic rules governing investigation execution, evidence processing, termination, and conclusion validation.

Purpose

This document defines how one investigation is executed from start to finish.

It specifies:

investigation lifecycle;

ownership of the agent loop;

tool execution;

deterministic result processing;

evidence creation;

hypothesis handling;

finding validation;

termination;

retry behavior;

partial investigation behavior;

conclude_investigation() behavior;

persistence coordination;

failure handling.

The LLM determines what evidence may be useful.

The application and domain determine whether the investigation can continue and how requested operations are executed.

Core Execution Principle

The investigation is a bounded controller-driven loop.

User Question
↓
Create Investigation
↓
LLM requests action
↓
ToolRequest / ConclusionRequest
↓
Validate
↓
Execute / Reject
↓
Process Result
↓
Update Evidence / Hypotheses
↓
Continue?
↙       ↘
yes        no
↓           ↓
Next      Conclude
Action      ↓
Validate
↓
Persist

The InvestigationController owns this loop.

The LLM provider does not own the lifecycle.

Phase 1 Scope

Phase 1 investigations are single-turn.

One investigation begins from one user question and ends with one terminal outcome.

Conversational memory is deferred.

The persisted investigation structure must nevertheless be sufficient for a future conversation layer to reference previous investigations without changing the investigation domain.

Investigation Lifecycle

The primary lifecycle is:

CREATED
↓
RUNNING
↓
TERMINAL

Terminal outcomes include:

COMPLETED
PARTIAL
INSUFFICIENT_EVIDENCE
FAILED

Status and termination reason remain separate concepts.

Example:

status = PARTIAL
termination_reason = MAX_TOOL_CALLS

No terminal investigation may execute another action.

Controller Responsibilities

The InvestigationController owns:

investigation execution loop;

action dispatch;

validation coordination;

tool execution coordination;

execution limits;

retry coordination;

evidence ingestion;

hypothesis/finding state updates;

conclusion validation;

terminal-state transition;

persistence coordination;

progress-event emission.

It must not contain:

provider-specific GCP query construction;

SQL;

LLM SDK logic;

infrastructure credential handling.

Investigation Initialization

When the user submits a question:

User Question
↓
Generate investigation_id
↓
Resolve authoritative temporal context
↓
Resolve initial scope where possible
↓
Create investigation
↓
Persist CREATED
↓
Transition to RUNNING

The original question is immutable.

The application, not the LLM, is authoritative for resolved timestamps and execution scope.

Agent Action Cycle

While the investigation is RUNNING:

Build the current LLM context.

Provide only the relevant evidence and constraints.

Ask the LLM for its next structured action.

Parse provider-specific output inside the LLM adapter.

Convert the result to an internal request.

Validate the request.

Execute or reject it.

Record the attempted step.

Process the result deterministically.

Update evidence and reasoning state.

Check termination conditions.

Continue or transition to terminal state.

The application controller owns the loop at every iteration.

Allowed Agent Actions

The agent may request:

search_metric_descriptors
query_metric
list_resources
get_alerts
conclude_investigation

Unknown actions are rejected.

The agent cannot request:

SQL
HTTP URLs
shell commands
arbitrary Python
credential retrieval
infrastructure mutation

Tool Validation Order

Each action follows:

Agent request
↓
Parse
↓
Schema validation
↓
Semantic validation
↓
Authorization / scope validation
↓
Execution-limit validation
↓
Result-size feasibility validation
↓
Provider/control execution

A rejected request must not reach the telemetry provider.

The attempted request and rejection reason are recorded for auditability.

Investigation Steps

Every attempted agent action receives one InvestigationStep.

InvestigationStep
├── sequence_number
├── ToolRequest / ConclusionRequest
├── validation result
├── ToolResult where applicable
├── derived observations
└── derived analyses

Sequence numbers are assigned by the application and are monotonic within an investigation.

A step is part of the historical audit record.

Deterministic Result Processing

Telemetry results are processed before being added to LLM context.

Provider Result
↓
Normalization
↓
Validation
↓
Alignment / Reduction / Aggregation
↓
Deterministic Analysis
↓
Observation Creation
↓
Bounded LLM-facing Result

The processor must preserve the semantics of the original query.

Observation Creation

The application creates authoritative observations from retrieved telemetry.

The LLM does not create authoritative observations.

An observation may represent:

a meaningful metric value;

a meaningful range;

an anomaly;

a deterministic comparison result;

another directly supportable telemetry fact.

Each observation receives an application-generated evidence ID.

Example:

obs-001

Observation IDs are stable for the lifetime of the investigation.

Deterministic Analysis Creation

Deterministic calculations are recorded as DeterministicAnalysis.

Examples:

percentage_change
mean
maximum
supported_percentile
trend_direction
threshold_crossing
temporal_overlap
cross_series_comparison

Each analysis receives an application-generated evidence ID:

analysis-001

Recorded inputs and parameters must make the calculation reproducible.

Evidence Generation Rules

The system should create investigation-facing evidence from meaningful results rather than turning every raw point into an observation.

Example:

10,000 raw points
↓
5-minute alignment
↓
deterministic summary
↓
3 observations
+
2 deterministic analyses

Raw telemetry may remain available through provenance.

The LLM receives bounded evidence, not an unbounded raw data dump.

Evidence Identity

Evidence IDs are generated by the application.

The LLM may reference existing IDs.

The LLM must not create authoritative evidence IDs.

Valid examples:

obs-001
obs-002
analysis-001

An evidence reference is valid only if it resolves to evidence already recorded in the current investigation.

Evidence Validity

Evidence is valid when:

it belongs to the current investigation;

it has not been invalidated;

provenance is available;

it represents a supported observation or deterministic analysis.

A nonexistent evidence ID invalidates a referencing hypothesis or finding.

Hypothesis Lifecycle

A hypothesis may evolve as evidence is collected.

Example:

OPEN
↓
SUPPORTED

or:

OPEN
↓
WEAKENED
↓
REJECTED

It may also remain:

UNRESOLVED

The LLM may propose a status.

The application/domain validates the referenced evidence and support level.

LLM confidence alone does not establish support.

For Phase 1, support_level is determined by the evidence relationships and
validation state rather than by a numerical confidence score:

SUPPORTED
At least one valid supporting evidence reference exists, and no material
contradictory evidence undermines the finding.

PARTIALLY_SUPPORTED
Valid supporting evidence exists, but material contradictory evidence or
a significant unresolved evidence gap remains.

UNSUPPORTED
No valid supporting evidence establishes the finding.

A causal finding must not be classified as SUPPORTED from temporal correlation
alone.

confidence is informational metadata in Phase 1. It may describe model
uncertainty, but it must not determine support_level, authorize a finding, or
override evidence validation.

Evidence Evaluation

Evidence may be classified as:

SUPPORTING
CONTRADICTING

Both relationships must remain represented.

Example:

Hypothesis:
"CPU saturation caused the latency increase."

Supporting:
obs-003
obs-004

Contradicting:
obs-005

Contradictory evidence must not be silently removed to simplify the response.

Finding Lifecycle

A finding is a conclusion the system is willing to report as supported.

A candidate finding should contain:

statement
supporting_evidence
optional contradicting_evidence
support_level

Possible support levels:

SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED

The application validates the evidence references before accepting the finding into authoritative investigation state.

Observation → Inference → Hypothesis/Finding

The epistemic progression is:

Observation
↓
Deterministic Analysis
↓
Inference
↓
Hypothesis / Finding

An inference directly supported by observations and deterministic analyses may become a finding.

An uncertain or unverified explanation remains a hypothesis.

Temporal correlation alone does not establish causation.

LLM Context Construction

The LLM context should contain only what is required for the current reasoning step.

Conceptually:

Investigation Context
├── original question
├── resolved scope
├── resolved time interval
├── relevant observations
├── deterministic analyses
├── hypothesis state
├── available tools
├── applicable constraints
└── relevant prior results

The system should not resend every raw provider result on every iteration.

Context Window Protection

Before a result enters LLM context:

Result
↓
Size check
↓
Within bound?
↙       ↘
yes       no
↓         ↓
pass      process
↓
bounded representation

Possible processing:

alignment;

reduction;

deterministic statistics;

summarization;

narrower query;

structured warning/error.

The exact method depends on the metric and investigation purpose.

Query Refinement

If evidence is too broad or too sparse, the LLM may request a refined query.

Example:

Broad scope
↓
list_resources()
↓
specific resource
↓
query_metric()

Every refined request is subject to the same validation and execution limits.

The agent may not bypass limits by decomposing one prohibited query into an unbounded number of smaller requests.

Tool-Call Budget

The investigation has a configurable maximum number of agent actions.

Preliminary default:

12 actions

The application owns budget accounting.

The policy must define consistently whether rejected/replayed actions consume budget; the initial implementation should count every action reaching the controller unless a documented replay rule explicitly excludes it.

The LLM cannot override the budget.

Investigation Duration

The controller tracks total execution duration.

When the configured limit is reached:

current evidence
↓
preserve
↓
terminate
↓
persist
↓
partial/failed outcome as appropriate

The controller must not continue merely because the LLM requests another action.

No-New-Evidence Termination

The controller may stop when additional actions are no longer producing meaningful new evidence.

Where possible, this should use deterministic signals such as:

repeated equivalent request
+
same relevant result
+
no new observations
+
no meaningful change in hypothesis state

The termination reason is:

NO_NEW_EVIDENCE

The exact heuristic can evolve without changing the domain contract.

Retry Policy

Retries occur only for retryable failures.

INVALID_REQUEST
→ no retry

POLICY_REJECTED
→ no retry

NOT_FOUND
→ no retry

NO_DATA
→ no retry

TIMEOUT
→ bounded retry

TRANSIENT_PROVIDER_ERROR
→ bounded retry

SYSTEM_ERROR
→ bounded retry where appropriate

Retries are application/infrastructure behavior.

The LLM does not control low-level retries.

LLM Failure Handling

If the LLM provider fails:

LLM failure
↓
record failure
↓
preserve collected evidence
↓
retry if policy permits
↓
otherwise terminate

If termination occurs:

status = FAILED
termination_reason = LLM_FAILURE

The final state must not imply successful completion.

Previously collected evidence remains part of the audit record.

Telemetry Failure Handling

If telemetry execution fails:

ToolRequest
↓
Provider failure
↓
Record failure
↓
Retry if retryable
↓
Continue or terminate

A provider failure must not be represented as NO_DATA.

Previously collected evidence remains valid unless explicitly invalidated.

No-Data Handling

NO_DATA means that the operation executed successfully but no matching observations were returned.

The LLM may decide to:

try another metric
narrow/broaden scope
adjust a supported query parameter
conclude insufficient evidence

All choices remain bounded by controller policy.

Duplicate Request Handling

Repeated identical requests must not create an unbounded loop.

The controller should derive a deterministic identity from normalized request content where practical.

Within one investigation:

first identical request
→ execute

repeat
→ replay previous deterministic result where safe
OR execute again subject to limits

A replayed result must preserve its original evidence IDs.

A bounded or paginated result must not be treated as complete unless its metadata says it is complete.

The detailed replay policy is implementation-level behavior.

conclude_investigation() Flow

The conclusion is a terminal agent action.

LLM
↓
conclude_investigation()
↓
Schema validation
↓
Evidence-reference validation
↓
Finding/hypothesis validation
↓
Domain state update
↓
Persist
↓
TERMINAL

The LLM does not directly set investigation status.

Conclusion Validation

Before acceptance:

Evidence

Every evidence ID must exist.

Ownership

Every referenced item must belong to the current investigation.

Support

A confirmed finding must have appropriate supporting evidence or deterministic analysis.

Hypothesis

Unresolved hypotheses cannot be represented as confirmed findings.

Contradictions

Known contradicting evidence must remain represented.

Lifecycle

The investigation must still be running.

If validation fails:

conclusion rejected
↓
record validation result
↓
investigation remains RUNNING
↓
LLM may request another action

Successful Conclusion

A valid conclusion produces:

Findings
+
Hypotheses
+
Unresolved Questions
+
Evidence References
+
Outcome

These are persisted as one consistent terminal transition.

The final response is returned only after durable persistence succeeds.

Conclusion With Insufficient Evidence

The agent may conclude that evidence is insufficient.

Example:

Finding:
Latency increased during the requested interval.

Hypothesis:
CPU saturation may have contributed.

Unresolved:
Available telemetry does not establish causation.

This may be a valid completed investigation rather than a system failure.

The outcome model distinguishes successful completion with insufficient evidence from technical failure.

Partial Investigation Semantics

If execution stops before sufficient evidence is collected:

status = PARTIAL

The final result must contain:

supported findings
unconfirmed hypotheses
unresolved questions
missing evidence where known
termination reason

Previously collected evidence is retained.

Example:

Termination:
MAX_TOOL_CALLS

Supported:
CPU increased during the latency spike.

Unconfirmed:
CPU caused the latency spike.

Missing:
Application logs were unavailable.

The system must never invent a definitive root cause merely to make the response appear complete.

Failed Investigations

Technical failures should not be disguised as evidence insufficiency.

Examples:

LLM provider unavailable
database unavailable
unrecoverable infrastructure failure

should result in a failure-oriented outcome.

Previously collected evidence should remain available for audit where possible.

Persistence Rules

The repository must persist:

investigation creation
important state transitions
investigation steps
tool requests
tool results
observations
deterministic analyses
hypotheses
findings
terminal outcome

At terminal transition, enough state must exist to reconstruct:

question
scope
steps
tool requests
tool results
observations
analyses
hypotheses
findings
outcome
termination reason

Transactional Terminal Transition

The final terminal transition should be persisted atomically where practical:

validate conclusion
↓
transaction
├── findings
├── hypotheses
├── outcome
└── investigation terminal state
↓
commit

If persistence fails, successful completion must not be reported.

Progress Events

The application should emit progress events independently of the UI implementation.

Potential events:

InvestigationStarted
StepStarted
ToolRequested
ToolValidated
ToolExecuted
EvidenceCreated
HypothesisUpdated
StepCompleted
InvestigationConcluded
InvestigationTerminated

These events may support:

Streamlit progress;

logging;

audit correlation;

testing;

future API/WebSocket/SSE presentation.

The event stream is not the authoritative investigation state. Persisted investigation state is authoritative.

Event Ordering

Events for one investigation must preserve causal ordering.

Example:

StepStarted
↓
ToolRequested
↓
ToolValidated
↓
ToolExecuted
↓
EvidenceCreated
↓
StepCompleted

No event may claim that a provider operation executed before its validation succeeded.

Deterministic Scenario Tests

The investigation logic should be tested against fixed mock scenarios.

CPU Saturation

traffic ↑
CPU ↑
latency ↑
memory stable

The system should identify the supported relationship without making unsupported causal claims.

Latency Without CPU

latency ↑
CPU normal

The system must not conclude CPU saturation.

Missing Data

query → NO_DATA

The system should adapt or conclude insufficient evidence.

Contradictory Evidence

supporting signal
+
contradicting signal

The reasoning must preserve the conflict.

Tool Limit

budget reached
→ PARTIAL
→ evidence retained
→ termination recorded

LLM Failure

LLM timeout
→ bounded retry
→ failure if exhausted
→ evidence preserved
→ failure persisted

Invalid Conclusion

invalid evidence ID
→ conclusion rejected
→ investigation remains RUNNING

Deterministic Correctness Rules

These rules must not depend on LLM interpretation:

start_time < end_time
tool exists
tool arguments satisfy schema
metric exists
resource scope is valid
aggregation is supported
limits are enforced
evidence IDs exist
evidence belongs to investigation
terminal investigation cannot continue
deterministic analysis is reproducible

LLM Decision Rules

The LLM may decide:

which metric may answer the question
which resource may be relevant
which evidence is useful next
whether additional evidence may reduce uncertainty
which hypothesis to consider
when to request conclusion
how to phrase the final explanation

The LLM may not decide:

whether an authorization policy can be bypassed
whether a hard execution limit can be exceeded
whether nonexistent evidence exists
whether invalid evidence references are valid
whether infrastructure may be modified
whether an unsupported causal claim is established fact

Completion Criteria

An investigation may terminate normally when:

sufficient evidence supports the requested answer; or

additional bounded investigation is unlikely to produce meaningful new evidence; or

the agent concludes with insufficient evidence.

It may terminate partially or unsuccessfully when:

an execution limit is reached; or

an unrecoverable execution/provider failure occurs.

The Controller and domain enforce the actual transition.

Implementation Constraints

Phase 1 uses a simple deterministic controller loop.

Do not introduce:

distributed workflow engines;

message brokers;

event sourcing;

multi-agent orchestration;

distributed locks

without a demonstrated requirement.

The project should remain a modular monolith during initial implementation.

Final Logic Model

         ┌──────────────────────┐
         │ Investigation        │
         │ Controller           │
         └──────────┬───────────┘
                    │
               next action
                    ▼
               ┌────────┐
               │  LLM   │
               └────┬───┘
                    │
          ToolRequest /
       ConclusionRequest
                    │
                    ▼
        ┌─────────────────────┐
        │ Validation + Policy │
        └──────────┬──────────┘
                   │
            approved action
                   ▼
      ┌─────────────────────────┐
      │ Registered Action Handler│
      └───────────┬─────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Provider /     │
         │ Control Action │
         └───────┬────────┘
                 │
             result
                 ▼
      ┌────────────────────────┐
      │ Deterministic Processor│
      └──────────┬─────────────┘
                 │
        bounded evidence
                 ▼
      ┌────────────────────────┐
      │ Investigation State     │
      │                         │
      │ observations            │
      │ analyses                │
      │ hypotheses              │
      │ findings                │
      └──────────┬─────────────┘
                 │
            continue?
            /                            yes           no
           │             │
           └─────┐   conclude
                 │       │
                 │       ▼
                 │   evidence validation
                 │       │
                 │       ▼
                 │    transaction
                 │       │
                 └───────►TERMINAL

Derived Documents

This document should guide:

AGENT_BEHAVIOR.md
SECURITY_ARCHITECTURE.md
OBSERVABILITY.md
TESTING_STRATEGY.md
GCP_INTEGRATION.md

The frozen PRD.md remains the product authority.

DOMAIN_MODEL.md defines the domain semantics.

SYSTEM_ARCHITECTURE.md defines component boundaries.

TOOL_CONTRACTS.md defines interaction contracts.

DATA_MODEL.md defines persistence structures.

This document defines how those pieces behave together during an investigation.