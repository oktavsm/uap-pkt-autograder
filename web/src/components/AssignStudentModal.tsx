import { useEffect, useMemo, useRef, useState } from "react";
import {
  PRODI_CLASSES,
  type ProdiCode,
  type StudentReport,
  type StudentRosterEntry,
} from "../types";
import { CheckIcon, CloseIcon, SearchIcon } from "./Icons";

interface AssignStudentModalProps {
  open: boolean;
  student: StudentReport | null;
  roster: StudentRosterEntry[];
  assignedNims: Set<string>;
  defaultProdi?: string;
  defaultKelas?: string;
  saving: boolean;
  onAssign: (entry: StudentRosterEntry) => void;
  onUnassign: () => void;
  onClose: () => void;
}

export function AssignStudentModal({
  open,
  student,
  roster,
  assignedNims,
  defaultProdi,
  defaultKelas,
  saving,
  onAssign,
  onUnassign,
  onClose,
}: AssignStudentModalProps) {
  const [prodiFilter, setProdiFilter] = useState<"ALL" | ProdiCode>("ALL");
  const [kelasFilter, setKelasFilter] = useState<string>("ALL");
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const initProdi =
      student?.matched_prodi === "PTI" || student?.matched_prodi === "TI"
        ? (student.matched_prodi as ProdiCode)
        : defaultProdi === "PTI" || defaultProdi === "TI"
          ? (defaultProdi as ProdiCode)
          : "ALL";
    const initKelas =
      initProdi !== "ALL"
        ? student?.matched_kelas || defaultKelas || "ALL"
        : "ALL";
    setProdiFilter(initProdi);
    setKelasFilter(initKelas);
    setQuery("");
    window.setTimeout(() => searchRef.current?.focus(), 40);
  }, [open, student, defaultProdi, defaultKelas]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const availableClasses = prodiFilter === "ALL" ? [] : PRODI_CLASSES[prodiFilter];

  const filteredRoster = useMemo(() => {
    const q = query.trim().toLowerCase();
    return roster.filter((entry) => {
      if (prodiFilter !== "ALL" && entry.prodi !== prodiFilter) return false;
      if (prodiFilter !== "ALL" && kelasFilter !== "ALL" && entry.kelas !== kelasFilter) {
        return false;
      }
      if (!q) return true;
      return entry.nim.toLowerCase().includes(q) || entry.nama.toLowerCase().includes(q);
    });
  }, [roster, prodiFilter, kelasFilter, query]);

  if (!open || !student) return null;

  const isCurrentlyMatched =
    student.match_source === "roster_nim" ||
    student.match_source === "roster_name" ||
    student.match_source === "manual";

  return (
    <div
      className="drawer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="assign-drawer-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="drawer-panel">
        <div className="drawer-header">
          <div>
            <p className="metric-label">ASSIGN IDENTITAS PRAKTIKAN</p>
            <h2 id="assign-drawer-title" className="empty-title">
              {student.filename}
            </h2>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label="Tutup panel assign praktikan"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </div>

        <div className="drawer-body">
          <div className="assign-file-context">
            <span className="metric-label">BERKAS SAAT INI</span>
            <span className="mono">{student.source_path}</span>
            <span className="metric-label">
              Terdeteksi:{" "}
              {student.nim
                ? `${student.nim} - ${student.student_name}`
                : student.student_name || "Belum ada NIM"}
            </span>
          </div>

          <div className="field-group">
            <label htmlFor="roster-search-input" className="field-label">
              Cari praktikan (NIM atau nama)
            </label>
            <div className="search-wrap">
              <span className="search-icon">
                <SearchIcon />
              </span>
              <input
                ref={searchRef}
                id="roster-search-input"
                type="search"
                className="search-input"
                placeholder="Ketik NIM atau sebagian nama..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          </div>

          <div className="field-group">
            <span className="metric-label">FILTER PRODI &amp; KELAS</span>
            <div className="filter-group" role="group" aria-label="Filter prodi roster">
              {(["ALL", "PTI", "TI"] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  className="filter-btn"
                  aria-pressed={prodiFilter === code}
                  onClick={() => {
                    setProdiFilter(code);
                    setKelasFilter("ALL");
                  }}
                >
                  {code === "ALL" ? "Semua Prodi" : code}
                </button>
              ))}
            </div>

            {prodiFilter !== "ALL" && (
              <div className="filter-group" role="group" aria-label={`Filter kelas ${prodiFilter}`}>
                <button
                  type="button"
                  className="filter-btn"
                  aria-pressed={kelasFilter === "ALL"}
                  onClick={() => setKelasFilter("ALL")}
                >
                  Semua {prodiFilter}
                </button>
                {availableClasses.map((k) => (
                  <button
                    key={k}
                    type="button"
                    className="filter-btn"
                    aria-pressed={kelasFilter === k}
                    onClick={() => setKelasFilter(k)}
                  >
                    {k}
                  </button>
                ))}
              </div>
            )}
          </div>

          {roster.length === 0 ? (
            <div className="empty-state">
              <p className="empty-title">Roster praktikan belum dimuat</p>
              <p className="empty-desc">
                Impor berkas CSV daftar praktikan melalui tab Riwayat terlebih dahulu untuk
                mengaktifkan pencocokan dan assignment otomatis.
              </p>
            </div>
          ) : filteredRoster.length === 0 ? (
            <div className="empty-state">
              <p className="empty-title">Praktikan tidak ditemukan</p>
              <p className="empty-desc">
                Ubah kata kunci pencarian atau pilih filter prodi/kelas lain.
              </p>
            </div>
          ) : (
            <div className="field-group">
              <span className="metric-label">
                MENAMPILKAN {filteredRoster.length} PRAKTIKAN
              </span>
              <ul className="roster-picker-list" role="list">
                {filteredRoster.slice(0, 120).map((entry) => {
                  const isCurrent = student.nim === entry.nim;
                  const isUsedElsewhere = !isCurrent && assignedNims.has(entry.nim);
                  return (
                    <li key={entry.nim}>
                      <button
                        type="button"
                        className="roster-picker-btn"
                        aria-pressed={isCurrent}
                        disabled={saving}
                        onClick={() => onAssign(entry)}
                      >
                        <div className="roster-picker-main">
                          <span className="roster-picker-name">{entry.nama}</span>
                          <span className="metric-label">
                            {entry.nim} · {entry.class_label}
                          </span>
                        </div>
                        <div className="roster-picker-meta">
                          {isCurrent ? (
                            <span className="status-badge status-pass">
                              <CheckIcon size={12} />
                              TERPILIH
                            </span>
                          ) : isUsedElsewhere ? (
                            <span className="status-badge status-partial">TERPAKAI</span>
                          ) : (
                            <span className="metric-label">Pilih</span>
                          )}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        <div className="drawer-footer">
          {isCurrentlyMatched ? (
            <button
              type="button"
              className="btn btn-destructive"
              disabled={saving}
              onClick={onUnassign}
            >
              {saving ? "Menyimpan..." : "Lepas assignment"}
            </button>
          ) : (
            <span className="metric-label">Pilih salah satu praktikan di atas</span>
          )}
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
