from contextops.auditors.repeated_file_reads import RepeatedFileReads
from contextops.session import load_session


def test_flags_three_reads_of_same_file(builder, write_session):
    big = "line " * 4000  # ~ 5K tokens
    for _ in range(3):
        _, ids = builder.assistant(tool_uses=[("Read", {"file_path": "/x/a.py"})])
        builder.tool_result(ids[0], big)
    s = load_session(write_session(builder))
    findings = RepeatedFileReads().run(s)
    assert len(findings) == 1
    assert findings[0].wasted_tokens > 1000
    assert "/x/a.py" in findings[0].evidence[0]


def test_edit_resets_zombie_clock(builder, write_session):
    body = "line " * 1000
    _, r1 = builder.assistant(tool_uses=[("Read", {"file_path": "/x/a.py"})])
    builder.tool_result(r1[0], body)
    builder.assistant(tool_uses=[("Edit", {"file_path": "/x/a.py", "old_string": "x", "new_string": "y"})])
    _, r2 = builder.assistant(tool_uses=[("Read", {"file_path": "/x/a.py"})])
    builder.tool_result(r2[0], body)
    s = load_session(write_session(builder))
    findings = RepeatedFileReads().run(s)
    assert findings == []  # the second read is justified by the edit
