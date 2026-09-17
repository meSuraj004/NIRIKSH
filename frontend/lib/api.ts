export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type UserRole = "ADMIN" | "OFFICER" | "REVIEWER";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface ProductImage {
  id: number;
  file_path: string;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  source_type: string;
}

export type InspectionStatus = "DRAFT" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface Inspection {
  id: number;
  status: InspectionStatus;
  notes: string | null;
  product_id: number | null;
  inspector_id: number | null;
  error_message: string | null;
}

export interface InspectionDetail extends Inspection {
  images: ProductImage[];
}

export type DeclarationStatus = "DETECTED" | "NOT_DETECTED" | "UNCERTAIN";

export interface Declaration {
  field_name: string;
  value: string | null;
  status: DeclarationStatus;
  confidence: number | null;
  bbox: Record<string, unknown> | null;
  source_image_id: number | null;
  extraction_method: string | null;
}

export type CheckStatus = "PASSED" | "FAILED" | "REVIEW" | "NOT_APPLICABLE";

export interface SubCheck {
  sub_check_id: string;
  name: string;
  status: CheckStatus;
  severity: string;
  mandatory: boolean;
  details: string;
  error_code: string | null;
  remediation: string | null;
}

export interface ComplianceCheck {
  parameter: string | null;
  status: CheckStatus;
  extracted_value: string | null;
  findings: string | null;
  details: { sub_checks?: SubCheck[]; section_reference?: string; rule_id?: string } | null;
}

export interface Violation {
  error_code: string | null;
  severity: string | null;
  description: string | null;
  remediation: string | null;
}

export interface OCRResult {
  image_id: number;
  engine: string | null;
  model: string | null;
  raw_text: string | null;
  line_count: number | null;
  latency_sec: number | null;
}

export interface InspectionResults {
  inspection_id: number;
  status: InspectionStatus;
  declarations: Declaration[];
  compliance_checks: ComplianceCheck[];
  violations: Violation[];
  ocr_results: OCRResult[];
}

export interface Rule {
  id: number;
  rule_id: string;
  title: string;
  section_reference: string | null;
  parameter: string | null;
  description: string | null;
  mandatory: boolean;
  rulebook_version: string | null;
}

export const TOKEN_KEY = "niriksh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/login")) {
    window.localStorage.removeItem(TOKEN_KEY);
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function fetchImageBlobUrl(inspectionId: number, imageId: number): Promise<string> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/inspections/${inspectionId}/images/${imageId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "Image unavailable");
  return URL.createObjectURL(await res.blob());
}

export const authApi = {
  async login(email: string, password: string): Promise<{ access_token: string; user: User }> {
    const data = await api<{ access_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    window.localStorage.setItem(TOKEN_KEY, data.access_token);
    window.localStorage.setItem("niriksh_user", JSON.stringify(data.user));
    return data;
  },
  async signup(email: string, fullName: string, password: string): Promise<User> {
    return api<User>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, full_name: fullName, password }),
    });
  },
  logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem("niriksh_user");
  },
};

export const inspectionApi = {
  list: () => api<Inspection[]>("/api/inspections"),
  get: (id: number) => api<InspectionDetail>(`/api/inspections/${id}`),
  create: (payload: { notes?: string | null }) =>
    api<Inspection>("/api/inspections", { method: "POST", body: JSON.stringify(payload) }),
  uploadImages: (id: number, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return api<ProductImage[]>(`/api/inspections/${id}/images`, {
      method: "POST",
      body: form,
    });
  },
  process: (id: number) =>
    api<Inspection>(`/api/inspections/${id}/process`, { method: "POST" }),
  results: (id: number) => api<InspectionResults>(`/api/inspections/${id}/results`),
};

export const rulesApi = {
  list: () => api<Rule[]>("/api/rules"),
};
