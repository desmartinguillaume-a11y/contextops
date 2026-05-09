from contextops.auditors.bloated_claude_md import BloatedClaudeMd
from contextops.session import load_session


def test_flags_oversized_claude_md(builder, write_session, tmp_path):
    big = "# Section\n" + ("blah blah blah " * 1500) + "\n# Other\n" + ("more content " * 300)
    cwd = tmp_path
    (cwd / "CLAUDE.md").write_text(big)
    for _ in range(20):
        builder.assistant(text="ok", cwd=str(cwd))
    s = load_session(write_session(builder))
    findings = BloatedClaudeMd().run(s)
    assert findings, "expected bloated CLAUDE.md finding"
    assert findings[0].wasted_tokens > 50_000


def test_no_finding_when_claude_md_small(builder, write_session, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# tiny\nnot much here.\n")
    builder.assistant(text="ok", cwd=str(tmp_path))
    s = load_session(write_session(builder))
    assert BloatedClaudeMd().run(s) == []
