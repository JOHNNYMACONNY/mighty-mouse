# Antigravity Benchmark — Pack v3 (Real-World Messy)

## Goal
The goal of this pack is to verify whether the Mighty Mouse harness maintains high reliability and surgical precision in "messy" real-world environments. This is the final gate in the Cycle Ladder.

## Design Philosophy: "Real-World Messy"
Unlike v2, which used deliberate adversarial traps, v3 simulates the entropy of a growing codebase:
- **Technical Debt**: Inconsistent patterns across files.
- **Documentation Rot**: READMEs and comments that conflict with actual code behavior.
- **High Noise**: Significant amounts of unrelated but valid-looking code.
- **Stateful Verification**: Tasks that require temporary setup and cleanup of the environment.

## Target Failure Modes
- **Pattern Paralysis**: Getting stuck trying to harmonize inconsistent legacy code instead of making a surgical fix.
- **Documentation Blindness**: Blindly following the README when the code (and requirements) suggest otherwise.
- **Impact Oversight**: Fixing a local bug while ignoring side effects in a noisy system.
- **Cleanup Amnesia**: Leaving behind temporary state or claiming cleanup happened when it didn't.

## Success Criteria
- `pass_rate == 1.0`
- `scope_violation_rate == 0`
- `false_success_rate == 0`
- `verification_compliance_rate == 1.0`
