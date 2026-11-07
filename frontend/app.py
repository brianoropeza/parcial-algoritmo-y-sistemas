"""Disruption Companion — frontend (Streamlit).

Only presents what the backend decides. Run:  streamlit run app.py
Environment variable: BACKEND_URL (default http://localhost:8000).
"""
import streamlit as st

from api_client import BackendClient, backend_url
from presenter import (action_feedback, decision_view, make_idempotency_key,
                       normalize_booking_id, rebook_permission, safe_trip)

st.set_page_config(page_title="Nubara · Disruption Companion", page_icon="✈️", layout="centered")


@st.cache_resource
def get_client() -> BackendClient:
    return BackendClient()


def show(level: str, text: str) -> None:
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}.get(level, st.info)(text)


client = get_client()
state = st.session_state
state.setdefault("booking_id", None)
state.setdefault("trip", None)
state.setdefault("decision", None)
state.setdefault("idempotency_keys", {})   # (booking, option) -> reusable key
state.setdefault("action_results", {})     # action -> (level, message)

st.title("✈️ Nubara Airlines")
st.caption("Find out what happened to your trip and what your next step is.")

# ------------------------------------------------------------- 1. Look up
with st.form("lookup"):
    raw = st.text_input("Booking code", placeholder="ABC123", max_chars=12)
    submitted = st.form_submit_button("Check my trip", type="primary")

if submitted:
    booking_id, error = normalize_booking_id(raw)
    state.trip = state.decision = None
    state.action_results = {}
    if error:
        st.error(error)
    else:
        with st.spinner("Checking your trip…"):
            trip_res = client.get_trip(booking_id)
            dec_res = client.analyze(booking_id) if trip_res.ok else None
        if trip_res.kind == "not_found":
            st.error("We could not find a booking with that code.")
        elif trip_res.kind == "unavailable":
            st.error(f"We could not reach the system ({backend_url()}). Please try again in a few minutes.")
        elif not trip_res.ok:
            st.error(f"The system returned an error ({trip_res.status}).")
        elif not dec_res.ok:
            state.booking_id, state.trip = booking_id, safe_trip(trip_res.data)
            st.error("We found your booking but could not analyze it. Please try again later.")
        else:
            state.booking_id = booking_id
            state.trip = safe_trip(trip_res.data)
            state.decision = decision_view(dec_res.data)

trip, view = state.trip, state.decision

# ------------------------------------------------------------- 2. Your trip
if trip:
    st.subheader(f"Your trip · {trip['booking_id']}")
    st.write("**Passengers:** " + ", ".join(
        f"{p.get('name', '—')} ({p['type_text']}{', age ' + str(p['age']) if p.get('age') else ''})"
        for p in trip["passengers"]))
    if trip["segments"]:
        st.dataframe(
            [{"Flight": s.get("flight_number"), "Route": f"{s.get('origin')} → {s.get('destination')}",
              "Date": s.get("date", "—"), "Departure": s.get("scheduled_departure", "—"),
              "Arrival": s.get("scheduled_arrival", "—")} for s in trip["segments"]],
            hide_index=True, use_container_width=True)
    if trip["completeness"] == "PARTIAL":
        st.caption("ℹ️ Some of your booking information is not available yet"
                   + (f" ({', '.join(trip['missing_fields'])})." if trip["missing_fields"] else "."))

# ------------------------------------------------------------- 3. What happened
if view:
    st.subheader("What happened?")
    show(view["level"], view["headline"])
    if view["summary"]:
        st.write(view["summary"])
    if view["missed_connection"]:
        st.error("With this delay you will not make your connecting flight.")
        for m in view["missed_connections"]:
            st.write(f"- Segment {m.get('from_segment')} arrives around **{m.get('estimated_arrival')}**, "
                     f"after segment {m.get('to_segment')} departs at **{m.get('next_departure')}**.")
    for w in view["warnings"]:
        st.warning(w)

    with st.expander("See the information this is based on"):
        st.dataframe(view["evidence"], hide_index=True, use_container_width=True)
        if view["analyzed_at"]:
            st.caption(f"Analyzed at: {view['analyzed_at']}")

    if view["decision_trace"]:
        with st.expander("How this decision was made"):
            for i, line in enumerate(view["decision_trace"], 1):
                st.write(f"{i}. {line}")

    # --------------------------------------------------------- 4. What to do
    st.subheader("What can you do?")
    if view["recommendation"]:
        st.write(view["recommendation"])
    rec = view["recommended_option"]
    if view["entitlements"]:
        st.write("**You are entitled to:** " + ", ".join(view["entitlements"]))
    if rec:
        st.success(f"**Recommended option:** {rec['label']}")
    for alt in view["alternatives"]:
        st.write(f"- Other valid option: {alt['label']}")
    if view["human_review_reasons"]:
        st.info("**An agent will review your case because:** " + "; ".join(view["human_review_reasons"]))
    policy = view["policy_ref"] or (rec or {}).get("policy_ref")
    if policy:
        st.caption(f"Backed by policy {policy}"
                   + (f" · rules: {'; '.join(view['applied_rules'])}" if view["applied_rules"] else ""))
    if view["discarded_options"]:
        with st.expander("Options that do not apply and why"):
            for o in view["discarded_options"]:
                st.write(f"- **{o['label'] or o.get('option_id')}** — {o['reason']}")

    can_rebook, why_not = rebook_permission(view)
    col1, col2 = st.columns(2)

    with col1:
        if can_rebook:
            confirm = st.checkbox(f"I confirm the change to {rec['label']}")
            if st.button("Request rebooking", disabled=not confirm, type="primary"):
                key_id = (state.booking_id, rec["option_id"])
                # Same key for the same attempt: a retry never creates a duplicate request.
                key = state.idempotency_keys.setdefault(key_id, make_idempotency_key(*key_id))
                with st.spinner("Sending request…"):
                    res = client.request_rebooking(state.booking_id, rec["option_id"], key)
                state.action_results["rebook"] = action_feedback(res, "rebook")
        else:
            st.button("Request rebooking", disabled=True, help=why_not)
            st.caption(why_not)

    with col2:
        if st.button("Talk to a person"):
            reason = "; ".join([view["headline"], *view["warnings"]])[:500]
            with st.spinner("Creating your case…"):
                res = client.create_human_case(state.booking_id, reason)
            state.action_results["human"] = action_feedback(res, "human")

    for level, msg in state.action_results.values():
        show(level, msg)

st.divider()
st.caption("We never show your ID document, email or phone number on this screen.")
