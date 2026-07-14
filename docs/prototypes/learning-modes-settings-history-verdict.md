# Learning modes and settings-history UX verdict

Decision artifact for [Design learning modes and settings-history UX](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/12). This is a behavior prototype expressed as a user-facing interaction contract; production UI and TUI implementation remain out of scope for the Wayfinder map.

## Goal

Keep automatic local improvement understandable. A person should know what Mighty Mouse will use, why it is using it, and how to take control without needing to learn the internal Candidate and Experiment vocabulary.

## One local core, many hosts

Mighty Mouse owns the local state and the safety-critical operations: Policies, Candidates, Champions, Evidence Bundles, Pins, Previews, Promotions, Restrictions, and Rollbacks. It supports direct standalone use through a CLI and exposes a portable MCP interface.

A host integration is deliberately thin: a skill, rules file, plugin, or MCP client may invoke the core and render a compact Integration Surface, but must not create a separate settings store or history. A host is recorded as part of the Execution Profile, so a result established in one host is not silently treated as applicable in another.

The v2 delivery order is CLI-first. The CLI defines the canonical data and actions; a later TUI reads the same local records. Each supported host receives the same compact controls only after its adapter can report the required Execution Profile facts.

## Everyday experience

### Automatic routing with visible control

Automatic routing is the default. Mighty Mouse chooses Coding, Agentic, or the fixed Hybrid flow, shows the selected Mode and a short reason, and always provides an override. It never hides the active Mode behind an opaque "automatic" label.

### Plain-language effective settings

At the start of a task, `mighty-mouse status` and every host integration show a compact, human-readable answer:

```text
Using: Project improvement
For: Coding in mighty-mouse
Why: This setting was verified for this project and your current local model.
Change: View what changed | Preview another setting | Pin this setting
```

The possible user-facing sources are intentionally few:

- **Project improvement** — a compatible Champion has evidence for this repository.
- **Shared improvement** — a compatible broader-scope Champion applies; the scope is named explicitly.
- **Safe starting settings** — no compatible learned Champion applies, so Mighty Mouse is using the shipped baseline.

The underlying terms (Champion, Scope, Model Identity, and Execution Profile) are available through `--details`, the future TUI, and linked history, but are not required to understand ordinary use.

### Compact controls everywhere

Every supported host presents only:

- current status and the effective-setting explanation;
- `Start Background Research` / `Stop Background Research` and its state;
- Pin, Preview, and Rollback; and
- a direct Promotion notice when a live setting changes.

The standalone CLI and future TUI additionally expose detailed history, Evidence Bundles, compatibility records, experiment outcomes, and advanced recovery. This preserves one source of truth without forcing ordinary host users into an administrative console.

## History and notifications

The default history is an understandable change timeline: Promotion, automatic Rollback or Restriction, Pin, Preview, and an Undo/Rollback action. Each entry answers what changed, when, where it applies, and a short "why" statement.

Notify the user when an autonomous event can affect live behavior: Promotion, automatic Rollback, Restriction, or a Background Research safety/budget pause. Candidate creation, rejected experiments, ordinary Signals, and routine research progress remain quiet but inspectable. Pins and Previews show an immediate confirmation because the user initiated them.

## Acceptance checks for a later implementation

- A user can determine the effective settings, their scope, and a plain-language reason in one status view.
- Automatic routing reveals the selected Mode and supports an explicit override.
- A host integration cannot write its own independent Champion, Pin, or history record.
- A Champion from an incompatible Model Identity or Execution Profile is shown as not applicable; the user sees Safe starting settings instead.
- A Promotion, Rollback, Restriction, or research pause produces a clear notice and a link to the relevant history item.
- Advanced terminology and diagnostics are available without becoming a prerequisite for routine operation.

## Boundary

This verdict sets the v2 interaction model and adapter boundary. It does not implement the CLI/TUI, add host adapters, or decide cross-user federation.
