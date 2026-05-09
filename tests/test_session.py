from contextops.session import load_session


def test_loads_basic_session(builder, write_session):
    builder.user_text("hello")
    builder.assistant(
        text="hi",
        tool_uses=[("Read", {"file_path": "/x/a.py"})],
        usage={"input_tokens": 200, "output_tokens": 80, "cache_read_input_tokens": 10},
    )
    path = write_session(builder)

    s = load_session(path)
    assert len(s.assistant_turns) == 1
    assert len(s.user_turns) == 1
    assert s.model == "claude-sonnet-4-6"
    assert s.assistant_turns[0].usage.input_tokens == 200
    assert s.tool_calls("Read")[0].input["file_path"] == "/x/a.py"


def test_attachments_register_tool_definitions(builder, write_session):
    builder.attach_tools(["Read", "Edit", "mcp__github__get_me"])
    builder.user_text("hi")
    path = write_session(builder)

    s = load_session(path)
    assert "Read" in s.tool_definitions
    assert "mcp__github__get_me" in s.tool_definitions


def test_tool_result_links_back(builder, write_session):
    builder.user_text("read it")
    _, ids = builder.assistant(tool_uses=[("Read", {"file_path": "/x/a.py"})])
    builder.tool_result(ids[0], "the file contents")
    path = write_session(builder)

    s = load_session(path)
    res = s.result_for(ids[0])
    assert res is not None
    assert res.content == "the file contents"
