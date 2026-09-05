GCP Integration

GCP Observability Investigation Agent

Status: Design Draft
Version: 0.2
Derived From: PRD v0.8, DOMAIN_MODEL.md, SYSTEM_ARCHITECTURE.md, TOOL_CONTRACTS v0.3, DATA_MODEL.md, INVESTIGATION_LOGIC.md, AGENT_BEHAVIOUR v0.2, SECURITY_ARCHITECTURE.md
Purpose: Define how the provider-neutral telemetry contracts map to Google Cloud Monitoring while preserving the domain and application boundaries.

1. Purpose

This document defines the real-GCP integration boundary.

It covers:

Google Cloud Monitoring APIs;

authentication;

IAM;

metric discovery;

monitored-resource discovery;

time-series queries;

alignment/reduction;

alerting-policy access;

response normalization;

pagination and result limits;

provider errors;

security constraints;

migration from the mock provider.

The GCP integration must remain an infrastructure concern.

The domain and LLM must not depend on GCP SDK types.

2. Integration Principle

The architecture is:

Domain/Application Contract
            ↓
     GCPTelemetryProvider
            ↓
      Google Cloud Client
            ↓
      Cloud Monitoring API

The provider adapter translates between:

our domain/tool contract

and:

Google Cloud Monitoring API

No GCP-specific API object should escape the adapter boundary.

3. Cloud Monitoring API Scope

The initial integration uses Cloud Monitoring API v3 concepts for:

MetricDescriptor
MonitoredResourceDescriptor
TimeSeries
AlertPolicy

Google documents TimeSeries, MetricDescriptor, and MonitoredResourceDescriptor as part of the Monitoring API's metrics API. timeSeries.list, metricDescriptors.list, and monitoredResourceDescriptors.list use a project name and can behave differently when the project is a metrics-scope scoping project. citeturn373320search3

The adapter must therefore distinguish:

named project
vs.
metrics-scope scoping project

rather than assuming every Monitoring API call has identical project semantics.

4. Authentication

4.1 Application Default Credentials

The initial provider should use Application Default Credentials (ADC).

Google documents ADC as the mechanism through which authentication libraries locate credentials based on the application environment. ADC supports local development and attached service accounts without requiring application code to change between environments. citeturn917325search0turn917325search2

Conceptually:

GCPTelemetryProvider
        ↓
Google authentication library
        ↓
ADC
        ↓
Credential
        ↓
Monitoring client

4.2 Credential Sources

Depending on environment, ADC may obtain credentials from:

GOOGLE_APPLICATION_CREDENTIALS;

local ADC created with gcloud auth application-default login;

an attached service account available through the environment. citeturn917325search0

The implementation should prefer environment-appropriate workload identity/service-account attachment over long-lived service-account key files.

Google explicitly notes that service-account keys create security risk and are not recommended. citeturn917325search0

5. IAM

The first real-GCP deployment should use the least-privileged read-only Monitoring permissions required by the application.

Google's roles/monitoring.viewer role provides read-only access to Monitoring data and configurations, including monitoring alerts and alert-policy read operations. citeturn917325search10

The final role assignment must be verified against the exact API methods used by this project.

No write role is required for the initial agent.

The agent does not create or modify:

alert policies;

metrics;

monitored resources;

infrastructure;

IAM policies.

6. Project and Metrics Scope Semantics

The integration must explicitly model the project used as the Monitoring API request name.

Google documents that:

some Monitoring API methods operate on a named project;

timeSeries.list, timeSeries.query, metricDescriptors.list, and monitoredResourceDescriptors.list have special behavior when the named project is also a scoping project for a metrics scope;

those methods may retrieve data from the named project and projects monitored by that metrics scope. citeturn373320search3

Therefore:

Application Authorization Scope
            ↓
Requested project/scoping project
            ↓
GCP adapter
            ↓
Monitoring API

The adapter must not silently expand the authorized project scope merely because the selected project is a metrics-scope scoping project.

7. Metric Discovery Mapping

Our:

search_metric_descriptors()

maps to the Cloud Monitoring:

projects.metricDescriptors.list

operation.

Google documents that metricDescriptors.list returns metric descriptors available in a project, and supports filtering to restrict the returned set. citeturn373320search1turn373320search4

The adapter should:

accept the provider-neutral discovery request;

construct the appropriate Monitoring API request;

iterate over the provider's paged response;

convert each descriptor into our MetricDescriptor;

apply application-level result limits;

return bounded candidate descriptors.

The LLM should see canonical metric types and useful metadata, not raw SDK objects.

8. Metric Descriptor Mapping

The domain's:

MetricDescriptor
├── metric_type
├── description
├── labels
├── metric_kind
├── value_type
└── metadata

maps naturally to the Monitoring API's metric descriptor concepts.

Google documents metric descriptors as the definitions used to describe metric types, including their labels, value type, metric kind, unit, description, and metadata. citeturn373320search0turn373320search2

The adapter should preserve these semantics.

It should not collapse:

metric descriptor labels

with:

monitored-resource labels

9. Monitored Resource Discovery Mapping

Our:

list_resources()

is an application-level resource discovery operation.

Cloud Monitoring's:

projects.monitoredResourceDescriptors.list

returns monitored-resource descriptors, which describe resource types and their label schemas. It is not a direct inventory of concrete resource instances.

Therefore the initial GCPTelemetryProvider should use telemetry-backed discovery for concrete resources when the requested resource scope cannot otherwise be resolved:

list_resources()
      ↓
GCPTelemetryProvider
      ↓
timeSeries.list()
      ↓
extract unique MonitoredResource identities
      ↓
apply requested resource/label filters
      ↓
return bounded resources

This approach keeps the initial integration within Cloud Monitoring and avoids adding a separate Cloud Asset Inventory dependency solely for resource discovery.

Important Limitation

Telemetry-backed discovery is not a universal GCP resource inventory.

A resource may exist in GCP but not appear if it has no relevant metric time series available to the discovery query.

The adapter must communicate this limitation through tool semantics/documentation and must not imply that the returned set is necessarily the complete set of resources in the project.

The resource-descriptor API may still be used when the application needs to discover supported resource types or their label schemas.

10. Resource Mapping

A real Cloud Monitoring time series contains the monitored resource that produced its values.

Google documents MonitoredResource as part of a time series and that the resource's label values identify the monitored resource instance.

The adapter maps:

GCP MonitoredResource
        ↓
MonitoredResource
├── type
└── labels

The adapter must preserve the labels required to identify the resource.

For list_resources(), concrete resource identities discovered from time series are deduplicated before being returned.

10. Resource Mapping

A real Cloud Monitoring time series embeds the monitored resource that produced its values.

Google documents the MonitoredResource object as part of a time series and states that each combination of resource-label values identifies a unique resource instance. citeturn373320search0

Therefore the adapter maps:

GCP MonitoredResource
        ↓
MonitoredResource
├── type
└── labels

The adapter must preserve all labels required to identify the resource.

11. Time-Series Query Mapping

Our:

query_metric()

maps to:

projects.timeSeries.list

for the initial implementation.

Google documents the query filters for timeSeries.list as including:

project
resource.type
resource.labels.[KEY]
metric.type
metric.labels.[KEY]

and requires the metric selector to identify exactly one metric type for timeSeries.list. citeturn373320search4

The adapter should therefore construct the provider filter from structured selectors rather than allowing the LLM to supply a raw Monitoring filter string.

Conceptually:

ToolRequest
    ↓
MetricSelector
ResourceSelector
TimeInterval
Aggregation
    ↓
GCPTelemetryProvider
    ↓
Monitoring API filter + aggregation

12. Filter Construction

The adapter may internally generate a filter such as:

metric.type = "compute.googleapis.com/instance/cpu/usage_time"
AND resource.type = "gce_instance"

but the LLM never sees raw provider filter syntax as its contract.

The application owns construction and escaping of the provider filter.

Metric and resource label filters must remain separately represented before construction.

13. Time-Series Identity

The provider mapping preserves:

Metric
├── type
└── labels

MonitoredResource
├── type
└── labels

TimeSeries
├── metric
├── resource
└── points

Google documents that a time series is a list of timestamped data points for one metric type from a specific monitored resource. citeturn373320search4turn373320search0

This matches the domain model directly.

14. Aggregation Mapping

Our aggregation contract:

alignment_period
per_series_aligner
cross_series_reducer
group_by_fields

maps to Cloud Monitoring aggregation concepts.

Google documents that aggregation typically begins by aligning each time series to common time boundaries and can then combine multiple aligned series. citeturn373320search9

For the API-level semantics:

per_series_aligner
+
alignment_period
        ↓
aligned series

cross_series_reducer
+
group_by_fields
        ↓
reduced series

15. Alignment Rules

Alignment is applied per series.

The provider adapter must preserve the selected:

alignment period
per-series aligner

and normalize the resulting time series into the domain representation.

The adapter must not silently replace an unsupported aligner with another calculation.

Unsupported combinations should produce a structured provider/validation error.

16. Cross-Series Reduction Rules

Cross-series reduction may combine aligned series.

Google documents that time-series data must first be aligned before cross-series reduction and that when a cross_series_reducer is specified, per_series_aligner must be specified and cannot be ALIGN_NONE; alignment_period must also be specified. citeturn917325search11

The adapter must enforce this before making the provider call.

17. Group-By Semantics

group_by_fields determine how time series are partitioned before cross-series reduction.

Google documents that:

group-by fields preserve dimensions;

each series belongs to one grouping subset;

fields not specified are aggregated away;

resource.type is implicitly part of grouping semantics;

cross-series reduction cannot reduce across different resource types. citeturn917325search11

The adapter must preserve these semantics when translating provider responses.

18. Metric Kind and Value Type Effects

Alignment and reduction can change the resulting metric kind or value type.

Google explicitly notes that alignment can change metric_kind or value_type, and reduction can also yield a series with different metric kind/value type from the input. citeturn917325search11

Therefore the adapter must not assume:

output value type == input value type

or:

output metric kind == input metric kind

when constructing the normalized result.

19. Query Result Normalization

The GCP adapter converts API responses into the domain/provider-neutral shape:

GCP TimeSeries
    ↓
Provider normalization
    ↓
TimeSeries
├── metric
├── resource
└── points

SDK/protobuf-specific representations must not escape the adapter.

20. Data Point Mapping

The domain model allows:

point_time
interval_start
interval_end
value

The adapter should preserve interval semantics from the provider.

This is particularly important for metric kinds whose values are associated with intervals rather than a single instant.

The normalization layer must not discard interval information merely to simplify the mock schema.

21. Pagination

Cloud Monitoring list operations may return paged results.

The adapter must iterate pages within application-configured bounds.

The domain/tool contract must not expose provider-specific page tokens unless continuation is intentionally included in the public contract.

For bounded operations:

provider pages
    ↓
adapter accumulation
    ↓
application result limit
    ↓
bounded result + metadata

If the provider result is incomplete because the adapter stopped at an application limit, result_metadata.truncated must be true.

22. Large Response Protection

The GCP adapter must protect the application from excessive provider responses before attempting to materialize unnecessarily large payloads.

The implementation should enforce:

response-size limit
+
page-size/result-count limit
+
time-series/result limit

before expensive downstream processing where possible.

The exact HTTP/client mechanism is an implementation decision.

For example:

response
 ↓
size guard
 ↓
safe to parse?
 ├── yes
 └── no → structured provider error

This protects against resource-exhaustion scenarios.

23. Result-Size and Context Limits

Two different limits must remain separate:

GCP/provider response safety
        ↓
application result safety
        ↓
LLM context safety

A result may be:

small enough to parse

but still:

too large to send to the LLM

The deterministic result processor handles the latter.

24. Metric Descriptor Search Limits

Descriptor discovery can return large numbers of metric types.

The adapter/application should bound:

number of descriptors
response size
search scope

The final LLM-facing result must explicitly indicate truncation where applicable.

Google documents that projects can contain many metric descriptors, so unbounded discovery should not be assumed safe. citeturn373320search1

25. Alert Integration

Our:

get_alerts()

is intended to retrieve alert/incident information relevant to an investigation.

The GCP integration must distinguish:

AlertPolicy
    = configuration/rule

Incident
    = firing/active alert occurrence

For the question:

"What alerts fired during this interval?"

alert incidents are the relevant source, not merely the policies that exist.

The current Monitoring API exposes incident retrieval through the alerts/incident API surface. The adapter should verify the exact client-library method and response shape used by the selected Python client version before implementation.

Alert policy metadata may be retrieved separately when needed to explain:

which policy/condition caused the incident

The initial integration remains read-only.

26. Alert and Incident Model Mapping

The domain Alert should preserve enough information for investigation:

alert_id
policy_reference
condition
resource_reference where applicable
metric_reference where applicable
severity
status
start_time
end_time
metadata

The adapter should populate incident/firing information from the incident endpoint and policy/condition metadata when available.

The conceptual distinction is:

AlertPolicy:
"CPU > 90% for 5 minutes"

Incident:
"That policy fired for resource X at time T"

An incident may therefore reference a policy without the policy itself being the event being investigated.

metric_reference remains optional because alert conditions are not necessarily limited to one metric form.

27. Alerting Policy and Incident Scope

Alert and incident retrieval must use the same application authorization model as telemetry queries.

The adapter must not allow an LLM-supplied project or scope to expand access.

Conceptually:

Authenticated Principal
        ↓
Authorized GCP scope
        ↓
Incident / policy query
        ↓
Normalized Alert

The adapter must verify the exact semantics of the selected Monitoring incident API for project and metrics-scope behavior before implementation.

Where policy metadata is required, it should be retrieved only for incidents already within the authorized investigation scope.

28. Provider Error Mapping

Google API/client errors should be mapped into provider-neutral error categories.

Conceptual mapping:

authentication failure
        ↓
AUTHENTICATION_ERROR

authorization denied
        ↓
AUTHORIZATION_ERROR

invalid Monitoring request
        ↓
INVALID_REQUEST

resource/metric unavailable
        ↓
NOT_FOUND

request timeout
        ↓
TIMEOUT

quota/transient service issue
        ↓
PROVIDER_ERROR

The exact mapping should preserve enough detail for retry decisions without leaking credentials or internal infrastructure details.

29. Retry Behavior

Retries should be performed by the application/provider layer.

Potential retry candidates:

transient provider errors
temporary unavailability
certain timeouts

Do not retry:

invalid filter
invalid metric
invalid aggregation
authorization failure
not found
policy rejection

Retry counts and backoff are application configuration.

30. Authentication Failure Handling

Authentication or authorization failures should terminate the relevant operation rather than prompting the LLM to "try another credential."

The LLM never receives credential details.

The system should expose a safe provider error to the investigation layer.

31. GCP SDK Boundary

The adapter may internally use:

MetricServiceClient
AlertPolicyServiceClient
protobuf messages
GCP enums

but none of these types should escape:

GCPTelemetryProvider

Instead:

GCP protobuf
      ↓
Mapper
      ↓
Domain/provider-neutral object

This is essential for preserving the mock-provider substitution requirement.

32. Mock-to-GCP Compatibility

The mock provider must satisfy the same provider-neutral contracts as the GCP provider.

                 TelemetryProvider
                    /          \
                   /            \
MockTelemetryProvider      GCPTelemetryProvider
          │                         │
      SQLite                  Cloud Monitoring

A scenario tested against the mock provider should be capable of exercising the same application/domain behavior when the provider is swapped.

Differences caused by actual GCP semantics should be represented in provider-specific tests rather than silently altering domain contracts.

33. GCP-Specific Capabilities Deferred

The initial integration does not need to support every Cloud Monitoring feature.

Possible future extensions include:

timeSeries.query
metric descriptor APIs beyond discovery
monitored resource descriptor querying
PromQL-related monitoring capabilities
advanced alert condition types
metric scopes
groups
additional aggregation semantics

Only the capabilities needed by the approved MVP should be implemented initially.

34. API Client Selection

The implementation should prefer official Google Cloud client libraries for Python unless a concrete requirement makes direct REST calls preferable.

This keeps authentication, retries, pagination, and API object handling within the supported client ecosystem while preserving our own adapter boundary.

The exact library/package selection is an implementation decision.

35. Development Authentication

For local development, ADC can be configured with:

gcloud auth application-default login

Google documents this as a way to make credentials available to Google Cloud client libraries and APIs. citeturn917325search7

Development credentials must not be copied into the repository or embedded into test fixtures.

36. Production Authentication

In a deployed GCP environment, prefer an attached service account or another workload-appropriate ADC mechanism rather than long-lived service-account key files.

Google documents attached service accounts as an ADC source and warns that service-account keys create additional security risk. citeturn917325search0

The final deployment platform determines how the identity is attached.

37. GCP Integration Test Strategy

Real GCP integration tests should verify:

authentication
authorization
metric discovery
resource semantics
time-series retrieval
metric/resource label separation
alignment
cross-series reduction
grouping
data-point intervals
pagination
large-result handling
alerts
provider errors
timeouts

Live tests should run against a controlled test project and should not be part of ordinary local unit-test execution.

38. GCP Mapping Acceptance Criteria

The GCP adapter is ready when:

search_metric_descriptors() returns provider-neutral metric descriptors.

query_metric() returns provider-neutral time series.

Metric labels remain distinct from resource labels.

list_resources() can discover concrete resources through the documented telemetry-backed mechanism where required.

list_resources() does not claim to be a universal inventory of all GCP resources.

get_alerts() retrieves incident/firing information rather than treating alert-policy configuration as an incident.

Policy metadata can be associated with incidents where required.

get_alerts() remains read-only.

Alignment and reduction semantics match documented GCP behavior.

Provider pagination and truncation are correctly represented.

Provider errors map to structured contract errors.

GCP SDK objects do not escape the adapter.

Existing application/domain tests pass unchanged when the telemetry provider is swapped.

39. Final Integration Boundary

┌────────────────────────────────────────┐
│ Application / Domain                   │
│                                        │
│ TelemetryProvider contract             │
└───────────────────┬────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────┐
│ GCPTelemetryProvider                   │
│                                        │
│ Auth / client                           │
│ Request mapping                         │
│ Response normalization                  │
│ Pagination                              │
│ Error mapping                           │
│ Size protection                        │
└───────────────────┬────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────┐
│ Google Cloud Monitoring API             │
│                                        │
│ metricDescriptors.list                 │
│ monitoredResourceDescriptors.list      │
│ timeSeries.list                        │
│ alertPolicies.list/get                 │
└────────────────────────────────────────┘

The GCP adapter is therefore an infrastructure translation layer, not part of the investigation domain.

40. Derived Documents

This document feeds into:

OBSERVABILITY.md
TESTING_STRATEGY.md
deployment/configuration documentation

The frozen PRD.md remains the product authority.

DOMAIN_MODEL.md remains the conceptual domain authority.

SYSTEM_ARCHITECTURE.md defines component boundaries.

TOOL_CONTRACTS.md defines the provider-neutral interaction contract.

DATA_MODEL.md defines persistence.

INVESTIGATION_LOGIC.md defines execution.

AGENT_BEHAVIOUR.md defines LLM behavior.

SECURITY_ARCHITECTURE.md defines security controls.

This document defines the translation between those abstractions and real Google Cloud Monitoring.