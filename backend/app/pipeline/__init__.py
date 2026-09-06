"""Core pipeline package: state machine, errors, progress, and stage contracts.

This package is the contract baseline for the pipeline rewrite (task C1).
The legacy pipeline in ``app/services`` / ``app/api/routes.py`` stays intact
until the orchestrator switch (C4); nothing here modifies legacy behavior.
"""
