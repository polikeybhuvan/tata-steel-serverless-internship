"""Publish an SNS email notification for S3 object-created events."""
import logging
import os
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = (
    os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)
sns = boto3.client("sns", region_name=AWS_REGION)


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        raise ValueError("The event did not contain any S3 records.")

    topic_arn = os.getenv("SNS_TOPIC_ARN", "").strip()
    if not topic_arn:
        raise RuntimeError("Set the SNS_TOPIC_ARN Lambda environment variable.")

    results = []
    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        file_key = unquote_plus(record["s3"]["object"]["key"])
        subject = f"AWS Alert: {file_key.rsplit('/', 1)[-1]} uploaded"[:100]
        message = (
            "A new file has been detected.\n\n"
            f"File: {file_key}\n"
            f"Bucket: {bucket}\n"
            "Event: ObjectCreated"
        )

        try:
            response = sns.publish(
                TopicArn=topic_arn,
                Message=message,
                Subject=subject,
            )
        except Exception:
            # Log the failure for operators; do not turn a failed publish into success.
            logger.exception("SNS publish failed for bucket %s", bucket)
            raise

        results.append({
            "bucket": bucket,
            "key": file_key,
            "messageId": response.get("MessageId"),
        })

    return {"statusCode": 200, "body": "Notification sent", "results": results}
