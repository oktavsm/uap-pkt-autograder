import { useRef, useState } from "react";
import { CloseIcon, FileIcon, UploadIcon } from "./Icons";

interface DropzoneProps {
  files: File[];
  loading: boolean;
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

  return (
    <section className="intake-panel" aria-label="Unggah berkas ujian">
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
        <div className="dropzone-icon">
          <UploadIcon size={20} />
        </div>
        <div>
          <p className="dropzone-title">Tarik file ke sini atau pilih dari perangkat</p>
          <p className="dropzone-hint">
            Mendukung arsip .zip berisi ratusan file maupun banyak file .pkt / .pka sekaligus.
          </p>
        </div>
        <div className="dropzone-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading}
            onClick={() => inputRef.current?.click()}
          >
            Pilih file .pkt / .zip
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pkt,.pka,.zip"
          className="sr-only"
          aria-label="Pilih file Packet Tracer atau ZIP"
          onChange={(e) => {
            handleFileList(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <div className="queue-box">
          <div className="queue-header">
            <span>Antrean unggah ({files.length} berkas)</span>
            <span>{formatBytes(files.reduce((sum, f) => sum + f.size, 0))}</span>
          </div>
          <ul className="queue-list" aria-label="Daftar file dalam antrean">
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
      )}

      <div className="intake-footer">
        <button
          type="button"
          className="btn btn-destructive"
          disabled={loading || files.length === 0}
          onClick={onClearFiles}
        >
          Kosongkan antrean
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
            `Nilai sekarang (${files.length})`
          )}
        </button>
      </div>
    </section>
  );
}
