import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "04-SPARKRouterLambda.py"
    spec = importlib.util.spec_from_file_location("spark_router", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.s3 = MagicMock()
    module.logs = MagicMock()
    module.sns = MagicMock()
    module.table = MagicMock()
    return module


def event(intent, slots=None, user_id="intern-test-user"):
    return {
        "sessionId": "session-123",
        "sessionState": {
            "sessionAttributes": {"userId": user_id},
            "intent": {"name": intent, "slots": slots or {}},
        },
    }


def slot(value):
    return {"value": {"interpretedValue": value}}


def test_welcome_intent_is_fulfilled():
    module = load_module()
    result = module.lambda_handler(event("WelcomeIntent"), None)
    assert result["sessionState"]["intent"]["state"] == "Fulfilled"
    assert "SPARK" in result["messages"][0]["content"]


def test_missing_slot_returns_failed_state_without_sdk_details():
    module = load_module()
    result = module.lambda_handler(event("CheckS3Status"), None)
    assert result["sessionState"]["intent"]["state"] == "Failed"
    assert "couldn't complete" in result["messages"][0]["content"]
    assert "Required slot" not in result["messages"][0]["content"]


def test_remember_and_recall_are_scoped_to_configured_user():
    module = load_module()
    remembered = module.lambda_handler(
        event("RememberThis", {"memoryKey": slot("project"), "memoryValue": slot("SPARK")}),
        None,
    )
    assert remembered["sessionState"]["intent"]["state"] == "Fulfilled"
    module.table.put_item.assert_called_once_with(
        Item={"userId": "intern-test-user", "infoKey": "project", "infoValue": "SPARK"}
    )

    module.table.get_item.return_value = {"Item": {"infoValue": "SPARK"}}
    recalled = module.lambda_handler(
        event("RecallMemory", {"memoryKey": slot("project")}),
        None,
    )
    assert recalled["messages"][0]["content"] == "The saved value for 'project' is: SPARK"
    module.table.get_item.assert_called_once_with(
        Key={"userId": "intern-test-user", "infoKey": "project"}
    )


def test_system_logs_returns_actual_log_events():
    module = load_module()
    module.logs.describe_log_streams.return_value = {
        "logStreams": [{"logStreamName": "latest-stream"}]
    }
    module.logs.get_log_events.return_value = {
        "events": [
            {"message": "first event"},
            {"message": "second event"},
        ]
    }

    result = module.lambda_handler(event("GetSystemLogs"), None)

    assert "first event" in result["messages"][0]["content"]
    assert "second event" in result["messages"][0]["content"]
    module.logs.get_log_events.assert_called_once()


def test_unknown_intent_uses_fallback():
    module = load_module()
    result = module.lambda_handler(event("UnknownIntent"), None)
    assert result["sessionState"]["intent"]["state"] == "Fulfilled"
    assert "don't recognise" in result["messages"][0]["content"]
