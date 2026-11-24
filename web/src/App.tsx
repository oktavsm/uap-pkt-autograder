import { useEffect, useMemo, useState } from "react";
import { downloadCsvReport, downloadJsonReport, fetchRubric, gradeFiles } from "./api";
import { Dropzone } from "./components/Dropzone";
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
import type { BatchReport, RubricCheckMeta, RubricConfig, StudentStatus } from "./types";

type StatusFilter = "all" | StudentStatus;
type SortKey = "score_desc" | "score_asc" | "nim_asc" | "name_asc";

const SORT_OPTIONS = [
  { value: "score_desc", label: "Skor tertinggi" },
  { value: "score_asc", label: "Skor terendah" },
  { value: "nim_asc", label: "NIM A-Z" },
  { value: "name_asc", label: "Nama A-Z" },
];

const FALLBACK_RUBRIC: RubricConfig = {
  name: "UAP Jaringan Komputer PTI",
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
      {status === "error" ? "ERROR" : "GAGAL"}
    </span>
  );
}

export function App() {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = window.localStorage.getItem("netgrade-theme");
    return saved === "light" ? "light" : "dark";
  });

  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [rubric, setRubric] = useState<RubricConfig>(FALLBACK_RUBRIC);
  const [defaultRubric, setDefaultRubric] = useState<RubricConfig>(FALLBACK_RUBRIC);
  const [checkCatalog, setCheckCatalog] = useState<RubricCheckMeta[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortKey>("score_desc");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("netgrade-theme", theme);
  }, [theme]);

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
  }, []);

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
      const result = await gradeFiles(queuedFiles, rubric);
      setReport(result);
      setStatusFilter("all");
      setSearch("");
      setSelectedKey(result.results[0]?.source_path ?? null);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Terjadi kesalahan saat menilai berkas.");
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = async () => {
    if (!report) return;
    setExportingCsv(true);
    setErrorMsg(null);
    try {
      await downloadCsvReport(report);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Gagal mengekspor CSV.");
    } finally {
      setExportingCsv(false);
    }
  };

  const counts = useMemo(() => {
    const items = report?.results ?? [];
    return {
      all: items.length,
      pass: items.filter((r) => r.status === "pass").length,
      partial: items.filter((r) => r.status === "partial").length,
      fail: items.filter((r) => r.status === "fail" || r.status === "error").length,
    };
  }, [report]);

  const filteredResults = useMemo(() => {
    if (!report) return [];
    const q = search.trim().toLowerCase();
    const list = report.results.filter((r) => {
      if (statusFilter === "pass" && r.status !== "pass") return false;
      if (statusFilter === "partial" && r.status !== "partial") return false;
      if (statusFilter === "fail" && r.status !== "fail" && r.status !== "error") return false;
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

  const totalRubricPoints = Object.values(rubric.weights).reduce((a, b) => a + b, 0);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="container topbar-inner">
          <a href="#top" className="brand">
            <span className="brand-mark">
              <NetworkMarkIcon size={16} />
            </span>
            <span>
              netgrade<span className="brand-dot">.uap</span>
            </span>
          </a>

          <div className="topbar-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setDrawerOpen(true)}
            >
              <SlidersIcon />
              Rubrik ({totalRubricPoints} pts)
            </button>

            {report && (
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
                  JSON
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
          <section className="intake-section" aria-labelledby="hero-heading">
            <div className="hero-copy">
              <p className="eyebrow">UAP JARINGAN KOMPUTER PTI · PACKET TRACER 9.0</p>
              <h1 id="hero-heading" className="hero-title">
                Penilaian topologi <em>tanpa buka GUI.</em>
              </h1>
              <p className="hero-lead">
                Unggah arsip ZIP atau kumpulan file .pkt/.pka mahasiswa. Mesin memeriksa VLAN,
                trunk, DHCP pool, static route dua arah, lease PC1/PC2, serta write memory dalam
                hitungan detik.
              </p>

              <dl className="spec-list">
                <div className="spec-row">
                  <dt>Format didukung</dt>
                  <dd className="mono">.pkt, .pka, .zip</dd>
                </div>
                <div className="spec-row">
                  <dt>Item evaluasi</dt>
                  <dd className="mono">19 aturan · {totalRubricPoints} poin</dd>
                </div>
                <div className="spec-row">
                  <dt>Ambang lulus</dt>
                  <dd className="mono">&gt;= {rubric.pass_threshold}%</dd>
                </div>
              </dl>
            </div>

            <Dropzone
              files={queuedFiles}
              loading={loading}
              onAddFiles={handleAddFiles}
              onRemoveFile={handleRemoveFile}
              onClearFiles={handleClearFiles}
              onRunGrade={handleRunGrade}
            />
          </section>

          {errorMsg && (
            <div className="results-section">
              <div className="alert" role="alert">
                <CloseIcon size={16} />
                <div>{errorMsg}</div>
              </div>
            </div>
          )}

          {!report && !errorMsg && (
            <section className="results-section" aria-label="Status hasil">
              <div className="empty-state">
                <p className="metric-label">MENUNGGU BERKAS</p>
                <h2 className="empty-title">Belum ada hasil penilaian</h2>
                <p className="empty-desc">
                  Tarik file .zip kelas atau beberapa file .pkt ke panel unggah di atas lalu klik
                  Nilai sekarang. Hasil per mahasiswa, kesalahan konfigurasi, dan tombol unduh CSV
                  akan tampil di sini.
                </p>
              </div>
            </section>
          )}

          {report && (
            <section className="results-section" aria-label="Ringkasan dan daftar nilai">
              <div className="summary-grid">
                <div className="metric-hero-card">
                  <span className="metric-label">RATA-RATA SKOR KELAS</span>
                  <div className="metric-hero-value">{report.summary.average_score.toFixed(1)}%</div>
                  <p className="metric-sub">
                    {report.summary.passed} dari {report.summary.total} mahasiswa lulus (
                    {report.summary.pass_rate.toFixed(1)}%).
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
                    <span className="stat-value">{report.summary.highest_score.toFixed(1)}%</span>
                  </div>
                  <div className="stat-cell">
                    <span className="metric-label">TERENDAH</span>
                    <span className="stat-value">{report.summary.lowest_score.toFixed(1)}%</span>
                  </div>
                </div>

                <div className="common-failures-panel">
                  <span className="metric-label">KESALAHAN PALING SERING</span>
                  {report.summary.common_failures.length === 0 ? (
                    <p className="metric-sub">Tidak ada kesalahan di seluruh berkas.</p>
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
                      Cari NIM, nama mahasiswa, atau nama file
                    </label>
                    <input
                      id="student-search"
                      type="search"
                      className="search-input"
                      placeholder="Cari NIM, nama mahasiswa, atau nama file..."
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
                        ["fail", "Gagal", counts.fail],
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
                  <h3 className="empty-title">Tidak ada hasil yang cocok</h3>
                  <p className="empty-desc">
                    Ubah kata kunci pencarian atau pilih filter status lain untuk melihat daftar
                    mahasiswa.
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
                                  <span>{student.errors.length} salah</span>
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

                  {activeStudent && <StudentDetail student={activeStudent} />}
                </div>
              )}
            </section>
          )}
        </div>
      </main>

      <footer className="site-footer">
        <div className="container footer-inner">
          <span>netgrade.uap · Offline Semantic Packet Tracer Autograder</span>
          <span className="mono">CLI: pkt-grade submissions.zip --csv nilai.csv</span>
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
    </div>
  );
}
