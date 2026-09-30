# GCP Observability Investigation Agent

An engineering project exploring a bounded, evidence-backed, LLM-assisted approach to GCP observability investigations. It is not a replacement for Google Cloud Monitoring or a general observability platform. Instead, it is a focused investigation layer: a user asks an operational question, the system gathers permitted telemetry through structured operations, records what it observed, and eventually produces a conclusion that is traceable to evidence.

The central engineering question is where to draw the line between probabilistic reasoning and deterministic control. An LLM may help interpret a question, choose the next useful observation, and explain a result. It does not get direct access to databases, cloud credentials, shell commands, or unconstrained APIs. Application and domain code own validation, scope, limits, lifecycle, evidence identity, calculations, and persistence.

## Project Snapshot

| Area | Verified current state |
| --- | --- |
| Completed | Phase 1, Phase 1.1, and M10 (Evaluation Domain) |
| Current | M11, Deterministic Evaluation Scenario Harness — authorized, not started |
| Planned evaluation | 5 documented M11 core scenarios; the harness, evaluator, and M12–M15 work are not implemented |
| Recorded M10 validation | 168 full-suite tests; 79 architecture tests; 7 focused M10 tests |
| Default investigation limits | 12 actions; 5-minute duration; 7-day query interval; 100 result/collection items |
| Default input limits | 4,000-question-character limit; 32 KiB serialized tool-request limit; 50 label/filter entries per map |

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

The telemetry operations are metric-descriptor discovery, metric queries, resource discovery, alert retrieval, and a structured conclusion action. The provider-facing contract is deliberately independent of SQLite and the eventual GCP adapter. Large or incomplete results are handled explicitly rather than silently treated as complete.

## Current status

Phase 1 and its Phase 1.1 corrective remediation are complete. Phase 2 is approved: M10, **Evaluation Domain**, is complete, and M11, **Deterministic Evaluation Scenario Harness**, is the current authorized milestone but has not started.

The Phase 2 documentation now defines the evaluation criterion semantics, the
five-scenario M11 execution catalog, semantic reproducibility rules, and later
M12-M15 dependencies. Those definitions are specifications only: no scenario
harness, evaluator, adversarial evaluation suite, hypothesis-history mechanism,
or evaluation-run persistence has been implemented yet.

Implemented today:

- A provider-independent domain model for investigations, time intervals, telemetry identities, evidence, hypotheses, findings, support levels, deterministic analyses, and evaluation-domain concepts.
- A bounded, single-turn investigation application with registered telemetry and conclusion tools, deterministic validation and authorization, evidence creation, persistence, and controller-owned execution.
- SQLite-backed telemetry and investigation/audit persistence with foreign keys, transactions, optimistic version checks, and append-oriented historical records.
- A deterministic, SQLite-backed `MockTelemetryProvider` and scenario fixtures, plus a `FakeLLMProvider` for deterministic automated tests.
- A Gemini adapter for the real runtime LLM provider and a Streamlit presentation interface.
- M10 evaluation scenario, criterion, criterion-outcome, result, and classification models. M10 adds no evaluator, deterministic evaluation execution, persistence changes, provider changes, or Streamlit changes.

The standard test suite is deterministic and does not require live GCP access or paid Gemini calls. Verified M10 validation recorded 7 focused tests, 79 architecture tests, and 168 full-suite tests.

Not implemented: the M11 scenario harness, an investigation-quality evaluator (M12), adversarial FakeLLM evaluation scenarios (M13), Phase 2 hypothesis/provenance enhancements (M14), evaluation run metadata/reproducibility work (M15), and real GCP telemetry integration. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the controlled milestone sequence.

## Architecture

The project is a modular monolith with dependency inversion at its center:

```text
Presentation  ->  Application  ->  Domain
                                  ^
                                  |
                           Infrastructure adapters
```

The domain contains provider-neutral investigation and observability concepts. Application code coordinates use cases and enforces policy. Infrastructure implements the boundaries: SQLite provides persistence and mock telemetry, Gemini is the runtime LLM adapter, and Google Cloud Monitoring remains a future adapter. Presentation is the Phase 1 Streamlit interface.

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
  domain/          Investigation, evidence, telemetry, evaluation types, and ports
  application/     Investigation orchestration, tools, and deterministic controls
  infrastructure/  SQLite, mock telemetry, Gemini, and configuration adapters
  presentation/    Streamlit interface
  bootstrap/       Runtime composition and wiring

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

The standard suite is deterministic: it uses SQLite, mock scenario data, `FakeLLMProvider`, and fake Gemini clients as applicable; it does not require live GCP access or paid Gemini calls. The tests exercise import boundaries, domain invariants, persistence integrity, provider and tool behavior, controller/application flows, Gemini adapter behavior, and Streamlit security.

## Direction

The current authorized milestone is M11, which will add a deterministic,
run-isolated harness for executing five documented core evaluation scenarios
against the existing application/controller stack. It is not yet implemented.
Planned subsequent milestones are M12 Investigation Evaluator, M13 Adversarial
FakeLLM Evaluation Suite, M14 Hypothesis Lifecycle and Provenance, and M15
Evaluation Run Metadata and Reproducibility.

The intended endpoint is not autonomous infrastructure remediation. It is a read-only, bounded investigation system that can help an operator understand what available telemetry establishes - and what it does not.
