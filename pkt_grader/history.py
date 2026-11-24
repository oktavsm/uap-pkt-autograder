"""SQLite persistence layer for evaluation history grouped by Prodi and Class."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pkt_grader.models import BatchReport, HistoryRunMeta


PRODI_CLASSES: dict[str, list[str]] = {
    "PTI": ["A", "B", "C", "D"],
    "TI": ["A", "B", "C", "D", "E", "F", "G"],
}


def format_class_label(prodi: str, kelas: str) -> str:
    p = prodi.strip().upper()
    k = kelas.strip().upper()
    if p and k:
        return f"{p} - {k}"
    if p:
        return p
    if k:
        return k
    return "Umum"


def validate_prodi_kelas(prodi: str, kelas: str) -> tuple[str, str]:
    p = prodi.strip().upper()
    k = kelas.strip().upper()
    if not p and not k:
        return "", ""
    if p not in PRODI_CLASSES:
        raise ValueError(f"Prodi tidak valid '{prodi}'. Pilihan yang tersedia: {', '.join(PRODI_CLASSES)}.")
    if k and k not in PRODI_CLASSES[p]:
        raise ValueError(
            f"Kelas '{kelas}' tidak tersedia untuk {p}. Pilihan: {', '.join(PRODI_CLASSES[p])}."
        )
    return p, k


def resolve_db_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path is not None:
        return Path(explicit_path)
    env_path = os.environ.get("HISTORY_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.cwd() / "data" / "history.db"


class HistoryStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_db_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    prodi TEXT NOT NULL,
                    kelas TEXT NOT NULL,
                    class_label TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    total INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    failed INTEGER NOT NULL,
                    parse_errors INTEGER NOT NULL,
                    average_score REAL NOT NULL,
                    pass_rate REAL NOT NULL,
                    report_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_prodi_kelas
                ON evaluation_runs (prodi, kelas, created_at DESC)
                """
            )

    def save_run(
        self,
        report: BatchReport,
        prodi: str = "",
        kelas: str = "",
        note: str = "",
    ) -> BatchReport:
        clean_prodi, clean_kelas = validate_prodi_kelas(prodi, kelas)
        label = format_class_label(clean_prodi, clean_kelas)
        run_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(timezone.utc).isoformat()
        clean_note = note.strip()[:120]

        enriched = report.model_copy(
            update={
                "run_id": run_id,
                "created_at": created_at,
                "prodi": clean_prodi,
                "kelas": clean_kelas,
                "class_label": label,
                "note": clean_note,
            }
        )
        payload_json = json.dumps(enriched.model_dump(), ensure_ascii=False)
        s = enriched.summary

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_runs (
                    id, created_at, prodi, kelas, class_label, note,
                    total, passed, failed, parse_errors, average_score, pass_rate, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    created_at,
                    clean_prodi,
                    clean_kelas,
                    label,
                    clean_note,
                    s.total,
                    s.passed,
                    s.failed,
                    s.parse_errors,
                    s.average_score,
                    s.pass_rate,
                    payload_json,
                ),
            )
        return enriched

    def list_runs(
        self,
        prodi: str | None = None,
        kelas: str | None = None,
        limit: int = 200,
    ) -> list[HistoryRunMeta]:
        clauses: list[str] = []
        params: list[object] = []
        if prodi:
            clauses.append("prodi = ?")
            params.append(prodi.strip().upper())
        if kelas:
            clauses.append("kelas = ?")
            params.append(kelas.strip().upper())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, created_at, prodi, kelas, class_label, note, "
            "total, passed, failed, parse_errors, average_score, pass_rate "
            f"FROM evaluation_runs {where} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            HistoryRunMeta(
                id=row["id"],
                created_at=row["created_at"],
                prodi=row["prodi"],
                kelas=row["kelas"],
                class_label=row["class_label"],
                note=row["note"],
                total=row["total"],
                passed=row["passed"],
                failed=row["failed"],
                parse_errors=row["parse_errors"],
                average_score=row["average_score"],
                pass_rate=row["pass_rate"],
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> BatchReport | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM evaluation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return BatchReport.model_validate(json.loads(row["report_json"]))

    def list_full_runs(
        self,
        prodi: str | None = None,
        kelas: str | None = None,
        limit: int = 200,
    ) -> list[BatchReport]:
        clauses: list[str] = []
        params: list[object] = []
        if prodi:
            clauses.append("prodi = ?")
            params.append(prodi.strip().upper())
        if kelas:
            clauses.append("kelas = ?")
            params.append(kelas.strip().upper())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT report_json FROM evaluation_runs {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [BatchReport.model_validate(json.loads(row["report_json"])) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM evaluation_runs WHERE id = ?", (run_id,))
            return cur.rowcount > 0

    def update_student_assignment(
        self,
        run_id: str,
        source_path: str,
        *,
        nim: str = "",
        student_name: str = "",
        matched_prodi: str = "",
        matched_kelas: str = "",
        match_source: str = "manual",
        match_confidence: float = 1.0,
    ) -> BatchReport | None:
        report = self.get_run(run_id)
        if report is None:
            return None

        updated = False
        next_results = []
        for item in report.results:
            if item.source_path == source_path:
                next_results.append(
                    item.model_copy(
                        update={
                            "nim": nim,
                            "student_name": student_name,
                            "matched_prodi": matched_prodi,
                            "matched_kelas": matched_kelas,
                            "match_source": match_source,
                            "match_confidence": match_confidence,
                        }
                    )
                )
                updated = True
            else:
                next_results.append(item)

        if not updated:
            raise KeyError(f"Berkas '{source_path}' tidak ditemukan pada riwayat '{run_id}'.")

        next_report = report.model_copy(update={"results": next_results})
        payload_json = json.dumps(next_report.model_dump(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "UPDATE evaluation_runs SET report_json = ? WHERE id = ?",
                (payload_json, run_id),
            )
        return next_report
