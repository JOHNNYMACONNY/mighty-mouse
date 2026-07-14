# Domain Docs

Mighty Mouse uses a single-context domain documentation layout.

## Before exploring, read these

- `CONTEXT.md` at the repository root, when present.
- Relevant architectural decisions under `docs/adr/`, when present.

If these files do not exist, proceed silently. Domain-modeling skills create them lazily when decisions or vocabulary are actually resolved.

## Use the glossary's vocabulary

Use terms as defined in `CONTEXT.md` in issue titles, specifications, hypotheses, code, and tests. If a needed concept is absent, either reconsider the invented term or record the gap for domain modeling.

## Flag ADR conflicts

Surface conflicts with an existing ADR explicitly rather than silently overriding the recorded decision.
