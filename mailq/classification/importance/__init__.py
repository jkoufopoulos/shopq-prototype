"""Importance classification module.

NOTE: heuristics.py was removed 2025-11-30 - it was an experiment that:
- Was only used in evals, not production
- Had poor precision (48-82% on upgrade patterns)
- Duplicated guardrail logic already in importance_mapping/

Production importance flow: Gemini → Guardrails → Final importance
"""

__all__: list[str] = []
