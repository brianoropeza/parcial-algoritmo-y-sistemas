# Design

FastAPI exposes a versioned REST contract. A deterministic decision service consumes booking, events, options and versioned policy adapters. The first slice implements booking and events, and refuses consequential actions pending validated policies. Contradictory or degraded operational sources are preserved as evidence; the system does not silently choose the newest timestamp as authoritative. The frontend consumes only contract-defined fields. No passenger email or phone is returned in the first slice.
