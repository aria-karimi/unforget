from unforget.core.scrubber import SecretScrubber


def test_scrub_mapping_redacts_sensitive_keys() -> None:
    scrubber = SecretScrubber()
    result = scrubber.scrub_mapping({"API_TOKEN": "abc", "PATH": "/usr/bin"})
    assert result["API_TOKEN"] == "[REDACTED]"
    assert result["PATH"] == "/usr/bin"


def test_scrub_text_redacts_key_value() -> None:
    scrubber = SecretScrubber()
    text = "password=my-secret and token:abc123"
    cleaned = scrubber.scrub_text(text)
    assert "password=[REDACTED]" in cleaned
    assert "token:[REDACTED]" in cleaned


def test_scrub_text_redacts_jwt_and_aws_key() -> None:
    scrubber = SecretScrubber()
    text = (
        "jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
        "aws=AKIAIOSFODNN7EXAMPLE"
    )
    cleaned = scrubber.scrub_text(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in cleaned
    assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
    assert "[REDACTED]" in cleaned


def test_scrub_text_redacts_private_key_block() -> None:
    scrubber = SecretScrubber()
    text = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
    cleaned = scrubber.scrub_text(text)
    assert cleaned == "[REDACTED]"
