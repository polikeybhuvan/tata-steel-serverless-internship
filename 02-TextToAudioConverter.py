"""Convert uploaded text files into MP3 audio with Amazon Polly.

Short inputs use synchronous synthesis. Longer inputs are submitted as
asynchronous Polly tasks, whose output is written directly to the configured
S3 output bucket.
"""
import logging
import os
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = (
    os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)
s3 = boto3.client("s3", region_name=AWS_REGION)
polly = boto3.client("polly", region_name=AWS_REGION)

SYNC_BILLED_CHARACTER_LIMIT = 3000
ASYNC_BILLED_CHARACTER_LIMIT = 100000


def decode_s3_key(encoded_key):
    """Decode the URL-encoded object key carried in an S3 event."""
    return unquote_plus(encoded_key)


def output_audio_key(text_key, output_prefix=""):
    """Return the target MP3 key for short, synchronous synthesis."""
    stem = str(PurePosixPath(text_key).with_suffix(""))
    filename = f"{stem}.mp3"
    prefix = output_prefix.strip("/")
    return posixpath.join(prefix, filename) if prefix else filename


def safe_polly_prefix(prefix):
    """Keep the async Polly output prefix within the API's allowed character set."""
    safe = re.sub(r"[^0-9a-zA-Z/!_.*'():;$@=+?,&-]", "_", prefix)
    return safe.strip("/") + "/"


def process_record(record, output_bucket, output_prefix, voice_id, engine):
    bucket = record["s3"]["bucket"]["name"]
    text_key = decode_s3_key(record["s3"]["object"]["key"])

    if not text_key.lower().endswith(".txt"):
        logger.info("Skipping non-text object: s3://%s/%s", bucket, text_key)
        return {"status": "skipped", "inputKey": text_key, "reason": "not a .txt file"}

    response = s3.get_object(Bucket=bucket, Key=text_key)
    body = response["Body"]
    try:
        text_content = body.read().decode("utf-8-sig").strip()
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()

    if not text_content:
        raise ValueError(f"The text file is empty: {text_key}")

    if len(text_content) > ASYNC_BILLED_CHARACTER_LIMIT:
        raise ValueError(
            "Input exceeds the configured safe limit of "
            f"{ASYNC_BILLED_CHARACTER_LIMIT} characters."
        )

    desired_key = output_audio_key(text_key, output_prefix)
    common_params = {
        "Text": text_content,
        "OutputFormat": "mp3",
        "VoiceId": voice_id,
        "Engine": engine,
    }

    if len(text_content) <= SYNC_BILLED_CHARACTER_LIMIT:
        synthesis = polly.synthesize_speech(**common_params)
        audio_stream = synthesis.get("AudioStream")
        if audio_stream is None:
            raise RuntimeError("Amazon Polly returned no audio stream.")

        try:
            audio_bytes = audio_stream.read()
        finally:
            close = getattr(audio_stream, "close", None)
            if callable(close):
                close()

        s3.put_object(
            Bucket=output_bucket,
            Key=desired_key,
            Body=audio_bytes,
            ContentType="audio/mpeg",
        )
        logger.info(
            "Completed synchronous text-to-audio conversion for %s",
            text_key,
        )
        return {
            "status": "completed",
            "mode": "synchronous",
            "inputKey": text_key,
            "outputKey": desired_key,
        }

    # StartSpeechSynthesisTask writes asynchronously into S3. Polly names the
    # generated file using its task ID; the prefix groups output by input file.
    async_prefix = safe_polly_prefix(f"{desired_key.rsplit('.', 1)[0]}/")
    task_response = polly.start_speech_synthesis_task(
        **common_params,
        OutputS3BucketName=output_bucket,
        OutputS3KeyPrefix=async_prefix,
    )
    task = task_response.get("SynthesisTask", {})
    task_id = task.get("TaskId")
    if not task_id:
        raise RuntimeError("Amazon Polly did not return a synthesis task ID.")

    logger.info(
        "Submitted asynchronous text-to-audio task %s for %s",
        task_id,
        text_key,
    )
    return {
        "status": "submitted",
        "mode": "asynchronous",
        "inputKey": text_key,
        "taskId": task_id,
        "outputBucket": output_bucket,
        "outputPrefix": async_prefix,
    }


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        raise ValueError("The event did not contain any S3 records.")

    output_bucket = os.getenv("OUTPUT_BUCKET")
    if not output_bucket:
        raise RuntimeError("Set the OUTPUT_BUCKET Lambda environment variable.")

    output_prefix = os.getenv("OUTPUT_PREFIX", "").strip("/")
    voice_id = os.getenv("POLLY_VOICE_ID", "Joanna")
    engine = os.getenv("POLLY_ENGINE", "standard")

    results = [
        process_record(record, output_bucket, output_prefix, voice_id, engine)
        for record in records
    ]
    return {
        "statusCode": 200,
        "results": results,
    }
