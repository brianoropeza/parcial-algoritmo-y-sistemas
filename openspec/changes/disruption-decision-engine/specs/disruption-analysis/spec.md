# Disruption analysis specification

## ADDED Requirements

### Requirement: Traceable analysis
The system SHALL return the booking identifier, decision, source events, warnings and human-review flag.

#### Scenario: Contradictory operational evidence
- **WHEN** booking ABC123 is analyzed
- **THEN** the result retains both the OPS_CORE delay and LEGACY_MIRROR on-time event
- **AND** indicates human review is required
- **AND** disallows automatic rebooking

### Requirement: Unknown booking
The system SHALL return HTTP 404 when the requested booking does not exist.

#### Scenario: Missing booking
- **WHEN** a nonexistent booking identifier is requested
- **THEN** the API returns HTTP 404

### Requirement: High-impact action guard
The system SHALL prevent rebooking without verified eligibility and approval.

#### Scenario: Unverified rebooking
- **WHEN** an unvalidated rebooking request is received
- **THEN** the API rejects it with HTTP 409

### Requirement: Event normalization by segment
The system SHALL group operational events by the booking's segments, ordered by `recorded_at`, keeping events from degraded sources as evidence and reporting events from foreign segments as ignored.

#### Scenario: ABC123 events grouped
- **WHEN** the events of booking ABC123 are normalized
- **THEN** segment S1 contains E-1012, E-1001 and E-1007 in that order
- **AND** segment S2 contains E-2003

#### Scenario: Event from a foreign segment
- **WHEN** an event references a segment that is not part of the booking
- **THEN** it is not assigned to any booking segment
- **AND** it is reported as ignored

### Requirement: Minimum personal data exposure
The system SHALL expose only `passenger_id`, `name` and `type` for each passenger through the API.

#### Scenario: Booking query
- **WHEN** booking ABC123 is requested
- **THEN** the response does not contain email, phone, document_id, loyalty_tier or age
- **AND** missing fare fields are reported in `missing_fields` instead of being filled in
