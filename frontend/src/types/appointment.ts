export type AppointmentStatus =
  | "confirmed"
  | "completed"
  | "cancelled"
  | "reschedule_required";

export interface SymptomInput {
  chief_complaint: string;
  symptom_description: string;
  duration: string;
  severity: number;
  existing_conditions: string | null;
  current_medications: string | null;
}

export interface HoldResponse {
  hold_token: string;
  hold_id: string;
  doctor_id: string;
  slot_start: string;
  slot_end: string;
  expires_at: string;
  remaining_seconds: number;
  status: "active" | "consumed" | "expired" | "released";
}

export interface AppointmentListItem {
  id: string;
  patient_user_id: string;
  doctor_id: string;
  doctor_name: string;
  patient_name: string;
  slot_start: string;
  slot_end: string;
  status: AppointmentStatus;
  cancellation_reason: string | null;
  rescheduled_from_id: string | null;
  created_at: string;
}

export interface AppointmentDetail extends AppointmentListItem {
  symptoms: SymptomInput | null;
  history: Array<{
    id: string;
    previous_status: AppointmentStatus | null;
    new_status: AppointmentStatus;
    actor_user_id: string | null;
    reason: string | null;
    created_at: string;
  }>;
}

export interface LeaveConflictPreview {
  doctor_id: string;
  date: string;
  affected_count: number;
  appointments: Array<{
    appointment_id: string;
    slot_start: string;
    slot_end: string;
    status: AppointmentStatus;
  }>;
}

