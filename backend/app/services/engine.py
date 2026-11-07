"""Motor de decisiones determinista (D-002, etapas 2 a 5).

Etapa 2  reconcile_segment     D-003   O(n)
Etapa 3  connection_impact     D-004, D-008   O(s)
Etapa 4  evaluate_policy       D-005, D-007   O(r)
Etapa 5  filter_options        D-009   O(m log m)
Cada etapa agrega pasos a `trace` (D-001).
"""

from datetime import datetime, timedelta

SOURCE_TRUST = {"OPS_CORE": 3, "AIRPORT_FEED": 2, "LEGACY_MIRROR": 1}  # D-003
CONFIDENCE_RANK = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
AIRPORT_COUNTRY = {"SCL": "CL", "LIM": "PE", "MEX": "MX"}  # para la condición "international" de R2

# Estado operacional que afirma cada evento. GATE_CHANGE es informativo y no afirma estado.
def _claimed_state(event: dict) -> str | None:
    if event.get("type") == "DELAY":
        return "DELAYED"
    if event.get("type") == "CANCELLATION":
        return "CANCELLED"
    if event.get("type") == "STATUS":
        return {"ON_TIME": "ON_TIME", "SCHEDULED": "ON_TIME"}.get(event.get("status"), event.get("status"))
    return None


# ---------------- Etapa 2 ----------------
def reconcile_segment(segment_id: str, events: list[dict], degraded: list[str], trace: list) -> dict:
    claims = [e for e in events if _claimed_state(e) is not None]
    info = [e for e in events if _claimed_state(e) is None]
    trusted = [e for e in claims if e["source"] not in degraded]
    discarded = [{"event_id": e["event_id"], "reason": f"source {e['source']} is degraded"} for e in claims if e["source"] in degraded]

    # Por fuente, prevalece su registro más reciente; entre fuentes, la de mayor confianza (no el más reciente).
    latest_by_source: dict[str, dict] = {}
    for e in trusted:
        if e["source"] not in latest_by_source or e["recorded_at"] > latest_by_source[e["source"]]["recorded_at"]:
            latest_by_source[e["source"]] = e
    trusted_states = {_claimed_state(e) for e in latest_by_source.values()}
    all_states = {_claimed_state(e) for e in claims}

    prevailing = max(latest_by_source.values(), key=lambda e: SOURCE_TRUST.get(e["source"], 0), default=None)
    unresolved = len(trusted_states) > 1  # contradicción entre fuentes no degradadas -> humano
    result = {
        "segment_id": segment_id,
        "state": None if unresolved or prevailing is None else _claimed_state(prevailing),
        "prevailing_event": prevailing["event_id"] if prevailing and not unresolved else None,
        "delay_minutes": prevailing.get("delay_minutes") if prevailing and not unresolved else None,
        "conflict_detected": len(all_states) > 1,
        "unresolved_conflict": unresolved,
        "discarded": discarded,
        "informational": [e["event_id"] for e in info],
    }
    trace.append({"stage": "reconcile", "segment_id": segment_id, "rule": "D-003",
                  "detail": f"state={result['state']} prevailing={result['prevailing_event']} "
                            f"conflict={result['conflict_detected']} unresolved={unresolved} discarded={[d['event_id'] for d in discarded]}"})
    return result


# ---------------- Etapa 3 ----------------
def _local(date: str, hhmm: str) -> datetime:
    return datetime.strptime(f"{date} {hhmm}", "%Y-%m-%d %H:%M")


def connection_impact(segments: list[dict], reconciled: dict[str, dict], trace: list) -> dict:
    missed = []
    for prev, nxt in zip(segments, segments[1:]):
        delay = reconciled[prev["segment_id"]].get("delay_minutes") or 0
        arrival = _local(prev["date"], prev["scheduled_arrival"])
        if arrival < _local(prev["date"], prev["scheduled_departure"]):
            arrival += timedelta(days=1)
        estimated = arrival + timedelta(minutes=delay)  # D-008
        departure = _local(nxt["date"], nxt["scheduled_departure"])
        is_missed = estimated > departure  # D-004
        trace.append({"stage": "impact", "segment_id": prev["segment_id"], "rule": "D-004/D-008",
                      "detail": f"estimated_arrival={estimated:%Y-%m-%d %H:%M} next_departure={departure:%Y-%m-%d %H:%M} missed={is_missed}"})
        if is_missed:
            missed.append({"from_segment": prev["segment_id"], "to_segment": nxt["segment_id"],
                           "estimated_arrival": estimated.strftime("%Y-%m-%d %H:%M"),
                           "next_departure": departure.strftime("%Y-%m-%d %H:%M")})
    return {"missed_connections": missed}


# ---------------- Etapa 4 ----------------
def _eval_term(term: str, facts: dict) -> bool:
    parts = term.strip().split()
    if len(parts) == 1:
        return bool(facts.get(parts[0], False))
    name, op, raw = parts
    value = {"true": True, "false": False}.get(raw.lower(), None)
    if value is None:
        value = float(raw)
    left = facts.get(name)
    if left is None:
        return False  # dato ausente: la regla no se activa (no se inventa)
    return {">=": left >= value, ">": left > value, "<=": left <= value, "<": left < value, "==": left == value}[op]


def evaluate_condition(condition: str, facts: dict) -> bool:
    return all(_eval_term(t, facts) for t in condition.split(" AND "))


def evaluate_policy(policy: dict, facts: dict, trace: list) -> list[dict]:
    applied = []
    for rule in policy["rules"]:
        ok = evaluate_condition(rule["condition"], facts)
        trace.append({"stage": "policy", "rule": f"{policy['version']}/{rule['rule_id']}",
                      "detail": f"{rule['condition']} -> {ok}"})
        if ok:
            applied.append({"rule_id": rule["rule_id"], "entitlement": rule["entitlement"],
                            "requires_human_approval": rule["requires_human_approval"]})
    return applied


# ---------------- Etapa 5 ----------------
def filter_options(options: list[dict], passengers: int, entitlements: set[str], valid_policies: set[str], trace: list):
    candidates, discarded = [], []
    for o in options:
        reasons = []
        if o.get("type") == "REBOOK" and o.get("seats_available", 0) < passengers:
            reasons.append(f"seats_available {o.get('seats_available')} < passengers {passengers}")
        if "REBOOK_NO_FEE" in entitlements and (o.get("fare_difference") or 0) > 0:
            reasons.append("fare_difference > 0 contradicts REBOOK_NO_FEE")
        if o.get("policy_ref") not in valid_policies:
            reasons.append(f"policy {o.get('policy_ref')} not retrieved/verified")
        if o.get("confidence") == "LOW":
            reasons.append("confidence LOW")
        (discarded.append({"option_id": o["option_id"], "reasons": reasons}) if reasons else candidates.append(o))
    candidates.sort(key=lambda o: (-CONFIDENCE_RANK.get(o.get("confidence"), 0), o.get("fare_difference") or 0,
                                   o.get("date", ""), o.get("departure", "")))
    trace.append({"stage": "options", "rule": "D-009",
                  "detail": f"candidates={[o['option_id'] for o in candidates]} discarded={[d['option_id'] for d in discarded]}"})
    return candidates, discarded


# ---------------- Orquestación ----------------
def analyze_trip(trip: dict, normalized, options_resp: dict, policy: dict | None) -> dict:
    trace: list = []
    segments = trip["segments"]
    reconciled = {s["segment_id"]: reconcile_segment(s["segment_id"], normalized.by_segment[s["segment_id"]],
                                                     normalized.degraded_sources, trace) for s in segments}
    impact = connection_impact(segments, reconciled, trace)

    delays = [r["delay_minutes"] for r in reconciled.values() if r["delay_minutes"]]
    facts = {
        "delay_minutes": max(delays) if delays else 0,
        "international": any(AIRPORT_COUNTRY.get(s["origin"]) != AIRPORT_COUNTRY.get(s["destination"]) for s in segments),
        "missed_connection": bool(impact["missed_connections"]),
        "compensation_requested": False,
        "group_includes_minor": any(p.get("type") == "CHILD" for p in trip["passengers"]),
    }
    applied = evaluate_policy(policy, facts, trace) if policy else []
    entitlements = {a["entitlement"] for a in applied}

    candidates, discarded = filter_options(options_resp.get("options", []), len(trip["passengers"]), entitlements,
                                           {policy["version"]} if policy else set(), trace)

    unresolved = [r["segment_id"] for r in reconciled.values() if r["unresolved_conflict"]]
    relevant = bool(impact["missed_connections"]) or any(r["state"] in ("DELAYED", "CANCELLED") for r in reconciled.values())
    human_reasons = []
    if unresolved:
        human_reasons.append(f"unresolved source conflict on {unresolved}")
    human_reasons += [f"{a['rule_id']} {a['entitlement']} requires human approval" for a in applied if a["requires_human_approval"]]
    if relevant and policy is None:
        human_reasons.append("no verified policy for scenario")

    # D-005 / D-007
    if human_reasons:
        level = "HUMAN"
    elif relevant and candidates:
        level = "AUTOMATIC_WITH_CONFIRMATION"
    else:
        level = "AUTOMATIC"
    trace.append({"stage": "classify", "rule": "D-005/D-007", "detail": f"relevant={relevant} level={level} reasons={human_reasons}"})

    return {
        "relevant_modification": relevant,
        "action_level": level,
        "human_review_reasons": human_reasons,
        "segments": list(reconciled.values()),
        "missed_connections": impact["missed_connections"],
        "applied_rules": applied,
        "entitlements": sorted(entitlements),
        "candidate_options": candidates,
        "discarded_options": discarded,
        "facts": facts,
        "decision_trace": trace,
    }


def passenger_message(booking_id: str, result: dict, policy_ref: str | None) -> dict:
    """Mensaje solo con hechos validados por el motor. Sin datos personales."""
    parts = []
    for m in result["missed_connections"]:
        parts.append(f"Your flight segment {m['from_segment']} is delayed; estimated arrival {m['estimated_arrival']} "
                     f"is after your connection departure {m['next_departure']}.")
    if result["candidate_options"]:
        o = result["candidate_options"][0]
        parts.append(f"Candidate alternative (not yet confirmed): flight {o['flight_number']} on {o['date']} at {o['departure']}.")
    if result["action_level"] == "HUMAN":
        parts.append("An agent will review your case before any change to your booking.")
    return {"booking_id": booking_id, "policy_ref": policy_ref, "text": " ".join(parts)}
