"""FastAPI web backend for drag-and-drop batch grading and CSV export."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from pkt_grader.engine import grade_archive_bytes, grade_bytes, summarize_batch
from pkt_grader.exporter import batch_to_csv_string
from pkt_grader.models import BatchReport, RubricConfig, StudentReport


WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"

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
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="UAP Packet Tracer Autograder",
        version="1.0.0",
        description="Offline semantic grading API for Cisco Packet Tracer (.pkt/.pka/.zip).",
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

    @app.get("/api/rubric")
    def get_rubric() -> dict[str, object]:
        return {
            "rubric": RubricConfig().model_dump(),
            "checks": CHECK_CATALOG,
        }

    @app.post("/api/grade", response_model=BatchReport)
    async def grade_uploads(
        files: list[UploadFile] = File(...),
        rubric_json: str | None = Form(default=None),
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
                        errors=[f"Ekstensi tidak didukung ('{suffix or 'tanpa ekstensi'}'). Gunakan .pkt, .pka, atau .zip."],
                        parse_error="Unsupported file extension",
                    )
                )

        if not results:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada file .pkt atau .pka ditemukan di dalam unggahan atau arsip ZIP.",
            )

        return summarize_batch(results, rubric)

    @app.post("/api/export/csv")
    def export_csv(report: BatchReport) -> Response:
        csv_text = batch_to_csv_string(report, include_bom=True)
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="uap_grades.csv"'},
        )

    if WEB_DIST_DIR.exists():
        assets_dir = WEB_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str) -> FileResponse:
            target = WEB_DIST_DIR / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST_DIR / "index.html")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("pkt_grader.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
