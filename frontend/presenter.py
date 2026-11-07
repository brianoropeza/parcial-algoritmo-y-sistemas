"""Pure presentation logic (no Streamlit), so it can be tested with pytest.

- Validates user input before calling the backend.
- Shows only allow-listed fields: never document, email, phone or loyalty tier.
- Tolerant reader: uses optional fields if the backend adds them, never fails if they are missing.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

BOOKING_ID_RE = re.compile(r"^[A-Z0-9]{5,8}$")

PASSENGER_FIELDS = ("name", "type", "age")
SEGMENT_FIELDS = ("segment_id", "flight_number", "origin", "destination", "date",
                  "scheduled_departure", "scheduled_arrival")

CLASSIFICATION_TEXT = {
    "DISRUPTION_REVIEW_REQUIRED": ("warning", "Your trip has a change that we are reviewing"),
    "MISSED_CONNECTION": ("error", "Your flight is delayed and you will miss your connection"),
    "DISRUPTION_CONFIRMED": ("warning", "Your trip has a confirmed change"),
    "DISRUPTION_DETECTED": ("warning", "Your trip has a relevant change"),
    "NO_DISRUPTION_CONFIRMED": ("success", "We found no changes to your trip"),
    # Automation levels from docs/DECISIONS.md (D-005); English and Spanish names accepted.
    "INFORM": ("info", "Your trip has a change; here is what it means for you"),
    "OFFER_OPTIONS": ("warning", "Your trip changed and we have options for you"),
    "ESCALATE_HUMAN": ("warning", "Your trip changed and an agent will review your case"),
    "INFORMAR": ("info", "Your trip has a change; here is what it means for you"),
    "OFRECER_OPCIONES": ("warning", "Your trip changed and we have options for you"),
    "ESCALAR_HUMANO": ("warning", "Your trip changed and an agent will review your case"),
}

HUMAN_CLASSIFICATIONS = {"ESCALATE_HUMAN", "ESCALAR_HUMANO"}

PASSENGER_TYPE_TEXT = {"ADULT": "Adult", "CHILD": "Child"}

ENTITLEMENT_TEXT = {
    "REBOOK_NO_FEE": "Rebooking at no extra cost",
    "MEAL_VOUCHER": "Meal voucher",
    "CASH_COMPENSATION": "Cash compensation (subject to approval)",
    "PRIORITY_HANDLING": "Priority handling",
}

CONFLICT_TEXT = {
    "HUMAN_APPROVAL_REQUIRED": "an agent must approve this change first",
    "OPTION_NOT_ELIGIBLE": "this option is no longer eligible",
}


# ---------------------------------------------------------------- input
def normalize_booking_id(raw: str | None) -> tuple[str | None, str | None]:
    """Return (booking_id, error). Rejects empty input or unexpected characters."""
    value = (raw or "").strip().upper()
    if not value:
        return None, "Enter your booking code."
    if not BOOKING_ID_RE.match(value):
        return None, "The booking code must be 5 to 8 letters or digits (e.g. ABC123)."
    return value, None


def make_idempotency_key(booking_id: str, option_id: str) -> str:
    """One key per action attempt. The UI stores it and reuses it if the user retries."""
    return f"{booking_id}-{option_id}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- booking
def _pick(d: dict, keys: tuple[str, ...]) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def safe_trip(trip: dict | None) -> dict:
    """Copy only the allowed booking fields (least privilege)."""
    trip = trip or {}
    passengers = []
    for p in trip.get("passengers") or []:
        clean = _pick(p, PASSENGER_FIELDS)
        clean["type_text"] = PASSENGER_TYPE_TEXT.get(clean.get("type", ""), clean.get("type", "—"))
        passengers.append(clean)
    meta = trip.get("_meta") or {}
    return {
        "booking_id": trip.get("booking_id"),
        "passengers": passengers,
        "segments": [_pick(s, SEGMENT_FIELDS) for s in trip.get("segments") or []],
        "completeness": trip.get("completeness") or meta.get("completeness"),
        "missing_fields": trip.get("missing_fields") or meta.get("missing_fields") or [],
        "has_minor": any(p.get("type") == "CHILD" for p in trip.get("passengers") or []),
    }


# ---------------------------------------------------------------- decision
def _option_label(opt: dict) -> str:
    parts = [opt.get("type"), opt.get("flight_number"),
             (f"{opt.get('origin')}→{opt.get('destination')}" if opt.get("origin") else None),
             opt.get("date"), opt.get("departure")]
    return " · ".join(str(p) for p in parts if p)


def _normalize_options(decision: dict) -> tuple[dict | None, list[dict], list[dict]]:
    """Accept 'recommended_option' (dict or id) and 'options'/'discarded_options' when present."""
    candidates = decision.get("candidate_options") or []
    options = candidates or decision.get("options") or decision.get("eligible_options") or []
    rec = decision.get("recommended_option")
    if rec is None and candidates:
        rec = candidates[0]   # the backend ranks candidates; the first one is the best
    if isinstance(rec, str):
        rec = next((o for o in options if o.get("option_id") == rec), {"option_id": rec})
    if rec is None:
        rec = next((o for o in options if o.get("recommended") or o.get("status") == "RECOMMENDED"), None)

    discarded = list(decision.get("discarded_options") or [])
    rec_id = rec.get("option_id") if rec else None
    alternatives = []
    for o in options:
        if o.get("option_id") == rec_id or o.get("status") == "RECOMMENDED":
            continue
        if candidates:
            alternatives.append({**o, "label": _option_label(o)})   # still valid, just ranked lower
        elif o not in discarded:
            discarded.append(o)

    if rec:
        rec = {**rec, "label": _option_label(rec)}
    discarded = [{**o, "label": _option_label(o),
                  "reason": o.get("reason") or o.get("discard_reason")
                  or "; ".join(o.get("reasons") or []) or "Not recommended"} for o in discarded]
    return rec, discarded, alternatives


def _trace_rows(trace: Any) -> list[str]:
    """Render decision_trace (list of strings or dicts) as readable lines, whatever its shape."""
    if isinstance(trace, dict):
        trace = trace.get("steps") or [f"{k}: {v}" for k, v in trace.items()]
    rows = []
    for step in trace or []:
        if isinstance(step, dict):
            name = step.get("stage") or step.get("step") or step.get("name") or ""
            if step.get("rule"):
                name = f"{name} [{step['rule']}]" if name else f"[{step['rule']}]"
            body = step.get("result") or step.get("detail") or step.get("description") or {
                k: v for k, v in step.items() if k not in ("stage", "step", "name", "rule")}
            rows.append(f"{name}: {body}" if name else str(body))
        else:
            rows.append(str(step))
    return rows


def decision_view(decision: dict) -> dict:
    """Turn the backend Decision response into what the screen needs."""
    classification = decision.get("classification", "")
    level, headline = CLASSIFICATION_TEXT.get(
        classification, ("info", classification.replace("_", " ").capitalize() or "Analysis result"))

    degraded = set(decision.get("sources_degraded") or [])
    discarded_events = {d.get("event_id"): d.get("reason", "discarded")
                        for seg in decision.get("segments") or [] for d in seg.get("discarded") or []}
    evidence = []
    for e in decision.get("evidence") or []:
        detail = []
        if e.get("delay_minutes") is not None:
            detail.append(f"delay {e['delay_minutes']} min")
        if e.get("new_departure"):
            detail.append(f"new departure {e['new_departure']}")
        if e.get("status"):
            detail.append(f"status {e['status']}")
        if e.get("gate"):
            detail.append(f"gate {e['gate']}")
        evidence.append({
            "Event": e.get("event_id", "—"),
            "Segment": e.get("segment_id", "—"),
            "Type": e.get("type", "—"),
            "Detail": ", ".join(detail) or "—",
            "Source": e.get("source", "—") + (" (degraded)" if e.get("source") in degraded else ""),
            "Used": "No: " + discarded_events[e.get("event_id")] if e.get("event_id") in discarded_events else "Yes",
            "Recorded at": e.get("recorded_at", "—"),
        })

    recommended, discarded, alternatives = _normalize_options(decision)
    missed = decision.get("missed_connections") or []
    message = decision.get("passenger_message") or {}
    rules = []
    for r in decision.get("applied_rules") or []:
        if isinstance(r, dict):
            approval = " (needs human approval)" if r.get("requires_human_approval") else ""
            rules.append(f"{r.get('rule_id', '?')} → {r.get('entitlement', '?')}{approval}")
        else:
            rules.append(str(r))
    return {
        "booking_id": decision.get("booking_id"),
        "level": level,
        "headline": headline,
        # Only show the backend message if it passed validation (notify_passenger requires policy_ref).
        "summary": decision.get("summary") or (message.get("text") if message.get("validated", True) else None),
        "missed_connection": bool(decision.get("missed_connection") or missed),
        "missed_connections": missed,
        "action_level": decision.get("action_level"),
        "human_review_reasons": list(decision.get("human_review_reasons") or []),
        "entitlements": [ENTITLEMENT_TEXT.get(e, e.replace("_", " ").capitalize())
                         for e in decision.get("entitlements") or []],
        "alternatives": alternatives,
        "recommendation": decision.get("recommendation") or "",
        "policy_ref": decision.get("policy_ref"),
        "applied_rules": rules,
        "requires_human_review": bool(decision.get("requires_human_review", True)
                                      or decision.get("escalate")
                                      or classification in HUMAN_CLASSIFICATIONS),
        "decision_trace": _trace_rows(decision.get("decision_trace")),
        "can_auto_rebook": bool(decision.get("can_auto_rebook", False)),
        "warnings": list(decision.get("warnings") or []),
        "evidence": evidence,
        "recommended_option": recommended,
        "discarded_options": discarded,
        "analyzed_at": decision.get("analyzed_at"),
    }


def rebook_permission(view: dict) -> tuple[bool, str]:
    """The frontend enables rebooking only when the backend explicitly authorizes it."""
    if not view.get("recommended_option"):
        return False, "There is no verified option to offer you yet."
    if not view.get("policy_ref") and not view["recommended_option"].get("policy_ref"):
        return False, "This option is not backed by a policy."
    if view.get("requires_human_review"):
        reasons = view.get("human_review_reasons") or []
        return False, "An agent must approve this change before it is made" + (
            f" ({'; '.join(reasons)})." if reasons else ".")
    # D-005: AUTOMATIC_WITH_CONFIRMATION = the passenger may request it after confirming.
    if view.get("can_auto_rebook") or view.get("action_level") == "AUTOMATIC_WITH_CONFIRMATION":
        return True, ""
    return False, "Rebooking is not available for this trip."


# ---------------------------------------------------------------- actions
def action_feedback(result: Any, action: str) -> tuple[str, str]:
    """(level, message) to show after an action. Never suggests a blind retry."""
    data = result.data or {}
    if result.ok:
        if action == "rebook":
            rid = data.get("request_id", "—")
            status = data.get("status", "registered")
            exp = f" Expires: {data['expires_at']}." if data.get("expires_at") else ""
            return "success", f"Rebooking request {rid} created (status: {status}).{exp}"
        cid = data.get("case_id", "—")
        sla = f" Expected response time: {data['sla_minutes']} min." if data.get("sla_minutes") else ""
        return "success", f"Case {cid} created. A member of our team will review your trip.{sla}"

    kind = result.kind
    if kind == "duplicate":
        rid = result.extra.get("request_id", "")
        return "info", f"This request was already registered{f' ({rid})' if rid else ''}. No new request was created."
    if kind == "conflict":
        reason = CONFLICT_TEXT.get(result.message, result.message or "verification required")
        return "warning", f"This action is not allowed yet: {reason}."
    if kind == "indeterminate":
        return "warning", ("We could not confirm whether your request went through (the system timed out). "
                           "Do not repeat it: an agent will verify its status.")
    if kind == "invalid":
        return "error", f"The system rejected the request: {result.message or 'incomplete data'}."
    if kind in ("not_found", "not_implemented"):
        return "info", "This action is not available in the system yet."
    if kind == "unavailable":
        return "error", "We could not reach the system. Please try again in a few minutes."
    return "error", f"Unexpected system error ({result.status})."
