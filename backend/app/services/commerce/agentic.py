"""Movement-analysis recommendation for agentic fitness commerce.

Catalog prices are authoritative. This module never invents amounts or charges.
"""
from __future__ import annotations

import json
import re

from app.services.commerce.catalog import matches_clips


SAFETY = re.compile(
    r"\b(pain|painful|injur\w*|hurt\w*|medical|unsafe|safe|safety|risk|sore|ache\w*|discomfort)\b",
    re.I,
)


def _facts_text(evidence: list[dict]) -> str:
    parts = []
    for clip in evidence:
        for fact in (clip.get("facts") or {}).values():
            text = (fact or {}).get("text")
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def analyze_movement(evidence: list[dict]) -> dict:
    """Use only canonical, meaningful rep differences with an exact evidence link.

    chat_context emits metric facts only after reliability and magnitude gates.
    Counts, availability/limitation text and merely mentioning a metric are not findings.
    """
    findings = []
    for clip in evidence:
        links = clip.get("evidence") or {}
        for key, fact in (clip.get("facts") or {}).items():
            match = re.fullmatch(r"rep_(\d+)_(torso_inclination|relative_depth|ascent_duration|descent_duration)", key)
            refs = (fact or {}).get("evidence_ids") or []
            if not match or not refs or not all(ref in links for ref in refs):
                continue
            ref = next((links[r] for r in refs if links[r].get("rep_id") == int(match[1])), None)
            if not ref or not fact.get("text"):
                continue
            findings.append({"metric": match[2], "recording_id": clip["recording_id"],
                             "rep_id": int(match[1]), "seconds": ref.get("seconds"), "text": fact["text"]})
    # Each rep/metric is counted once. Severity is an internal matching score, never a technique grade.
    findings = list({(f["recording_id"], f["rep_id"], f["metric"]): f for f in findings}.values())
    recurring = len({(f["recording_id"], f["rep_id"]) for f in findings}) > 1
    metrics = {f["metric"] for f in findings}
    issues = []
    if "torso_inclination" in metrics:
        issues.append("torso angle differences from your personal reference")
    if "relative_depth" in metrics:
        issues.append("relative depth differences from your personal reference")
    if metrics & {"ascent_duration", "descent_duration"}:
        issues.append("rep timing differences from your personal reference")
    return {"severity": min(8, len(findings) * 2), "recurring": recurring,
            "issues": issues, "beneficial": bool(findings), "findings": findings[:8],
            "summary": ", ".join(issues) if issues else "No reliable rep-linked movement difference is available."}


def _pick(eligible: list[dict], analysis: dict, question: str) -> str | None:
    if not eligible:
        return None
    by_id = {p["id"]: p for p in eligible}
    wants_session = bool(re.search(r"\b(session|call|live|book|appoint|coach with me|1:?1|one.on.one)\b", question, re.I))
    if wants_session and "personal-coaching-session" in by_id:
        return "personal-coaching-session"
    if analysis["severity"] >= 5 and "expert-video-review" in by_id:
        return "expert-video-review"
    if analysis["recurring"] and "expert-video-review" in by_id:
        return "expert-video-review"
    if analysis["severity"] >= 2 and "ai-technique-review" in by_id:
        return "ai-technique-review"
    # Prefer lowest eligible agentic package when benefit is mild.
    for pid in ("ai-technique-review", "expert-video-review", "personal-coaching-session"):
        if pid in by_id:
            return pid
    return eligible[0]["id"]


def explain(package: dict, analysis: dict, alternatives: list[dict]) -> str:
    price = f"${package['price_cents'] / 100:.2f}"
    focus = analysis["summary"]
    why = (
        f"Saved comparisons describe {focus}. For a closer review, an optional choice is the {price} "
        f"{package['name']} for {package['description'].rstrip('.')}."
    )
    if alternatives:
        alts = "; ".join(f"{a['name']} (${a['price_cents'] / 100:.2f})" for a in alternatives)
        why += f" Alternatives in your budget: {alts}."
    return why


def recommend_agentic(body, packages, evidence):
    """Recommend from the agentic catalog using movement analysis. Prices come only from packages."""
    eligible = sorted(
        [p for p in packages if matches_clips(p, len(evidence))
         and (body.budget_cents is None or p["price_cents"] <= body.budget_cents)],
        key=lambda p: (p["price_cents"], p["id"]),
    )
    analysis = analyze_movement(evidence)
    base = {
        "outcome": "recommend",
        "package_id": None,
        "source": "deterministic_movement",
        "source_label": "Deterministic movement analysis · no AI call",
        "explanation": "",
        "limits": (
            "Server catalog prices are authoritative. Automated reports and expert review requests "
            "are separate services. Checkout starts only after your approval."
        ),
        "analysis": analysis,
        "alternatives": [{"id": p["id"], "name": p["name"], "price_cents": p["price_cents"],
                          "kind": p.get("kind"), "deliverables": p.get("deliverables", [])} for p in eligible],
        "comparison": [
            {"id": p["id"], "name": p["name"], "price_cents": p["price_cents"],
             "expertise": p.get("delivery_label") or p.get("kind"),
             "deliverable": p.get("description")}
            for p in eligible
        ],
    }
    if SAFETY.search(body.question or ""):
        return {**base, "outcome": "no_match", "package_id": None,
                "explanation": "Safety or pain-related questions are not used to recommend a purchase. Use free saved feedback or seek qualified care."}
    if len((body.question or "").strip()) < 10:
        return {**base, "outcome": "follow_up", "package_id": None,
                "explanation": "Add a short goal or focus for coaching (for example, torso lean on later reps)."}
    explicit_session = bool(re.search(r"\b(session|call|live|book|appointment)\b", body.question or "", re.I))
    if not analysis["beneficial"] and not explicit_session:
        return {**base, "outcome": "no_match", "package_id": None,
                "explanation": "Saved movement evidence does not clearly support an additional coaching purchase. Keep using free feedback."}
    if not eligible:
        return {**base, "outcome": "no_match",
                "explanation": "No active coaching service fits your clips and budget. You can raise the budget or skip purchase."}
    chosen_id = _pick(eligible, analysis, body.question)
    chosen = next(p for p in eligible if p["id"] == chosen_id)
    alts = [p for p in eligible if p["id"] != chosen_id]
    return {
        **base,
        "outcome": "recommend",
        "package_id": chosen_id,
        "explanation": explain(chosen, analysis, alts) if analysis["beneficial"] else (
            f"You asked for live coaching. {chosen['name']} fits your shared clip scope and budget. "
            "This is your requested service, not a detected technique problem. Availability requires confirmation."),
        "alternatives": [{"id": p["id"], "name": p["name"], "price_cents": p["price_cents"],
                          "kind": p.get("kind"), "deliverables": p.get("deliverables", [])} for p in alts],
    }


def enrich_legacy_recommendation(result: dict, packages: list[dict], evidence: list[dict]) -> dict:
    """Attach analysis metadata without changing legacy package selection contracts."""
    if "analysis" not in result:
        result = {**result, "analysis": analyze_movement(evidence),
                  "alternatives": result.get("alternatives") or [
                      {"id": p["id"], "name": p["name"], "price_cents": p["price_cents"]} for p in packages
                  ],
                  "comparison": result.get("comparison") or []}
    return result
