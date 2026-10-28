# IRIS-SIG-50 - EU Tenders Electronic Daily (TED) Infrastructure API Harvester

Transcription of the candidate assignment (summary of the PDF).

- Source / endpoint in brief: https://ted.europa.eu/api/v2.0/notices/search
- Integration pattern: B (REST API)
- Destination: iris_staging.signal_ingest (PostgreSQL 16 / PostGIS 3.4)
- Objective: capture public procurement notices above EU thresholds for grid cabling, transformers and public data centres.

## Scope
- Identify the public source, confirm its current format, implement the ingestion pattern.
- Preserve source identifiers, titles, publication dates, source URLs, geographic context.
- Normalise for PostGIS and load idempotently.
- Resolve locations to EPSG:25832 points where possible; document ambiguous/unresolved ones.
- Handle pagination, network failures, duplicates, malformed data, empty responses.

## Submit
- Python implementation + configuration instructions (no credentials in code).
- README: source, mapping assumptions, how to run, known limitations.
- Automated tests with fixtures/mocks incl. re-run/duplicate behaviour.
- Sample output, validation queries, concise error/quality report.

## Acceptance
- Signal type and domain filtering match the objective.
- Valid, traceable staging records; no duplicates on re-run.
- Errors and missing fields visible; invalid coordinates never silently accepted.
- Maintainable, configurable, demonstrable without production access.

## Candidate notes
Use only lawful access. If the endpoint in the brief is obsolete, document it and provide a tested fixture-based implementation and a justified alternative. Verify access and publication dates rather than assuming.
