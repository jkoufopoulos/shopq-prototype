"""MailQ Production System"""

from __future__ import annotations

__version__ = "0.1.0"


def __getattr__(name: str):
    """
    Lazy imports to avoid loading heavy dependencies when only importing lightweight modules.
    """
    if name == "MemoryClassifier":
        from mailq.classification.memory_classifier import MemoryClassifier

        return MemoryClassifier
    if name == "RulesEngine":
        from mailq.classification.rules_engine import RulesEngine

        return RulesEngine
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["RulesEngine", "MemoryClassifier"]
