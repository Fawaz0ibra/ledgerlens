# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-10-28

## Context

LedgerLens is built over many months, one component at a time. Most components are a choice between
real alternatives (serving engines, vector stores, agent designs), and the reasons fade quickly. Commit
messages say *what* changed, not what else was considered. A reviewer, or future us, needs the why and
the evidence.

## Decision

Every major component gets a decision record in `docs/adr/`, written when the decision is made.

- Files are named `NNNN-short-title.md` and numbered in the order they are written.
- Each record follows [template.md](template.md) and fits on one page: context, what we chose, what
  we rejected and why, the measured numbers, consequences, and when to revisit.
- Numbers come from our own runs, with the dataset version, hardware, commit and date. A decision
  that wasn't measured says so.
- An accepted record is never rewritten. A changed decision gets a new record that supersedes it, and
  the old one's status points to the new one.

## Rejected options

- **No records:** the reasoning is lost, and decisions get re-argued without new evidence.
- **A wiki or notes app:** it lives apart from the code, isn't versioned with the commits it explains,
  and isn't visible to people reading the repository.
- **One design document:** it gets rewritten as things change, so the history of why disappears.
- **A fuller template (such as MADR's):** more sections than a one-page record needs. Ours keeps the
  parts that carry evidence.

## Measurements

Not measured. This is a process decision.

## Consequences

- Each major decision costs about 15 minutes of writing.
- Anyone can see why each component exists and what it beat.
- Old records stay as a history of decisions, including the ones we reversed.

## Revisit when

Records regularly run past one page, or decisions start being made without one.
