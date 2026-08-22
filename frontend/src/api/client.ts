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
};
