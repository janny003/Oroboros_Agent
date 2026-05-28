from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from agent_memory import append_verification_record
except ImportError:  # pragma: no cover - package import path for tests/tools
    from tools.agent_memory import append_verification_record


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


def _collect_interview_answers(step7: dict[str, Any]) -> list[str]:
    questions = step7.get("interview_questions", []) if isinstance(step7, dict) else []
    if not isinstance(questions, list):
        return []

    answers: list[str] = []
    for i, q in enumerate(questions[:4], 1):
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
        "questions": questions[:4],
        "answers": answers[:4],
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정비 보고서 생성 + Ouroboros Step7~9 검토 연동 실행기")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--log-root", required=True)
    parser.add_argument("--out-doc", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--focus-log", default="")
    parser.add_argument("--operator-feedback", default="")
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
        except Exception as ex:
            print(f"[REVIEW] summary parse skipped: {ex}", flush=True)

    print(f"[DONE] report_doc={out_doc}")
    print(f"[DONE] report_json={out_json}")
    print(f"[DONE] review_dir={review_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
