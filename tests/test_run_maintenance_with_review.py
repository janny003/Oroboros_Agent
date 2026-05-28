import json
from pathlib import Path

from tools.agent_memory import load_memory_bundle
from tools.run_maintenance_with_review import _collect_interview_answers, _persist_interview_answers


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
