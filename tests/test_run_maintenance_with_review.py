import json
import sys
from pathlib import Path

from tools.agent_memory import load_memory_bundle
from tools.ouroboros_review_loop import build_interview
from tools.run_maintenance_with_review import (
    _build_final_diagnosis_payload,
    _collect_interview_answers,
    _persist_interview_answers,
    main,
)


def test_collect_interview_answers_prints_four_separate_yes_no_prompts(monkeypatch, capsys):
    step7 = {
        "interview_questions": [
            "1번 확인 질문입니까? (Yes/No)",
            "2번 확인 질문입니까? (Yes/No)",
            "3번 확인 질문입니까? (Yes/No)",
            "4번 확인 질문입니까? (Yes/No)",
        ]
    }
    answers = iter(["yes", "no", "예", "아니오"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    result = _collect_interview_answers(step7)

    out = capsys.readouterr().out
    assert result == ["예", "아니요", "예", "아니요"]
    for i in range(1, 5):
        assert f"[INTERVIEW_Q{i}]" in out
        assert f"[INTERVIEW_A{i}]" in out
    assert out.index("[INTERVIEW_Q1]") < out.index("[INTERVIEW_Q2]") < out.index("[INTERVIEW_Q3]") < out.index("[INTERVIEW_Q4]")


def test_build_interview_asks_two_questions_for_each_top3_fail_candidate():
    current = {
        "fail_candidates": [
            {"file": "low_candidate.txt", "risk": "LOW", "cause": "통신"},
            {"file": "high_candidate.txt", "risk": "HIGH", "cause": "전원"},
            {"file": "medium_candidate.txt", "risk": "MEDIUM", "cause": "RF"},
            {"file": "numeric_candidate.txt", "risk": 0.9, "cause": "제어"},
        ],
        "focus": {
            "file": "focus_only.txt",
            "risk": "HIGH",
            "cause": "전원",
            "test_ids": ["T06"],
            "recommended_exclusion_items": ["시스템제어기조립체 우선 점검", "케이블조립체(TW605/TW606) 우선 점검"],
        },
    }

    questions = build_interview(current)

    assert len(questions) == 6
    assert all(q.endswith("(Yes/No)") for q in questions)
    joined = "\n".join(questions)
    assert "high_candidate.txt" in joined
    assert "numeric_candidate.txt" in joined
    assert "medium_candidate.txt" in joined
    assert "low_candidate.txt" not in joined
    for candidate in ["high_candidate.txt", "numeric_candidate.txt", "medium_candidate.txt"]:
        assert sum(candidate in q for q in questions) == 2


def test_collect_interview_answers_accepts_all_generated_questions(monkeypatch, capsys):
    step7 = {"interview_questions": [f"후보 {i} 확인 질문입니까? (Yes/No)" for i in range(1, 7)]}
    answers = iter(["yes", "no", "예", "아니오", "y", "n"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    result = _collect_interview_answers(step7)

    out = capsys.readouterr().out
    assert result == ["예", "아니요", "예", "아니요", "예", "아니요"]
    for i in range(1, 7):
        assert f"[INTERVIEW_Q{i}]" in out
        assert f"[INTERVIEW_A{i}]" in out


def test_persist_and_final_payload_preserve_all_step7_questions_and_answers(tmp_path):
    memory_path = tmp_path / "out" / "inspection_memory.json"
    report_json = tmp_path / "out" / "report.json"
    review_json = tmp_path / "review" / "ouroboros_review_result.json"
    memory_path.parent.mkdir(parents=True)
    review_json.parent.mkdir(parents=True)
    questions = [f"후보 {i} 확인 질문입니까? (Yes/No)" for i in range(1, 7)]
    answers = ["예", "아니요", "예", "아니요", "예", "아니요"]

    memory_path.write_text(json.dumps({"history": [], "preferences": {}}, ensure_ascii=False), encoding="utf-8")
    report_json.write_text(
        json.dumps(
            {
                "memory_json": str(memory_path),
                "summary": {"total_logs": 3, "fail_candidates": 3, "high_risk_count": 2},
                "focus": {
                    "file": "sample_test_log.txt",
                    "cause": "전원",
                    "risk": "HIGH",
                    "test_ids": ["T06"],
                    "recommended_exclusion_items": ["전원 경로", "케이블/커넥터"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    review_json.write_text(
        json.dumps(
            {"step7": {"interview_questions": questions, "interview_answers": answers, "evaluate": {"verdict": "ready"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _persist_interview_answers(report_json, review_json, answers)
    legacy = json.loads(memory_path.read_text(encoding="utf-8"))
    assert legacy["last_interview"]["questions"] == questions
    assert legacy["last_interview"]["answers"] == answers

    payload = _build_final_diagnosis_payload(
        report_json,
        review_json,
        json.loads(report_json.read_text(encoding="utf-8")),
        json.loads(review_json.read_text(encoding="utf-8")),
        "approved",
    )
    assert payload["step7_questions"] == questions
    assert payload["step7_answers"] == answers


def test_persist_interview_answers_updates_legacy_and_split_verification_memory(tmp_path):
    memory_path = tmp_path / "out" / "inspection_memory.json"
    report_json = tmp_path / "out" / "report.json"
    review_json = tmp_path / "review" / "ouroboros_review_result.json"
    memory_path.parent.mkdir(parents=True)
    review_json.parent.mkdir(parents=True)

    memory_path.write_text(json.dumps({"history": [], "preferences": {}}, ensure_ascii=False), encoding="utf-8")
    report_json.write_text(
        json.dumps(
            {
                "memory_json": str(memory_path),
                "focus": {"file": "sample_test_log.txt", "test_ids": ["T06"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    review_json.write_text(
        json.dumps(
            {
                "step7": {
                    "interview_questions": [
                        "1순위 점검을 확인했습니까? (Yes/No)",
                        "전원 경로를 확인했습니까? (Yes/No)",
                        "통신 라인을 확인했습니까? (Yes/No)",
                        "재시험 필요성을 남기겠습니까? (Yes/No)",
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _persist_interview_answers(report_json, review_json, ["예", "아니요", "예", "예"])

    legacy = json.loads(memory_path.read_text(encoding="utf-8"))
    assert legacy["last_interview"]["answers"] == ["예", "아니요", "예", "예"]
    assert legacy["last_interview"]["focus_log"] == "sample_test_log.txt"

    split = load_memory_bundle(tmp_path / "out" / "memory")
    assert split["verification"]["last_interview"]["answers"] == ["예", "아니요", "예", "예"]
    assert split["verification"]["last_interview"]["questions"][0].startswith("1순위")
    assert split["verification"]["interview_history"][-1]["focus_log"] == "sample_test_log.txt"


def test_wrapper_e2e_approved_final_confirmation_is_used_by_next_diagnosis(tmp_path, monkeypatch):
    project_root = Path(__file__).parents[1]
    fixture_dir = Path(__file__).parent / "fixtures"
    fault_csv = project_root / "data" / "fault_exclusion_master_map.csv"
    memory_json = tmp_path / "out" / "inspection_memory.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)

    answers = iter([
        "yes", "yes", "yes", "yes", "approved",
        "no", "no", "no", "no", "rejected",
    ])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    first_doc = tmp_path / "first.docx"
    first_json = tmp_path / "first.json"
    first_review = tmp_path / "review1"
    assert main([
        "--python", sys.executable,
        "--project-root", str(project_root),
        "--log-root", str(fixture_dir),
        "--out-doc", str(first_doc),
        "--out-json", str(first_json),
        "--focus-log", str(fixture_dir / "sample_test_log.txt"),
        "--memory-json", str(memory_json),
        "--fault-exclusion-csv", str(fault_csv),
        "--review-history-dir", str(history_dir),
        "--review-out-dir", str(first_review),
    ]) == 0

    legacy = json.loads(memory_json.read_text(encoding="utf-8"))
    approved_actions = legacy["history"][-1]["recommended_actions"][:3]
    assert legacy["history"][-1]["final_confirmed"] is True
    assert approved_actions

    second_doc = tmp_path / "second.docx"
    second_json = tmp_path / "second.json"
    second_review = tmp_path / "review2"
    assert main([
        "--python", sys.executable,
        "--project-root", str(project_root),
        "--log-root", str(fixture_dir),
        "--out-doc", str(second_doc),
        "--out-json", str(second_json),
        "--focus-log", str(fixture_dir / "sample_test_log.txt"),
        "--memory-json", str(memory_json),
        "--fault-exclusion-csv", str(fault_csv),
        "--review-history-dir", str(history_dir),
        "--review-out-dir", str(second_review),
    ]) == 0

    second_payload = json.loads(second_json.read_text(encoding="utf-8"))
    focus = second_payload["focus"]
    assert "최종확정 이력" in focus["final_confirmation_note"]
    assert "최종확정 이력" in focus["summary_text"]
    assert focus["recommended_exclusion_items"][: len(approved_actions)] == approved_actions
