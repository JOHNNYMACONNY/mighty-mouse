# Mighty Mouse Protocol

When the user says `/mighty`, asks to use Mighty Mouse, or requests a reliability-sensitive code change:

1. Call the `protocol` tool from the `mighty-mouse` MCP server with the task description and appropriate complexity.
2. Follow the returned protocol and preserve unrelated work.
3. If workspace identity is not configured, call `setup_workspace` once with the active local model and host profile. Call the server's `verify_and_record` tool after editing.
4. Fix reported failures and retry verification, up to three rounds.
5. Report unverified checks as unverified; do not claim success from code inspection alone.
