# Agent Orchestrator Transition Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Keep the existing deterministic JAN maintenance pipeline core while adding an Agent Orchestrator layer that coordinates memory lookup, diagnosis review, recommendation adjustment, interview, verification, and report generation.

**Architecture:** The current pipeline remains the trusted calculation engine. New agent-facing modules will wrap it in stages: memory layer, recommendation policy, orchestrator, and report writer. Pipeline outputs and memory-based adjustments must remain separate so raw model results are reproducible.

**Tech Stack:** Python 3, pytest, JSON UTF-8, existing python-docx reporting path, existing MFC/stdout interview contract.

---

## Implementation Order

### Task 1: Split legacy inspection memory into an agent memory layer

**Objective:** Introduce `tools/agent_memory.py` that can read the current `inspection_memory.json` and expose separated memory objects without changing the existing runtime path yet.

**Files:**
- Create: `tools/agent_memory.py`
- Create: `tests/test_agent_memory.py`

**Acceptance Criteria:**
- Legacy `history[]` becomes episode memory.
- Legacy `preferences` and `resolved_priority` become preference memory.
- Legacy `last_interview` and `interview_history[]` become verification memory.
- Korean text is saved with `ensure_ascii=False` and reloaded without garbling.
- Existing tests remain green.

### Task 2: Add recommendation policy module

**Objective:** Move memory-based priority adjustment rules into `tools/recommendation_policy.py` while preserving current behavior.

**Files:**
- Create: `tools/recommendation_policy.py`
- Create: `tests/test_recommendation_policy.py`
- Later Modify: `tools/generate_maintenance_report.py`

**Acceptance Criteria:**
- Resolved history priority can reorder recommended exclusion items.
- Last interview answer can keep 전원/케이블/통신 라인 at the front when appropriate.
- User preference can be applied without changing raw analysis payload.

### Task 3: Extract pure pipeline core payload generation

**Objective:** Create `tools/pipeline_core.py` for deterministic analysis output, avoiding memory writes and report writes.

**Files:**
- Create: `tools/pipeline_core.py`
- Create: `tests/test_pipeline_core.py`
- Later Modify: `tools/generate_maintenance_report.py`

**Acceptance Criteria:**
- Same input logs/models produce the same `analysis_payload` regardless of memory state.
- No `inspection_memory.json` write occurs inside pipeline core.
- Existing report generation still works through compatibility wrappers.

### Task 4: Add Agent Orchestrator skeleton

**Objective:** Add `tools/agent_orchestrator.py` that coordinates memory loading, pipeline execution, recommendation policy, review, report writing, and memory persistence.

**Files:**
- Create: `tools/agent_orchestrator.py`
- Create: `tests/test_agent_orchestrator.py`

**Acceptance Criteria:**
- Orchestrator exposes deterministic agent steps: MemoryAgent, PipelineAgent, RecommendationAgent, VerificationAgent, ReportAgent.
- Each step returns a structured dict.
- Side effects are explicit and limited to memory/report writer stages.

### Task 5: Keep GUI wrapper compatible

**Objective:** Keep `tools/run_maintenance_with_review.py` and MFC stdout contract stable while gradually routing through the orchestrator.

**Files:**
- Modify: `tools/run_maintenance_with_review.py`
- Modify only if needed: MFC command path files

**Acceptance Criteria:**
- `[INTERVIEW_Q1]` to `[INTERVIEW_Q4]` output remains unchanged.
- Yes/No answer persistence remains compatible.
- Korean output remains readable.

### Task 6: Final report writer split

**Objective:** Isolate DOCX/JSON file creation from analysis and memory logic.

**Files:**
- Create: `tools/report_writer.py`
- Create: `tests/test_report_writer.py`
- Later Modify: `tools/generate_maintenance_report.py`

**Acceptance Criteria:**
- Report writer only serializes payloads.
- Diagnosis/recommendation logic does not live in report writer.

## Verification Commands

Run after each task:

```bash
python -m pytest tests/test_inspection_pipeline.py tests/test_model_factory.py -q
python -m pytest tests/test_agent_memory.py -q
```

Run after orchestration tasks:

```bash
python -m pytest -q
```

## First Implementation Slice

Start with Task 1 only. This gives the Agent Orchestrator a stable memory interface while preserving the existing pipeline behavior.
