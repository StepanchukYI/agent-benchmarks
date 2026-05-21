# Security Policy

## Reporting a vulnerability

Email the maintainer: **Evgeniy Stepanchuk** (`StepanchukYI` on GitHub). Do not open a public issue for security reports.

Expected response time: best effort within 7 days. This is a friends-first project; no SLA.

## What counts as a security issue

- Credential exposure in published artifacts (results repos, trajectory dumps).
- Sandbox escape (Docker isolation bypass) during task execution.
- Submission re-scoring bypass enabling fraudulent `verified` trust tier.
- Privacy boundary violations (LSN-006): personal vault content, real account names, home-directory paths in committed data.
- OAuth/session handling flaws in `ab-server`.

## Privacy scanner

CI runs a privacy scanner on every PR. If you discover a class of leak the scanner misses, file a security report — do not push a public reproducer.

## Supported versions

Only the `main` branch is supported in v1. Once we tag a release line, this section will be updated.
