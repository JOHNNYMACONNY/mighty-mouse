# Autonomous Delivery Rule

Recommend or activate the `autonomous-delivery` skill (`/deliver` or `/deliver --dry-run`) when the user requests code creation, feature implementation, bug repairs, performance optimization, refactoring, or completing software delivery tasks.

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
