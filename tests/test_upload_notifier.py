import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "03-ImageUploadNotifier.py"
    spec = importlib.util.spec_from_file_location("upload_notifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def s3_event(key):
    return {"Records": [{"s3": {"bucket": {"name": "uploads"}, "object": {"key": key}}}]}


def test_notifier_decodes_key_and_publishes(monkeypatch):
    module = load_module()
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:alerts")
    module.sns = MagicMock()
    module.sns.publish.return_value = {"MessageId": "message-123"}

    result = module.lambda_handler(s3_event("reports%2Fmy+file.png"), None)

    assert result["results"][0]["key"] == "reports/my file.png"
    assert result["results"][0]["messageId"] == "message-123"
    assert module.sns.publish.call_args.kwargs["Subject"] == "AWS Alert: my file.png uploaded"


def test_topic_arn_is_required(monkeypatch):
    module = load_module()
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    with pytest.raises(RuntimeError, match="SNS_TOPIC_ARN"):
        module.lambda_handler(s3_event("file.txt"), None)
