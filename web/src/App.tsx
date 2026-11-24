import { useCallback, useEffect, useMemo, useState } from "react";
import {
  assignHistoryStudent,
  deleteHistoryRun,
  downloadClassRekapCsv,
  downloadCsvReport,
  downloadHistoryCsv,
  downloadJsonReport,
  fetchHistory,
  fetchHistoryRun,
  fetchRoster,
  fetchRubric,
  gradeFiles,
  importRosterCsv,
} from "./api";
import { AssignStudentModal } from "./components/AssignStudentModal";
import { Dropzone } from "./components/Dropzone";
import { HistoryView } from "./components/HistoryView";
import {
  CheckIcon,
  CloseIcon,
  DownloadIcon,
  MinusCircleIcon,
  MoonIcon,
  NetworkMarkIcon,
  SearchIcon,
  SlidersIcon,
  SunIcon,
} from "./components/Icons";
import { RubricDrawer } from "./components/RubricDrawer";
import { SortListbox } from "./components/SortListbox";
import { StudentDetail } from "./components/StudentDetail";
import {
  PRODI_CLASSES,
  type BatchReport,
  type HistoryRunMeta,
  type ProdiCode,
  type RosterResponse,
  type RubricCheckMeta,
  type RubricConfig,
  type StudentReport,
  type StudentRosterEntry,
  type StudentStatus,
} from "./types";

type AppView = "evaluate" | "history";
type StatusFilter = "all" | StudentStatus | "unmatched";
type SortKey = "score_desc" | "score_asc" | "nim_asc" | "name_asc";

const SORT_OPTIONS = [
  { value: "score_desc", label: "Skor tertinggi" },
  { value: "score_asc", label: "Skor terendah" },
  { value: "nim_asc", label: "NIM A-Z" },
  { value: "name_asc", label: "Nama A-Z" },
];

const FALLBACK_RUBRIC: RubricConfig = {
  name: "UAP Jaringan Komputer TI/PTI",
  pass_threshold: 70,
  allow_exit_interface_route: false,
  require_explicit_trunk_allowed: true,
  weights: {
    topo_devices: 2,
    topo_links: 3,
    s1_vlans: 5,
    s1_access_fa01: 5,
    s1_access_fa02: 5,
    s1_trunk_mode: 5,
    s1_trunk_allowed: 5,
    r1_base_ip: 4,
    r1_dhcp_excl_10: 5,
    r1_dhcp_excl_20: 5,
    r1_dhcp_pool_10: 8,
    r1_dhcp_pool_20: 8,
    r2_base_ip: 2,
    r1_route_lanb: 6,
    r2_route_vlan10: 6,
    r2_route_vlan20: 6,
    pc1_dhcp: 7,
    pc2_dhcp: 7,
    save_config: 6,
    opt_dns: 5,
  },
};

function RowStatusBadge({ status }: { status: StudentStatus }) {
  if (status === "pass") {
    return (
      <span className="status-badge status-pass">
        <CheckIcon size={12} />
        LULUS
      </span>
    );
  }
  if (status === "partial") {
    return (
      <span className="status-badge status-partial">
        <MinusCircleIcon size={12} />
        PARSIAL
      </span>
    );
  }
  return (
    <span className="status-badge status-fail">
      <CloseIcon size={12} />
      {status === "error" ? "GALAT" : "TIDAK LULUS"}
    </span>
  );
}

function formatRunDate(iso?: string | null): string {
  if (!iso) return "";
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

export function App() {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = window.localStorage.getItem("netgrade-theme");
    return saved === "light" ? "light" : "dark";
  });

  const [view, setView] = useState<AppView>("evaluate");
  const [prodi, setProdi] = useState<ProdiCode>("PTI");
  const [kelas, setKelas] = useState<string>("A");
  const [note, setNote] = useState<string>("");

  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [rubric, setRubric] = useState<RubricConfig>(FALLBACK_RUBRIC);
  const [defaultRubric, setDefaultRubric] = useState<RubricConfig>(FALLBACK_RUBRIC);
  const [checkCatalog, setCheckCatalog] = useState<RubricCheckMeta[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);

  const [historyRuns, setHistoryRuns] = useState<HistoryRunMeta[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [openingRunId, setOpeningRunId] = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [exportingHistory, setExportingHistory] = useState(false);
  const [exportingClassCsv, setExportingClassCsv] = useState(false);

  const [rosterData, setRosterData] = useState<RosterResponse>({
    total: 0,
    counts: {},
    students: [],
  });
  const [importingRoster, setImportingRoster] = useState(false);
  const [rosterNotice, setRosterNotice] = useState<string | null>(null);
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [assignSaving, setAssignSaving] = useState(false);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortKey>("score_desc");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("netgrade-theme", theme);
  }, [theme]);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const items = await fetchHistory();
      setHistoryRuns(items);
    } catch {
      // Keep existing state if server momentarily unavailable
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshRoster = useCallback(async () => {
    try {
      const data = await fetchRoster();
      setRosterData(data);
    } catch {
      // Keep existing state if server momentarily unavailable
    }
  }, []);

  useEffect(() => {
    fetchRubric()
      .then((data) => {
        setRubric(data.rubric);
        setDefaultRubric(data.rubric);
        setCheckCatalog(data.checks);
      })
      .catch(() => {
        // Fallback rubric already loaded
      });
    void refreshHistory();
    void refreshRoster();
  }, [refreshHistory, refreshRoster]);

  const handleProdiChange = (nextProdi: ProdiCode) => {
    setProdi(nextProdi);
    if (!PRODI_CLASSES[nextProdi].includes(kelas)) {
      setKelas(PRODI_CLASSES[nextProdi][0]);
    }
  };

  const handleAddFiles = (incoming: File[]) => {
    setErrorMsg(null);
    setQueuedFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const next = [...prev];
      for (const file of incoming) {
        const key = `${file.name}:${file.size}`;
        if (!seen.has(key)) {
          seen.add(key);
          next.push(file);
        }
      }
      return next;
    });
  };

  const handleRemoveFile = (index: number) => {
    setQueuedFiles((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleClearFiles = () => {
    setQueuedFiles([]);
    setErrorMsg(null);
  };

  const handleRunGrade = async () => {
    if (queuedFiles.length === 0) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const result = await gradeFiles(queuedFiles, rubric, { prodi, kelas, note });
      setReport(result);
      setStatusFilter("all");
      setSearch("");
      setSelectedKey(result.results[0]?.source_path ?? null);
      void refreshHistory();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Terjadi kesalahan saat memproses berkas.");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenHistoryRun = async (runId: string) => {
    setOpeningRunId(runId);
    setErrorMsg(null);
    try {
      const loaded = await fetchHistoryRun(runId);
      setReport(loaded);
      setStatusFilter("all");
      setSearch("");
      setSelectedKey(loaded.results[0]?.source_path ?? null);
      setView("evaluate");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal membuka riwayat evaluasi.");
    } finally {
      setOpeningRunId(null);
    }
  };

  const handleDeleteHistoryRun = async (runId: string) => {
    setDeletingRunId(runId);
    setErrorMsg(null);
    try {
      await deleteHistoryRun(runId);
      setHistoryRuns((prev) => prev.filter((r) => r.id !== runId));
      if (report?.run_id === runId) {
        setReport(null);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal menghapus riwayat.");
    } finally {
      setDeletingRunId(null);
    }
  };

  const handleExportHistoryCsv = async (p?: string, k?: string) => {
    setExportingHistory(true);
    setErrorMsg(null);
    try {
      await downloadHistoryCsv(p, k);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal mengunduh rekap CSV.");
    } finally {
      setExportingHistory(false);
    }
  };

  const handleExportClassRekapCsv = async (p: string, k?: string) => {
    setExportingClassCsv(true);
    setErrorMsg(null);
    try {
      await downloadClassRekapCsv(p, k);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal mengunduh rekap lengkap kelas.");
    } finally {
      setExportingClassCsv(false);
    }
  };

  const handleImportRosterCsv = async (file: File) => {
    setImportingRoster(true);
    setErrorMsg(null);
    setRosterNotice(null);
    try {
      const res = await importRosterCsv(file, true);
      await refreshRoster();
      setRosterNotice(
        `Berhasil mengimpor ${res.imported} praktikan (${res.skipped} baris non-PTI/TI dilewati).`
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal mengimpor berkas CSV data praktikan.");
    } finally {
      setImportingRoster(false);
    }
  };

  const handleAssignStudent = async (entry: StudentRosterEntry) => {
    if (!report || !activeStudent) return;
    setAssignSaving(true);
    setErrorMsg(null);
    try {
      if (report.run_id) {
        const updated = await assignHistoryStudent(report.run_id, {
          source_path: activeStudent.source_path,
          nim: entry.nim,
        });
        setReport(updated);
      } else {
        setReport((prev) =>
          prev
            ? {
                ...prev,
                results: prev.results.map((r) =>
                  r.source_path === activeStudent.source_path
                    ? {
                        ...r,
                        nim: entry.nim,
                        student_name: entry.nama,
                        matched_prodi: entry.prodi,
                        matched_kelas: entry.kelas,
                        match_source: "manual",
                        match_confidence: 1,
                      }
                    : r
                ),
              }
            : prev
        );
      }
      setAssignModalOpen(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal menyimpan assignment praktikan.");
    } finally {
      setAssignSaving(false);
    }
  };

  const handleUnassignStudent = async () => {
    if (!report || !activeStudent) return;
    setAssignSaving(true);
    setErrorMsg(null);
    try {
      if (report.run_id) {
        const updated = await assignHistoryStudent(report.run_id, {
          source_path: activeStudent.source_path,
          nim: null,
        });
        setReport(updated);
      } else {
        setReport((prev) =>
          prev
            ? {
                ...prev,
                results: prev.results.map((r) =>
                  r.source_path === activeStudent.source_path
                    ? {
                        ...r,
                        nim: "",
                        matched_prodi: "",
                        matched_kelas: "",
                        match_source: "unmatched",
                        match_confidence: 0,
                      }
                    : r
                ),
              }
            : prev
        );
      }
      setAssignModalOpen(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal melepas assignment praktikan.");
    } finally {
      setAssignSaving(false);
    }
  };

  const handleExportCsv = async () => {
    if (!report) return;
    setExportingCsv(true);
    setErrorMsg(null);
    try {
      await downloadCsvReport(report);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal mengekspor berkas CSV.");
    } finally {
      setExportingCsv(false);
    }
  };

  const isRosterMatched = (r: StudentReport) =>
    r.match_source === "roster_nim" ||
    r.match_source === "roster_name" ||
    r.match_source === "manual";

  const counts = useMemo(() => {
    const items = report?.results ?? [];
    return {
      all: items.length,
      pass: items.filter((r) => r.status === "pass").length,
      partial: items.filter((r) => r.status === "partial").length,
      fail: items.filter((r) => r.status === "fail" || r.status === "error").length,
      unmatched: items.filter((r) => !isRosterMatched(r)).length,
    };
  }, [report]);

  const assignedNimsInBatch = useMemo(() => {
    const set = new Set<string>();
    for (const r of report?.results ?? []) {
      if (r.nim && isRosterMatched(r)) {
        set.add(r.nim);
      }
    }
    return set;
  }, [report]);

  const filteredResults = useMemo(() => {
    if (!report) return [];
    const q = search.trim().toLowerCase();
    const list = report.results.filter((r) => {
      if (statusFilter === "pass" && r.status !== "pass") return false;
      if (statusFilter === "partial" && r.status !== "partial") return false;
      if (statusFilter === "fail" && r.status !== "fail" && r.status !== "error") return false;
      if (statusFilter === "unmatched" && isRosterMatched(r)) return false;
      if (!q) return true;
      return (
        r.filename.toLowerCase().includes(q) ||
        r.nim.toLowerCase().includes(q) ||
        r.student_name.toLowerCase().includes(q)
      );
    });

    const sorted = [...list];
    sorted.sort((a, b) => {
      if (sortBy === "score_desc") return b.percentage - a.percentage;
      if (sortBy === "score_asc") return a.percentage - b.percentage;
      if (sortBy === "nim_asc") return (a.nim || a.filename).localeCompare(b.nim || b.filename);
      return (a.student_name || a.filename).localeCompare(b.student_name || b.filename);
    });
    return sorted;
  }, [report, search, statusFilter, sortBy]);

  const activeStudent = useMemo(() => {
    if (filteredResults.length === 0) return null;
    return filteredResults.find((r) => r.source_path === selectedKey) ?? filteredResults[0];
  }, [filteredResults, selectedKey]);

  const mandatoryRubricPoints = Object.entries(rubric.weights)
    .filter(([key]) => key !== "opt_dns")
    .reduce((sum, [, val]) => sum + val, 0);
  const dnsBonusPoints = rubric.weights["opt_dns"] ?? 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="container topbar-inner">
          <a href="#top" className="brand">
            <span className="brand-mark">
              <NetworkMarkIcon size={16} />
            </span>
            <span>
              UAP Autograder<span className="brand-dot"> · Jaringan Komputer TI/PTI</span>
            </span>
          </a>

          <div className="topbar-actions">
            <div className="filter-group" role="tablist" aria-label="Navigasi tampilan">
              <button
                type="button"
                role="tab"
                aria-selected={view === "evaluate"}
                className="filter-btn"
                aria-pressed={view === "evaluate"}
                onClick={() => setView("evaluate")}
              >
                Evaluasi
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === "history"}
                className="filter-btn"
                aria-pressed={view === "history"}
                onClick={() => {
                  setView("history");
                  void refreshHistory();
                }}
              >
                <span>Riwayat</span>
                <span className="filter-count">{historyRuns.length}</span>
              </button>
            </div>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setDrawerOpen(true)}
            >
              <SlidersIcon />
              Rubrik ({mandatoryRubricPoints} poin)
            </button>

            {report && view === "evaluate" && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={exportingCsv}
                  onClick={handleExportCsv}
                >
                  <DownloadIcon />
                  {exportingCsv ? "Menyiapkan..." : "Ekspor CSV"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => downloadJsonReport(report)}
                >
                  Ekspor JSON
                </button>
              </>
            )}

            <button
              type="button"
              className="btn btn-secondary btn-icon"
              aria-label={theme === "dark" ? "Ubah ke mode terang" : "Ubah ke mode gelap"}
              onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
        </div>
      </header>

      <main id="top" className="main-content">
        <div className="container">
          <div className="page-header">
            <h1 className="page-title">Evaluasi Konfigurasi Cisco Packet Tracer UAP PTI/TI</h1>
            <div className="page-meta-bar">
              <span>Format: .pkt, .pka, .zip</span>
              <span>Indikator wajib: 19 ({mandatoryRubricPoints} poin)</span>
              <span>Bonus opsional DNS: +{dnsBonusPoints} poin (maks. 100)</span>
              <span>Batas lulus: &gt;= {rubric.pass_threshold}%</span>
            </div>
          </div>

          {errorMsg && (
            <div className="error-wrap">
              <div className="alert" role="alert">
                <CloseIcon size={16} />
                <div>{errorMsg}</div>
              </div>
            </div>
          )}

          {view === "history" ? (
            <HistoryView
              runs={historyRuns}
              loading={historyLoading}
              openingId={openingRunId}
              deletingId={deletingRunId}
              exporting={exportingHistory}
              exportingClass={exportingClassCsv}
              rosterTotal={rosterData.total}
              rosterCounts={rosterData.counts}
              importingRoster={importingRoster}
              rosterNotice={rosterNotice}
              onOpenRun={handleOpenHistoryRun}
              onDeleteRun={handleDeleteHistoryRun}
              onExportCombinedCsv={handleExportHistoryCsv}
              onExportClassRekapCsv={handleExportClassRekapCsv}
              onImportRosterCsv={handleImportRosterCsv}
            />
          ) : (
            <>
              <section className="intake-section" aria-label="Panel unggah berkas">
                <Dropzone
                  files={queuedFiles}
                  loading={loading}
                  prodi={prodi}
                  kelas={kelas}
                  note={note}
                  onProdiChange={handleProdiChange}
                  onKelasChange={setKelas}
                  onNoteChange={setNote}
                  onAddFiles={handleAddFiles}
                  onRemoveFile={handleRemoveFile}
                  onClearFiles={handleClearFiles}
                  onRunGrade={handleRunGrade}
                />
              </section>

              {!report && !errorMsg && (
                <section className="results-section" aria-label="Status evaluasi">
                  <div className="empty-state">
                    <p className="metric-label">STATUS EVALUASI</p>
                    <h2 className="empty-title">Belum terdapat data penilaian</h2>
                    <p className="empty-desc">
                      Pilih prodi dan kelas, unggah arsip .zip atau kumpulan berkas .pkt/.pka pada
                      panel di atas, lalu tekan Mulai evaluasi. Hasil akan tersimpan otomatis pada
                      tab Riwayat.
                    </p>
                  </div>
                </section>
              )}

              {report && (
                <section className="results-section" aria-label="Ringkasan dan daftar nilai">
                  {report.class_label && (
                    <div className="run-context-bar">
                      <span className="class-badge">{report.class_label}</span>
                      {report.created_at && (
                        <span className="metric-label">
                          Tersimpan: {formatRunDate(report.created_at)}
                        </span>
                      )}
                      {report.note && <span className="history-note">{report.note}</span>}
                    </div>
                  )}

                  <div className="summary-grid">
                    <div className="metric-hero-card">
                      <span className="metric-label">RATA-RATA SKOR</span>
                      <div className="metric-hero-value">
                        {report.summary.average_score.toFixed(1)}%
                      </div>
                      <p className="metric-sub">
                        {report.summary.passed} dari {report.summary.total} berkas memenuhi batas
                        lulus ({report.summary.pass_rate.toFixed(1)}%).
                      </p>
                    </div>

                    <div className="summary-stats-panel">
                      <div className="stat-cell">
                        <span className="metric-label">TOTAL BERKAS</span>
                        <span className="stat-value">{report.summary.total}</span>
                      </div>
                      <div className="stat-cell">
                        <span className="metric-label">MEDIAN</span>
                        <span className="stat-value">{report.summary.median_score.toFixed(1)}%</span>
                      </div>
                      <div className="stat-cell">
                        <span className="metric-label">TERTINGGI</span>
                        <span className="stat-value">
                          {report.summary.highest_score.toFixed(1)}%
                        </span>
                      </div>
                      <div className="stat-cell">
                        <span className="metric-label">TERENDAH</span>
                        <span className="stat-value">{report.summary.lowest_score.toFixed(1)}%</span>
                      </div>
                    </div>

                    <div className="common-failures-panel">
                      <span className="metric-label">KETIDAKSESUAIAN TERBANYAK</span>
                      {report.summary.common_failures.length === 0 ? (
                        <p className="metric-sub">
                          Tidak ditemukan ketidaksesuaian pada seluruh berkas.
                        </p>
                      ) : (
                        <div className="failure-bars">
                          {report.summary.common_failures.slice(0, 4).map((item) => (
                            <div key={item.check_id} className="failure-bar-item">
                              <div className="failure-bar-top">
                                <span>
                                  <strong className="mono">{item.device}</strong> {item.title}
                                </span>
                                <span className="mono metric-label">
                                  {item.count}/{report.summary.total} ({item.rate}%)
                                </span>
                              </div>
                              <div className="failure-track" aria-hidden="true">
                                <div
                                  className="failure-fill"
                                  style={{ width: `${Math.min(100, item.rate)}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="toolbar">
                    <div className="toolbar-row">
                      <div className="search-wrap">
                        <span className="search-icon">
                          <SearchIcon />
                        </span>
                        <label htmlFor="student-search" className="sr-only">
                          Cari NIM, nama mahasiswa, atau nama berkas
                        </label>
                        <input
                          id="student-search"
                          type="search"
                          className="search-input"
                          placeholder="Cari NIM, nama mahasiswa, atau nama berkas..."
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>

                      <div className="filter-group" role="group" aria-label="Filter status kelulusan">
                        {(
                          [
                            ["all", "Semua", counts.all],
                            ["pass", "Lulus", counts.pass],
                            ["partial", "Parsial", counts.partial],
                            ["fail", "Tidak lulus", counts.fail],
                            ...(rosterData.total > 0 && counts.unmatched > 0
                              ? ([["unmatched", "Belum cocok", counts.unmatched]] as [
                                  StatusFilter,
                                  string,
                                  number,
                                ][])
                              : []),
                          ] as [StatusFilter, string, number][]
                        ).map(([key, label, count]) => (
                          <button
                            key={key}
                            type="button"
                            className="filter-btn"
                            aria-pressed={statusFilter === key}
                            onClick={() => setStatusFilter(key)}
                          >
                            <span>{label}</span>
                            <span className="filter-count">{count}</span>
                          </button>
                        ))}
                      </div>

                      <SortListbox
                        label="Urutkan hasil"
                        value={sortBy}
                        options={SORT_OPTIONS}
                        onChange={(v) => setSortBy(v as SortKey)}
                      />
                    </div>
                  </div>

                  {filteredResults.length === 0 ? (
                    <div className="empty-state">
                      <h3 className="empty-title">Data tidak ditemukan</h3>
                      <p className="empty-desc">
                        Ubah kata kunci pencarian atau pilih filter status lain untuk menampilkan
                        daftar hasil evaluasi.
                      </p>
                    </div>
                  ) : (
                    <div className="workspace-split">
                      <nav className="ledger-card" aria-label="Daftar nilai mahasiswa">
                        <ul className="ledger-list">
                          {filteredResults.map((student) => {
                            const isSelected = activeStudent?.source_path === student.source_path;
                            return (
                              <li key={student.source_path} className="ledger-item">
                                <button
                                  type="button"
                                  className="ledger-row-btn"
                                  aria-selected={isSelected}
                                  onClick={() => setSelectedKey(student.source_path)}
                                >
                                  <div className="student-ident">
                                    <span className="student-name">
                                      {student.student_name || student.filename}
                                    </span>
                                    <span className="student-meta">
                                      <span>{student.nim || "Tanpa NIM"}</span>
                                      <span>· {student.errors.length} tidak sesuai</span>
                                      {student.matched_prodi && student.matched_kelas && (
                                        <span>
                                          · {student.matched_prodi} - {student.matched_kelas}
                                        </span>
                                      )}
                                      {rosterData.total > 0 && !isRosterMatched(student) && (
                                        <span className="meta-warn">· Belum cocok</span>
                                      )}
                                      {student.dns_optional_status !== "none" && (
                                        <span>
                                          · DNS:{" "}
                                          {student.dns_optional_status === "complete"
                                            ? "lengkap"
                                            : "parsial"}
                                        </span>
                                      )}
                                    </span>
                                  </div>
                                  <div className="student-score-col">
                                    <span className="score-num">{student.percentage.toFixed(0)}%</span>
                                    <RowStatusBadge status={student.status} />
                                  </div>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </nav>

                      {activeStudent && (
                        <StudentDetail
                          student={activeStudent}
                          rosterCount={rosterData.total}
                          onOpenAssign={() => setAssignModalOpen(true)}
                        />
                      )}
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </main>

      <footer className="site-footer">
        <div className="container footer-inner">
          <span>UAP Jaringan Komputer TI/PTI · Sistem Evaluasi Otomatis Packet Tracer</span>
          <span className="mono">CLI: pkt-grade submissions.zip --prodi TI --kelas A --csv nilai.csv</span>
        </div>
      </footer>

      <RubricDrawer
        open={drawerOpen}
        rubric={rubric}
        defaultRubric={defaultRubric}
        checks={checkCatalog}
        onChange={setRubric}
        onClose={() => setDrawerOpen(false)}
      />

      <AssignStudentModal
        open={assignModalOpen}
        student={activeStudent}
        roster={rosterData.students}
        assignedNims={assignedNimsInBatch}
        defaultProdi={report?.prodi || prodi}
        defaultKelas={report?.kelas || kelas}
        saving={assignSaving}
        onAssign={handleAssignStudent}
        onUnassign={handleUnassignStudent}
        onClose={() => setAssignModalOpen(false)}
      />
    </div>
  );
}
