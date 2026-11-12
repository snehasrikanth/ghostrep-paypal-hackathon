"""Bounded evidence for explicitly shared clips only; no paths, profiles or previous clips."""
import math

from app.services.coaching.chat_context import build_context
from app.services.recording_provenance import is_sample_set


def shared_evidence(db, rec):
    context = build_context(db, rec, "Explain this set.")
    evidence = {k: v for k, v in context["evidence"].items() if v.get("set_id") == rec.id}
    facts = {k: v for k, v in context["facts"].items()
             if k in {"counts", "reported", "limits", "availability", "sample"} or k.startswith("rep_")}
    facts = {k: v for k, v in facts.items() if all(e in evidence for e in v.get("evidence_ids", []))}
    return {"recording_id": rec.id, "synthetic": is_sample_set(rec),
            "exercise": rec.exercise_id, "facts": facts, "evidence": evidence,
            "reference_rep": rec.analysis.reference_rep if rec.analysis else None,
            "reps": [{"rep_index": r.rep_index, "start_seconds": r.start_seconds,
                      "end_seconds": r.end_seconds, "is_reference": r.is_reference}
                     for r in sorted(rec.reps, key=lambda r: r.rep_index)[:20]
                     if all(isinstance(v, (int, float)) and math.isfinite(v)
                            for v in (r.start_seconds, r.end_seconds))
                     and 0 <= r.start_seconds < r.end_seconds <= (rec.duration_seconds or 0)]}
