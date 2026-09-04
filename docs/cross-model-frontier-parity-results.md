# Milestone 13 — Cross-Model Frontier Parity v1 Final Adjudication & Closure Report

Status: **M13_CROSS_MODEL_FRONTIER_PARITY_COMPLETE -> READY_FOR_NEW_MILESTONE**

## 1. Executive Summary & Immutable Milestone Provenance

Milestone 13 evaluated whether the Mighty Mouse single-agent prompt, tool, and response-application protocol generalizes beyond its development model (`gemma4:e4b`) to distinct open-weights local model families without candidate-specific prompt tuning or architecture specialization.

### 1.1 Milestone Provenance Identifiers
- **Repository:** `JOHNNYMACONNY/mighty-mouse`
- **Final Production/Harness Main SHA:** `08cacfb510753e70c3f4910f436e540225523efe`
- **Experiment Base SHA:** `e396d1960208673679d7aac8d2f9e6f5d10f2545`
- **Phase A Execution Base SHA:** `751d5094ccb472ccdaf65fc967405913f0136e09`
- **Phase B Execution Base SHA:** `667fd939bbcc865d166d86a8dbd28c81272c4ecb`
- **Phase A Experiment ID (Ticket 05):** `m13-cross-model-pilot-01`
- **Phase B Experiment ID (Ticket 07):** `m13-cross-model-phase-b-01`
- **Canonical Configuration:** `configs/mighty_mouse_v1.yaml`
- **Tool Protocol:** MCP Tool Contract `v6` (15 tools)
- **Local Runtime:** Ollama `0.33.2`

### 1.2 Frozen Candidates
Both candidate models were evaluated under strict frozen SHA-256 manifest digests:
1. **`llama31_8b_q4km`**:
   - Model Tag: `llama3.1:8b-instruct-q4_K_M`
   - Model Family: `llama`
   - Model Class: `llama3.1-8b-local`
   - Manifest Digest: `sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`
   - Effective Context Limit: `32768`
2. **`qwen25_7b_q4km`**:
   - Model Tag: `qwen2.5:7b-instruct-q4_K_M`
   - Model Family: `qwen2`
   - Model Class: `qwen2.5-7b-local`
   - Manifest Digest: `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730`
   - Effective Context Limit: `32768`

---

## 2. Phase A Pilot Evidence (`m13-cross-model-pilot-01`)

The Phase A pilot evaluated 12 trial units across 3 anchor tasks (`task_003` / Tier 1, `task_047` / Tier 5, `task_1407` / Tier 7) with 1 replicate:
- **Analyzable Units:** 12 / 12 (100.0%)
- **Infrastructure Exclusions:** 0 / 12 (0.0%)
- **Overall Completion:** 5 / 12 (41.7%)
- **Control Arm (`control_once`):** 0 / 6 (0.0%)
- **Mighty Mouse Single Arm (`mm_single`):** 5 / 6 (83.3%)
- **Discordant Pairs:** 5 Mighty Mouse wins, 0 Control wins
- **Generation Calls:** 13
- **Total Tokens:** 25,040

The pilot established that the prompt and tool harness generalized to external families without infrastructure crashes or parsing deadlocks, justifying the expanded Phase B evaluation.

---

## 3. Phase B Comprehensive Evaluation Evidence (`m13-cross-model-phase-b-01`)

Phase B expanded evaluation to the full historical Milestone 12 P2 14-task benchmark across 7 difficulty tiers with 2 candidates, 2 arms, and 1 replicate (exactly 56 trial units):
- **Planned / Executed Units:** 56 / 56 (100.0%)
- **Analyzable Units:** 56 / 56 (100.0%)
- **Infrastructure Exclusions:** 0 / 56 (0.0%)
- **Total Passes:** 29 / 56 (51.8%)
- **Actual Generation Calls:** 63 (Control: 28 direct; MM: 35 calls with 7 bounded internal correction/retry calls)
- **Total Tokens:** 117,037 (100% complete coverage)
- **Total Wall Latency:** 2,077.18s (~34.6 min)

### 3.1 Candidate × Arm Aggregate Results

| Candidate | Arm | Passed / Analyzable | Pass Rate | Gen Calls | Total Tokens | Wall Time (s) |
|---|---|---|---|---|---|---|
| **llama31_8b_q4km** | Control (`control_once`) | 2 / 14 | 14.3% | 14 | 8,384 | 349.72 |
| **llama31_8b_q4km** | Mighty Mouse (`mm_single`) | 13 / 14 | 92.9% | 16 | 45,920 | 642.60 |
| **qwen25_7b_q4km** | Control (`control_once`) | 0 / 14 | 0.0% | 14 | 7,978 | 311.75 |
| **qwen25_7b_q4km** | Mighty Mouse (`mm_single`) | 14 / 14 | 100.0% | 19 | 54,755 | 773.11 |
| **Combined** | Control (`control_once`) | 2 / 28 | 7.1% | 28 | 16,362 | 661.47 |
| **Combined** | Mighty Mouse (`mm_single`) | 27 / 28 | 96.4% | 35 | 100,675 | 1,415.71 |

### 3.2 Paired Win / Loss / Tie Distribution (28 Pairs)
- **Paired Mighty Mouse Wins:** **25** (89.3%)
- **Paired Control Wins:** **0** (0.0%)
- **Both Passed:** **2** (7.1%) (`llama31_8b_q4km` on `task_011` and `task_033`)
- **Neither Passed:** **1** (3.6%) (`llama31_8b_q4km` on `task_1407`)
- **Absolute Percentage-Point Lift:** **+89.29%** (+89.3 percentage points)
- **Resource Cost Multipliers:**
  - Token Overhead: **6.15×** (Control: 16,362 vs MM: 100,675)
  - Wall Latency Overhead: **2.14×** (Control: 661.47s vs MM: 1,415.71s)

### 3.3 Candidate × Task Paired Outcomes

| Task ID | Tier | llama31 Control | llama31 MM | llama31 Outcome | qwen25 Control | qwen25 MM | qwen25 Outcome |
|---|---|---|---|---|---|---|---|
| `task_003` | tier_1 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_001` | tier_1 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_011` | tier_overnight | PASS | PASS | BOTH_PASS | FAIL | PASS | ONLY_MM_SINGLE |
| `task_012` | tier_overnight | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_025` | tier_3 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_016` | tier_3 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_033` | tier_4 | PASS | PASS | BOTH_PASS | FAIL | PASS | ONLY_MM_SINGLE |
| `task_029` | tier_4 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_047` | tier_5 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_045` | tier_5 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_1014` | tier_6 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_1007` | tier_6 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_1415` | tier_7 | FAIL | PASS | ONLY_MM_SINGLE | FAIL | PASS | ONLY_MM_SINGLE |
| `task_1407` | tier_7 | FAIL | FAIL | NEITHER_PASS | FAIL | PASS | ONLY_MM_SINGLE |

### 3.4 Tier-Level Breakdown

| Tier | Control Passed / Total | Control Pass Rate | MM Passed / Total | MM Pass Rate | Paired MM Wins |
|---|---|---|---|---|---|
| `tier_1` | 0 / 4 | 0.0% | 4 / 4 | 100.0% | 4 |
| `tier_3` | 0 / 4 | 0.0% | 4 / 4 | 100.0% | 4 |
| `tier_4` | 1 / 4 | 25.0% | 4 / 4 | 100.0% | 3 |
| `tier_5` | 0 / 4 | 0.0% | 4 / 4 | 100.0% | 4 |
| `tier_6` | 0 / 4 | 0.0% | 4 / 4 | 100.0% | 4 |
| `tier_7` | 0 / 4 | 0.0% | 3 / 4 | 75.0% | 3 |
| `tier_overnight` | 1 / 4 | 25.0% | 4 / 4 | 100.0% | 3 |

---

## 4. Failure Analysis & Single MM Failure Characterization

### 4.1 Failure Distribution by Category (27 Total Failures)
- **`control_once:scope_failure` (24 failures):** Bare baseline models emitted code without file target paths, hallucinated path syntax (e.g., `python:file.py`), or omitted required secondary files.
- **`control_once:test_failure` (2 failures):** The baseline code applied cleanly to the workspace, but unit tests failed.
- **`mm_single:scope_failure` (1 failure):** `llama31_8b_q4km` on `task_1407` (Tier 7).
- **Infrastructure Exclusions (0 failures):** Zero provider crashes, transport errors, or verifier timeouts.

### 4.2 Single Remaining MM Failure Characterization
The single failure in the Mighty Mouse arm occurred on `task_1407` (`tier_7`) by `llama31_8b_q4km`:
- The candidate emitted response code missing the expected target file `memory_data.py`.
- Mighty Mouse's bounded schema correction and recovery loop triggered, issuing targeted schema reprompts.
- The model generated files under `path/to/memory_data.py` instead of the root-level target, reaching `MAX_ATTEMPTS_REACHED` (3 attempts) before cleanly aborting.
- **Closure Discipline:** In accordance with evaluation integrity rules, this failure is preserved truthfully as an analyzable benchmark outcome and was not retroactively repaired.

---

## 5. Final Qualified Production Conclusion

1. **Cross-Family Architecture Generalization:**
   Mighty Mouse single-agent orchestration (`mm_single`) strongly generalizes across all three evaluated local open-weights model families: Google Gemma (`gemma4:e4b`), Meta Llama (`llama3.1:8b-instruct-q4_K_M`), and Alibaba Qwen (`qwen2.5:7b-instruct-q4_K_M`).
2. **Protocol Compliance vs. Raw Reasoning:**
   The observed +89.3 percentage-point lift reflects the enforcement of structured file-block protocols, surgical diff application, and single-attempt schema reprompting. It does **not** indicate an 89 percentage-point increase in the underlying foundation models' intrinsic reasoning capability.
3. **Topology Default Retained:**
   Canonical single-agent execution (`HostAdapter.solve` / `agent_execute`) remains the unambiguous production default (`MM_SINGLE_ALWAYS`). No evidence justifies adopting multi-agent swarms or altering the M12 production policy.
4. **Reliability-Cost Frontier:**
   Mighty Mouse achieves near-saturation reliability (96.4%) at the cost of higher token consumption (6.15×) and wall latency (2.14×). Future iterations must treat token and latency cost as first-class optimization frontiers.

---

## 6. Milestone Transition

- **Status Transition:**
  `M13_CROSS_MODEL_FRONTIER_PARITY_COMPLETE -> READY_FOR_NEW_MILESTONE`
- **Recommended Next Milestone:**
  **Milestone 14 — Benchmark Scaling & Perpetual Evaluation Sweep v1**
  *(Focusing on broader task corpora, multi-replicate variance measurement, and automated continuous evaluation).*
