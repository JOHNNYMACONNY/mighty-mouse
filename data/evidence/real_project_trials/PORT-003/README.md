# PORT-003 — Evidence-correct Mighty Mouse case study

The first delivery attempt was invalidated before recording because its harness
prompt named a nonexistent skill path and did not invoke the released protocol
and verifier. The implementation was not merged and does not count in the
aggregate. Local raw-session hashes for that invalid attempt are
`1bbaae43c4e0c093abf8d302ab1b0fc7d96c67af793dd4e5ba1dd15ae5cac254`
(control) and
`d9e0668f9f06badb56c41e03826566c2c56699328f3f72b1a9ab8e34eaa42eff`
(harness).

The valid retry started both conditions from AudioServiceApp commit `5b967ef`.
The harness condition read the released Codex integration, invoked the medium
CLI protocol before editing, and used the released verifier after editing.

Both initially passed their automated suites but missed the exact visible unit
in WorkSignal. Evaluator feedback triggered one repair round for each. Harness
also repaired an incomplete exploratory-unit invariant. Final evaluator results
were 21 suites/67 tests for control and 21 suites/75 tests for harness, with
TypeScript passing for both and no scope violations.

Blind re-review selected harness 4.6/5 versus control 4.5/5. Harness made bases
mandatory for quantitative Mighty Mouse evidence and had stronger semantic
rendering and regression coverage. Its filename-based source/class relationship
remains a documented maintainability weakness.

Raw sessions remain local because they contain local paths and agent
instructions; hashes are published in the result files.
