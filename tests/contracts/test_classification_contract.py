from pydantic import ValidationError

from shopq.storage.classification import ClassificationContract

BASE = {
    "message_id": "msg-1",
    "type": "notification",
    "importance": "critical",
    "importance_conf": 0.95,  # Required field for importance confidence
    "confidence": 0.95,
    "type_conf": 0.95,
    "attention": "action_required",
    "attention_conf": 0.9,
    "relationship": "from_unknown",
    "relationship_conf": 0.7,
    "decider": "gemini",
    "reason": "fraud alert detected",
    "propose_rule": {"should_propose": "False", "pattern": "", "kind": "", "support_count": "0"},
    "model_name": "gemini-2.0-flash",
    "model_version": "2.0",
    "prompt_version": "v1",
}


def test_classification_contract_accepts_valid():
    contract = ClassificationContract(**BASE)
    assert contract.type == "notification"
    assert contract.importance == "critical"


def test_classification_contract_rejects_bad_importance():
    data = {**BASE, "importance": "urgent"}
    try:
        ClassificationContract(**data)
        raise AssertionError("Expected ValidationError")
    except ValidationError as exc:
        assert "importance" in str(exc)


def test_classification_contract_requires_reason_length():
    data = {**BASE, "reason": "ok"}
    try:
        ClassificationContract(**data)
        raise AssertionError("Expected ValidationError")
    except ValidationError as exc:
        assert "reason" in str(exc)
