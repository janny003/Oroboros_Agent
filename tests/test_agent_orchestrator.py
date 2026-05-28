from pathlib import Path

from tools.agent_memory import empty_memory_bundle, save_memory_bundle
from tools.agent_orchestrator import MaintenanceAgentOrchestrator, run_orchestration


FIXTURE_DIR = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parents[1]
FAULT_CSV = PROJECT_ROOT / "data" / "fault_exclusion_master_map.csv"


def _write_memory_bundle(memory_root: Path) -> None:
    bundle = empty_memory_bundle()
    bundle["preference"]["preferences"] = {"prefer_first_check": "시스템제어기조립체"}
    bundle["preference"]["resolved_priority"] = {"GLOBAL": {"전원제어기 경로 우선 점검": 2}}
    bundle["verification"]["last_interview"] = {"answers": ["예", "아니오", "예", "예"]}
    save_memory_bundle(memory_root, bundle)


def test_agent_orchestrator_runs_deterministic_agents_in_order(tmp_path):
    memory_root = tmp_path / "memory"
    _write_memory_bundle(memory_root)

    result = run_orchestration(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory_root=memory_root,
        generated_at="2026-05-28 11:00:00",
    )

    assert [step["agent"] for step in result["steps"]] == [
        "MemoryAgent",
        "PipelineAgent",
        "RecommendationAgent",
        "VerificationAgent",
        "ReportAgent",
    ]
    assert all(step["mode"] == "deterministic" for step in result["steps"])
    assert all(step["side_effect"] is False for step in result["steps"])
    for step in result["steps"]:
        assert isinstance(step["input"], dict)
        assert isinstance(step["output"], dict)
    assert result["steps"][0]["input"] == {"memory_root": str(memory_root)}
    assert "memory_bundle_keys" in result["steps"][0]["output"]
    assert result["report_payload"]["generated_at"] == "2026-05-28 11:00:00"
    assert result["report_payload"]["focus"]["file"] == "sample_test_log.txt"


def test_agent_orchestrator_uses_split_memory_for_recommendation_notes(tmp_path):
    memory_root = tmp_path / "memory"
    _write_memory_bundle(memory_root)

    orchestrator = MaintenanceAgentOrchestrator(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=Path("missing-folder") / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory_root=memory_root,
        generated_at="2026-05-28 11:00:00",
    )
    result = orchestrator.run()

    focus = result["report_payload"]["focus"]
    assert focus["file"] == "sample_test_log.txt"
    assert "이전 인터뷰 답변 반영" in focus["summary_text"]
    assert focus["interview_memory_note"]
    assert result["recommendation"]["recommended_exclusion_items"] == focus["recommended_exclusion_items"]
    assert result["verification"]["requires_operator_confirmation"] is True
    assert len(result["verification"]["checks"]) >= 3


def test_agent_orchestrator_handles_missing_focus_as_attention_without_crashing(tmp_path):
    memory_root = tmp_path / "memory"
    _write_memory_bundle(memory_root)

    result = run_orchestration(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=None,
        fault_exclusion_csv=FAULT_CSV,
        memory_root=memory_root,
        generated_at="2026-05-28 11:00:00",
    )

    assert result["report_payload"]["focus"] is None
    assert result["verification"]["requires_operator_confirmation"] is False
    assert result["steps"][3]["status"] == "needs_attention"
    assert result["report_ready"] is True


def test_agent_orchestrator_is_pure_and_does_not_write_report_or_memory(tmp_path):
    memory_root = tmp_path / "memory"
    _write_memory_bundle(memory_root)
    unexpected_report = tmp_path / "agent_report.json"

    result = run_orchestration(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory_root=memory_root,
        generated_at="2026-05-28 11:00:00",
    )

    assert result["report_ready"] is True
    assert not unexpected_report.exists()
    assert (memory_root / "preference_memory.json").exists()
    before = (memory_root / "preference_memory.json").read_text(encoding="utf-8")
    run_orchestration(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory_root=memory_root,
        generated_at="2026-05-28 11:00:00",
    )
    after = (memory_root / "preference_memory.json").read_text(encoding="utf-8")
    assert before == after
