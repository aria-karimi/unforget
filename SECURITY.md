# Security Policy

## Local-First Context
`unforget` collects context on the local machine to answer shell-assistance requests. This can include local file names, selected environment variables, and recent terminal output. Context processing occurs locally, and outbound transmission is limited to the LLM provider configured by the user.

## Secret Scrubbing
Before context is sent to an LLM provider, `unforget` applies regex-based redaction to environment variables and stdout/history text. This includes key/value-style matches for sensitive keys such as `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `AUTH`, and related credential identifiers, plus pattern-based detection for common secret formats.

Redaction replaces detected sensitive values with `[REDACTED]`.

## Data Residency and Storage
`unforget` does not operate a central service and does not provide a vendor-hosted backend for user prompts or command history. Data remains local except for the user-directed request sent to the configured LLM provider. Users should review their provider's data handling and residency policies.

## AI Transparency and Compliance
`unforget` returns AI-generated suggestions and does not guarantee deterministic or risk-free output. Users must review and validate every suggestion before execution.

The project aligns with:
- **NIST AI RMF** principles for transparency, governance, and risk management.
- **EU AI Act Article 50** transparency expectations by clearly identifying that outputs are AI-generated assistance and require user verification.

## Reporting Security Issues
Please report vulnerabilities privately to project maintainers before public disclosure. Include reproduction steps, impact assessment, and any affected versions.
