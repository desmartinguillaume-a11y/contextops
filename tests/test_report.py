from io import StringIO

from rich.console import Console

from contextops.auditors import all_auditors
from contextops.report import compute_bill, render_report
from contextops.session import load_session


def test_render_does_not_crash_on_empty_session(builder, write_session):
    builder.user_text("hello")
    builder.assistant(text="hi", usage={"input_tokens": 10, "output_tokens": 5})
    s = load_session(write_session(builder))
    findings = []
    for a in all_auditors():
        findings.extend(a.run(s))
    buf = StringIO()
    render_report(s, findings, console=Console(file=buf, force_terminal=False, width=100))
    out = buf.getvalue()
    assert "Context Utilization Report" in out
    assert "Total cost" in out


def test_compute_bill_caps_waste_at_total(builder, write_session):
    builder.assistant(usage={"input_tokens": 100, "output_tokens": 50})
    s = load_session(write_session(builder))
    # Synthetic finding that claims to waste more than was billed.
    from contextops.auditors import Finding, Category
    inflated = [Finding(
        auditor="x", title="X", category=Category.RIGHTSIZING,
        wasted_tokens=1_000_000, wasted_dollars=1000.0,
        recommendation="r", methodology="m",
    )]
    bill = compute_bill(s, inflated)
    assert bill.waste_tokens <= bill.total_tokens
    assert bill.waste_dollars <= bill.total_dollars
