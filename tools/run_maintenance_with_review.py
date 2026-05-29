from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from agent_memory import append_final_approval, append_episode, append_verification_record
except ImportError:  # pragma: no cover - package import path for tests/tools
    from tools.agent_memory import append_final_approval, append_episode, append_verification_record

AGENT_CONTEXT_FIELD_INTERVIEW = "Context & Field Interview Agent"
AGENT_PERSISTENT_MEMORY_RETRIEVAL = "Persistent Memory Retrieval Agent"
AGENT_DIAGNOSTIC_REASONING = "Diagnostic Reasoning Agent"
AGENT_PROCEDURE_PRIORITY = "Procedure & Priority Agent"
AGENT_TRUST_GATE = "Trust Gate Agent"
AGENT_FEEDBACK_LEARNING = "Feedback Learning Agent"


def _agent(name: str, detail: str) -> None:
    print(f"[AGENT] {name} | {detail}", flush=True)


def _run(cmd: list[str]) -> int:
    print("[RUN] " + " ".join(cmd), flush=True)
    p = subprocess.run(cmd)
    return p.returncode


def _normalize_yes_no(raw: str) -> str:
    v = (raw or "").strip().lower()
    yes_set = {"y", "yes", "1", "예", "ㅇ", "응", "네"}
    no_set = {"n", "no", "0", "아니요", "아니오", "ㄴ"}
    if v in yes_set:
        return "예"
    if v in no_set:
        return "아니요"
    return "아니요"


def _normalize_final_confirmation(raw: str) -> str:
    v = (raw or "").strip().lower()
    approved = {"y", "yes", "1", "예", "ㅇ", "응", "네", "approve", "approved", "승인", "확정"}
    pending = {"hold", "pending", "보류", "대기", "검토"}
    rejected = {"n", "no", "0", "아니요", "아니오", "ㄴ", "reject", "rejected", "반려", "거절"}
    if v in approved:
        return "approved"
    if v in pending:
        return "pending"
    if v in rejected:
        return "rejected"
    return "rejected"


def _collect_final_confirmation() -> str:
    _agent(AGENT_TRUST_GATE, "최종 진단 확정 여부를 확인합니다.")
    question = "최종 진단을 확정하고 정비 이력에 저장하시겠습니까? (approved/pending/rejected 또는 Yes/No)"
    print(f"[FINAL_CONFIRM_Q] {question}", flush=True)
    try:
        user_input = input()
    except EOFError:
        user_input = "rejected"
    status = _normalize_final_confirmation(user_input)
    print(f"[FINAL_CONFIRM_A] {status}", flush=True)
    return status


def _collect_interview_answers(step7: dict[str, Any]) -> list[str]:
    _agent(AGENT_CONTEXT_FIELD_INTERVIEW, "현장 확인 질문을 표시하고 예/아니요 응답을 수집합니다.")
    questions = step7.get("interview_questions", []) if isinstance(step7, dict) else []
    if not isinstance(questions, list):
        return []

    answers: list[str] = []
    for i, q in enumerate(questions, 1):
        print(f"[INTERVIEW_Q{i}] {q}", flush=True)
        try:
            user_input = input()
        except EOFError:
            user_input = "아니요"
        yn = _normalize_yes_no(user_input)
        answers.append(yn)
        print(f"[INTERVIEW_A{i}] {yn}", flush=True)

    return answers


def _persist_interview_answers(report_json: Path, review_json: Path, answers: list[str]) -> None:
    """Persist Step7 Yes/No answers so the next diagnosis can use them."""
    _agent(AGENT_FEEDBACK_LEARNING, "현장 인터뷰 응답을 다음 진단 학습 이력에 저장합니다.")
    if not answers:
        return

    try:
        report_data = json.loads(report_json.read_text(encoding="utf-8"))
    except Exception:
        return

    memory_path_raw = str(report_data.get("memory_json") or "").strip()
    if not memory_path_raw:
        return

    memory_path = Path(memory_path_raw)
    try:
        memory = json.loads(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}
    except Exception:
        memory = {}

    focus = report_data.get("focus") if isinstance(report_data.get("focus"), dict) else {}
    try:
        review_data = json.loads(review_json.read_text(encoding="utf-8")) if review_json.exists() else {}
    except Exception:
        review_data = {}
    step7 = review_data.get("step7", {}) if isinstance(review_data.get("step7"), dict) else {}
    questions = step7.get("interview_questions", []) if isinstance(step7.get("interview_questions", []), list) else []

    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "current_report": str(report_json),
        "focus_log": str(focus.get("file", "")),
        "test_ids": focus.get("test_ids", []),
        "questions": questions,
        "answers": answers,
    }

    memory["last_interview"] = record
    hist = memory.setdefault("interview_history", [])
    if isinstance(hist, list):
        hist.append(record)
        if len(hist) > 200:
            del hist[:-200]

    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")

    split_memory_root = memory_path.parent / "memory"
    append_verification_record(split_memory_root, record)


def _priority_check_order(step9: dict[str, Any]) -> list[dict[str, Any]]:
    feedback = step9.get("feedback", []) if isinstance(step9, dict) else []
    if not isinstance(feedback, list):
        return []
    for item in feedback:
        if isinstance(item, dict) and item.get("type") == "priority_reorder":
            order = item.get("top3_check_order", [])
            return order if isinstance(order, list) else []
    return []


def _risk_trend_note(step9: dict[str, Any]) -> str:
    feedback = step9.get("feedback", []) if isinstance(step9, dict) else []
    if not isinstance(feedback, list):
        return ""
    for item in feedback:
        if isinstance(item, dict) and item.get("type") == "risk_trend":
            return str(item.get("message", ""))
    return ""


def _build_final_diagnosis_payload(
    report_json: Path,
    review_json: Path,
    report_data: dict[str, Any],
    review_data: dict[str, Any],
    approval_status: str,
) -> dict[str, Any]:
    focus = report_data.get("focus") if isinstance(report_data.get("focus"), dict) else {}
    step7 = review_data.get("step7", {}) if isinstance(review_data.get("step7"), dict) else {}
    step8 = review_data.get("step8", {}) if isinstance(review_data.get("step8"), dict) else {}
    step9 = review_data.get("step9", {}) if isinstance(review_data.get("step9"), dict) else {}
    approved = approval_status == "approved"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "final_confirmed" if approved else "not_confirmed",
        "approval_status": approval_status,
        "final_confirmed": approved,
        "approved_by": "operator" if approved else "",
        "report_json": str(report_json),
        "review_json": str(review_json),
        "summary": report_data.get("summary", {}),
        "focus_log": str(focus.get("file", "")),
        "cause": str(focus.get("cause", "")),
        "risk": str(focus.get("risk", "")),
        "test_ids": focus.get("test_ids", []),
        "recommended_actions": focus.get("recommended_exclusion_items", []),
        "step7_questions": step7.get("interview_questions", []) if isinstance(step7.get("interview_questions", []), list) else [],
        "step7_answers": step7.get("interview_answers", []) if isinstance(step7.get("interview_answers", []), list) else [],
        "step7_evaluate": step7.get("evaluate", {}),
        "step8_compare": step8,
        "step9_feedback": step9.get("feedback", []),
        "final_priority_check_order": _priority_check_order(step9),
        "risk_trend_note": _risk_trend_note(step9),
    }


def _persist_final_confirmation(report_json: Path, review_json: Path, approval_status: str) -> Path | None:
    _agent(AGENT_FEEDBACK_LEARNING, "최종 확정/반려 결과를 지속 메모리에 반영합니다.")
    try:
        report_data = json.loads(report_json.read_text(encoding="utf-8"))
        review_data = json.loads(review_json.read_text(encoding="utf-8")) if review_json.exists() else {}
    except Exception:
        return None

    memory_path_raw = str(report_data.get("memory_json") or "").strip()
    if not memory_path_raw:
        return None
    memory_path = Path(memory_path_raw)
    try:
        memory = json.loads(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}
    except Exception:
        memory = {}

    payload = _build_final_diagnosis_payload(report_json, review_json, report_data, review_data, approval_status)
    final_json: Path | None = None
    split_memory_root = memory_path.parent / "memory"

    if approval_status == "approved":
        final_dir = memory_path.parent / "final_diagnosis"
        final_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_json = final_dir / f"final_diagnosis_{report_json.stem}_{stamp}.json"
        final_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        hist = memory.setdefault("history", [])
        if isinstance(hist, list):
            hist_record = {
                "ts": payload["generated_at"],
                "focus_log": payload["focus_log"],
                "cause": payload["cause"],
                "risk": payload["risk"],
                "feedback": "최종진단 확정",
                "final_confirmed": True,
                "approval_status": approval_status,
                "final_diagnosis_json": str(final_json),
                "current_report": str(report_json),
                "review_json": str(review_json),
                "similar_tests": payload["test_ids"],
                "test_ids": payload["test_ids"],
                "recommended_actions": payload["recommended_actions"],
                "final_priority_check_order": payload["final_priority_check_order"],
            }
            hist.append(hist_record)
            if len(hist) > 200:
                del hist[:-200]
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")

        approval_record = {
            "ts": payload["generated_at"],
            "approval_status": approval_status,
            "approved_by": "operator",
            "basis": "최종진단 확정",
            "report_json": str(report_json),
            "review_json": str(review_json),
            "final_diagnosis_json": str(final_json),
            "test_ids": payload["test_ids"],
            "recommended_actions": payload["recommended_actions"],
            "final_priority_check_order": payload["final_priority_check_order"],
            "step7_evaluate": payload["step7_evaluate"],
        }
        append_final_approval(split_memory_root, approval_record)
        append_episode(split_memory_root, {"event_type": "final_diagnosis_confirmed", **hist_record})
    else:
        append_final_approval(
            split_memory_root,
            {
                "ts": payload["generated_at"],
                "approval_status": approval_status,
                "approved_by": "operator",
                "basis": "최종진단 미확정",
                "report_json": str(report_json),
                "review_json": str(review_json),
            },
        )

    review_data["step10"] = {"approval_status": approval_status, "final_confirmed": approval_status == "approved"}
    review_data["step11"] = {"final_diagnosis_json": str(final_json) if final_json else ""}
    review_json.write_text(json.dumps(review_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정비 보고서 생성 + Ouroboros Step7~9 검토 연동 실행기")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--log-root", required=True)
    parser.add_argument("--out-doc", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--focus-log", default="")
    parser.add_argument("--operator-feedback", default="")
    parser.add_argument("--memory-json", default="", help="지속 점검 메모리 JSON 경로(테스트/GUI 격리 실행용)")
    parser.add_argument("--fault-exclusion-csv", default="", help="시험 항목별 고장배제 매트릭스 CSV 경로")
    parser.add_argument("--review-history-dir", default="")
    parser.add_argument("--review-out-dir", default="")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root)
    gen_script = project_root / "tools" / "generate_maintenance_report.py"
    review_script = project_root / "tools" / "ouroboros_review_loop.py"

    out_doc = Path(args.out_doc)
    out_json = Path(args.out_json) if args.out_json else out_doc.with_suffix(".json")
    review_history_dir = Path(args.review_history_dir) if args.review_history_dir else out_doc.parent
    review_out_dir = Path(args.review_out_dir) if args.review_out_dir else (project_root / "out" / "ouroboros_review")

    cmd_gen = [
        args.python,
        str(gen_script),
        "--project-root", str(project_root),
        "--log-root", str(Path(args.log_root)),
        "--out-doc", str(out_doc),
        "--out-json", str(out_json),
    ]
    if args.focus_log:
        cmd_gen += ["--focus-log", str(Path(args.focus_log))]
    if args.operator_feedback:
        cmd_gen += ["--operator-feedback", args.operator_feedback]
    if args.memory_json:
        cmd_gen += ["--memory-json", str(Path(args.memory_json))]
    if args.fault_exclusion_csv:
        cmd_gen += ["--fault-exclusion-csv", str(Path(args.fault_exclusion_csv))]

    _agent(AGENT_PERSISTENT_MEMORY_RETRIEVAL, "누적 점검 메모리와 과거 보고서 기준을 불러옵니다.")
    _agent(AGENT_DIAGNOSTIC_REASONING, "로그 이상탐지, 원인분류, 위험도 분석 보고서를 생성합니다.")
    rc = _run(cmd_gen)
    if rc != 0:
        return rc

    cmd_review = [
        args.python,
        str(review_script),
        "--current-report-json", str(out_json),
        "--history-dir", str(review_history_dir),
        "--out-dir", str(review_out_dir),
    ]
    _agent(AGENT_PROCEDURE_PRIORITY, "고장배제 절차와 우선점검 순서를 산정합니다.")
    rc = _run(cmd_review)
    if rc != 0:
        return rc

    review_json = review_out_dir / "ouroboros_review_result.json"
    if review_json.exists():
        try:
            review_data = json.loads(review_json.read_text(encoding="utf-8"))
            step7 = review_data.get("step7", {})
            evaluate = step7.get("evaluate", {})
            qa_checks = step7.get("qa_checks", [])
            _agent(AGENT_TRUST_GATE, "검토 점수와 QA 체크 결과로 신뢰 기준을 평가합니다.")
            print(
                f"[REVIEW] score={evaluate.get('score', 'n/a')} verdict={evaluate.get('verdict', 'n/a')} qa_checks={len(qa_checks)}",
                flush=True,
            )

            # 질문 4개를 순차 출력하고 stdin 응답(Yes/No)을 실제로 수신할 때까지 대기한다.
            answers = _collect_interview_answers(step7)
            if answers:
                review_data.setdefault("step7", {})["interview_answers"] = answers
                review_json.write_text(json.dumps(review_data, ensure_ascii=False, indent=2), encoding="utf-8")
                _persist_interview_answers(out_json, review_json, answers)
                approval_status = _collect_final_confirmation()
                final_json = _persist_final_confirmation(out_json, review_json, approval_status)
                print(f"[FINAL_CONFIRM] status={approval_status} final_diagnosis_json={final_json or ''}", flush=True)
        except Exception as ex:
            print(f"[REVIEW] summary parse skipped: {ex}", flush=True)

    print(f"[DONE] report_doc={out_doc}")
    print(f"[DONE] report_json={out_json}")
    print(f"[DONE] review_dir={review_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
