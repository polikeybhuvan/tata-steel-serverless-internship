import json
from pathlib import Path


def test_bucket_policy_uses_a_statement_list_and_visible_placeholders():
    policy_path = Path(__file__).resolve().parents[1] / "01-bucket-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert isinstance(policy["Statement"], list)
    statement = policy["Statement"][0]
    assert statement["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert statement["Action"] == "s3:GetObject"
    assert "YOUR_BUCKET_NAME" in statement["Resource"]
    assert "YOUR_DISTRIBUTION_ID" in statement["Condition"]["StringEquals"]["AWS:SourceArn"]
