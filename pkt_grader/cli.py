"""Command-line interface for batch grading Cisco Packet Tracer labs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pkt_grader.engine import grade_inputs
from pkt_grader.exporter import format_console_report, write_csv, write_json
from pkt_grader.models import RubricConfig


def load_rubric(path: str | None, pass_threshold: float | None = None) -> RubricConfig:
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        rubric = RubricConfig.model_validate(raw)
    else:
        rubric = RubricConfig()
    if pass_threshold is not None:
        rubric.pass_threshold = pass_threshold
    return rubric


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pkt-grade",
        description="Autograder offline untuk file Cisco Packet Tracer (.pkt/.pka/.zip).",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="File .pkt/.pka, arsip .zip, atau direktori berisi kumpulan submission.",
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        help="Simpan hasil rekap penilaian ke file CSV.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        help="Simpan laporan lengkap (termasuk detail per check & config) ke file JSON.",
    )
    parser.add_argument(
        "--rubric",
        dest="rubric_path",
        help="File JSON konfigurasi bobot rubrik (default: rubrik UAP Jarkom PTI).",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=None,
        help="Override ambang kelulusan dalam persen (default: 70).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Tampilkan rincian kesalahan untuk setiap mahasiswa meski jumlah file > 15.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        rubric = load_rubric(args.rubric_path, args.pass_threshold)
    except Exception as exc:
        print(f"Error membaca rubrik: {exc}", file=sys.stderr)
        return 2

    report = grade_inputs(args.inputs, rubric=rubric)
    print(format_console_report(report, verbose=args.verbose))

    if args.csv_path:
        out_csv = write_csv(report, args.csv_path)
        print(f"CSV tersimpan: {out_csv}")

    if args.json_path:
        out_json = write_json(report, args.json_path)
        print(f"JSON tersimpan: {out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
