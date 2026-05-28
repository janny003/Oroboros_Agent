from __future__ import annotations

from typing import Any


INTERVIEW_LABELS = [
    "1순위 정비대상 확정",
    "동일 조건 재시험",
    "전원/케이블/통신 우선점검 유지",
    "회차별 고위험/기준 적용",
]


def _preference_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Return preference-shaped memory from either legacy or split bundle input."""
    if not isinstance(memory, dict):
        return {}
    if "preference" in memory and isinstance(memory.get("preference"), dict):
        return memory.get("preference", {})
    return memory


def _verification_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Return verification-shaped memory from either legacy or split bundle input."""
    if not isinstance(memory, dict):
        return {}
    if "verification" in memory and isinstance(memory.get("verification"), dict):
        return memory.get("verification", {})
    return memory


def _iter_approved_final_records(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Return approved Step10/11 records from split or legacy memory, newest first."""
    records: list[dict[str, Any]] = []
    verification = _verification_memory(memory)
    approvals = verification.get("approvals", []) if isinstance(verification, dict) else []
    if isinstance(approvals, list):
        for record in approvals:
            if isinstance(record, dict) and str(record.get("approval_status", "")).strip() == "approved":
                records.append(record)

    legacy_history = memory.get("history", []) if isinstance(memory, dict) else []
    if isinstance(legacy_history, list):
        for record in legacy_history:
            if isinstance(record, dict) and record.get("final_confirmed"):
                records.append(record)

    return list(reversed(records))


def _record_matches_test_ids(record: dict[str, Any], test_ids: list[str]) -> bool:
    wanted = {str(t) for t in (test_ids or []) if str(t).strip()}
    if not wanted or "GLOBAL" in wanted:
        return True
    record_ids = record.get("test_ids") or record.get("similar_tests") or []
    if isinstance(record_ids, str):
        record_ids = [record_ids]
    if not isinstance(record_ids, list):
        return False
    record_set = {str(t) for t in record_ids if str(t).strip()}
    return bool(record_set & wanted) or "GLOBAL" in record_set


def _action_text(action: Any) -> str:
    if isinstance(action, dict):
        for key in ("item", "action", "name", "check_item", "label"):
            value = str(action.get(key, "")).strip()
            if value:
                return value
        return ""
    return str(action).strip()


def apply_final_confirmation_priority(memory: dict[str, Any], test_ids: list[str], exclusion_items: list[str]) -> tuple[list[str], str]:
    """Reuse approved final diagnoses as the first signal for the next diagnosis."""
    ranked: list[str] = []
    for record in _iter_approved_final_records(memory):
        if not _record_matches_test_ids(record, test_ids):
            continue
        actions = record.get("recommended_actions") or record.get("final_priority_check_order") or []
        if isinstance(actions, str):
            actions = [actions]
        if not isinstance(actions, list):
            continue
        for action in actions:
            text = _action_text(action)
            if text and text not in ranked:
                ranked.append(text)
        if len(ranked) >= 3:
            break

    if not ranked:
        return list(exclusion_items), ""

    reordered: list[str] = []
    used: set[str] = set()
    for item in ranked:
        reordered.append(item)
        used.add(item)
    for item in exclusion_items:
        if item not in used:
            reordered.append(item)
            used.add(item)
    return reordered[:5], f"(최종확정 이력 반영: 이전 승인 진단의 우선점검 {min(3, len(ranked))}개를 앞에 배치)"


def build_interview_memory_note(memory: dict[str, Any]) -> str:
    verification = _verification_memory(memory)
    last = verification.get("last_interview", {}) if isinstance(verification, dict) else {}
    if not isinstance(last, dict):
        return ""
    answers = last.get("answers", [])
    if not isinstance(answers, list) or not answers:
        return ""

    pairs: list[str] = []
    for i, ans in enumerate(answers[:4]):
        label = INTERVIEW_LABELS[i] if i < len(INTERVIEW_LABELS) else f"질문{i + 1}"
        pairs.append(f"{label}={ans}")
    return "이전 인터뷰 답변 반영: " + ", ".join(pairs)


def apply_interview_priority(memory: dict[str, Any], exclusion_items: list[str]) -> tuple[list[str], str]:
    verification = _verification_memory(memory)
    last = verification.get("last_interview", {}) if isinstance(verification, dict) else {}
    answers = last.get("answers", []) if isinstance(last, dict) else []
    if not isinstance(answers, list) or len(answers) < 3:
        return list(exclusion_items), ""

    # Q3: 전원/케이블/통신 라인을 우선 점검 순서로 유지할지 여부.
    if str(answers[2]).strip() != "예":
        return list(exclusion_items), ""

    preferred = "전원/케이블/통신 라인"
    reordered = [preferred]
    for item in exclusion_items:
        if item != preferred and item not in reordered:
            reordered.append(item)
    return reordered[:5], "(이전 인터뷰 답변 반영: 전원/케이블/통신 라인 우선 유지)"


def apply_resolved_priority(memory: dict[str, Any], test_ids: list[str], exclusion_items: list[str]) -> tuple[list[str], str]:
    preference = _preference_memory(memory)
    solved_map = preference.get("resolved_priority", {}) if isinstance(preference, dict) else {}
    merged: dict[str, int] = {}
    for t in (test_ids or []):
        bucket = solved_map.get(t, {}) if isinstance(solved_map, dict) else {}
        for k, v in (bucket or {}).items():
            merged[str(k)] = merged.get(str(k), 0) + int(v)
    global_bucket = solved_map.get("GLOBAL", {}) if isinstance(solved_map, dict) else {}
    for k, v in (global_bucket or {}).items():
        merged[str(k)] = merged.get(str(k), 0) + int(v)

    if not merged:
        return list(exclusion_items), ""

    ranked = [k for k, _ in sorted(merged.items(), key=lambda kv: kv[1], reverse=True)]
    reordered: list[str] = []
    used: set[str] = set()

    for item in ranked:
        if item not in used:
            reordered.append(item)
            used.add(item)
    for item in exclusion_items:
        if item not in used:
            reordered.append(item)
            used.add(item)

    note = f"(지속 메모리 반영: 과거 해결 이력 기반 우선항목 {min(3, len(ranked))}개를 앞에 배치)"
    return reordered[:5], note


def apply_preference_priority(memory: dict[str, Any], exclusion_items: list[str]) -> tuple[list[str], str]:
    preference = _preference_memory(memory)
    prefs = preference.get("preferences", {}) if isinstance(preference, dict) else {}
    prefer_first = str(prefs.get("prefer_first_check", "")).strip() if isinstance(prefs, dict) else ""
    if not prefer_first:
        return list(exclusion_items), ""

    reordered = list(exclusion_items)
    idx = next((i for i, it in enumerate(reordered) if prefer_first in it), -1)
    if idx > 0:
        first_item = reordered.pop(idx)
        reordered.insert(0, first_item)
    elif idx < 0:
        reordered.insert(0, prefer_first)
    return reordered[:5], f"지속 메모리 적용: 이전 우선점검 선호 '{prefer_first}'를 본 권고 순서에 반영했습니다."


def apply_recommendation_policy(memory: dict[str, Any], test_ids: list[str], exclusion_items: list[str]) -> dict[str, Any]:
    """Apply memory-driven ordering without mutating raw pipeline analysis data."""
    ordered, final_note = apply_final_confirmation_priority(memory, test_ids, list(exclusion_items))
    ordered, resolved_note = apply_resolved_priority(memory, test_ids, ordered)
    ordered, interview_note = apply_interview_priority(memory, ordered)
    ordered, preference_note = apply_preference_priority(memory, ordered)
    return {
        "recommended_exclusion_items": ordered[:3],
        "final_confirmation_note": final_note,
        "resolved_priority_note": resolved_note,
        "interview_priority_note": interview_note,
        "preference_note": preference_note,
        "interview_memory_note": build_interview_memory_note(memory),
    }
