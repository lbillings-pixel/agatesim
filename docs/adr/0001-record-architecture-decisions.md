# 1. Record architecture decisions

- Status: accepted
- Date: 2026-10-14

## Context

This project is meant to grow into research software for others to use. People
reading it later, including future collaborators, will need to know why the
project is built the way it is, not only how.

## Decision

Each significant, hard-to-reverse decision is recorded as a short numbered
Architecture Decision Record (ADR) in `docs/adr/`. Each ADR gives the context, the
decision and its consequences. An accepted ADR is never edited to change its
meaning. A later ADR replaces it and marks the old one `superseded by N`.

## Consequences

- Decisions can be traced, and reversing one is a deliberate act.
- Changes to the archetype criteria, the tech stack or the model architecture need
  an ADR.
