"""Pluggable judges for agent-assisted audit classification.

The library stays model-agnostic: ``corroborate.audit.classify_near_duplicates``
takes any callable with the ``DuplicateJudge`` signature. Submodules here
provide reference implementations for specific LLM backends. Bring your own
callable if you prefer a different model, provider, or a pure-heuristic judge.
"""
