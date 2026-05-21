"""Pull-based git fetch worker (ADR-007).

In Phase 1 this module polls each RegisteredRepo, clones / fetches it,
parses `results/` directories, and inserts Submission rows.
"""
