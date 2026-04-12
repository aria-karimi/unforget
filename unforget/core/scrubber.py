from __future__ import annotations

import re
from typing import Pattern

SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(key|token|auth|secret|password|pwd|credential|private|client[_-]?secret)"
)
KEY_VALUE_PATTERN = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_\-\.]*)\s*(?P<sep>=|:)\s*(?P<value>[^\s]+)"
)


def _compile_patterns() -> list[Pattern[str]]:
    # Common secret formats from cloud providers, API tokens, and credentials.
    raw_patterns = [
        r"AKIA[0-9A-Z]{16}",  # AWS access key ID
        r"ASIA[0-9A-Z]{16}",  # AWS temporary access key ID
        r"(?i)aws(.{0,20})?(secret|access)?(.{0,20})?[=:]\s*[A-Za-z0-9/+]{40}",
        r"(?i)-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        r"gh[pousr]_[A-Za-z0-9_]{36,255}",  # GitHub tokens
        r"github_pat_[A-Za-z0-9_]{22,255}",
        r"glpat-[A-Za-z0-9\-_]{20,255}",  # GitLab personal token
        r"xox[baprs]-[A-Za-z0-9-]{10,255}",  # Slack token families
        r"AIza[0-9A-Za-z\-_]{35}",  # Google API key
        r"sk-(live|test)-[0-9A-Za-z]{16,255}",  # Stripe keys
        r"rk_(live|test)_[0-9A-Za-z]{16,255}",  # Stripe restricted keys
        r"SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}",  # SendGrid key
        r"npm_[A-Za-z0-9]{36}",  # npm token
        r"xoxc-[A-Za-z0-9-]{10,255}",  # Slack session-like tokens
        r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",  # Bearer auth values
        r"(?i)authorization:\s*basic\s+[A-Za-z0-9+/=]+",
        r"(?i)mongodb(\+srv)?:\/\/[^:\s]+:[^@\s]+@",
        r"(?i)postgres(ql)?:\/\/[^:\s]+:[^@\s]+@",
        r"(?i)mysql:\/\/[^:\s]+:[^@\s]+@",
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",  # JWT
        r"(?i)sk-ant-[A-Za-z0-9\-_=]{20,255}",  # Anthropic-like key prefix
        r"(?i)sk-[A-Za-z0-9]{20,255}",  # Generic sk- style API keys
    ]
    return [re.compile(pattern, re.MULTILINE) for pattern in raw_patterns]


CREDENTIAL_PATTERNS = _compile_patterns()


class SecretScrubber:
    def __init__(self, redacted_value: str = "[REDACTED]") -> None:
        self.redacted_value = redacted_value

    def _redact_key_values(self, text: str) -> str:
        def replacer(match: re.Match[str]) -> str:
            key = match.group("key")
            sep = match.group("sep")
            if SENSITIVE_KEY_PATTERN.search(key):
                return f"{key}{sep}{self.redacted_value}"
            return match.group(0)

        return KEY_VALUE_PATTERN.sub(replacer, text)

    def _redact_patterns(self, text: str) -> str:
        scrubbed = text
        for pattern in CREDENTIAL_PATTERNS:
            scrubbed = pattern.sub(self.redacted_value, scrubbed)
        return scrubbed

    def scrub_text(self, text: str) -> str:
        return self._redact_patterns(self._redact_key_values(text))

    def scrub_mapping(self, mapping: dict[str, str]) -> dict[str, str]:
        scrubbed: dict[str, str] = {}
        for key, value in mapping.items():
            if SENSITIVE_KEY_PATTERN.search(key):
                scrubbed[key] = self.redacted_value
            else:
                scrubbed[key] = self.scrub_text(str(value))
        return scrubbed
