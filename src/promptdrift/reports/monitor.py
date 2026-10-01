"""Terminal monitoring summary containing no raw provider content."""

from rich.console import Console
from rich.table import Table

from promptdrift.models.monitor import MonitorReport


def print_monitor_report(report: MonitorReport, console: Console) -> None:
    table = Table(title="PromptDrift Monitoring")
    for name in ("Case", "Status", "Diagnosis", "Failed / probes"):
        table.add_column(name)
    for test in report.tests:
        table.add_row(
            test.test_id, test.status, test.diagnosis, f"{test.failures} / {test.samples}"
        )
    console.print(table)
    for test in report.tests:
        if test.diagnosis != "stable":
            console.print(f"{test.test_id}: {test.summary}", markup=False)
            for item in test.evidence:
                console.print(f"  - {item}", markup=False)
    for warning in report.warnings:
        console.print(f"Warning: {warning}", markup=False)
    console.print("Observations are not proof of a vendor model update. Baseline was not modified.")
