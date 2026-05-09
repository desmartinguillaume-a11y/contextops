from contextops.auditors.unused_mcp_tools import UnusedMcpTools
from contextops.session import load_session


def test_flags_unused_mcp_tools(builder, write_session):
    builder.attach_tools(
        [
            "Read",
            "Edit",
            "Bash",
            "mcp__github__add_issue_comment",
            "mcp__github__merge_pull_request",
            "mcp__github__create_branch",
        ]
    )
    for _ in range(5):
        builder.assistant(tool_uses=[("Read", {"file_path": "/a"})])
    s = load_session(write_session(builder))
    findings = UnusedMcpTools().run(s)
    assert len(findings) == 1
    assert findings[0].wasted_tokens > 0
    assert "github" in findings[0].recommendation


def test_no_finding_when_all_tools_used(builder, write_session):
    builder.attach_tools(["Read"])
    builder.assistant(tool_uses=[("Read", {"file_path": "/a"})])
    s = load_session(write_session(builder))
    assert UnusedMcpTools().run(s) == []
