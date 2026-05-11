"""Tests for BOLT-01: fix_hint field on Finding and new stub auditors in all_auditors()."""

from __future__ import annotations

import pytest

from contextops.auditors import Auditor, Finding, all_auditors


def test_finding_no_fix_hint_defaults_to_none():
    """AC-1: Constructing Finding without fix_hint should succeed and fix_hint is None."""
    finding = Finding(
        auditor="x",
        title="y",
        category="z",
        wasted_tokens=10,
        wasted_dollars=0.001,
        recommendation="r",
        methodology="m",
    )
    assert finding.fix_hint is None


def test_finding_with_fix_hint():
    """AC-2: Constructing Finding with fix_hint keyword argument sets the value."""
    finding = Finding(
        auditor="x",
        title="y",
        category="z",
        wasted_tokens=10,
        wasted_dollars=0.001,
        recommendation="r",
        methodology="m",
        fix_hint="Truncate bash output to the first 50 lines.",
    )
    assert finding.fix_hint == "Truncate bash output to the first 50 lines."


def test_all_auditors_length_and_names():
    """AC-3: all_auditors() returns exactly 10 auditors with the expected names."""
    auditors = all_auditors()
    assert len(auditors) == 10
    names = {a.name for a in auditors}
    expected = {
        "repeated_file_reads",
        "oversized_file_reads",
        "bloated_claude_md",
        "unused_mcp_tools",
        "redundant_exploration",
        "failed_then_retried",
        "oversized_tool_outputs",
        "duplicate_bash_runs",
        "large_image_uploads",
        "prompt_context_stuffing",
    }
    assert names == expected


def test_all_auditors_are_auditor_instances():
    """AC-4: Every auditor satisfies the Auditor protocol with required attributes."""
    for auditor in all_auditors():
        assert isinstance(auditor, Auditor), f"{auditor!r} is not an Auditor"
        assert isinstance(auditor.name, str) and auditor.name
        assert isinstance(auditor.title, str) and auditor.title
        assert isinstance(auditor.category, str) and auditor.category
        assert callable(auditor.run)
