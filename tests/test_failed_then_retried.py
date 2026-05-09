from contextops.auditors.failed_then_retried import FailedThenRetried
from contextops.session import load_session


def test_flags_retry_after_error(builder, write_session):
    err_payload = "bash: foo: command not found\n" * 50
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "foo --bar"})])
    builder.tool_result(ids1[0], err_payload, is_error=True)
    builder.assistant(tool_uses=[("Bash", {"command": "foo --bar"})])  # identical retry
    s = load_session(write_session(builder))
    findings = FailedThenRetried().run(s)
    assert len(findings) == 1
    assert findings[0].wasted_tokens > 0


def test_does_not_flag_dissimilar_retry(builder, write_session):
    _, ids1 = builder.assistant(tool_uses=[("Bash", {"command": "foo"})])
    builder.tool_result(ids1[0], "boom", is_error=True)
    builder.assistant(tool_uses=[("Bash", {"command": "ls /tmp/something/totally/different"})])
    s = load_session(write_session(builder))
    assert FailedThenRetried().run(s) == []
