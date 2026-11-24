"""CSV, JSON, and console table exporters (zero emoji, ASCII-safe formatting)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pkt_grader.models import BatchReport


CSV_COLUMNS = [
    "filename",
    "nim",
    "student_name",
    "status",
    "score",
    "max_score",
    "percentage",
    "passed",
    "pt_version",
    "topologi",
    "vlan_switch",
    "dhcp_r1",
    "static_routing",
    "end_device_dhcp",
    "penyimpanan",
    "dns_optional",
    "failed_check_ids",
    "error_details",
]


def _cat_score(cat_scores: dict[str, dict[str, float]], key: str) -> str:
    bucket = cat_scores.get(key)
    if not bucket:
        return "0/0"
    return f"{bucket['earned']:g}/{bucket['possible']:g}"


def batch_to_csv_string(report: BatchReport, include_bom: bool = True) -> str:
    """Serialize a BatchReport to CSV text (UTF-8 BOM optional for Excel compatibility)."""
    buf = io.StringIO()
    if include_bom:
        buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for r in report.results:
        failed_ids = [c.id for c in r.checks if not c.optional and c.status != "pass"]
        dns_label = {"complete": "LENGKAP", "partial": "PARSIAL", "none": "TIDAK ADA"}[
            r.dns_optional_status
        ]
        writer.writerow(
            {
                "filename": r.filename,
                "nim": r.nim,
                "student_name": r.student_name,
                "status": r.status.upper(),
                "score": f"{r.score:.2f}",
                "max_score": f"{r.max_score:.2f}",
                "percentage": f"{r.percentage:.2f}",
                "passed": "LULUS" if r.passed else "TIDAK LULUS",
                "pt_version": r.pt_version,
                "topologi": _cat_score(r.category_scores, "Topologi"),
                "vlan_switch": _cat_score(r.category_scores, "VLAN & Switch"),
                "dhcp_r1": _cat_score(r.category_scores, "DHCP & R1"),
                "static_routing": _cat_score(r.category_scores, "Static Routing"),
                "end_device_dhcp": _cat_score(r.category_scores, "End Device DHCP"),
                "penyimpanan": _cat_score(r.category_scores, "Penyimpanan"),
                "dns_optional": dns_label,
                "failed_check_ids": "; ".join(failed_ids),
                "error_details": " | ".join(r.errors),
            }
        )
    return buf.getvalue()


def write_csv(report: BatchReport, output_path: str | Path) -> Path:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(batch_to_csv_string(report, include_bom=True), encoding="utf-8")
    return dest


def write_json(report: BatchReport, output_path: str | Path) -> Path:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return dest


def format_console_report(report: BatchReport, verbose: bool = False) -> str:
    """Format a clean, readable CLI report without emojis or ANSI dependency."""
    s = report.summary
    lines: list[str] = []

    sep = "=" * 84
    thin = "-" * 84

    lines.append(sep)
    lines.append(f"  AUTOGRADER: {report.rubric.name}")
    lines.append(sep)
    lines.append(
        f"  Total: {s.total}  |  Lulus (>={report.rubric.pass_threshold:g}%): {s.passed} ({s.pass_rate:.1f}%)"
        f"  |  Tidak Lulus: {s.failed}  |  Error: {s.parse_errors}"
    )
    lines.append(
        f"  Rata-rata: {s.average_score:.2f}  |  Median: {s.median_score:.2f}"
        f"  |  Tertinggi: {s.highest_score:.2f}  |  Terendah: {s.lowest_score:.2f}"
    )
    lines.append(thin)

    if not report.results:
        lines.append("  Tidak ada file .pkt atau .pka ditemukan pada input yang diberikan.")
        lines.append(sep)
        return "\n".join(lines)

    header = f"  {'No':>3}  {'NIM':<16} {'Nama / File':<24} {'Skor':>10} {'%':>6}  {'Status':<7} {'DNS':<8} {'Salah'}"
    lines.append(header)
    lines.append(thin)

    dns_short = {"complete": "LENGKAP", "partial": "PARSIAL", "none": "-"}
    for idx, r in enumerate(report.results, start=1):
        label = (r.student_name or r.filename)[:23]
        nim = (r.nim or "-")[:15]
        score_str = f"{r.score:.1f}/{r.max_score:.0f}"
        err_count = len(r.errors)
        lines.append(
            f"  {idx:>3}  {nim:<16} {label:<24} {score_str:>10} {r.percentage:>5.1f}%  {r.status.upper():<7} {dns_short[r.dns_optional_status]:<8} {err_count}"
        )
        if verbose or len(report.results) <= 15:
            for err in r.errors:
                lines.append(f"       -> {err}")

    if s.common_failures:
        lines.append(thin)
        lines.append("  Kesalahan Paling Sering:")
        for item in s.common_failures[:5]:
            lines.append(
                f"    - [{item['device']}] {item['title']}: {item['count']}/{s.total} mahasiswa ({item['rate']}%)"
            )

    lines.append(sep)
    return "\n".join(lines)
