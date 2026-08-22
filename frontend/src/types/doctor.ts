export interface WorkingHour {
  id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  created_at: string;
  updated_at: string;
}

export interface DoctorLeave {
  id: string;
  leave_date: string;
  reason: string | null;
  created_at: string;
}

export interface DoctorAdmin {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: "doctor";
  is_active: boolean;
  specialisation: string;
  qualifications: string;
  biography: string;
  consultation_mode: string;
  location: string | null;
  slot_duration_minutes: number;
  timezone: string;
  is_available_for_booking: boolean;
  created_at: string;
  updated_at: string;
  working_hours: WorkingHour[];
  leaves: DoctorLeave[];
}

export interface DoctorPublic {
  id: string;
  full_name: string;
  specialisation: string;
  qualifications: string;
  biography: string;
  consultation_mode: string;
  location: string | null;
  slot_duration_minutes: number;
  timezone: string;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface DoctorProvisionInput {
  full_name: string;
  email: string;
  initial_password: string;
  specialisation: string;
  qualifications: string;
  biography: string;
  consultation_mode: "in_person" | "video" | "hybrid";
  location: string | null;
  slot_duration_minutes: number;
  timezone: string;
  is_available_for_booking: boolean;
}

export interface WorkingHourInput {
  day_of_week: number;
  start_time: string;
  end_time: string;
}

export interface SlotPreview {
  doctor_id: string;
  date: string;
  timezone: string;
  availability: "available" | "doctor_inactive" | "on_leave" | "no_working_hours";
  slots: Array<{ start: string; end: string }>;
  disclaimer: string;
}

export type DoctorSelf = Omit<
  DoctorAdmin,
  "role" | "created_at" | "updated_at" | "working_hours" | "leaves"
>;

export interface DoctorSchedule {
  timezone: string;
  slot_duration_minutes: number;
  working_hours: WorkingHour[];
}
