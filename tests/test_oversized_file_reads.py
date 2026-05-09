from contextops.auditors.oversized_file_reads import OversizedFileReads
from contextops.session import load_session


def _big_distinctive_content(n_lines: int = 800) -> str:
    return "\n".join(
        f"distinctive_marker_{i}_xxxxxxxxxxxxxxxxxxxx some payload here"
        for i in range(n_lines)
    )


def test_flags_oversized_unused_read(builder, write_session):
    body = _big_distinctive_content(2000)  # > 5K tokens
    _, ids = builder.assistant(tool_uses=[("Read", {"file_path": "/v/lib.js"})])
    builder.tool_result(ids[0], body)
    # Following turns barely reference the file
    builder.assistant(text="ok, working on something else entirely")
    builder.assistant(text="moving on with unrelated reasoning")

    s = load_session(write_session(builder))
    findings = OversizedFileReads().run(s)
    assert findings, "expected oversized read finding"
    assert findings[0].wasted_tokens > 1000


def test_does_not_flag_well_used_read(builder, write_session):
    body = _big_distinctive_content(2000)
    _, ids = builder.assistant(tool_uses=[("Read", {"file_path": "/v/lib.js"})])
    builder.tool_result(ids[0], body)
    # Quote whole lines (middle-of-line snippets are what the auditor samples).
    quoted = "\n".join(
        f"distinctive_marker_{i}_xxxxxxxxxxxxxxxxxxxx some payload here"
        for i in range(0, 2000, 3)
    )
    builder.assistant(text=quoted)

    s = load_session(write_session(builder))
    findings = OversizedFileReads().run(s)
    assert findings == []
