import json
from pathlib import Path

from tools.pipeline_core import build_maintenance_analysis_payload


FIXTURE_DIR = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parents[1]
FAULT_CSV = PROJECT_ROOT / "data" / "fault_exclusion_master_map.csv"


def test_build_payload_preserves_report_schema_and_korean_focus_text(tmp_path):
    memory_path = tmp_path / "inspection_memory.json"
    memory = {
        "preferences": {"prefer_first_check": "시스템제어기조립체"},
        "last_interview": {"answers": ["예", "아니오", "예", "예"]},
    }

    payload = build_maintenance_analysis_payload(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory=memory,
        memory_path=memory_path,
        generated_at="2026-05-28 10:00:00",
    )

    assert set(payload) == {
        "generated_at",
        "log_root",
        "model_paths",
        "summary",
        "top_causes",
        "fail_candidates",
        "focus",
        "memory_json",
    }
    assert payload["generated_at"] == "2026-05-28 10:00:00"
    assert payload["summary"]["total_logs"] == 1
    assert payload["memory_json"] == str(memory_path)

    focus = payload["focus"]
    assert focus["file"] == "sample_test_log.txt"
    assert "우선점검권고" in focus["summary_text"]
    assert "고장배제 점검 권고" in focus["summary_text"]
    assert "이전 인터뷰 답변 반영" in focus["summary_text"]
    assert focus["recommended_exclusion_items"]
    assert focus["interview_memory_note"]


def test_final_confirmed_memory_is_reused_in_next_payload_priority_and_summary(tmp_path):
    memory_path = tmp_path / "inspection_memory.json"
    memory = {
        "verification": {
            "approvals": [
                {
                    "approval_status": "approved",
                    "test_ids": ["GLOBAL"],
                    "recommended_actions": ["전원제어기 경로 우선 점검", "케이블조립체(TW605/TW606) 우선 점검"],
                }
            ]
        }
    }

    payload = build_maintenance_analysis_payload(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory=memory,
        memory_path=memory_path,
        generated_at="2026-05-28 10:00:00",
    )

    focus = payload["focus"]
    assert focus["recommended_exclusion_items"][:2] == ["전원제어기 경로 우선 점검", "케이블조립체(TW605/TW606) 우선 점검"]
    assert "최종확정 이력" in focus["summary_text"]
    assert "최종확정 이력" in focus["final_confirmation_note"]


def test_build_payload_is_pure_and_does_not_write_memory_json(tmp_path):
    memory_path = tmp_path / "inspection_memory.json"

    payload = build_maintenance_analysis_payload(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=Path("nested") / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory={"history": [], "preferences": {}},
        memory_path=memory_path,
        generated_at="2026-05-28 10:00:00",
    )

    assert payload["focus"]["file"] == "sample_test_log.txt"
    assert not memory_path.exists()


def test_cli_json_matches_pipeline_core_payload_schema(tmp_path):
    # The CLI wrapper should keep writing exactly the same payload shape that
    # Agent Orchestrator can obtain directly from pipeline_core.
    from tools.generate_maintenance_report import main

    out_doc = tmp_path / "report.docx"
    out_json = tmp_path / "report.json"
    memory_json = tmp_path / "inspection_memory.json"

    import sys

    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "generate_maintenance_report.py",
            "--log-root",
            str(FIXTURE_DIR),
            "--out-doc",
            str(out_doc),
            "--out-json",
            str(out_json),
            "--project-root",
            str(PROJECT_ROOT),
            "--focus-log",
            str(FIXTURE_DIR / "sample_test_log.txt"),
            "--fault-exclusion-csv",
            str(FAULT_CSV),
            "--memory-json",
            str(memory_json),
        ]
        assert main() == 0
    finally:
        sys.argv = old_argv

    cli_payload = json.loads(out_json.read_text(encoding="utf-8"))
    core_payload = build_maintenance_analysis_payload(
        log_root=FIXTURE_DIR,
        project_root=PROJECT_ROOT,
        focus_log=FIXTURE_DIR / "sample_test_log.txt",
        fault_exclusion_csv=FAULT_CSV,
        memory=json.loads(memory_json.read_text(encoding="utf-8")),
        memory_path=memory_json,
        generated_at=cli_payload["generated_at"],
    )

    assert out_doc.exists()
    assert set(cli_payload) == set(core_payload)
    assert cli_payload["summary"] == core_payload["summary"]
    assert cli_payload["top_causes"] == core_payload["top_causes"]
    assert cli_payload["fail_candidates"] == core_payload["fail_candidates"]
    assert cli_payload["focus"]["summary_text"] == core_payload["focus"]["summary_text"]
