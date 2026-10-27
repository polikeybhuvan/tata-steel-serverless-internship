import importlib.util
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "02-TextToAudioConverter.py"
    spec = importlib.util.spec_from_file_location("text_to_audio", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def s3_event(key, bucket="input-bucket"):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


def test_s3_event_key_decoding_and_output_key():
    module = load_module()
    assert module.decode_s3_key("folder%2Fmy+file.txt") == "folder/my file.txt"
    assert module.output_audio_key("folder/my file.txt", "audio") == "audio/folder/my file.mp3"


def test_short_text_uses_sync_synthesis(monkeypatch):
    module = load_module()
    monkeypatch.setenv("OUTPUT_BUCKET", "output-bucket")
    monkeypatch.setenv("OUTPUT_PREFIX", "audio")
    module.s3 = MagicMock()
    module.polly = MagicMock()
    module.s3.get_object.return_value = {"Body": io.BytesIO(b"Hello from SPARK.")}
    module.polly.synthesize_speech.return_value = {"AudioStream": io.BytesIO(b"mp3-data")}

    result = module.lambda_handler(s3_event("notes%2Fhello.txt"), None)

    assert result["results"][0]["mode"] == "synchronous"
    assert result["results"][0]["outputKey"] == "audio/notes/hello.mp3"
    module.polly.synthesize_speech.assert_called_once()
    module.polly.start_speech_synthesis_task.assert_not_called()
    module.s3.put_object.assert_called_once_with(
        Bucket="output-bucket",
        Key="audio/notes/hello.mp3",
        Body=b"mp3-data",
        ContentType="audio/mpeg",
    )


def test_long_text_uses_async_task(monkeypatch):
    module = load_module()
    monkeypatch.setenv("OUTPUT_BUCKET", "output-bucket")
    monkeypatch.setenv("OUTPUT_PREFIX", "audio")
    module.s3 = MagicMock()
    module.polly = MagicMock()
    module.s3.get_object.return_value = {"Body": io.BytesIO(("x" * 3001).encode())}
    module.polly.start_speech_synthesis_task.return_value = {
        "SynthesisTask": {"TaskId": "task-123"}
    }

    result = module.lambda_handler(s3_event("long.txt"), None)

    assert result["results"][0]["mode"] == "asynchronous"
    assert result["results"][0]["taskId"] == "task-123"
    assert result["results"][0]["outputPrefix"] == "audio/long/"
    module.polly.synthesize_speech.assert_not_called()
    module.polly.start_speech_synthesis_task.assert_called_once()


def test_non_text_upload_is_skipped(monkeypatch):
    module = load_module()
    monkeypatch.setenv("OUTPUT_BUCKET", "output-bucket")
    module.s3 = MagicMock()
    module.polly = MagicMock()

    result = module.lambda_handler(s3_event("photo.png"), None)

    assert result["results"][0]["status"] == "skipped"
    module.s3.get_object.assert_not_called()


def test_output_bucket_is_required(monkeypatch):
    module = load_module()
    monkeypatch.delenv("OUTPUT_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="OUTPUT_BUCKET"):
        module.lambda_handler(s3_event("hello.txt"), None)
