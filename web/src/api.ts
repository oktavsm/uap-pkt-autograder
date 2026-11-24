import type {
  BatchReport,
  HistoryRunMeta,
  ProdiCode,
  RosterImportResponse,
  RosterResponse,
  RubricConfig,
  RubricResponse,
} from "./types";

const API_BASE = "";

export async function fetchRubric(): Promise<RubricResponse> {
  const res = await fetch(`${API_BASE}/api/rubric`);
  if (!res.ok) {
    throw new Error(`Gagal memuat rubrik (${res.status}).`);
  }
  return (await res.json()) as RubricResponse;
}

export async function gradeFiles(
  files: File[],
  rubric: RubricConfig | null,
  meta: { prodi: ProdiCode; kelas: string; note: string }
): Promise<BatchReport> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  if (rubric) {
    form.append("rubric_json", JSON.stringify(rubric));
  }
  form.append("prodi", meta.prodi);
  form.append("kelas", meta.kelas);
  form.append("note", meta.note);
  form.append("save_history", "true");

  const res = await fetch(`${API_BASE}/api/grade`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let detail = `Gagal memproses berkas (${res.status}).`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) {
        detail = errBody.detail;
      }
    } catch {
      // keep default error message
    }
    throw new Error(detail);
  }

  return (await res.json()) as BatchReport;
}

export async function fetchHistory(prodi?: string, kelas?: string): Promise<HistoryRunMeta[]> {
  const params = new URLSearchParams();
  if (prodi) params.set("prodi", prodi);
  if (kelas) params.set("kelas", kelas);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/api/history${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    throw new Error(`Gagal memuat riwayat evaluasi (${res.status}).`);
  }
  return (await res.json()) as HistoryRunMeta[];
}

export async function fetchHistoryRun(runId: string): Promise<BatchReport> {
  const res = await fetch(`${API_BASE}/api/history/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Gagal memuat detail riwayat (${res.status}).`);
  }
  return (await res.json()) as BatchReport;
}

export async function deleteHistoryRun(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/history/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`Gagal menghapus riwayat (${res.status}).`);
  }
}

export async function downloadHistoryCsv(prodi?: string, kelas?: string): Promise<void> {
  const params = new URLSearchParams();
  if (prodi) params.set("prodi", prodi);
  if (kelas) params.set("kelas", kelas);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/api/history/export/csv${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    let detail = `Gagal mengunduh rekap CSV (${res.status}).`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const tag = [prodi, kelas].filter(Boolean).join("_").toLowerCase() || "semua";
  a.download = `rekap_uap_${tag}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadCsvReport(report: BatchReport): Promise<void> {
  const res = await fetch(`${API_BASE}/api/export/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  if (!res.ok) {
    throw new Error(`Gagal membuat berkas CSV (${res.status}).`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const slug = (report.class_label || "uap").toLowerCase().replace(/\s+/g, "").replace(/-/g, "_");
  a.download = `nilai_${slug}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function fetchRoster(
  prodi?: string,
  kelas?: string,
  q?: string
): Promise<RosterResponse> {
  const params = new URLSearchParams();
  if (prodi) params.set("prodi", prodi);
  if (kelas) params.set("kelas", kelas);
  if (q) params.set("q", q);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/api/roster${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    throw new Error(`Gagal memuat data roster (${res.status}).`);
  }
  return (await res.json()) as RosterResponse;
}

export async function importRosterCsv(file: File, replace = true): Promise<RosterImportResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("replace", replace ? "true" : "false");
  const res = await fetch(`${API_BASE}/api/roster/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = `Gagal mengimpor CSV roster (${res.status}).`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as RosterImportResponse;
}

export async function assignHistoryStudent(
  runId: string,
  payload: {
    source_path: string;
    nim?: string | null;
    custom_nim?: string;
    custom_name?: string;
    custom_prodi?: string;
    custom_kelas?: string;
  }
): Promise<BatchReport> {
  const res = await fetch(`${API_BASE}/api/history/${encodeURIComponent(runId)}/assign`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `Gagal menyimpan assignment praktikan (${res.status}).`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as BatchReport;
}

export async function downloadClassRekapCsv(prodi: string, kelas?: string): Promise<void> {
  const params = new URLSearchParams();
  params.set("prodi", prodi);
  if (kelas) params.set("kelas", kelas);
  const res = await fetch(`${API_BASE}/api/history/export/class-csv?${params.toString()}`);
  if (!res.ok) {
    let detail = `Gagal mengunduh rekap lengkap kelas (${res.status}).`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const tag = [prodi, kelas].filter(Boolean).join("_").toLowerCase();
  a.download = `rekap_lengkap_${tag}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadJsonReport(report: BatchReport): void {
  const blob = new Blob([JSON.stringify(report, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const slug = (report.class_label || "uap").toLowerCase().replace(/\s+/g, "").replace(/-/g, "_");
  a.download = `nilai_${slug}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
