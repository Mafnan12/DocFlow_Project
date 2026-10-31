"""Sanity test verifying that the test harness and environment run cleanly."""


def test_sanity_environment():
    """Verify standard assertions and basic imports."""
    import sys

    assert sys.version_info >= (3, 11), "DocFlow requires Python 3.11+"


def test_package_structure():
    """Verify that core package namespaces exist and import."""
    import docflow
    import llmkit

    assert docflow is not None
    assert llmkit is not None
