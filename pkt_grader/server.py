"""FastAPI web backend for drag-and-drop batch grading, history storage, and CSV export."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pkt_grader.engine import (
    extract_student_identity,
    grade_archive_bytes,
    grade_bytes,
    grade_pkz_bytes,
    summarize_batch,
)
from pkt_grader.exporter import batch_to_csv_string, batches_to_csv_string, class_rekap_to_csv_string
from pkt_grader.history import HistoryStore, PRODI_CLASSES, validate_prodi_kelas
from pkt_grader.models import BatchReport, HistoryRunMeta, RubricConfig, StudentReport
from pkt_grader.roster import RosterStore


class AssignStudentRequest(BaseModel):
    source_path: str
    nim: str | None = None
    custom_nim: str | None = None
    custom_name: str | None = None
    custom_prodi: str | None = None
    custom_kelas: str | None = None


def _resolve_web_dist_dir() -> Path | None:
    env_dir = os.environ.get("WEB_DIST_DIR")
    candidates = [
        Path(env_dir) if env_dir else None,
        Path(__file__).resolve().parent.parent / "web" / "dist",
        Path.cwd() / "web" / "dist",
        Path("/app/web/dist"),
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate
    return None


CHECK_CATALOG = [
    {"id": "topo_devices", "category": "Topologi", "device": "Topologi", "label": "Kelengkapan 6 perangkat utama"},
    {"id": "topo_links", "category": "Topologi", "device": "Topologi", "label": "Pemetaan 5 koneksi kabel"},
    {"id": "s1_vlans", "category": "VLAN & Switch", "device": "S1", "label": "Pembuatan VLAN 10 dan VLAN 20"},
    {"id": "s1_access_fa01", "category": "VLAN & Switch", "device": "S1", "label": "Port access Fa0/1 (VLAN 10)"},
    {"id": "s1_access_fa02", "category": "VLAN & Switch", "device": "S1", "label": "Port access Fa0/2 (VLAN 20)"},
    {"id": "s1_trunk_mode", "category": "VLAN & Switch", "device": "S1", "label": "Mode trunk pada Gi0/1"},
    {"id": "s1_trunk_allowed", "category": "VLAN & Switch", "device": "S1", "label": "Allowed VLAN 10,20 pada Gi0/1"},
    {"id": "r1_base_ip", "category": "DHCP & R1", "device": "R1", "label": "Integritas IP interface awal R1"},
    {"id": "r1_dhcp_excl_10", "category": "DHCP & R1", "device": "R1", "label": "Excluded-address VLAN 10 (.1-.10)"},
    {"id": "r1_dhcp_excl_20", "category": "DHCP & R1", "device": "R1", "label": "Excluded-address VLAN 20 (.1-.10)"},
    {"id": "r1_dhcp_pool_10", "category": "DHCP & R1", "device": "R1", "label": "DHCP pool subnet VLAN 10"},
    {"id": "r1_dhcp_pool_20", "category": "DHCP & R1", "device": "R1", "label": "DHCP pool subnet VLAN 20"},
    {"id": "r2_base_ip", "category": "Static Routing", "device": "R2", "label": "Integritas IP awal R2 & Server1"},
    {"id": "r1_route_lanb", "category": "Static Routing", "device": "R1", "label": "Static route R1 -> LAN B"},
    {"id": "r2_route_vlan10", "category": "Static Routing", "device": "R2", "label": "Static route R2 -> VLAN 10"},
    {"id": "r2_route_vlan20", "category": "Static Routing", "device": "R2", "label": "Static route R2 -> VLAN 20"},
    {"id": "pc1_dhcp", "category": "End Device DHCP", "device": "PC1", "label": "DHCP lease valid PC1"},
    {"id": "pc2_dhcp", "category": "End Device DHCP", "device": "PC2", "label": "DHCP lease valid PC2"},
    {"id": "save_config", "category": "Penyimpanan", "device": "S1, R1, R2", "label": "Simpan konfigurasi (write memory)"},
    {"id": "opt_dns", "category": "Opsional", "device": "R1, Server1", "label": "Konfigurasi DNS opsional (bonus, nilai tetap maks. 100)"},
]


def create_app(db_path: str | Path | None = None) -> FastAPI:
    store = HistoryStore(db_path=db_path)
    roster = RosterStore(db_path=db_path)

    app = FastAPI(
        title="UAP Packet Tracer Autograder",
        version="1.2.0",
        description="Offline semantic grading API for Cisco Packet Tracer (.pkt/.pka/.zip) with roster auto-detect and class history.",
    )

    allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins if o.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/classes")
    def get_classes() -> dict[str, list[str]]:
        return PRODI_CLASSES

    @app.get("/api/rubric")
    def get_rubric() -> dict[str, object]:
        return {
            "rubric": RubricConfig().model_dump(),
            "checks": CHECK_CATALOG,
            "classes": PRODI_CLASSES,
        }

    @app.post("/api/grade", response_model=BatchReport)
    async def grade_uploads(
        files: list[UploadFile] = File(...),
        rubric_json: str | None = Form(default=None),
        prodi: str = Form(default=""),
        kelas: str = Form(default=""),
        note: str = Form(default=""),
        save_history: bool = Form(default=True),
    ) -> BatchReport:
        if not files:
            raise HTTPException(status_code=400, detail="Minimal satu file .pkt, .pka, atau .zip wajib diunggah.")

        try:
            rubric = (
                RubricConfig.model_validate(json.loads(rubric_json))
                if rubric_json
                else RubricConfig()
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Format rubrik tidak valid: {exc}") from exc

        results: list[StudentReport] = []
        for upload in files:
            name = upload.filename or "submission.pkt"
            suffix = Path(name).suffix.lower()
            raw = await upload.read()

            if suffix == ".zip":
                try:
                    extracted = grade_archive_bytes(raw, archive_name=name, rubric=rubric)
                    results.extend(extracted)
                except Exception as exc:
                    results.append(
                        StudentReport(
                            filename=name,
                            source_path=name,
                            status="error",
                            score=0.0,
                            max_score=100.0,
                            percentage=0.0,
                            passed=False,
                            errors=[f"Gagal mengekstrak arsip ZIP '{name}': {exc}"],
                            parse_error=str(exc),
                        )
                    )
            elif suffix == ".pkz":
                results.append(grade_pkz_bytes(raw, filename=name, source_path=name, rubric=rubric))
            elif suffix in (".pkt", ".pka"):
                results.append(grade_bytes(raw, filename=name, source_path=name, rubric=rubric))
            else:
                results.append(
                    StudentReport(
                        filename=name,
                        source_path=name,
                        status="error",
                        score=0.0,
                        max_score=100.0,
                        percentage=0.0,
                        passed=False,
                        errors=[f"Ekstensi tidak didukung ('{suffix or 'tanpa ekstensi'}'). Gunakan .pkt, .pka, .pkz, atau .zip."],
                        parse_error="Unsupported file extension",
                    )
                )

        if not results:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada file .pkt, .pka, atau .pkz ditemukan di dalam unggahan atau arsip ZIP.",
            )

        roster_cache = roster.list_students()
        if roster_cache:
            enriched: list[StudentReport] = []
            for item in results:
                match = roster.match_student(
                    filename=item.filename,
                    source_path=item.source_path,
                    parsed_nim=item.nim,
                    parsed_name=item.student_name,
                    preferred_prodi=prodi,
                    preferred_kelas=kelas,
                    roster_cache=roster_cache,
                )
                if match is not None:
                    enriched.append(
                        item.model_copy(
                            update={
                                "nim": match.student.nim,
                                "student_name": match.student.nama,
                                "matched_prodi": match.student.prodi,
                                "matched_kelas": match.student.kelas,
                                "match_source": match.method,
                                "match_confidence": match.confidence,
                            }
                        )
                    )
                else:
                    enriched.append(item)
            results = enriched

        batch = summarize_batch(results, rubric)
        if save_history:
            try:
                batch = store.save_run(batch, prodi=prodi, kelas=kelas, note=note)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return batch

    @app.get("/api/roster")
    def list_roster(
        prodi: str | None = Query(default=None),
        kelas: str | None = Query(default=None),
        q: str | None = Query(default=None),
    ) -> dict[str, object]:
        items = roster.list_students(prodi=prodi or None, kelas=kelas or None, query=q or None)
        return {
            "total": roster.count(),
            "counts": roster.counts_by_prodi_kelas(),
            "students": [s.model_dump() for s in items],
        }

    @app.post("/api/roster/import")
    async def import_roster_csv(
        file: UploadFile = File(...),
        replace: bool = Form(default=True),
    ) -> dict[str, object]:
        raw = await file.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        try:
            return roster.import_csv_text(text, replace=replace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/history", response_model=list[HistoryRunMeta])
    def list_history(
        prodi: str | None = Query(default=None),
        kelas: str | None = Query(default=None),
    ) -> list[HistoryRunMeta]:
        return store.list_runs(prodi=prodi or None, kelas=kelas or None)

    @app.get("/api/history/export/csv")
    def export_history_csv(
        prodi: str | None = Query(default=None),
        kelas: str | None = Query(default=None),
    ) -> Response:
        runs = store.list_full_runs(prodi=prodi or None, kelas=kelas or None)
        if not runs:
            raise HTTPException(status_code=404, detail="Tidak ada data riwayat untuk filter yang dipilih.")
        csv_text = batches_to_csv_string(runs, include_bom=True)
        suffix = "_".join(p for p in [prodi, kelas] if p).lower() or "semua"
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="rekap_uap_{suffix}.csv"'},
        )

    @app.get("/api/history/export/class-csv")
    def export_class_rekap_csv(
        prodi: str = Query(...),
        kelas: str = Query(default=""),
    ) -> Response:
        try:
            clean_prodi, clean_kelas = validate_prodi_kelas(prodi, kelas)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not clean_prodi:
            raise HTTPException(status_code=400, detail="Parameter prodi (PTI atau TI) wajib dipilih.")

        students = roster.list_students(prodi=clean_prodi, kelas=clean_kelas or None)
        if not students:
            raise HTTPException(
                status_code=404,
                detail="Daftar roster praktikan untuk prodi/kelas ini belum tersedia. Impor CSV roster terlebih dahulu.",
            )
        all_runs = store.list_full_runs(limit=500)
        csv_text = class_rekap_to_csv_string(
            roster_students=students,
            runs=all_runs,
            prodi=clean_prodi,
            kelas=clean_kelas,
            include_bom=True,
        )
        suffix = "_".join(p for p in [clean_prodi, clean_kelas] if p).lower()
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="rekap_lengkap_{suffix}.csv"'},
        )

    @app.get("/api/history/{run_id}", response_model=BatchReport)
    def get_history_run(run_id: str) -> BatchReport:
        found = store.get_run(run_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Data riwayat evaluasi tidak ditemukan.")
        return found

    @app.patch("/api/history/{run_id}/assign", response_model=BatchReport)
    def assign_history_student(run_id: str, payload: AssignStudentRequest) -> BatchReport:
        if payload.nim is not None and payload.nim.strip():
            student = roster.get_by_nim(payload.nim)
            if student is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Praktikan dengan NIM '{payload.nim}' tidak ditemukan pada roster.",
                )
            try:
                updated = store.update_student_assignment(
                    run_id,
                    payload.source_path,
                    nim=student.nim,
                    student_name=student.nama,
                    matched_prodi=student.prodi,
                    matched_kelas=student.kelas,
                    match_source="manual",
                    match_confidence=1.0,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        elif payload.custom_nim or payload.custom_name:
            clean_p, clean_k = "", ""
            if payload.custom_prodi:
                try:
                    clean_p, clean_k = validate_prodi_kelas(
                        payload.custom_prodi, payload.custom_kelas or ""
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            try:
                updated = store.update_student_assignment(
                    run_id,
                    payload.source_path,
                    nim=(payload.custom_nim or "").strip(),
                    student_name=(payload.custom_name or "").strip(),
                    matched_prodi=clean_p,
                    matched_kelas=clean_k,
                    match_source="manual",
                    match_confidence=1.0,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            # Reset assignment back to filename-parsed identity
            existing = store.get_run(run_id)
            if existing is None:
                raise HTTPException(status_code=404, detail="Data riwayat evaluasi tidak ditemukan.")
            target_item = next(
                (i for i in existing.results if i.source_path == payload.source_path), None
            )
            if target_item is None:
                raise HTTPException(status_code=404, detail="Berkas tidak ditemukan pada riwayat ini.")
            f_nim, f_name = extract_student_identity(target_item.filename)
            updated = store.update_student_assignment(
                run_id,
                payload.source_path,
                nim=f_nim,
                student_name=f_name,
                matched_prodi="",
                matched_kelas="",
                match_source="filename" if f_nim else "unmatched",
                match_confidence=0.0,
            )

        if updated is None:
            raise HTTPException(status_code=404, detail="Data riwayat evaluasi tidak ditemukan.")
        return updated

    @app.delete("/api/history/{run_id}")
    def delete_history_run(run_id: str) -> dict[str, object]:
        deleted = store.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Data riwayat evaluasi tidak ditemukan.")
        return {"deleted": True, "id": run_id}

    @app.post("/api/export/csv")
    def export_csv(report: BatchReport) -> Response:
        csv_text = batch_to_csv_string(report, include_bom=True)
        cls_slug = (report.class_label or "uap").lower().replace(" ", "").replace("-", "_")
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="nilai_{cls_slug}.csv"'},
        )

    web_dist = _resolve_web_dist_dir()
    if web_dist is not None:
        assets_dir = web_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str) -> FileResponse:
            target = web_dist / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(web_dist / "index.html")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("pkt_grader.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
