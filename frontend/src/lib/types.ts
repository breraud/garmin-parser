export type ExportMode = "single_activity" | "multi_activity" | "date_range";
export type ExportStatus = "success" | "error";
export type BatchExportFormat = "zip" | "markdown";

export interface MarkdownExportRequest {
  mode?: ExportMode;
  activity_id?: string;
  date_from?: string;
  date_to?: string;
  activity_type?: string;
  max_activities?: number;
  include_notes?: boolean;
  notes?: string;
}

export interface MarkdownExportResponse {
  status: ExportStatus;
  markdown: string;
  metadata: Record<string, string | number | boolean | null>;
}

export interface BatchFileExportRequest {
  activity_ids: string[];
  export_format: BatchExportFormat;
  include_notes?: boolean;
  notes?: string;
}

export interface BatchFileDownload {
  blob: Blob;
  filename: string;
}

export interface RecentActivitySummary {
  activity_id: string;
  date: string;
  title: string | null;
  distance_km: number | null;
}

export interface GarminLoginRequest {
  email: string;
  password: string;
}

export interface GarminLoginResponse {
  access_token: string;
  token_type: "bearer";
}

export interface GarminLogoutResponse {
  status: "logged_out";
  message: string;
}

export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
}

export interface ApiError {
  status: number;
  message: string;
  details?: ApiErrorBody;
}

export interface ExportFormValues {
  email: string;
  password: string;
  mode: ExportMode;
  selectedActivityIds: string[];
  batchExportFormat: BatchExportFormat;
  dateFrom: string;
  dateTo: string;
  maxActivities: string;
  notes: string;
}
