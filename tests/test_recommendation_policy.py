from tools.recommendation_policy import (
    apply_final_confirmation_priority,
    apply_interview_priority,
    apply_preference_priority,
    apply_recommendation_policy,
    apply_resolved_priority,
    build_interview_memory_note,
)


def _legacy_memory():
    return {
        "preferences": {"prefer_first_check": "시스템제어기조립체"},
        "resolved_priority": {
            "T03": {"케이블 불량": 3, "전원제어기": 1},
            "GLOBAL": {"공통 접지 확인": 1},
        },
        "last_interview": {"answers": ["예", "아니요", "예", "예"]},
    }


def _split_memory():
    return {
        "preference": {
            "preferences": {"prefer_first_check": "시스템제어기조립체"},
            "resolved_priority": {"T03": {"케이블 불량": 2}},
        },
        "verification": {
            "last_interview": {"answers": ["예", "예", "예", "아니요"]},
        },
    }


def test_apply_resolved_priority_reorders_by_test_history():
    ordered, note = apply_resolved_priority(
        _legacy_memory(),
        ["T03"],
        ["시스템제어기조립체", "전원제어기"],
    )

    assert ordered[:3] == ["케이블 불량", "전원제어기", "공통 접지 확인"]
    assert "과거 해결 이력" in note


def test_apply_interview_priority_adds_power_cable_comm_when_q3_yes():
    ordered, note = apply_interview_priority(_legacy_memory(), ["시스템제어기조립체"])

    assert ordered[0] == "전원/케이블/통신 라인"
    assert "이전 인터뷰 답변" in note


def test_apply_preference_priority_moves_user_preference_to_front():
    ordered, note = apply_preference_priority(
        _legacy_memory(),
        ["케이블 불량", "시스템제어기조립체 우선 점검", "전원제어기"],
    )

    assert ordered[0] == "시스템제어기조립체 우선 점검"
    assert "지속 메모리 적용" in note


def test_build_interview_memory_note_supports_split_memory():
    note = build_interview_memory_note(_split_memory())

    assert "전원/케이블/통신 우선점검 유지=예" in note
    assert "회차별 고위험/기준 적용=아니요" in note


def test_apply_final_confirmation_priority_reuses_approved_diagnosis_for_next_run():
    memory = {
        "verification": {
            "approvals": [
                {
                    "approval_status": "approved",
                    "test_ids": ["T06"],
                    "recommended_actions": ["전원제어기 경로 우선 점검", "케이블조립체(TW605/TW606) 우선 점검"],
                },
                {
                    "approval_status": "rejected",
                    "test_ids": ["T06"],
                    "recommended_actions": ["반려된 항목"],
                },
            ]
        }
    }

    ordered, note = apply_final_confirmation_priority(memory, ["T06"], ["시스템제어기조립체 우선 점검"])

    assert ordered[:3] == [
        "전원제어기 경로 우선 점검",
        "케이블조립체(TW605/TW606) 우선 점검",
        "시스템제어기조립체 우선 점검",
    ]
    assert "최종확정 이력" in note
    assert "반려된 항목" not in ordered


def test_apply_recommendation_policy_keeps_raw_items_unmutated_and_returns_notes():
    raw_items = ["시스템제어기조립체", "전원제어기"]
    result = apply_recommendation_policy(_split_memory(), ["T03"], raw_items)

    assert raw_items == ["시스템제어기조립체", "전원제어기"]
    assert result["recommended_exclusion_items"][0] == "시스템제어기조립체"
    assert result["resolved_priority_note"]
    assert result["interview_priority_note"]
    assert result["preference_note"]
    assert result["interview_memory_note"]
