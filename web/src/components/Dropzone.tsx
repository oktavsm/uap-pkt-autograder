import { useRef, useState } from "react";
import { PRODI_CLASSES, type ProdiCode } from "../types";
import { CloseIcon, FileIcon, UploadIcon } from "./Icons";

interface DropzoneProps {
  files: File[];
  loading: boolean;
  prodi: ProdiCode;
  kelas: string;
  note: string;
  onProdiChange: (next: ProdiCode) => void;
  onKelasChange: (next: string) => void;
  onNoteChange: (next: string) => void;
  onAddFiles: (incoming: File[]) => void;
  onRemoveFile: (index: number) => void;
  onClearFiles: () => void;
  onRunGrade: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function Dropzone({
  files,
  loading,
  prodi,
  kelas,
  note,
  onProdiChange,
  onKelasChange,
  onNoteChange,
  onAddFiles,
  onRemoveFile,
  onClearFiles,
  onRunGrade,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFileList = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onAddFiles(Array.from(list));
  };

  const classOptions = PRODI_CLASSES[prodi];

  return (
    <section className="intake-panel" aria-label="Unggah berkas evaluasi">
      <div className="class-picker-bar">
        <div className="class-picker-group">
          <span className="metric-label">PRODI</span>
          <div className="filter-group" role="group" aria-label="Pilih program studi">
            {(["PTI", "TI"] as const).map((code) => (
              <button
                key={code}
                type="button"
                className="filter-btn"
                disabled={loading}
                aria-pressed={prodi === code}
                onClick={() => onProdiChange(code)}
              >
                {code}
              </button>
            ))}
          </div>
        </div>

        <div className="class-picker-group">
          <span className="metric-label">KELAS ({prodi})</span>
          <div className="filter-group" role="group" aria-label={`Pilih kelas ${prodi}`}>
            {classOptions.map((k) => (
              <button
                key={k}
                type="button"
                className="filter-btn"
                disabled={loading}
                aria-pressed={kelas === k}
                onClick={() => onKelasChange(k)}
              >
                {k}
              </button>
            ))}
          </div>
        </div>

        <div className="class-note-group">
          <label htmlFor="session-note-input" className="metric-label">
            CATATAN SESI (OPSIONAL)
          </label>
          <input
            id="session-note-input"
            type="text"
            maxLength={120}
            className="text-input"
            disabled={loading}
            placeholder="Contoh: Gelombang 1 / Susulan"
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
          />
        </div>
      </div>

      <div className="intake-grid">
        <div
          className="dropzone"
          data-dragging={dragging ? "true" : "false"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            handleFileList(e.dataTransfer.files);
          }}
        >
          <div className="dropzone-row">
            <div className="dropzone-icon">
              <UploadIcon size={20} />
            </div>
            <div>
              <p className="dropzone-title">
                Unggah berkas kelas {prodi} - {kelas} atau letakkan di area ini
              </p>
              <p className="dropzone-hint">
                Format yang diterima: arsip .zip, .pkt, atau .pka (mendukung pemilihan banyak berkas).
              </p>
            </div>
          </div>
          <div className="dropzone-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={loading}
              onClick={() => inputRef.current?.click()}
            >
              Pilih berkas (.pkt / .pka / .zip)
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pkt,.pka,.zip"
            className="sr-only"
            aria-label="Pilih berkas Packet Tracer atau arsip ZIP"
            onChange={(e) => {
              handleFileList(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        <div className="intake-side">
          {files.length > 0 ? (
            <div className="queue-box">
              <div className="queue-header">
                <span>
                  Antrean {prodi} - {kelas} ({files.length} berkas)
                </span>
                <span>{formatBytes(files.reduce((sum, f) => sum + f.size, 0))}</span>
              </div>
              <ul className="queue-list" aria-label="Daftar berkas dalam antrean">
                {files.map((file, idx) => (
                  <li key={`${file.name}-${file.size}-${idx}`} className="queue-item">
                    <div className="queue-item-meta">
                      <FileIcon />
                      <span className="queue-item-name" title={file.name}>
                        {file.name}
                      </span>
                      <span className="queue-item-size">{formatBytes(file.size)}</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon"
                      aria-label={`Hapus ${file.name} dari antrean`}
                      disabled={loading}
                      onClick={() => onRemoveFile(idx)}
                    >
                      <CloseIcon />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="queue-empty">
              Belum ada berkas dalam antrean untuk kelas {prodi} - {kelas}. Pilih berkas .pkt/.pka
              maupun arsip .zip, hasil evaluasi akan tersimpan otomatis ke riwayat.
            </div>
          )}

          <div className="intake-footer">
            <button
              type="button"
              className="btn btn-destructive"
              disabled={loading || files.length === 0}
              onClick={onClearFiles}
            >
              Hapus antrean
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading || files.length === 0}
              onClick={onRunGrade}
            >
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Memproses {files.length} berkas...
                </>
              ) : (
                `Mulai evaluasi ${prodi} - ${kelas} (${files.length})`
              )}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
