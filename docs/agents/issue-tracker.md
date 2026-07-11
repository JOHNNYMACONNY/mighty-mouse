# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `JOHNNYMACONNY/mighty-mouse`. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments` with appropriate filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`.
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Close**: `gh issue close <number> --comment "..."`.

Infer the repository from `git remote -v` when running inside the clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** External pull requests do not enter the issue triage queue.

## Publishing and fetching

- When a skill says **publish to the issue tracker**, create a GitHub issue.
- When a skill says **fetch the relevant ticket**, run `gh issue view <number> --comments`.

## Wayfinding operations

The map is one issue labelled `wayfinder:map`; its tickets are child issues.

- **Map**: create an issue containing Destination, Notes, Decisions so far, Not yet specified, and Out of scope.
- **Child ticket**: create an issue labelled `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`, then link it as a GitHub sub-issue. If sub-issues are unavailable, add `Part of #<map>` to the ticket and a task-list entry to the map.
- **Blocking**: use GitHub native issue dependencies. Add an edge with `gh api --method POST repos/JOHNNYMACONNY/mighty-mouse/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-database-id>`. If unavailable, add `Blocked by: #<number>` to the child body.
- **Frontier**: open, unblocked, unassigned child issues are takeable; first in map order wins.
- **Claim**: assign the ticket before work with `gh issue edit <number> --add-assignee @me`.
- **Resolve**: post the decision as a resolution comment, close the ticket, and append a one-line linked gist to the map's Decisions so far.
