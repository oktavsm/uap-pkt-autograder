export type CheckStatus = "pass" | "partial" | "fail" | "optional";
export type StudentStatus = "pass" | "partial" | "fail" | "error";
export type DnsOptionalStatus = "complete" | "partial" | "none";
export type ProdiCode = "PTI" | "TI";
export type MatchSource = "roster_nim" | "roster_name" | "manual" | "filename" | "unmatched";
export type DiffLineKind =
  | "header"
  | "match"
  | "missing"
  | "extra"
  | "optional_missing"
  | "optional_match";

export interface StudentRosterEntry {
  nim: string;
  nama: string;
  prodi: ProdiCode;
  kelas: string;
  class_label: string;
  angkatan: string;
}

export interface RosterResponse {
  total: number;
  counts: Record<string, number>;
  students: StudentRosterEntry[];
}

export interface RosterImportResponse {
  imported: number;
  skipped: number;
  total: number;
  counts: Record<string, number>;
}

export const PRODI_CLASSES: Record<ProdiCode, string[]> = {
  PTI: ["A", "B", "C", "D"],
  TI: ["A", "B", "C", "D", "E", "F", "G"],
};

export interface DiffLine {
  kind: DiffLineKind;
  prefix: string;
  text: string;
  note: string;
}

export interface RubricConfig {
  name: string;
  pass_threshold: number;
  allow_exit_interface_route: boolean;
  require_explicit_trunk_allowed: boolean;
  weights: Record<string, number>;
}

export interface RubricCheckMeta {
  id: string;
  category: string;
  device: string;
  label: string;
}

export interface RubricResponse {
  rubric: RubricConfig;
  checks: RubricCheckMeta[];
  classes?: Record<ProdiCode, string[]>;
}

export interface CheckResult {
  id: string;
  category: string;
  device: string;
  title: string;
  status: CheckStatus;
  optional: boolean;
  points_earned: number;
  points_possible: number;
  expected: string;
  actual: string;
  message: string;
}

export interface DeviceSnapshot {
  name: string;
  device_type: string;
  model: string;
  ip: string;
  subnet: string;
  gateway: string;
  dhcp_enabled: boolean;
  dhcp_server_ip: string;
  dns_client_ip: string;
  dns_server_enabled: boolean;
  dns_records: string[];
  has_startup_config: boolean;
  running_config: string;
  vlans: number[];
}

export interface StudentReport {
  filename: string;
  source_path: string;
  nim: string;
  student_name: string;
  matched_prodi?: string;
  matched_kelas?: string;
  match_source?: MatchSource;
  match_confidence?: number;
  pt_version: string;
  file_kind: string;
  status: StudentStatus;
  score: number;
  max_score: number;
  percentage: number;
  passed: boolean;
  dns_optional_status: DnsOptionalStatus;
  checks: CheckResult[];
  errors: string[];
  category_scores: Record<string, { earned: number; possible: number }>;
  devices: Record<string, DeviceSnapshot>;
  config_diffs: Record<string, DiffLine[]>;
  parse_error: string | null;
}

export interface CommonFailure {
  check_id: string;
  device: string;
  title: string;
  count: number;
  rate: number;
}

export interface BatchSummary {
  total: number;
  passed: number;
  failed: number;
  parse_errors: number;
  average_score: number;
  highest_score: number;
  lowest_score: number;
  median_score: number;
  pass_rate: number;
  common_failures: CommonFailure[];
}

export interface HistoryRunMeta {
  id: string;
  created_at: string;
  prodi: string;
  kelas: string;
  class_label: string;
  note: string;
  total: number;
  passed: number;
  failed: number;
  parse_errors: number;
  average_score: number;
  pass_rate: number;
}

export interface BatchReport {
  run_id?: string | null;
  created_at?: string | null;
  prodi?: string;
  kelas?: string;
  class_label?: string;
  note?: string;
  rubric: RubricConfig;
  summary: BatchSummary;
  results: StudentReport[];
}
