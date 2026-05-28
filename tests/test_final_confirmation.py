import json
from pathlib import Path

from tools.agent_memory import load_memory_bundle
from tools.run_maintenance_with_review import (
    _build_final_diagnosis_payload,
    _normalize_final_confirmation,
    _persist_final_confirmation,
)


def _write_report_and_review(tmp_path: Path):
    memory_path = tmp_path / "out" / "inspection_memory.json"
    report_json = tmp_path / "out" / "report.json"
    review_json = tmp_path / "review" / "ouroboros_review_result.json"
    memory_path.parent.mkdir(parents=True)
    review_json.parent.mkdir(parents=True)
    memory_path.write_text(json.dumps({"history": [], "preferences": {}}, ensure_ascii=False), encoding="utf-8")

    report_data = {
        "memory_json": str(memory_path),
        "summary": {"total_logs": 1, "fail_candidates": 1, "high_risk_count": 1},
        "focus": {
            "file": "한글_시험로그_T06.txt",
            "cause": "전원",
            "risk": "HIGH",
            "test_ids": ["T06"],
            "recommended_exclusion_items": ["전원 경로", "케이블/커넥터"],
        },
    }
    review_data = {
        "step7": {
            "interview_questions": [
                "1순위 전원 경로를 확인했습니까? (Yes/No)",
                "케이블을 확인했습니까? (Yes/No)",
                "주장비 전원을 확인했습니까? (Yes/No)",
                "재시험 필요성을 남기겠습니까? (Yes/No)",
            ],
            "interview_answers": ["예", "아니요", "예", "예"],
            "evaluate": {"score": 100.0, "verdict": "ready"},
        },
        "step8": {"history_count": 2, "high_risk_trend": "up"},
        "step9": {
            "feedback": [
                {
                    "type": "priority_reorder",
                    "priority": 1,
                    "top3_check_order": [
                        {"file": "한글_시험로그_T06.txt", "risk": 1.0, "cause": "전원"}
                    ],
                },
                {"type": "risk_trend", "priority": 2, "message": "고위험 증가"},
            ]
        },
    }
    report_json.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    review_json.write_text(json.dumps(review_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_json, review_json, memory_path, report_data, review_data


def test_normalize_final_confirmation_supports_approved_pending_rejected():
    assert _normalize_final_confirmation("예") == "approved"
    assert _normalize_final_confirmation("approved") == "approved"
    assert _normalize_final_confirmation("보류") == "pending"
    assert _normalize_final_confirmation("hold") == "pending"
    assert _normalize_final_confirmation("아니요") == "rejected"
    assert _normalize_final_confirmation("unknown") == "rejected"


def test_build_final_diagnosis_payload_preserves_korean_and_review_evidence(tmp_path):
    report_json, review_json, _, report_data, review_data = _write_report_and_review(tmp_path)

    payload = _build_final_diagnosis_payload(report_json, review_json, report_data, review_data, "approved")

    assert payload["approval_status"] == "approved"
    assert payload["final_confirmed"] is True
    assert payload["focus_log"] == "한글_시험로그_T06.txt"
    assert payload["test_ids"] == ["T06"]
    assert payload["step7_answers"] == ["예", "아니요", "예", "예"]
    assert payload["step7_evaluate"]["verdict"] == "ready"
    assert payload["step8_compare"]["high_risk_trend"] == "up"
    assert payload["final_priority_check_order"][0]["cause"] == "전원"


def test_persist_final_confirmation_updates_final_json_legacy_and_split_memory(tmp_path):
    report_json, review_json, memory_path, _, _ = _write_report_and_review(tmp_path)

    final_json = _persist_final_confirmation(report_json, review_json, "approved")

    assert final_json is not None
    final_data = json.loads(Path(final_json).read_text(encoding="utf-8"))
    assert final_data["approval_status"] == "approved"
    assert final_data["final_confirmed"] is True
    assert final_data["focus_log"] == "한글_시험로그_T06.txt"

    legacy = json.loads(memory_path.read_text(encoding="utf-8"))
    hist = legacy["history"][-1]
    assert hist["final_confirmed"] is True
    assert hist["final_diagnosis_json"] == str(final_json)
    assert hist["focus_log"] == "한글_시험로그_T06.txt"

    split = load_memory_bundle(tmp_path / "out" / "memory")
    assert split["verification"]["approvals"][-1]["approval_status"] == "approved"
    assert split["verification"]["approvals"][-1]["final_diagnosis_json"] == str(final_json)
    assert split["verification"]["audit_log"][-1]["event_type"] == "final_confirmation"
    assert split["episode"]["episodes"][-1]["event_type"] == "final_diagnosis_confirmed"


def test_rejected_final_confirmation_audits_without_final_history(tmp_path):
    report_json, review_json, memory_path, _, _ = _write_report_and_review(tmp_path)

    final_json = _persist_final_confirmation(report_json, review_json, "rejected")

    assert final_json is None
    legacy = json.loads(memory_path.read_text(encoding="utf-8"))
    assert legacy["history"] == []
    split = load_memory_bundle(tmp_path / "out" / "memory")
    assert split["verification"]["approvals"] == []
    assert split["verification"]["audit_log"][-1]["approval_status"] == "rejected"
