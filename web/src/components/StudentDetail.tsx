import { useEffect, useState } from "react";
import type { CheckStatus, DiffLine, DnsOptionalStatus, MatchSource, StudentReport } from "../types";
import { CheckIcon, CloseIcon, CopyIcon, MinusCircleIcon } from "./Icons";

interface StudentDetailProps {
  student: StudentReport;
  rosterCount?: number;
  batchProdi?: string;
  batchKelas?: string;
  onOpenAssign?: () => void;
}

function MatchSourceBadge({
  source,
  matchedProdi,
  matchedKelas,
}: {
  source?: MatchSource;
  matchedProdi?: string;
  matchedKelas?: string;
}) {
  const classTag =
    matchedProdi && matchedKelas ? ` · ${matchedProdi} - ${matchedKelas}` : "";
  if (source === "roster_nim") {
    return (
      <span className="status-badge status-pass">
        <CheckIcon size={12} />
        COCOK: NIM{classTag}
      </span>
    );
  }
  if (source === "roster_name") {
    return (
      <span className="status-badge status-pass">
        <CheckIcon size={12} />
        COCOK: NAMA{classTag}
      </span>
    );
  }
  if (source === "manual") {
    return (
      <span className="status-badge status-optional">
        <CheckIcon size={12} />
        ASSIGN MANUAL{classTag}
      </span>
    );
  }
  return (
    <span className="status-badge status-partial">
      BELUM TERDETEKSI
    </span>
  );
}

type InspectorTab = "checks" | "S1" | "R1" | "R2" | "hosts";
type ConfigViewMode = "diff" | "raw";

function StatusBadge({ status, optional }: { status: CheckStatus | "error"; optional?: boolean }) {
  if (optional) {
    if (status === "pass") {
      return (
        <span className="status-badge status-optional">
          <CheckIcon size={12} />
          OPSIONAL · LENGKAP
        </span>
      );
    }
    if (status === "partial") {
      return (
        <span className="status-badge status-optional">
          <MinusCircleIcon size={12} />
          OPSIONAL · PARSIAL
        </span>
      );
    }
    return <span className="status-badge status-optional">OPSIONAL · TIDAK ADA</span>;
  }

  if (status === "pass") {
    return (
      <span className="status-badge status-pass">
        <CheckIcon size={12} />
        SESUAI
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
      {status === "error" ? "GALAT" : "TIDAK SESUAI"}
    </span>
  );
}

function DnsSummaryBadge({ status }: { status: DnsOptionalStatus }) {
  if (status === "complete") {
    return (
      <span className="status-badge status-optional">
        <CheckIcon size={12} />
        DNS OPSIONAL: LENGKAP
      </span>
    );
  }
  if (status === "partial") {
    return (
      <span className="status-badge status-optional">
        <MinusCircleIcon size={12} />
        DNS OPSIONAL: PARSIAL
      </span>
    );
  }
  return <span className="status-badge status-optional">DNS OPSIONAL: TIDAK DIKONFIGURASI</span>;
}

function DiffBlock({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="diff-box" role="region" aria-label="Perbandingan konfigurasi terhadap kunci jawaban">
      {lines.map((line, idx) => (
        <div key={`${line.kind}-${idx}`} className={`diff-line diff-line-${line.kind}`}>
          <span className="diff-prefix" aria-hidden="true">
            {line.prefix}
          </span>
          <span className="diff-text">{line.text}</span>
          {line.note && <span className="diff-note">{line.note}</span>}
        </div>
      ))}
    </div>
  );
}

export function StudentDetail({
  student,
  rosterCount = 0,
  batchProdi,
  batchKelas,
  onOpenAssign,
}: StudentDetailProps) {
  const [tab, setTab] = useState<InspectorTab>("checks");
  const [configMode, setConfigMode] = useState<ConfigViewMode>("diff");
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const hasClassMismatch = Boolean(
    student.matched_prodi &&
      student.matched_kelas &&
      batchProdi &&
      batchKelas &&
      (student.matched_prodi !== batchProdi || student.matched_kelas !== batchKelas)
  );
  const studentClassLabel =
    student.matched_prodi && student.matched_kelas
      ? `${student.matched_prodi} - ${student.matched_kelas}`
      : "";
  const batchClassLabel = batchProdi && batchKelas ? `${batchProdi} - ${batchKelas}` : "";

  useEffect(() => {
    setTab("checks");
    setConfigMode("diff");
    setCopiedKey(null);
  }, [student.source_path]);

  const visibleChecks = onlyErrors
    ? student.checks.filter((c) => !c.optional && c.status !== "pass")
    : student.checks;

  const copyConfig = async (deviceKey: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedKey(deviceKey);
      window.setTimeout(() => setCopiedKey(null), 1600);
    } catch {
      setCopiedKey(null);
    }
  };

  const renderConfigTab = (deviceKey: "S1" | "R1" | "R2") => {
    const dev = student.devices[deviceKey];
    const diffLines = student.config_diffs[deviceKey] ?? [];
    const diffPlainText = diffLines
      .map((l) => (l.kind === "header" ? l.text : `${l.prefix} ${l.text}${l.note ? `  # ${l.note}` : ""}`))
      .join("\n");

    return (
      <div className="config-viewer">
        <div className="config-bar">
          <div className="config-mode-group" role="group" aria-label={`Mode tampilan ${deviceKey}`}>
            <button
              type="button"
              className="filter-btn"
              aria-pressed={configMode === "diff"}
              onClick={() => setConfigMode("diff")}
            >
              Diff vs Kunci
            </button>
            <button
              type="button"
              className="filter-btn"
              aria-pressed={configMode === "raw"}
              onClick={() => setConfigMode("raw")}
            >
              Raw show run
            </button>
          </div>

          <div className="check-title-wrap">
            {dev && (
              <span className="metric-label">
                {dev.name} ({dev.model || dev.device_type}) · startup-config:{" "}
                {dev.has_startup_config ? "tersimpan" : "kosong"}
              </span>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={configMode === "raw" ? !dev?.running_config : diffLines.length === 0}
              onClick={() =>
                copyConfig(
                  `${deviceKey}-${configMode}`,
                  configMode === "raw" ? dev?.running_config ?? "" : diffPlainText
                )
              }
            >
              {copiedKey === `${deviceKey}-${configMode}` ? <CheckIcon /> : <CopyIcon />}
              {copiedKey === `${deviceKey}-${configMode}`
                ? "Tersalin"
                : configMode === "raw"
                  ? "Salin show run"
                  : "Salin diff"}
            </button>
          </div>
        </div>

        {configMode === "diff" ? (
          diffLines.length > 0 ? (
            <>
              <div className="diff-legend">
                <span>Spasi: sesuai kunci</span>
                <span>- : kurang dari kunci</span>
                <span>+ : beda / opsional aktif</span>
                <span>~ : opsional tidak diisi</span>
              </div>
              <DiffBlock lines={diffLines} />
            </>
          ) : (
            <div className="empty-state">
              <p className="empty-title">Diff konfigurasi {deviceKey} tidak tersedia</p>
              <p className="empty-desc">Data konfigurasi tidak ditemukan pada berkas ini.</p>
            </div>
          )
        ) : dev?.running_config ? (
          <pre className="config-pre">{dev.running_config}</pre>
        ) : (
          <div className="empty-state">
            <p className="empty-title">Konfigurasi {deviceKey} tidak tersedia</p>
            <p className="empty-desc">
              Perangkat {deviceKey} tidak ditemukan atau tidak memiliki running-config pada berkas ini.
            </p>
          </div>
        )}
      </div>
    );
  };

  const serverDiff = student.config_diffs["Server1"] ?? [];

  return (
    <section className="inspector-card" aria-label="Rincian hasil evaluasi mahasiswa">
      <div className="inspector-header">
        <div className="inspector-ident">
          <p className="metric-label">
            {student.nim ? `NIM ${student.nim}` : "Tanpa NIM"} · {student.filename}
          </p>
          <h3 className="inspector-title">{student.student_name || student.filename}</h3>
          <p className="metric-label">
            Sumber: {student.source_path}
            {student.pt_version ? ` · Packet Tracer ${student.pt_version}` : ""}
          </p>
          {rosterCount > 0 && (
            <div className="assign-inline-bar">
              <MatchSourceBadge
                source={student.match_source}
                matchedProdi={student.matched_prodi}
                matchedKelas={student.matched_kelas}
              />
              {hasClassMismatch && (
                <span className="status-badge status-partial">
                  <MinusCircleIcon size={12} />
                  BEDA KELAS (SESI: {batchClassLabel})
                </span>
              )}
              {onOpenAssign && (
                <button
                  type="button"
                  className="btn btn-secondary btn-compact"
                  onClick={onOpenAssign}
                >
                  {student.match_source === "roster_nim" ||
                  student.match_source === "roster_name" ||
                  student.match_source === "manual"
                    ? "Ubah praktikan"
                    : "Assign praktikan"}
                </button>
              )}
            </div>
          )}
        </div>
        <div className="inspector-score-box">
          <span className="score-num">
            {student.score.toFixed(1)} / {student.max_score.toFixed(0)}
          </span>
          <StatusBadge status={student.status} />
          <DnsSummaryBadge status={student.dns_optional_status} />
        </div>
      </div>

      {hasClassMismatch && (
        <div className="alert alert-warn" role="status">
          <MinusCircleIcon size={16} />
          <div>
            <strong>Perbedaan kelas terdeteksi:</strong> praktikan ini terdaftar di{" "}
            <strong>{studentClassLabel}</strong>, sedangkan sesi evaluasi ini adalah{" "}
            <strong>{batchClassLabel}</strong>. Pastikan berkas tidak salah masuk kelas atau
            gunakan tombol Ubah praktikan bila pencocokan perlu disesuaikan.
          </div>
        </div>
      )}

      {student.parse_error && (
        <div className="alert" role="alert">
          <CloseIcon size={16} />
          <div>
            <strong>Berkas tidak dapat diproses:</strong> {student.parse_error}
          </div>
        </div>
      )}

      {Object.keys(student.category_scores).length > 0 && (
        <div className="category-strip">
          {Object.entries(student.category_scores).map(([cat, bucket]) => (
            <div key={cat} className="category-tile">
              <span className="category-tile-label">{cat}</span>
              <span className="category-tile-score">
                {bucket.earned} / {bucket.possible}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="tab-bar" role="tablist" aria-label="Panel inspeksi perangkat">
        {(
          [
            ["checks", `Indikator (${student.checks.length})`],
            ["S1", "S1 Diff / Config"],
            ["R1", "R1 Diff / Config"],
            ["R2", "R2 Diff / Config"],
            ["hosts", "End Device & DNS"],
          ] as [InspectorTab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className="tab-btn"
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "checks" && (
        <div className="check-list">
          <div className="config-bar">
            <span className="metric-label">
              {student.errors.length === 0
                ? "Seluruh indikator wajib terpenuhi."
                : `${student.errors.length} indikator wajib memerlukan perbaikan.`}
            </span>
            <button
              type="button"
              className="btn btn-secondary"
              aria-pressed={onlyErrors}
              onClick={() => setOnlyErrors((v) => !v)}
            >
              {onlyErrors ? "Tampilkan semua indikator" : "Hanya indikator bermasalah"}
            </button>
          </div>

          {visibleChecks.length === 0 ? (
            <div className="empty-state">
              <p className="empty-title">Tidak ditemukan ketidaksesuaian</p>
              <p className="empty-desc">
                Seluruh indikator wajib pada rubrik telah terpenuhi untuk berkas ini.
              </p>
            </div>
          ) : (
            visibleChecks.map((check) => (
              <article key={check.id} className="check-row">
                <div className="check-row-top">
                  <div className="check-title-wrap">
                    <span className="device-tag">{check.device}</span>
                    <span className="check-title">{check.title}</span>
                  </div>
                  <div className="check-title-wrap">
                    <span className="metric-label mono">
                      {check.optional
                        ? `bonus +${check.points_earned}/${check.points_possible}`
                        : `${check.points_earned}/${check.points_possible}`}
                    </span>
                    <StatusBadge status={check.status} optional={check.optional} />
                  </div>
                </div>
                <p className="check-msg">{check.message}</p>
                {(check.status !== "pass" || check.optional) && (
                  <dl className="check-diff-meta">
                    <div>
                      <dt>Acuan</dt>
                      <dd>{check.expected}</dd>
                    </div>
                    <div>
                      <dt>Terdeteksi</dt>
                      <dd>{check.actual}</dd>
                    </div>
                  </dl>
                )}
              </article>
            ))
          )}
        </div>
      )}

      {tab === "S1" && renderConfigTab("S1")}
      {tab === "R1" && renderConfigTab("R1")}
      {tab === "R2" && renderConfigTab("R2")}

      {tab === "hosts" && (
        <div className="config-viewer">
          <div className="host-grid">
            {(["PC1", "PC2", "Server1"] as const).map((hostName) => {
              const host = student.devices[hostName];
              return (
                <article key={hostName} className="host-card">
                  <p className="check-title">{hostName}</p>
                  {host ? (
                    <dl className="host-kv">
                      <dt>Mode IP</dt>
                      <dd>{host.dhcp_enabled ? "DHCP" : "Statis"}</dd>
                      <dt>IP</dt>
                      <dd>{host.ip || (host.dhcp_enabled ? "Dinamis (DHCP)" : "-")}</dd>
                      <dt>Subnet</dt>
                      <dd>{host.subnet || (host.dhcp_enabled ? "Dinamis (DHCP)" : "-")}</dd>
                      <dt>Gateway</dt>
                      <dd>{host.gateway || "-"}</dd>
                      {host.dhcp_server_ip && (
                        <>
                          <dt>DHCP Server</dt>
                          <dd>{host.dhcp_server_ip}</dd>
                        </>
                      )}
                      {host.dns_client_ip && (
                        <>
                          <dt>DNS Client</dt>
                          <dd>{host.dns_client_ip}</dd>
                        </>
                      )}
                      {hostName === "Server1" && (
                        <>
                          <dt>Layanan DNS</dt>
                          <dd>
                            {host.dns_server_enabled
                              ? `Aktif (${host.dns_records.length} record)`
                              : "Nonaktif"}
                          </dd>
                        </>
                      )}
                    </dl>
                  ) : (
                    <p className="metric-label">Perangkat tidak ditemukan.</p>
                  )}
                </article>
              );
            })}
          </div>

          {serverDiff.length > 0 && (
            <>
              <p className="metric-label">DIFF SERVER1 &amp; DNS OPSIONAL</p>
              <DiffBlock lines={serverDiff} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
