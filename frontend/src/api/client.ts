import type { AuthResponse, LoginInput, RegisterInput, User } from "../types/auth";
import type {
  DoctorAdmin,
  DoctorLeave,
  DoctorProvisionInput,
  DoctorPublic,
  DoctorSchedule,
  DoctorSelf,
  Paginated,
  SlotPreview,
  WorkingHour,
  WorkingHourInput,
} from "../types/doctor";
import type {
  AppointmentDetail,
  AppointmentListItem,
  HoldResponse,
  LeaveConflictPreview,
  SymptomInput,
  PreVisitSummary,
  PostVisitSummary,
  PatientPostVisitSummary,
  CompleteVisitInput,
  ClinicalRecord,
} from "../types/appointment";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | Array<{ msg?: string }>;
    } | null;
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg ?? "Invalid value").join(". ")
      : typeof detail === "string"
        ? detail
        : undefined;
    throw new ApiError(
      message ?? (response.status === 409 ? "The request conflicts with current availability." : "Something went wrong. Please try again."),
      response.status,
      detail,
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  calendarStatus: (token: string) => request<{ status: "connected" | "reauthorization_required" | "disconnected"; calendar_id: string | null }>("/integrations/google-calendar/status", {}, token),
  connectCalendar: (token: string) => request<{ authorization_url: string }>("/integrations/google-calendar/connect", { method: "POST" }, token),
  disconnectCalendar: (token: string) => request<{ status: string }>("/integrations/google-calendar/disconnect", { method: "POST" }, token),
  syncCalendarAppointment: (token: string, appointmentId: string) => request<{ job_id: string; status: string }>(`/integrations/google-calendar/sync/${appointmentId}`, { method: "POST" }, token),
  register: (input: RegisterInput) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify(input) }),
  login: (input: LoginInput) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  refresh: () => request<AuthResponse>("/auth/refresh", { method: "POST" }),
  me: (accessToken: string) => request<User>("/auth/me", {}, accessToken),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  adminDoctors: (token: string, page = 1) =>
    request<Paginated<DoctorAdmin>>(`/admin/doctors?page=${page}&page_size=20`, {}, token),
  adminCreateDoctor: (token: string, input: DoctorProvisionInput) =>
    request<DoctorAdmin>(
      "/admin/doctors",
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  adminGetDoctor: (token: string, doctorId: string) =>
    request<DoctorAdmin>(`/admin/doctors/${doctorId}`, {}, token),
  adminUpdateDoctor: (token: string, doctorId: string, input: Partial<DoctorAdmin>) =>
    request<DoctorAdmin>(
      `/admin/doctors/${doctorId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    ),
  adminAddWorkingHour: (token: string, doctorId: string, input: WorkingHourInput) =>
    request<WorkingHour>(
      `/admin/doctors/${doctorId}/working-hours`,
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  adminUpdateWorkingHour: (
    token: string,
    doctorId: string,
    workingHourId: string,
    input: WorkingHourInput,
  ) =>
    request<WorkingHour>(
      `/admin/doctors/${doctorId}/working-hours/${workingHourId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    ),
  adminDeleteWorkingHour: (token: string, doctorId: string, workingHourId: string) =>
    request<void>(
      `/admin/doctors/${doctorId}/working-hours/${workingHourId}`,
      { method: "DELETE" },
      token,
    ),
  adminAddLeave: (token: string, doctorId: string, leaveDate: string, reason: string, confirmConflicts = false) =>
    request<DoctorLeave & { affected_count: number; affected_appointment_ids: string[] }>(
      `/admin/doctors/${doctorId}/leave?confirm_conflicts=${confirmConflicts}`,
      { method: "POST", body: JSON.stringify({ leave_date: leaveDate, reason: reason || null }) },
      token,
    ),
  adminDeleteLeave: (token: string, doctorId: string, leaveId: string) =>
    request<void>(
      `/admin/doctors/${doctorId}/leave/${leaveId}`,
      { method: "DELETE" },
      token,
    ),
  publicDoctors: (token: string, specialisation: string, page: number) => {
    const query = new URLSearchParams({ page: String(page), page_size: "10" });
    if (specialisation.trim()) query.set("specialisation", specialisation.trim());
    return request<Paginated<DoctorPublic>>(`/doctors?${query}`, {}, token);
  },
  publicDoctor: (token: string, doctorId: string) =>
    request<DoctorPublic>(`/doctors/${doctorId}`, {}, token),
  previewSlots: (token: string, doctorId: string, date: string) =>
    request<SlotPreview>(`/doctors/${doctorId}/slots?date=${encodeURIComponent(date)}`, {}, token),
  doctorProfile: (token: string) => request<DoctorSelf>("/doctor/me/profile", {}, token),
  doctorSchedule: (token: string) => request<DoctorSchedule>("/doctor/me/schedule", {}, token),
  doctorLeave: (token: string) =>
    request<{ leaves: DoctorLeave[] }>("/doctor/me/leave", {}, token),
  holdSlot: (token: string, doctorId: string, slotStart: string) =>
    request<HoldResponse>(
      "/appointments/holds",
      { method: "POST", body: JSON.stringify({ doctor_id: doctorId, slot_start: slotStart }) },
      token,
    ),
  confirmAppointment: (token: string, holdToken: string, symptoms: SymptomInput) =>
    request<AppointmentDetail>(
      "/appointments",
      { method: "POST", body: JSON.stringify({ hold_token: holdToken, symptoms }) },
      token,
    ),
  patientAppointments: (token: string) =>
    request<Paginated<AppointmentListItem>>("/appointments/me", {}, token),
  cancelAppointment: (token: string, appointmentId: string, reason: string) =>
    request<AppointmentDetail>(
      `/appointments/${appointmentId}/cancel`,
      { method: "POST", body: JSON.stringify({ reason }) },
      token,
    ),
  rescheduleAppointment: (token: string, appointmentId: string, holdToken: string) =>
    request<AppointmentDetail>(
      `/appointments/${appointmentId}/reschedule`,
      { method: "POST", body: JSON.stringify({ new_hold_token: holdToken, reason: "Rescheduled by patient" }) },
      token,
    ),
  doctorAppointments: (token: string) =>
    request<Paginated<AppointmentListItem>>("/doctor/me/appointments", {}, token),
  doctorAppointment: (token: string, appointmentId: string) =>
    request<AppointmentDetail>(`/doctor/me/appointments/${appointmentId}`, {}, token),
  adminAppointments: (token: string) =>
    request<Paginated<AppointmentListItem>>("/admin/appointments", {}, token),
  leaveConflicts: (token: string, doctorId: string, date: string) =>
    request<LeaveConflictPreview>(
      `/admin/doctors/${doctorId}/leave-conflicts?date=${encodeURIComponent(date)}`,
      {},
      token,
    ),
  patientPreVisitSummary: (token: string, appointmentId: string) =>
    request<PreVisitSummary>(`/appointments/${appointmentId}/pre-visit-summary`, {}, token),
  patientPostVisitSummary: (token: string, appointmentId: string) =>
    request<PatientPostVisitSummary>(`/appointments/${appointmentId}/post-visit-summary`, {}, token),
  doctorPreVisitSummary: (token: string, appointmentId: string) =>
    request<PreVisitSummary>(`/doctor/me/appointments/${appointmentId}/pre-visit-summary`, {}, token),
  regeneratePreVisitSummary: (token: string, appointmentId: string) =>
    request<{ appointment_id: string; status: "retry_pending" }>(
      `/doctor/me/appointments/${appointmentId}/pre-visit-summary/regenerate`,
      { method: "POST" },
      token,
    ),
  completeVisit: (token: string, appointmentId: string, input: CompleteVisitInput) =>
    request<ClinicalRecord>(
      `/doctor/me/appointments/${appointmentId}/complete`,
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  clinicalRecord: (token: string, appointmentId: string) =>
    request<ClinicalRecord>(`/doctor/me/appointments/${appointmentId}/clinical-record`, {}, token),
  updateClinicalRecord: (token: string, appointmentId: string, input: CompleteVisitInput) =>
    request<ClinicalRecord>(
      `/doctor/me/appointments/${appointmentId}/clinical-record`,
      { method: "PUT", body: JSON.stringify(input) },
      token,
    ),
  visitRecord: (token: string, appointmentId: string) =>
    request<ClinicalRecord>(`/doctor/me/appointments/${appointmentId}/visit`, {}, token),
  updateVisitRecord: (token: string, appointmentId: string, input: CompleteVisitInput) =>
    request<ClinicalRecord>(
      `/doctor/me/appointments/${appointmentId}/visit`,
      { method: "PUT", body: JSON.stringify(input) },
      token,
    ),
  addPrescriptionItem: (token: string, appointmentId: string, input: CompleteVisitInput["prescription"]["items"][number]) =>
    request<CompleteVisitInput["prescription"]["items"][number] & { id: string }>(
      `/doctor/me/appointments/${appointmentId}/prescriptions`,
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  updatePrescriptionItem: (token: string, appointmentId: string, prescriptionId: string, input: Partial<CompleteVisitInput["prescription"]["items"][number]>) =>
    request<CompleteVisitInput["prescription"]["items"][number] & { id: string }>(
      `/doctor/me/appointments/${appointmentId}/prescriptions/${prescriptionId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    ),
  deletePrescriptionItem: (token: string, appointmentId: string, prescriptionId: string) =>
    request<void>(`/doctor/me/appointments/${appointmentId}/prescriptions/${prescriptionId}`, { method: "DELETE" }, token),
  doctorPostVisitSummary: (token: string, appointmentId: string) =>
    request<PostVisitSummary>(`/doctor/me/appointments/${appointmentId}/post-visit-summary`, {}, token),
  regeneratePostVisitSummary: (token: string, appointmentId: string) =>
    request<{ appointment_id: string; status: "retry_pending" }>(
      `/doctor/me/appointments/${appointmentId}/post-visit-summary/regenerate`,
      { method: "POST" },
      token,
    ),
  approvePostVisitSummary: (
    token: string,
    appointmentId: string,
    patientFriendlySummary?: string,
  ) => request<PostVisitSummary>(
    `/doctor/me/appointments/${appointmentId}/post-visit-summary/approve`,
    { method: "POST", body: JSON.stringify({ patient_friendly_summary: patientFriendlySummary || null }) },
    token,
  ),
  rejectPostVisitSummary: (token: string, appointmentId: string) =>
    request<PostVisitSummary>(
      `/doctor/me/appointments/${appointmentId}/post-visit-summary/reject`,
      { method: "POST" },
      token,
    ),
};
