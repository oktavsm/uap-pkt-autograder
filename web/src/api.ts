import type { BatchReport, RubricConfig, RubricResponse } from "./types";

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
  rubric: RubricConfig | null
): Promise<BatchReport> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  if (rubric) {
    form.append("rubric_json", JSON.stringify(rubric));
  }

  const res = await fetch(`${API_BASE}/api/grade`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let detail = `Gagal memproses file (${res.status}).`;
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

export async function downloadCsvReport(report: BatchReport): Promise<void> {
  const res = await fetch(`${API_BASE}/api/export/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  if (!res.ok) {
    throw new Error(`Gagal membuat file CSV (${res.status}).`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "uap_grades.csv";
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
  a.download = "uap_grades.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
