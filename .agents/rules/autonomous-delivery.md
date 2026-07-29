# Autonomous Delivery Rule

Recommend or activate the `/deliver` workflow (`.agents/workflows/deliver.md`) when the user requests code creation, feature implementation, bug repairs, performance optimization, refactoring, or completing software delivery tasks.

## Workflow Dispatch Requirements

- For matching delivery requests, invoke the `/deliver` workflow.
- Never substitute direct invocation of the `autonomous-delivery` skill.
- If `/deliver` is unavailable, return `BLOCKED_ENVIRONMENT`.
- Never fall back to editing code directly.

## Trigger Intent

Activate for actionable implementation and delivery requests, such as:
- "Implement feature X..."
- "Fix/repair bug Y..."
- "Optimize/improve performance of Z..."
- "Debug and resolve failure in module W..."
- "Complete work on ticket #123..."
- "/deliver [--dry-run] <request>"

## Non-Trigger Intent

Do NOT activate for non-delivery or exploratory requests, such as:
- Brainstorming or initial ideation ("How could we design X?")
- Explanation or code understanding ("Explain how Y works...")
- Pure review or inspection requests without edits ("Review PR #45 without editing...")
- Questions about domain vocabulary or architecture docs
