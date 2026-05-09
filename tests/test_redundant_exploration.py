from contextops.auditors.redundant_exploration import RedundantExploration
from contextops.session import load_session


def test_flags_repeated_ls(builder, write_session):
    listing = "\n".join(f"file_{i}.py" for i in range(50))
    for _ in range(4):
        _, ids = builder.assistant(tool_uses=[("LS", {"path": "/repo/src"})])
        builder.tool_result(ids[0], listing)
    s = load_session(write_session(builder))
    findings = RedundantExploration().run(s)
    assert len(findings) == 1
    assert "/repo/src" in findings[0].evidence[0]


def test_does_not_flag_single_call(builder, write_session):
    _, ids = builder.assistant(tool_uses=[("LS", {"path": "/repo/src"})])
    builder.tool_result(ids[0], "a\nb\nc")
    s = load_session(write_session(builder))
    assert RedundantExploration().run(s) == []
