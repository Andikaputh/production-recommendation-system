from __future__ import annotations

from rasa.data.quality import run_data_quality_checks


def test_processed_dataset_passes_all_critical_checks() -> None:
    report = run_data_quality_checks()
    critical_failures = [
        check for check in report["checks"]
        if check["severity"] == "critical" and check["status"] != "pass"
    ]
    assert critical_failures == []
    assert report["summary"]["critical_failures"] == 0
