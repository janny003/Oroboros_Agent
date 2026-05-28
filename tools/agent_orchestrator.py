from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from agent_memory import load_memory_bundle
    from pipeline_core import build_maintenance_analysis_payload
except ImportError:  # pragma: no cover - package import path for tests/tools
    from tools.agent_memory import load_memory_bundle
    from tools.pipeline_core import build_maintenance_analysis_payload


@dataclass(frozen=True)
class AgentStepResult:
    agent: str
    mode: str
    side_effect: bool
    status: str
    input: dict[str, Any]
    output: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "mode": self.mode,
            "side_effect": self.side_effect,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "details": self.output,
        }


class DeterministicAgent:
    name = "DeterministicAgent"
    side_effect = False

    def run(self, context: dict[str, Any]) -> AgentStepResult:  # pragma: no cover - interface guard
        raise NotImplementedError


class MemoryAgent(DeterministicAgent):
    name = "MemoryAgent"

    def run(self, context: dict[str, Any]) -> AgentStepResult:
        memory_root = Path(context["memory_root"])
        bundle = load_memory_bundle(memory_root)
        context["memory_bundle"] = bundle
        counts = {
            "episodes": len(bundle.get("episode", {}).get("episodes", []) or []),
            "resolved_priority_tests": len(bundle.get("preference", {}).get("resolved_priority", {}) or {}),
            "interview_history": len(bundle.get("verification", {}).get("interview_history", []) or []),
        }
        return AgentStepResult(
            self.name,
            "deterministic",
            self.side_effect,
            "ok",
            {"memory_root": str(memory_root)},
            {"memory_bundle_keys": sorted(bundle.keys()), **counts},
        )


class PipelineAgent(DeterministicAgent):
    name = "PipelineAgent"

    def run(self, context: dict[str, Any]) -> AgentStepResult:
        payload = build_maintenance_analysis_payload(
            log_root=context["log_root"],
            project_root=context["project_root"],
            focus_log=context.get("focus_log"),
            fault_exclusion_csv=context.get("fault_exclusion_csv"),
            memory=context.get("memory_bundle", {}),
            memory_path=Path(context["memory_root"]),
            generated_at=context.get("generated_at"),
        )
        context["report_payload"] = payload
        summary = dict(payload.get("summary", {}))
        summary["focus_file"] = (payload.get("focus") or {}).get("file", "")
        return AgentStepResult(
            self.name,
            "deterministic",
            self.side_effect,
            "ok",
            {
                "log_root": str(context["log_root"]),
                "project_root": str(context["project_root"]),
                "focus_log": str(context.get("focus_log") or ""),
                "fault_exclusion_csv": str(context.get("fault_exclusion_csv") or ""),
                "memory_bundle_present": bool(context.get("memory_bundle")),
            },
            summary,
        )


class RecommendationAgent(DeterministicAgent):
    name = "RecommendationAgent"

    def run(self, context: dict[str, Any]) -> AgentStepResult:
        focus = (context.get("report_payload") or {}).get("focus") or {}
        recommendation = {
            "recommended_exclusion_items": list(focus.get("recommended_exclusion_items", []) or []),
            "interview_memory_note": str(focus.get("interview_memory_note", "")),
            "interview_priority_note": str(focus.get("interview_priority_note", "")),
            "preference_note": str(focus.get("preference_note", "")),
            "test_ids": list(focus.get("test_ids", []) or []),
        }
        context["recommendation"] = recommendation
        status = "ok" if recommendation["recommended_exclusion_items"] else "no_focus_recommendation"
        return AgentStepResult(
            self.name,
            "deterministic",
            self.side_effect,
            status,
            {"focus_present": bool(focus), "test_ids": recommendation["test_ids"]},
            recommendation,
        )


class VerificationAgent(DeterministicAgent):
    name = "VerificationAgent"

    def run(self, context: dict[str, Any]) -> AgentStepResult:
        payload = context.get("report_payload") or {}
        focus = payload.get("focus") or {}
        summary = payload.get("summary") or {}
        checks = [
            {
                "name": "payload_schema",
                "passed": all(k in payload for k in ["generated_at", "summary", "top_causes", "fail_candidates", "focus"]),
            },
            {
                "name": "focus_analysis_available",
                "passed": bool(focus),
            },
            {
                "name": "korean_recommendation_text",
                "passed": "우선점검권고" in str(focus.get("summary_text", "")),
            },
            {
                "name": "summary_counts_valid",
                "passed": int(summary.get("total_logs", 0)) >= int(summary.get("fail_candidates", 0)),
            },
        ]
        verification = {
            "checks": checks,
            "passed": all(c["passed"] for c in checks),
            "requires_operator_confirmation": bool(focus),
            "question_contract": "GUI wrapper must keep [INTERVIEW_Q1]~[INTERVIEW_Q4] Yes/No prompts",
        }
        context["verification"] = verification
        return AgentStepResult(
            self.name,
            "deterministic",
            self.side_effect,
            "ok" if verification["passed"] else "needs_attention",
            {
                "payload_present": bool(payload),
                "focus_present": bool(focus),
                "summary_keys": sorted(summary.keys()),
            },
            verification,
        )


class ReportAgent(DeterministicAgent):
    name = "ReportAgent"

    def run(self, context: dict[str, Any]) -> AgentStepResult:
        payload = context.get("report_payload") or {}
        report_ready = bool(payload.get("summary"))
        context["report_ready"] = report_ready
        return AgentStepResult(
            self.name,
            "deterministic",
            self.side_effect,
            "ok" if report_ready else "empty_payload",
            {"payload_present": bool(payload), "verification_passed": bool(context.get("verification", {}).get("passed"))},
            {
                "report_ready": report_ready,
                "writes_files": False,
                "handoff": "report_writer.py 또는 기존 generate_maintenance_report.py wrapper가 저장 책임을 갖습니다.",
            },
        )


class MaintenanceAgentOrchestrator:
    """Deterministic JAN maintenance agent coordinator.

    The orchestrator deliberately performs no file writes. It coordinates the
    separated memory layer, pipeline core, recommendation view, verification
    checks, and report handoff so later LLM agents can replace individual stages
    without changing the surrounding contract.
    """

    def __init__(
        self,
        *,
        log_root: Path | str,
        project_root: Path | str,
        focus_log: Path | str | None = None,
        fault_exclusion_csv: Path | str | None = None,
        memory_root: Path | str | None = None,
        generated_at: str | dt.datetime | None = None,
        agents: list[DeterministicAgent] | None = None,
    ) -> None:
        self.context: dict[str, Any] = {
            "log_root": Path(log_root),
            "project_root": Path(project_root),
            "focus_log": Path(focus_log) if focus_log else None,
            "fault_exclusion_csv": Path(fault_exclusion_csv) if fault_exclusion_csv else None,
            "memory_root": Path(memory_root) if memory_root else Path(project_root) / "out" / "memory",
            "generated_at": generated_at,
        }
        self.agents = agents or [
            MemoryAgent(),
            PipelineAgent(),
            RecommendationAgent(),
            VerificationAgent(),
            ReportAgent(),
        ]

    def run(self) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        for agent in self.agents:
            result = agent.run(self.context)
            steps.append(result.as_dict())

        return {
            "steps": steps,
            "memory_root": str(self.context["memory_root"]),
            "report_payload": self.context.get("report_payload"),
            "recommendation": self.context.get("recommendation", {}),
            "verification": self.context.get("verification", {}),
            "report_ready": bool(self.context.get("report_ready")),
        }


def run_orchestration(**kwargs: Any) -> dict[str, Any]:
    return MaintenanceAgentOrchestrator(**kwargs).run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic JAN maintenance agent orchestration without file writes.")
    parser.add_argument("--log-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--focus-log", default="")
    parser.add_argument("--fault-exclusion-csv", default="")
    parser.add_argument("--memory-root", default="")
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    result = run_orchestration(
        log_root=Path(args.log_root),
        project_root=Path(args.project_root),
        focus_log=Path(args.focus_log) if args.focus_log else None,
        fault_exclusion_csv=Path(args.fault_exclusion_csv) if args.fault_exclusion_csv else None,
        memory_root=Path(args.memory_root) if args.memory_root else None,
        generated_at=args.generated_at or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
