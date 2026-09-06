# GCP Observability Investigation Agent

An engineering project exploring a bounded, evidence-backed, LLM-assisted approach to GCP observability investigations. It is not a replacement for Google Cloud Monitoring or a general observability platform. Instead, it is a focused investigation layer: a user asks an operational question, the system gathers permitted telemetry through structured operations, records what it observed, and eventually produces a conclusion that is traceable to evidence.

The central engineering question is where to draw the line between probabilistic reasoning and deterministic control. An LLM may help interpret a question, choose the next useful observation, and explain a result. It does not get direct access to databases, cloud credentials, shell commands, or unconstrained APIs. Application and domain code own validation, scope, limits, lifecycle, evidence identity, calculations, and persistence.

## Why this exists

Investigating an incident often means moving between metrics, resources, alerts, time windows, and competing explanations. A question such as "Why did the payment service become slow?" should not be answered by plausible prose alone. It needs explicit observations - for example, latency, traffic, CPU, memory, and alerts - and a clear account of what those observations support, contradict, or leave unresolved.

This project models that workflow as a bounded investigation. It distinguishes raw telemetry from investigation-facing observations, deterministic analyses, hypotheses, and findings. Temporal correlation is not treated as proof of causation, missing data is not treated as zero, and contradictory evidence remains part of the record.

## How the system is intended to work

At a high level, a single-turn investigation follows this path:

```text
Question
  -> application resolves scope and time context
  -> LLM proposes a structured action
  -> application validates policy and executes a registered operation
  -> telemetry is normalized and reduced deterministically
  -> observations and analyses become durable evidence
  -> validated findings, hypotheses, and outcome are persisted
```

The planned telemetry operations are metric-descriptor discovery, metric queries, resource discovery, alert retrieval, and a structured conclusion action. The provider-facing contract is deliberately independent of SQLite and the eventual GCP adapter. Large or incomplete results are meant to be handled explicitly rather than silently treated as complete.

## Current status

The project has completed and verified the foundation, domain, persistence, and mock-telemetry milestones.

Implemented today:

- A provider-independent domain model for investigations, time intervals, telemetry identities, evidence, hypotheses, findings, support levels, and deterministic analysis primitives.
- Explicit investigation lifecycle rules and application-generated evidence IDs.
- SQLite migrations for telemetry plus investigation/audit data, with foreign-key enforcement, transactions, optimistic version checks, and append-oriented historical records.
- A deterministic, SQLite-backed `MockTelemetryProvider` with scenario fixtures for CPU saturation, latency without CPU pressure, missing data, and contradictory evidence.
- Metric descriptor search, resource discovery, metric time-series queries, supported alignment/reduction, and alert retrieval at the provider layer.
- Architecture, domain, persistence, and mock-provider test suites.

Not implemented yet: the registered tool layer and its Pydantic contracts, authorization and policy validation, the investigation controller/context builder, a fake or Gemini LLM adapter, the application service, and the Streamlit interface. The repository therefore does not yet provide an end-user investigation command or web application.

The current implementation plan places the project at **M4: Tools and Validation**. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the controlled milestone sequence.

## Architecture

The project is a modular monolith with dependency inversion at its center:

```text
Presentation  ->  Application  ->  Domain
                                  ^
                                  |
                           Infrastructure adapters
```

The domain contains provider-neutral investigation and observability concepts. Application code is intended to coordinate use cases and enforce policy. Infrastructure implements the boundaries: SQLite currently provides persistence and mock telemetry; future adapters include Google Cloud Monitoring and Gemini. Presentation is reserved for the Phase 1 Streamlit interface.

This separation is practical rather than ornamental. The domain has no SQLite, Streamlit, GCP SDK, or LLM SDK dependency. The mock telemetry adapter implements the same provider-shaped capabilities intended for a future GCP adapter, while SQLite records an audit trail without becoming the domain model.

## Engineering principles

- **Evidence before conclusions.** Findings reference observations or deterministic analyses; hypotheses remain distinct from established findings.
- **Deterministic enforcement.** The model may suggest an action, but deterministic code controls validation, authorization, execution limits, calculations, lifecycle transitions, and evidence validation.
- **Bounded investigations.** Tool calls, duration, query size, and context size are designed to be application-controlled constraints.
- **Preserved observability semantics.** Metric labels and monitored-resource labels are separate namespaces, and a time series identifies both a metric and a resource.
- **Auditability over hidden reasoning.** Investigation steps, results, evidence, hypotheses, findings, and outcomes are designed to be reconstructible from persisted state.
- **Untrusted telemetry.** Labels, metadata, and alert text are data, not instructions. Credentials and provider SDK objects stay outside domain state and LLM context.

## Project layout

```text
src/gcp_observability_agent/
  domain/          Investigation, evidence, telemetry value types, and ports
  infrastructure/  SQLite persistence and mock telemetry implementations
  application/     Reserved for use-case orchestration
  presentation/    Reserved for the Streamlit interface
  bootstrap/       Reserved for composition and runtime wiring

docs/               Product, architecture, contracts, security, and test design
tests/              Architecture, domain, persistence, and telemetry tests
```

The design documentation is intentionally detailed because it defines boundaries that later milestones must preserve. Useful entry points are the [PRD](docs/PRD.md), [system architecture](docs/SYSTEM_ARCHITECTURE.md), [domain model](docs/DOMAIN_MODEL.md), [tool contracts](docs/TOOL_CONTRACTS.md), and [implementation plan](docs/IMPLEMENTATION_PLAN.md).

## Development and testing

The project targets Python 3.11+ and uses `pytest`. Install the project with development dependencies, then run the test suite:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The standard suite is deterministic: it uses SQLite and checked-in/mock scenario data, and does not require live GCP access or paid LLM calls. The current tests exercise import boundaries, domain invariants, persistence integrity and round trips, and mock-provider behavior.

## Direction

The next step is the tools-and-validation milestone: structured request/result schemas, a registered tool set, semantic and scope validation, result-size protection, retry classification, and evidence creation. Later milestones add the controller-driven investigation loop, application wiring, Gemini integration, and Streamlit presentation.

The intended endpoint is not autonomous infrastructure remediation. It is a read-only, bounded investigation system that can help an operator understand what available telemetry establishes - and what it does not.
