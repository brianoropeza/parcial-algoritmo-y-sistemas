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
