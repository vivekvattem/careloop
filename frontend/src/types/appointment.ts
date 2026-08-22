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

export type GenerationStatus = "pending" | "completed" | "fallback" | "retry_pending" | "failed";

export interface PreVisitSummary {
  appointment_id: string;
  status: GenerationStatus;
  provider: string;
  model_identifier: string;
  prompt_version: string;
  attempt_count: number;
  failure_category: string | null;
  failure_message: string | null;
  generated_at: string | null;
  historical_context_used: boolean;
  generation_source: "llm" | "deterministic_fallback" | null;
  urgency: "Low" | "Medium" | "High" | null;
  chief_complaint: string | null;
  suggested_questions: string[] | null;
  relevant_history_note: string | null;
  safety_disclaimer: string | null;
  sources: Array<{
    document_id: string;
    appointment_id: string;
    document_type: string;
    event_date: string;
    rank_position: number;
    ranking_score: number;
  }>;
}

export interface PrescriptionItemInput {
  medication_name: string;
  dosage: string;
  route: string | null;
  frequency_per_day: number;
  reminder_times: string[];
  start_date: string;
  end_date: string | null;
  food_instructions: string | null;
  additional_instructions: string | null;
}

export interface CompleteVisitInput {
  clinical_note: {
    original_notes: string;
    diagnosis: string | null;
    follow_up_instructions: string;
    recommended_follow_up_date: string | null;
  };
  prescription: { general_instructions: string | null; items: PrescriptionItemInput[] };
}

export interface ClinicalRecord {
  appointment_id: string;
  original_notes: string;
  diagnosis: string | null;
  follow_up_instructions: string;
  recommended_follow_up_date: string | null;
  general_instructions: string | null;
  items: Array<PrescriptionItemInput & { id: string }>;
  created_at: string;
  updated_at: string;
}

export interface PostVisitSummary {
  appointment_id: string;
  status: GenerationStatus;
  generation_source: "llm" | "deterministic_fallback" | null;
  failure_message: string | null;
  patient_friendly_summary: string | null;
  medication_schedule: Array<Record<string, unknown>> | null;
  follow_up_steps: string[] | null;
  warning_signs: string[] | null;
  review_status: "pending_review" | "approved" | "rejected";
  approved_content: Record<string, unknown> | null;
}

export interface PatientPostVisitSummary {
  appointment_id: string;
  availability: "awaiting_doctor_review" | "approved";
  generation_source: "llm" | "deterministic_fallback" | null;
  approved_content: {
    patient_friendly_summary: string;
    medication_schedule: Array<Record<string, unknown>>;
    follow_up_steps: string[];
    warning_signs: string[];
  } | null;
}
