# Autoresearch Specification: Mighty Mouse Reliability Loop

## Optimization Target
**Goal**: Increase successful completion of coding tasks on the first or second attempt while reducing unverified or incorrect code changes.

## Benchmark Design: "Mighty Mouse Benchmark"
The benchmark consists of deterministic tasks with fixed scoring rules and pass/fail thresholds.

### Evaluation Metrics
| Metric | Description | Target |
| :--- | :--- | :--- |
| **Success Rate** | Percentage of tasks passed on first/second attempt. | Maximize |
| **Instruction Adherence** | Adherence to formatting and constraint rules. | 100% |
| **Verification Logic** | Did the agent run tests and verify results? | Mandatory |
| **Retry Count** | Average attempts per successful task. | < 1.5 |
| **Token Usage** | Cost per successful task (Guardrail metric). | Minimize |
| **Unnecessary Edits** | Number of files touched outside the required scope. | 0 |

## Autoresearch Protocol (V1)
Mighty Mouse utilizes the existing Antigravity `/autoresearch` workflow.

- **Iterate**: Focus on prompt engineering and skill (tool) refinement.
- **Verify Command**: `python3 eval/run_benchmark.py --config configs/current_prompts.yaml`
- **Guard Command**: `python3 eval/check_token_usage.py --max 5000` (example value)
- **Stopping Criteria**:
  - Achievement of 95% success rate on the benchmark.
  - Token cost increases beyond the "sustainable cost" threshold.
  - Diminishing returns after 10 consecutive non-improving iterations.

## Iteration #0 Strategy
- **Baseline**: Raw Gemini 3 Flash without the "Mighty Mouse" orchestration or prompt enhancements.
- **Data Capture**: All baseline metrics will be stored in `autoresearch-results.tsv` as the ground-truth reference point.
