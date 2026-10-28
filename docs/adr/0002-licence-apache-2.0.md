# 0002. Licence the code under Apache-2.0

- **Status:** Accepted
- **Date:** 2026-10-28

## Context

The repository is public. Without a licence, the code is "all rights reserved": people can read it but
can't legally reuse it. The licence also limits which dependencies we can combine with our code later.

## Decision

Apache License 2.0 for all code and documents in this repository.

## Rejected options

- **MIT:** just as permissive and shorter, but without Apache-2.0's explicit patent grant. A fine
  choice too. Apache-2.0 is the norm in the ML serving tools we build on, such as vLLM and Kubernetes.
- **No licence:** reading is allowed but reuse isn't, which defeats the point of a public project.
- **GPL-3.0 or AGPL-3.0:** these require anyone who distributes changed versions (or, for AGPL, runs
  them as a service) to publish their source under the same terms. That restricts users more than this
  project needs.

## Measurements

Not measured. This is a legal choice.

## Consequences

- Permissive dependencies (MIT, BSD, Apache-2.0) are fine.
- Copyleft dependencies (GPL, AGPL) need a check before use, because their terms would apply to the
  combined work. This matters for some vision libraries; the layout-detector record covers it.
- Model weights and datasets carry their own licences. Each one is recorded where it is used
  (`data/README.md` for datasets).

## Revisit when

A dependency we need has a licence that conflicts with Apache-2.0.
