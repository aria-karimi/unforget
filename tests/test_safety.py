import pytest

from unforget.config import SafetyConfig
from unforget.core.safety import block_if_forbidden, should_warn_destructive


def test_block_if_forbidden_raises() -> None:
    with pytest.raises(ValueError):
        block_if_forbidden("mkfs /dev/sda", SafetyConfig())


def test_warn_destructive_pattern() -> None:
    assert should_warn_destructive("sudo rm -rf /tmp/x", SafetyConfig()) is True
