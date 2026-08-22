# Phase 4: Visit Completion and Post-Visit Intelligence

## Schema

Phase 4 extends the existing Phase 3 clinical-note record instead of creating a duplicate visit table. A clinical note remains one-to-one with an appointment and now records treatment-plan text, private doctor notes, and visit start/completion timestamps. Private notes are returned only from doctor-only endpoints and are never used in patient responses or the LLM prompt.

Prescription items remain doctor-owned rows beneath the appointment prescription. They now have an active flag and database checks for nonblank medication name and dosage plus valid date ranges. One post-visit summary remains linked to each completed appointment and adds a persisted safety disclaimer.

## Lifecycle and authorization

The assigned doctor records the visit and prescription data, then completes the appointment in one transaction. That transaction creates or reuses the clinical record, writes prescription rows, transitions the appointment to `completed`, records appointment history, creates the pending post-visit summary, and writes verified CareLoop history documents. The LLM call happens only after this transaction commits.

Doctor-only routes expose the visit and prescription-item operations. Patient routes expose only approved post-visit content for the patient’s own appointment. Private notes, raw generation failures, provider metadata, prompts, and unrelated history are not sent to patients.

## LLM generation and fidelity checks

`post_visit_v1` receives doctor-authored observations, assessment, treatment plan, follow-up instructions, and the structured active prescription schedule. The provider is instructed not to diagnose, prescribe, change a medication, or invent a warning sign. It returns strict JSON which is validated with Pydantic.

The stored medication schedule must exactly match active prescription rows. A mismatch is classified as `prescription_fidelity` and uses deterministic fallback. The fallback derives its medication schedule and follow-up instructions directly from stored doctor records and includes a fixed safety disclaimer.

Failure categories include missing configuration, authentication, timeout, rate limit, provider/server failure, schema failure, prescription fidelity, and unexpected error. Failures never block the already-valid completion transaction and never store raw provider content or secrets.

## Regeneration policy

Regeneration locks the summary row. A request received while the summary is `pending` or `retry_pending` returns the ordinary accepted response but does not queue another task. The frontend disables the button immediately and performs bounded two-second polling. Historical attempt counts are preserved.

## Manual test procedure

1. Sign in as the doctor assigned to a confirmed appointment.
2. Record observations, assessment, treatment plan, private notes, follow-up instructions, and prescriptions.
3. Complete the visit and wait for a completed or fallback post-visit summary.
4. Confirm medication names, dosages, and frequencies match the stored prescription.
5. Approve the summary, then sign in as that appointment’s patient to view the approved content and safety disclaimer.
6. Confirm another patient receives the normal hidden-resource response.

## Evaluation talking points and trade-offs

- The database transaction protects clinical completion; LLM latency does not hold the appointment row lock.
- The LLM organizes doctor-approved data only. Prescription rows are never created or edited by AI.
- Existing Phase 3 routes remain supported while `/visit` and prescription-item aliases provide the Phase 4 surface.
- Completed-record editing remains available through the legacy Phase 3 clinical-record route for backward compatibility; every edit invalidates the prior patient approval and marks the post-visit summary for regeneration.
- Generation is in-process rather than queue-backed, so durable retry orchestration is the next operational improvement.
