"""Tests for student roster CSV import, auto-matching, manual assignment, and class CSV export."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from pkt_grader.models import BatchReport, BatchSummary, RubricConfig, StudentReport
from pkt_grader.roster import RosterStore
from pkt_grader.server import create_app


SAMPLE_ROSTER_CSV = """NIM,NAMA,ANGKATAN,PROGSTUDI,MATA_KULIAH,KELAS
255150700111001,ANDI PRATAMA PUTRA,2025,Teknologi Informasi,Jaringan Komputer,A
255150700111002,CITRA KUSUMA DEWI,2025,Teknologi Informasi,Jaringan Komputer,A
255150700111003,ANDI WIJAYA,2025,Teknologi Informasi,Jaringan Komputer,B
255150600111010,BUDI SANTOSO,2025,Pendidikan Teknologi Informasi,Jaringan Komputer,A
255150600111011,DEWI LESTARI,2025,Pendidikan Teknologi Informasi,Jaringan Komputer,B
255150700111001,ANDI PRATAMA PUTRA,2025,Teknologi Informasi,Teknologi Keamanan Siber,C
255150200111099,EKO NUGROHO,2025,Teknik Informatika,Jaringan Komputer,A
255150300111088,FAJAR HIDAYAT,2025,Teknik Komputer,Pengantar Sistem Operasi,A
"""


def _dummy_report(filename: str, source_path: str | None = None, score: float = 95.0) -> StudentReport:
    return StudentReport(
        filename=filename,
        source_path=source_path or filename,
        nim="",
        student_name="",
        status="pass",
        score=score,
        max_score=100.0,
        percentage=score,
        passed=True,
        dns_optional_status="none",
        category_scores={"Topologi": {"earned": 5.0, "possible": 5.0}},
    )


def test_roster_import_filters_pti_ti_jarkom(tmp_path: Path) -> None:
    store = RosterStore(db_path=tmp_path / "test.db")
    summary = store.import_csv_text(SAMPLE_ROSTER_CSV, replace=True)
    assert summary["imported"] == 5
    assert summary["total"] == 5
    assert summary["skipped"] == 3
    counts = store.counts_by_prodi_kelas()
    assert counts["TI"] == 3
    assert counts["PTI"] == 2
    assert counts["TI - A"] == 2
    assert counts["PTI - A"] == 1


def test_roster_auto_match_nim_name_and_ambiguity(tmp_path: Path) -> None:
    store = RosterStore(db_path=tmp_path / "test.db")
    store.import_csv_text(SAMPLE_ROSTER_CSV, replace=True)

    # 1. Exact NIM in filename
    m_nim = store.match_student("UAP_255150600111010_Budi.pkt")
    assert m_nim is not None
    assert m_nim.method == "roster_nim"
    assert m_nim.student.nim == "255150600111010"
    assert m_nim.student.prodi == "PTI"

    # 2. NIM only in ZIP parent folder
    m_folder = store.match_student(
        filename="UAP Topology.pkt",
        source_path="TI_A.zip::255150700111002_Citra/UAP Topology.pkt",
    )
    assert m_folder is not None
    assert m_folder.method == "roster_nim"
    assert m_folder.student.nim == "255150700111002"

    # 3. Match by name without NIM
    m_name = store.match_student(
        filename="UAP_Citra_Kusuma.pkt",
        preferred_prodi="TI",
        preferred_kelas="A",
    )
    assert m_name is not None
    assert m_name.method == "roster_name"
    assert m_name.student.nim == "255150700111002"

    # 4. Generic filename should stay unmatched
    m_none = store.match_student("UAP Topology.pkt", preferred_prodi="TI", preferred_kelas="A")
    assert m_none is None

    # 5. Disambiguate shared first name by preferred class
    m_pref = store.match_student(
        filename="Andi_Pratama.pkt",
        preferred_prodi="TI",
        preferred_kelas="A",
    )
    assert m_pref is not None
    assert m_pref.student.nim == "255150700111001"


def test_api_roster_assign_and_class_rekap_csv(tmp_path: Path) -> None:
    db_file = tmp_path / "app.db"
    app = create_app(db_path=db_file)
    client = TestClient(app)

    # Import roster via API
    imp = client.post(
        "/api/roster/import",
        files={"file": ("roster.csv", SAMPLE_ROSTER_CSV.encode("utf-8"), "text/csv")},
        data={"replace": "true"},
    )
    assert imp.status_code == 200
    assert imp.json()["imported"] == 5

    # Query roster endpoint
    lst = client.get("/api/roster", params={"prodi": "TI", "kelas": "A"})
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] == 5
    assert len(body["students"]) == 2

    # Seed a saved evaluation run directly in history store to test manual assign + class CSV
    from pkt_grader.history import HistoryStore

    hstore = HistoryStore(db_path=db_file)
    batch = BatchReport(
        rubric=RubricConfig(),
        summary=BatchSummary(
            total=2,
            passed=2,
            failed=0,
            parse_errors=0,
            average_score=92.5,
            highest_score=95.0,
            lowest_score=90.0,
            median_score=92.5,
            pass_rate=100.0,
            common_failures=[],
        ),
        results=[
            _dummy_report("UAP Topology.pkt", "UAP Topology.pkt", score=95.0),
            _dummy_report("unknown_file.pkt", "unknown_file.pkt", score=90.0),
        ],
    )
    saved = hstore.save_run(batch, prodi="TI", kelas="A", note="Sesi 1")
    assert saved.run_id is not None

    # Manually assign the first file to Andi Pratama Putra
    res_assign = client.patch(
        f"/api/history/{saved.run_id}/assign",
        json={"source_path": "UAP Topology.pkt", "nim": "255150700111001"},
    )
    assert res_assign.status_code == 200
    updated_first = res_assign.json()["results"][0]
    assert updated_first["nim"] == "255150700111001"
    assert updated_first["student_name"] == "ANDI PRATAMA PUTRA"
    assert updated_first["match_source"] == "manual"
    assert updated_first["matched_prodi"] == "TI"
    assert updated_first["matched_kelas"] == "A"

    # Export full class rekap CSV for TI - A
    csv_res = client.get("/api/history/export/class-csv", params={"prodi": "TI", "kelas": "A"})
    assert csv_res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_res.text.lstrip("\ufeff"))))
    assert len(rows) == 3  # 2 roster students in TI-A + 1 unassigned file
    by_nim = {r["nim"]: r for r in rows if r["nim"]}
    assert by_nim["255150700111001"]["status_pengumpulan"] == "DINILAI"
    assert by_nim["255150700111001"]["skor"] == "95.00"
    assert by_nim["255150700111002"]["status_pengumpulan"] == "BELUM DINILAI"
    assert rows[-1]["status_pengumpulan"] == "BELUM DI-ASSIGN"
    assert rows[-1]["nama_berkas"] == "unknown_file.pkt"

    # Unassign test
    res_unassign = client.patch(
        f"/api/history/{saved.run_id}/assign",
        json={"source_path": "UAP Topology.pkt", "nim": None},
    )
    assert res_unassign.status_code == 200
    assert res_unassign.json()["results"][0]["nim"] == ""
    assert res_unassign.json()["results"][0]["match_source"] == "unmatched"
