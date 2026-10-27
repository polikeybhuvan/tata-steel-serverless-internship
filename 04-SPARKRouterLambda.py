"""SPARK: Amazon Lex V2 fulfillment router for selected AWS operations."""
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = (
    os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)
LOG_GROUP_NAME = os.getenv(
    "SPARK_LOG_GROUP",
    "/aws/lambda/SPARKRouterLambda",
)
MEMORY_TABLE_NAME = os.getenv("SPARK_MEMORY_TABLE", "SPARKMemory")
ALERTS_TOPIC_ARN = os.getenv("SPARK_ALERTS_TOPIC_ARN", "").strip()
DEFAULT_USER_ID = os.getenv("SPARK_DEFAULT_USER_ID", "Bhuvan")

s3 = boto3.client("s3", region_name=AWS_REGION)
logs = boto3.client("logs", region_name=AWS_REGION)
sns = boto3.client("sns", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(MEMORY_TABLE_NAME)


def get_slot_value(slots, name):
    """Return an interpreted Lex slot value or raise a readable validation error."""
    slot = slots.get(name) or {}
    value = (slot.get("value") or {}).get("interpretedValue")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Required slot '{name}' is missing.")
    return value.strip()


def get_user_id(event):
    """Use a configured session attribute to scope memory per user."""
    session_state = event.get("sessionState") or {}
    attributes = session_state.get("sessionAttributes") or {}
    return str(attributes.get("userId") or DEFAULT_USER_ID)


def handle_intent(intent, slots, event):
    if intent == "WelcomeIntent":
        return "Hello! SPARK is online. What would you like to do?"

    if intent == "CheckS3Status":
        bucket = get_slot_value(slots, "bucketName")
        s3.get_bucket_location(Bucket=bucket)
        return f"I could access bucket {bucket!r} successfully."

    if intent == "GetSystemLogs":
        streams_response = logs.describe_log_streams(
            logGroupName=LOG_GROUP_NAME,
            orderBy="LastEventTime",
            descending=True,
            limit=1,
        )
        streams = streams_response.get("logStreams", [])
        if not streams:
            return f"No log streams were found in {LOG_GROUP_NAME!r}."

        stream_name = streams[0]["logStreamName"]
        events_response = logs.get_log_events(
            logGroupName=LOG_GROUP_NAME,
            logStreamName=stream_name,
            limit=10,
            startFromHead=False,
        )
        events = events_response.get("events", [])
        if not events:
            return f"The latest log stream is {stream_name!r}, but it has no events."

        lines = [
            str(item.get("message", "")).strip()
            for item in events[-5:]
            if item.get("message")
        ]
        # Keep conversational responses bounded; full logs remain in CloudWatch.
        summary = "\n".join(lines)[-1800:]
        return f"Recent events from {stream_name}:\n{summary}"

    if intent == "RememberThis":
        key = get_slot_value(slots, "memoryKey")
        value = get_slot_value(slots, "memoryValue")
        table.put_item(Item={
            "userId": get_user_id(event),
            "infoKey": key,
            "infoValue": value,
        })
        return f"Saved the value under {key!r}."

    if intent == "RecallMemory":
        key = get_slot_value(slots, "memoryKey")
        response = table.get_item(Key={
            "userId": get_user_id(event),
            "infoKey": key,
        })
        item = response.get("Item")
        if not item:
            return f"I couldn't find a saved value for {key!r}."
        return f"The saved value for {key!r} is: {item.get('infoValue', '')}"

    if intent == "SendAlert":
        if not ALERTS_TOPIC_ARN:
            raise RuntimeError(
                "SPARK_ALERTS_TOPIC_ARN is not configured for this Lambda."
            )
        message = get_slot_value(slots, "alertMessage")
        # Keep user-controlled content within a predictable message size.
        message = message[:4000]
        sns.publish(
            TopicArn=ALERTS_TOPIC_ARN,
            Message=f"SPARK Alert: {message}",
            Subject="SPARK Dispatch",
        )
        return "The alert was submitted to Amazon SNS."

    return "I don't recognise that action yet. Try one of the configured SPARK commands."


def lambda_handler(event, context):
    session_state = event.get("sessionState") or {}
    intent_payload = session_state.get("intent") or {}
    intent_name = intent_payload.get("name") or "UnknownIntent"
    slots = intent_payload.get("slots") or {}

    try:
        message = handle_intent(intent_name, slots, event)
        intent_state = "Fulfilled"
    except Exception:
        # Keep service/SDK details in CloudWatch rather than exposing them to users.
        logger.exception("SPARK failed to fulfill intent %s", intent_name)
        message = (
            "I couldn't complete that action. Please check the Lambda logs "
            "or contact the administrator."
        )
        intent_state = "Failed"

    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": {
                "name": intent_name,
                "slots": slots,
                "state": intent_state,
            },
        },
        "messages": [{
            "contentType": "PlainText",
            "content": message,
        }],
    }
