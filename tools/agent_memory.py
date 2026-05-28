from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemoryPaths:
    """Filesystem layout for separated agent memory files."""

    root: Path
    episode: Path
    preference: Path
    verification: Path
    dynamic: Path
    legacy_backup: Path

    @classmethod
    def from_root(cls, root: Path | str) -> "MemoryPaths":
        base = Path(root)
        return cls(
            root=base,
            episode=base / "episode_memory.json",
            preference=base / "preference_memory.json",
            verification=base / "verification_memory.json",
            dynamic=base / "dynamic_memory.json",
            legacy_backup=base / "legacy_inspection_memory_backup.json",
        )


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default or {})
    return data if isinstance(data, dict) else dict(default or {})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def empty_memory_bundle() -> dict[str, Any]:
    return {
        "episode": {"episodes": []},
        "preference": {"preferences": {}, "resolved_priority": {}},
        "verification": {"last_interview": {}, "interview_history": [], "approvals": [], "audit_log": []},
        "dynamic": {"records": []},
    }


def split_legacy_inspection_memory(legacy: dict[str, Any]) -> dict[str, Any]:
    """Convert the old all-in-one inspection_memory.json into separated memory payloads.

    The conversion is intentionally conservative.  It preserves original records
    rather than trying to infer missing fields such as recurrence or approver.
    """

    bundle = empty_memory_bundle()

    history = legacy.get("history", [])
    if isinstance(history, list):
        bundle["episode"]["episodes"] = history

    preferences = legacy.get("preferences", {})
    if isinstance(preferences, dict):
        bundle["preference"]["preferences"] = preferences

    resolved_priority = legacy.get("resolved_priority", {})
    if isinstance(resolved_priority, dict):
        bundle["preference"]["resolved_priority"] = resolved_priority

    last_interview = legacy.get("last_interview", {})
    if isinstance(last_interview, dict):
        bundle["verification"]["last_interview"] = last_interview

    interview_history = legacy.get("interview_history", [])
    if isinstance(interview_history, list):
        bundle["verification"]["interview_history"] = interview_history

    final_confirmed = [r for r in history if isinstance(r, dict) and r.get("final_confirmed")] if isinstance(history, list) else []
    if final_confirmed:
        bundle["verification"]["approvals"] = [
            {
                "ts": r.get("ts", ""),
                "approval_status": "approved",
                "approved_by": "operator",
                "basis": r.get("feedback", "최종진단 확정"),
                "final_diagnosis_json": r.get("final_diagnosis_json", ""),
            }
            for r in final_confirmed
        ]

    return bundle


def migrate_legacy_inspection_memory(legacy_path: Path | str, memory_root: Path | str, *, backup: bool = True) -> dict[str, Any]:
    """Split a legacy memory file into the new out/memory JSON files."""

    legacy_path = Path(legacy_path)
    paths = MemoryPaths.from_root(memory_root)
    legacy = _read_json(legacy_path, {})
    bundle = split_legacy_inspection_memory(legacy)

    if backup and legacy_path.exists():
        paths.root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(legacy_path, paths.legacy_backup)

    save_memory_bundle(paths, bundle)
    return bundle


def load_memory_bundle(memory_root: Path | str) -> dict[str, Any]:
    paths = MemoryPaths.from_root(memory_root)
    defaults = empty_memory_bundle()
    return {
        "episode": _read_json(paths.episode, defaults["episode"]),
        "preference": _read_json(paths.preference, defaults["preference"]),
        "verification": _read_json(paths.verification, defaults["verification"]),
        "dynamic": _read_json(paths.dynamic, defaults["dynamic"]),
    }


def save_memory_bundle(paths: MemoryPaths | Path | str, bundle: dict[str, Any]) -> None:
    if not isinstance(paths, MemoryPaths):
        paths = MemoryPaths.from_root(paths)
    defaults = empty_memory_bundle()
    _write_json(paths.episode, bundle.get("episode", defaults["episode"]))
    _write_json(paths.preference, bundle.get("preference", defaults["preference"]))
    _write_json(paths.verification, bundle.get("verification", defaults["verification"]))
    _write_json(paths.dynamic, bundle.get("dynamic", defaults["dynamic"]))


def append_episode(memory_root: Path | str, episode: dict[str, Any], *, limit: int = 200) -> None:
    bundle = load_memory_bundle(memory_root)
    episodes = bundle.setdefault("episode", {}).setdefault("episodes", [])
    if not isinstance(episodes, list):
        episodes = []
        bundle["episode"]["episodes"] = episodes
    episodes.append(episode)
    if len(episodes) > limit:
        del episodes[:-limit]
    save_memory_bundle(memory_root, bundle)


def append_verification_record(memory_root: Path | str, record: dict[str, Any], *, limit: int = 200) -> None:
    bundle = load_memory_bundle(memory_root)
    verification = bundle.setdefault("verification", {})
    verification["last_interview"] = record
    history = verification.setdefault("interview_history", [])
    if not isinstance(history, list):
        history = []
        verification["interview_history"] = history
    history.append(record)
    if len(history) > limit:
        del history[:-limit]
    save_memory_bundle(memory_root, bundle)


def append_final_approval(memory_root: Path | str, record: dict[str, Any], *, limit: int = 200) -> None:
    """Append a Step10/11 final-confirmation audit record.

    Approved records are kept in verification.approvals. All statuses are kept in
    verification.audit_log so rejected/pending confirmations remain auditable
    without being treated as approved maintenance history.
    """
    bundle = load_memory_bundle(memory_root)
    verification = bundle.setdefault("verification", {})
    status = str(record.get("approval_status", "")).strip() or "rejected"
    audit_record = {"event_type": "final_confirmation", **record, "approval_status": status}

    audit_log = verification.setdefault("audit_log", [])
    if not isinstance(audit_log, list):
        audit_log = []
        verification["audit_log"] = audit_log
    audit_log.append(audit_record)
    if len(audit_log) > limit:
        del audit_log[:-limit]

    if status == "approved":
        approvals = verification.setdefault("approvals", [])
        if not isinstance(approvals, list):
            approvals = []
            verification["approvals"] = approvals
        approval_record = dict(record)
        approval_record["approval_status"] = status
        approvals.append(approval_record)
        if len(approvals) > limit:
            del approvals[:-limit]
        verification["last_approval"] = approval_record

    save_memory_bundle(memory_root, bundle)
