import { useMemo, useRef, useState } from "react";
import { PRODI_CLASSES, type HistoryRunMeta, type ProdiCode } from "../types";
import { DownloadIcon, UploadIcon } from "./Icons";

interface HistoryViewProps {
  runs: HistoryRunMeta[];
  loading: boolean;
  openingId: string | null;
  deletingId: string | null;
  exporting: boolean;
  exportingClass: boolean;
  rosterTotal: number;
  rosterCounts: Record<string, number>;
  importingRoster: boolean;
  rosterNotice: string | null;
  onOpenRun: (runId: string) => void;
  onDeleteRun: (runId: string) => void;
  onExportCombinedCsv: (prodi?: string, kelas?: string) => void;
  onExportClassRekapCsv: (prodi: string, kelas?: string) => void;
  onImportRosterCsv: (file: File) => void;
}

function formatDateWib(iso: string): string {
  try {
    return new Intl.DateTimeFormat("id-ID", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function HistoryView({
  runs,
  loading,
  openingId,
  deletingId,
  exporting,
  exportingClass,
  rosterTotal,
  rosterCounts,
  importingRoster,
  rosterNotice,
  onOpenRun,
  onDeleteRun,
  onExportCombinedCsv,
  onExportClassRekapCsv,
  onImportRosterCsv,
}: HistoryViewProps) {
  const [prodiFilter, setProdiFilter] = useState<"ALL" | ProdiCode>("ALL");
  const [kelasFilter, setKelasFilter] = useState<string>("ALL");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const rosterInputRef = useRef<HTMLInputElement>(null);

  const availableClasses = prodiFilter === "ALL" ? [] : PRODI_CLASSES[prodiFilter];

  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (prodiFilter !== "ALL" && r.prodi !== prodiFilter) return false;
      if (prodiFilter !== "ALL" && kelasFilter !== "ALL" && r.kelas !== kelasFilter) return false;
      return true;
    });
  }, [runs, prodiFilter, kelasFilter]);

  const classCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const r of runs) {
      if (r.prodi) map[r.prodi] = (map[r.prodi] ?? 0) + 1;
      if (r.class_label) map[r.class_label] = (map[r.class_label] ?? 0) + 1;
    }
    return map;
  }, [runs]);

  const handleProdiChange = (next: "ALL" | ProdiCode) => {
    setProdiFilter(next);
    setKelasFilter("ALL");
  };

  return (
    <section className="history-section" aria-label="Riwayat evaluasi tersimpan">
      <div className="roster-bar">
        <div className="roster-bar-info">
          <span className="metric-label">ROSTER PRAKTIKAN AUTO-DETECT</span>
          <div className="roster-bar-stats">
            {rosterTotal > 0 ? (
              <span>
                <strong>{rosterTotal}</strong> praktikan terdaftar (PTI: {rosterCounts["PTI"] ?? 0} ·
                TI: {rosterCounts["TI"] ?? 0})
              </span>
            ) : (
              <span>Belum ada data roster diimpor. Unggah CSV Data Praktikan untuk auto-detect NIM/Nama.</span>
            )}
            {rosterNotice && <span className="metric-label">{rosterNotice}</span>}
          </div>
        </div>
        <div className="roster-bar-actions">
          <input
            ref={rosterInputRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label="Impor berkas CSV roster praktikan"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                onImportRosterCsv(file);
              }
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            disabled={importingRoster}
            onClick={() => rosterInputRef.current?.click()}
          >
            <UploadIcon />
            {importingRoster ? "Mengimpor..." : "Impor Roster CSV"}
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="toolbar-row">
          <div className="filter-group" role="group" aria-label="Filter program studi">
            {(["ALL", "PTI", "TI"] as const).map((code) => {
              const label = code === "ALL" ? "Semua Prodi" : code;
              const cnt = code === "ALL" ? runs.length : classCounts[code] ?? 0;
              return (
                <button
                  key={code}
                  type="button"
                  className="filter-btn"
                  aria-pressed={prodiFilter === code}
                  onClick={() => handleProdiChange(code)}
                >
                  <span>{label}</span>
                  <span className="filter-count">{cnt}</span>
                </button>
              );
            })}
          </div>

          <div className="toolbar-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={exporting || filteredRuns.length === 0}
              onClick={() =>
                onExportCombinedCsv(
                  prodiFilter === "ALL" ? undefined : prodiFilter,
                  prodiFilter !== "ALL" && kelasFilter !== "ALL" ? kelasFilter : undefined
                )
              }
            >
              <DownloadIcon />
              {exporting ? "Menyiapkan CSV..." : "Ekspor Rekap CSV"}
            </button>

            {prodiFilter !== "ALL" && rosterTotal > 0 && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={exportingClass}
                onClick={() =>
                  onExportClassRekapCsv(
                    prodiFilter,
                    kelasFilter !== "ALL" ? kelasFilter : undefined
                  )
                }
              >
                <DownloadIcon />
                {exportingClass
                  ? "Menyiapkan..."
                  : kelasFilter !== "ALL"
                    ? `Rekap Lengkap ${prodiFilter} - ${kelasFilter}`
                    : `Rekap Lengkap ${prodiFilter}`}
              </button>
            )}
          </div>
        </div>

        {prodiFilter !== "ALL" && (
          <div className="filter-group" role="group" aria-label={`Filter kelas ${prodiFilter}`}>
            <button
              type="button"
              className="filter-btn"
              aria-pressed={kelasFilter === "ALL"}
              onClick={() => setKelasFilter("ALL")}
            >
              <span>Semua {prodiFilter}</span>
              <span className="filter-count">{classCounts[prodiFilter] ?? 0}</span>
            </button>
            {availableClasses.map((k) => {
              const label = `${prodiFilter} - ${k}`;
              return (
                <button
                  key={k}
                  type="button"
                  className="filter-btn"
                  aria-pressed={kelasFilter === k}
                  onClick={() => setKelasFilter(k)}
                >
                  <span>{label}</span>
                  <span className="filter-count">{classCounts[label] ?? 0}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {loading ? (
        <div className="empty-state">
          <p className="metric-label">MEMUAT RIWAYAT</p>
          <p className="empty-desc">Mengambil data riwayat evaluasi tersimpan dari server...</p>
        </div>
      ) : filteredRuns.length === 0 ? (
        <div className="empty-state">
          <p className="metric-label">RIWAYAT KOSONG</p>
          <h2 className="empty-title">Belum ada riwayat evaluasi untuk filter ini</h2>
          <p className="empty-desc">
            Setiap kali evaluasi dijalankan pada tab Evaluasi, hasil analisis kelas (termasuk
            indikator, diff konfigurasi, dan nilai) akan tersimpan otomatis di sini.
          </p>
        </div>
      ) : (
        <div className="history-list">
          {filteredRuns.map((run) => {
            const isOpening = openingId === run.id;
            const isDeleting = deletingId === run.id;
            const isConfirming = confirmDeleteId === run.id;

            return (
              <article key={run.id} className="history-card">
                <div className="history-card-main">
                  <div className="history-title-row">
                    <span className="class-badge">{run.class_label}</span>
                    <span className="metric-label">{formatDateWib(run.created_at)}</span>
                    {run.note && <span className="history-note">{run.note}</span>}
                  </div>
                  <div className="history-metrics mono">
                    <span>{run.total} berkas</span>
                    <span>Lulus: {run.passed} ({run.pass_rate.toFixed(1)}%)</span>
                    <span>Rata-rata: {run.average_score.toFixed(1)}%</span>
                  </div>
                </div>

                <div className="history-card-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={isOpening || isDeleting}
                    onClick={() => onOpenRun(run.id)}
                  >
                    {isOpening ? "Membuka..." : "Buka analisis"}
                  </button>

                  {isConfirming ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-destructive"
                        disabled={isDeleting}
                        onClick={() => {
                          setConfirmDeleteId(null);
                          onDeleteRun(run.id);
                        }}
                      >
                        {isDeleting ? "Menghapus..." : "Konfirmasi hapus"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={isDeleting}
                        onClick={() => setConfirmDeleteId(null)}
                      >
                        Batal
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-destructive"
                      disabled={isOpening || isDeleting}
                      onClick={() => setConfirmDeleteId(run.id)}
                    >
                      Hapus
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
