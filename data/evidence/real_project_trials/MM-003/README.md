# MM-003 — Release-grade CI

Both conditions started at `50ba189`, used identical agent/model/dependency
configuration, and received the same workflow requirements. The harness alone
received the Mighty Mouse medium protocol.

Both passed 86 tests, semantic workflow tests, YAML parsing, and evaluator-run
clean wheel build/install/outside-checkout smokes on first external acceptance.
Neither violated scope. Control completed in 154.515 seconds versus 167.717 for
harness and won blind review because its workflow parsed and asserted JSON smoke
semantics.

GitHub-hosted Python 3.10–3.13 execution was not available before selection and
is therefore recorded as not checked. It must pass after the selected workflow
is pushed before the workflow is described as operational on GitHub.

Raw sessions remain local; hashes and source-only patches are published here.
