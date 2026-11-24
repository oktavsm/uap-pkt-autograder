"""Student roster storage (SQLite) and auto-matching by NIM or name."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from pkt_grader.history import PRODI_CLASSES, format_class_label, resolve_db_path
from pkt_grader.models import RosterMatch, StudentRosterEntry

PRODI_ALIASES: dict[str, str] = {
    "TI": "TI",
    "TEKNOLOGI INFORMASI": "TI",
    "PTI": "PTI",
    "PENDIDIKAN TEKNOLOGI INFORMASI": "PTI",
}

NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "uap",
        "uas",
        "uts",
        "jarkom",
        "jaringan",
        "komputer",
        "praktikum",
        "topologi",
        "topology",
        "configured",
        "config",
        "final",
        "revisi",
        "rev",
        "new",
        "fix",
        "fixed",
        "copy",
        "pkt",
        "pka",
        "zip",
        "kelas",
        "kls",
        "class",
        "ti",
        "pti",
        "tif",
        "filkom",
        "ub",
        "submission",
        "submissions",
        "tugas",
        "ujian",
        "akhir",
        "file",
        "berkas",
        "jawaban",
        "hasil",
        "packet",
        "tracer",
        "pt",
        "lab",
    }
)


def normalize_prodi(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw.strip()).upper()
    return PRODI_ALIASES.get(cleaned, "")


def normalize_name_tokens(text: str, strip_noise: bool = False) -> list[str]:
    lowered = text.lower()
    lowered = re.sub(r"\.(pkt|pka|zip)$", "", lowered)
    lowered = re.sub(r"[^a-z\s]", " ", lowered)
    tokens = [tok for tok in lowered.split() if tok]
    if strip_noise:
        filtered: list[str] = []
        for tok in tokens:
            if tok in NOISE_TOKENS:
                continue
            # Drop lone single-letter class labels like "a".."g" when mixed with noise
            if len(tok) == 1 and tok in {"a", "b", "c", "d", "e", "f", "g"}:
                continue
            filtered.append(tok)
        return filtered
    return tokens


def _token_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) >= 4 and len(b) >= 4:
        if b.startswith(a) or a.startswith(b):
            return 0.92
        return SequenceMatcher(None, a, b).ratio()
    return SequenceMatcher(None, a, b).ratio()


def _extract_candidate_queries(filename: str, source_path: str, parsed_name: str) -> list[str]:
    queries: list[str] = []
    if parsed_name.strip():
        queries.append(parsed_name.strip())

    stem = Path(filename).stem
    if stem and stem not in queries:
        queries.append(stem)

    # Extract inner folder names from ZIP source_path like "ti_a.zip::2551507_Budi/UAP Topology.pkt"
    if "::" in source_path:
        inner = source_path.split("::", 1)[1]
        parts = [p for p in Path(inner).parts[:-1] if p and p != "__MACOSX"]
        for part in reversed(parts):
            if part not in queries:
                queries.append(part)
    else:
        parent = Path(source_path).parent.name
        if parent and parent not in (".", "/", "") and parent not in queries:
            queries.append(parent)
    return queries


def _extract_nims(parsed_nim: str, filename: str, source_path: str) -> list[str]:
    seen: list[str] = []
    for candidate in (parsed_nim, filename, source_path):
        if not candidate:
            continue
        for match in re.findall(r"\d{8,20}", candidate):
            if match not in seen:
                seen.append(match)
    return seen


class RosterStore:
    """SQLite-backed roster table stored privately alongside evaluation history."""

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
                CREATE TABLE IF NOT EXISTS students (
                    nim TEXT PRIMARY KEY,
                    nama TEXT NOT NULL,
                    prodi TEXT NOT NULL,
                    kelas TEXT NOT NULL,
                    angkatan TEXT NOT NULL DEFAULT '',
                    mata_kuliah TEXT NOT NULL DEFAULT 'Jaringan Komputer',
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_students_prodi_kelas
                ON students (prodi, kelas, nim)
                """
            )

    def _row_to_entry(self, row: sqlite3.Row) -> StudentRosterEntry:
        prodi = row["prodi"]
        kelas = row["kelas"]
        return StudentRosterEntry(
            nim=row["nim"],
            nama=row["nama"],
            prodi=prodi,
            kelas=kelas,
            class_label=format_class_label(prodi, kelas),
            angkatan=row["angkatan"],
        )

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM students").fetchone()
            return int(row["cnt"]) if row else 0

    def counts_by_prodi_kelas(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT prodi, kelas, COUNT(*) AS cnt FROM students GROUP BY prodi, kelas"
            ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            prodi = row["prodi"]
            kelas = row["kelas"]
            cnt = int(row["cnt"])
            counts[prodi] = counts.get(prodi, 0) + cnt
            counts[format_class_label(prodi, kelas)] = cnt
        return counts

    def get_by_nim(self, nim: str) -> StudentRosterEntry | None:
        clean = nim.strip()
        if not clean:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT nim, nama, prodi, kelas, angkatan FROM students WHERE nim = ?",
                (clean,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def list_students(
        self,
        prodi: str | None = None,
        kelas: str | None = None,
        query: str | None = None,
    ) -> list[StudentRosterEntry]:
        clauses: list[str] = []
        params: list[object] = []
        if prodi:
            clauses.append("prodi = ?")
            params.append(prodi.strip().upper())
        if kelas:
            clauses.append("kelas = ?")
            params.append(kelas.strip().upper())
        if query and query.strip():
            like = f"%{query.strip().lower()}%"
            clauses.append("(LOWER(nim) LIKE ? OR LOWER(nama) LIKE ?)")
            params.extend([like, like])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT nim, nama, prodi, kelas, angkatan FROM students {where} ORDER BY prodi, kelas, nim"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def upsert_students(
        self,
        entries: Iterable[StudentRosterEntry],
        replace: bool = False,
        mata_kuliah: str = "Jaringan Komputer",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        records = [
            (
                e.nim.strip(),
                e.nama.strip(),
                e.prodi.strip().upper(),
                e.kelas.strip().upper(),
                e.angkatan.strip(),
                mata_kuliah,
                now,
            )
            for e in entries
            if e.nim.strip() and e.nama.strip()
        ]
        with self._connect() as conn:
            if replace:
                conn.execute("DELETE FROM students")
            conn.executemany(
                """
                INSERT INTO students (nim, nama, prodi, kelas, angkatan, mata_kuliah, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(nim) DO UPDATE SET
                    nama = excluded.nama,
                    prodi = excluded.prodi,
                    kelas = excluded.kelas,
                    angkatan = excluded.angkatan,
                    mata_kuliah = excluded.mata_kuliah,
                    updated_at = excluded.updated_at
                """,
                records,
            )
        return len(records)

    def import_csv_text(
        self,
        csv_text: str,
        replace: bool = True,
        allowed_prodi: tuple[str, ...] = ("TI", "PTI"),
        course_filter: str = "jaringan komputer",
    ) -> dict[str, object]:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        if not reader.fieldnames:
            raise ValueError("Berkas CSV kosong atau tidak memiliki baris header.")

        col_map = {h.strip().lower(): h for h in reader.fieldnames if h}

        def pick(row: dict[str, str], *keys: str) -> str:
            for k in keys:
                actual = col_map.get(k)
                if actual is not None and row.get(actual) is not None:
                    return row[actual].strip()
            return ""

        has_course_col = any(k in col_map for k in ("mata_kuliah", "matakuliah", "mk", "course"))
        allowed_set = {p.upper() for p in allowed_prodi}

        parsed: dict[str, StudentRosterEntry] = {}
        skipped = 0
        for row in reader:
            nim = re.sub(r"\s+", "", pick(row, "nim", "no_induk", "id"))
            nama = re.sub(r"\s+", " ", pick(row, "nama", "name", "student_name", "nama_lengkap"))
            raw_prodi = pick(row, "progstudi", "prodi", "program_studi")
            kelas = pick(row, "kelas", "class").upper()
            angkatan = pick(row, "angkatan", "tahun", "year")
            mk = pick(row, "mata_kuliah", "matakuliah", "mk", "course")

            prodi = normalize_prodi(raw_prodi)
            if not nim or not nama or prodi not in allowed_set:
                skipped += 1
                continue
            if has_course_col and course_filter and mk and course_filter.lower() not in mk.lower():
                skipped += 1
                continue
            valid_classes = PRODI_CLASSES.get(prodi, [])
            if valid_classes and kelas not in valid_classes:
                skipped += 1
                continue

            parsed[nim] = StudentRosterEntry(
                nim=nim,
                nama=nama,
                prodi=prodi,
                kelas=kelas,
                class_label=format_class_label(prodi, kelas),
                angkatan=angkatan,
            )

        if not parsed:
            raise ValueError(
                "Tidak ada data praktikan PTI/TI Jaringan Komputer yang valid pada berkas CSV."
            )

        imported = self.upsert_students(parsed.values(), replace=replace)
        return {
            "imported": imported,
            "skipped": skipped,
            "total": self.count(),
            "counts": self.counts_by_prodi_kelas(),
        }

    def match_student(
        self,
        filename: str,
        source_path: str = "",
        parsed_nim: str = "",
        parsed_name: str = "",
        preferred_prodi: str = "",
        preferred_kelas: str = "",
        roster_cache: list[StudentRosterEntry] | None = None,
    ) -> RosterMatch | None:
        students = roster_cache if roster_cache is not None else self.list_students()
        if not students:
            return None

        by_nim = {s.nim: s for s in students}

        # 1. Exact NIM lookup (from parsed_nim, filename, or ZIP parent folder)
        for cand_nim in _extract_nims(parsed_nim, filename, source_path):
            hit = by_nim.get(cand_nim)
            if hit is not None:
                return RosterMatch(student=hit, method="roster_nim", confidence=1.0)

        # 2. Normalized name matching (full name, token subset, or fuzzy)
        pref_p = preferred_prodi.strip().upper()
        pref_k = preferred_kelas.strip().upper()
        queries = _extract_candidate_queries(filename, source_path, parsed_name)

        best_match: tuple[float, StudentRosterEntry] | None = None
        second_score = 0.0

        for raw_query in queries:
            q_tokens = normalize_name_tokens(raw_query, strip_noise=True)
            if not q_tokens:
                continue
            q_norm = " ".join(q_tokens)

            scored: list[tuple[float, StudentRosterEntry]] = []
            for student in students:
                c_tokens = normalize_name_tokens(student.nama, strip_noise=False)
                if not c_tokens:
                    continue
                c_norm = " ".join(c_tokens)

                in_same_class = bool(pref_p and pref_k and student.prodi == pref_p and student.kelas == pref_k)
                in_same_prodi = bool(pref_p and student.prodi == pref_p)
                boost = 0.06 if in_same_class else (0.02 if in_same_prodi else 0.0)

                if q_norm == c_norm:
                    scored.append((1.0 + boost, student))
                    continue

                if len(q_tokens) >= 2:
                    matched_sims: list[float] = []
                    used_indices: set[int] = set()
                    for qt in q_tokens:
                        best_t_sim = 0.0
                        best_idx = -1
                        for idx, ct in enumerate(c_tokens):
                            if idx in used_indices:
                                continue
                            sim = _token_similarity(qt, ct)
                            if sim > best_t_sim:
                                best_t_sim = sim
                                best_idx = idx
                        if best_t_sim >= 0.84 and best_idx >= 0:
                            used_indices.add(best_idx)
                            matched_sims.append(best_t_sim)

                    all_query_matched = len(matched_sims) == len(q_tokens)
                    if all_query_matched:
                        coverage = len(used_indices) / max(len(c_tokens), 1)
                        avg_sim = sum(matched_sims) / len(matched_sims)
                        score = (0.84 + 0.14 * coverage) * avg_sim + boost
                        scored.append((score, student))
                        continue

                    seq_ratio = SequenceMatcher(None, q_norm, c_norm).ratio()
                    if seq_ratio >= 0.80:
                        scored.append((seq_ratio + boost, student))
                else:
                    # Single token: only allow if distinctive (>=5 chars) and matches clearly
                    qt = q_tokens[0]
                    if len(qt) < 5:
                        continue
                    best_tok_sim = max(_token_similarity(qt, ct) for ct in c_tokens)
                    if best_tok_sim >= 0.94:
                        scored.append((0.80 * best_tok_sim + boost, student))

            if not scored:
                continue

            scored.sort(key=lambda pair: pair[0], reverse=True)
            top_score, top_student = scored[0]
            runner_up = scored[1][0] if len(scored) > 1 else 0.0

            is_exact = top_score >= 1.0
            has_margin = (top_score - runner_up) >= 0.055
            if top_score >= 0.78 and (is_exact or has_margin):
                if best_match is None or top_score > best_match[0]:
                    best_match = (top_score, top_student)
                    second_score = runner_up

        if best_match is None:
            return None

        conf = round(min(0.99 if best_match[0] < 1.0 else 1.0, best_match[0]), 2)
        if best_match[0] < 1.0 and (best_match[0] - second_score) < 0.055:
            return None
        return RosterMatch(student=best_match[1], method="roster_name", confidence=conf)
