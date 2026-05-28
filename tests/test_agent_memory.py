import json

from tools.agent_memory import (
    MemoryPaths,
    append_episode,
    append_verification_record,
    load_memory_bundle,
    migrate_legacy_inspection_memory,
    split_legacy_inspection_memory,
)


def _legacy_memory():
    return {
        "history": [
            {
                "ts": "2026-05-27T10:00:00",
                "focus_log": "3.2 GICA-5.Ethernet.250724.TXT",
                "cause": "normal",
                "risk": "HIGH",
                "feedback": "최종진단 확정",
                "prefer_first_check": "시스템제어기조립체",
                "resolved": True,
                "resolved_item": "케이블 불량",
                "similar_tests": ["T03"],
                "final_confirmed": True,
                "final_diagnosis_json": "out/final.json",
            }
        ],
        "preferences": {"prefer_first_check": "시스템제어기조립체"},
        "resolved_priority": {"T03": {"케이블 불량": 2}},
        "last_interview": {
            "focus_log": "3.2 GICA-5.Ethernet.250724.TXT",
            "questions": ["케이블을 확인했습니까?"],
            "answers": ["예"],
        },
        "interview_history": [
            {
                "focus_log": "3.2 GICA-5.Ethernet.250724.TXT",
                "questions": ["케이블을 확인했습니까?"],
                "answers": ["예"],
            }
        ],
    }


def test_split_legacy_memory_keeps_episode_preference_and_verification():
    bundle = split_legacy_inspection_memory(_legacy_memory())

    assert bundle["episode"]["episodes"][0]["resolved_item"] == "케이블 불량"
    assert bundle["preference"]["preferences"]["prefer_first_check"] == "시스템제어기조립체"
    assert bundle["preference"]["resolved_priority"]["T03"]["케이블 불량"] == 2
    assert bundle["verification"]["last_interview"]["answers"] == ["예"]
    assert bundle["verification"]["approvals"][0]["approval_status"] == "approved"


def test_migrate_legacy_memory_writes_separated_utf8_json(tmp_path):
    legacy_path = tmp_path / "inspection_memory.json"
    memory_root = tmp_path / "memory"
    legacy_path.write_text(json.dumps(_legacy_memory(), ensure_ascii=False, indent=2), encoding="utf-8")

    migrate_legacy_inspection_memory(legacy_path, memory_root)
    paths = MemoryPaths.from_root(memory_root)

    assert paths.episode.exists()
    assert paths.preference.exists()
    assert paths.verification.exists()
    assert paths.dynamic.exists()
    assert paths.legacy_backup.exists()

    reloaded = load_memory_bundle(memory_root)
    assert reloaded["episode"]["episodes"][0]["focus_log"] == "3.2 GICA-5.Ethernet.250724.TXT"
    assert reloaded["preference"]["resolved_priority"]["T03"]["케이블 불량"] == 2
    assert "시스템제어기조립체" in paths.preference.read_text(encoding="utf-8")


def test_append_episode_and_verification_record_preserve_korean(tmp_path):
    memory_root = tmp_path / "memory"

    append_episode(memory_root, {"focus_log": "1. SELFTEST(케이블X)_251020.TXT", "result": "케이블 재체결 후 정상"})
    append_verification_record(memory_root, {"questions": ["전원 경로를 확인했습니까?"], "answers": ["예"]})

    bundle = load_memory_bundle(memory_root)
    assert bundle["episode"]["episodes"][0]["result"] == "케이블 재체결 후 정상"
    assert bundle["verification"]["last_interview"]["answers"] == ["예"]
