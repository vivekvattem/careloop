# Phase 2B: concurrency-safe appointment booking

## 1. Why previews are not guarantees

A preview is a read taken at one moment. Another patient can act immediately afterward. Confirmation therefore repeats every availability rule inside its own transaction instead of trusting the screen or an earlier API response.

## 2. What a race condition is

A race occurs when two requests observe the same available slot before either has written its result. Without coordination, both can decide they won. Correctness must not depend on which Python line happens to execute first.

## 3. Why check-then-insert is unsafe

Two transactions can both run `SELECT` and see no appointment, then both insert. A service-level check improves error messages but is not final protection. PostgreSQL must reject the second conflicting write.

## 4. Hold lifecycle

An active hold lasts five minutes by default. It can become `consumed` after confirmation, `expired` when its server expiry passes, or `released` for a future explicit-release flow. Relevant requests lazily update expired active holds, so correctness does not require a worker.

The active-hold exclusion constraint prevents overlapping half-open ranges for one doctor. Expired rows stop blocking only after their status is lazily changed.

## 5. Why raw tokens are not stored

The patient receives a random opaque token once. The database stores only its SHA-256 hash. Random tokens have enough entropy that hashing is appropriate for lookup without making token recovery practical. A database reader cannot replay the raw token.

## 6. PostgreSQL overlap protection

The migration installs `btree_gist` and combines doctor UUID equality with `tstzrange(start, end, '[)') &&`. Separate exclusion constraints cover active holds and appointments in `confirmed` or `reschedule_required` state. Half-open ranges allow adjacent 09:00–09:30 and 09:30–10:00 appointments.

SQLite does not implement these constraints, so fast behavior tests use SQLite while the compulsory race tests use PostgreSQL.

## 7. Confirmation transaction

Confirmation identifies the hold hash, locks the doctor and hold, checks ownership/status/expiry, revalidates schedule and leave, checks active appointments, creates the appointment and symptoms, writes initial history, consumes the hold, and commits once. An integrity conflict rolls the whole transaction back and becomes HTTP `409`.

## 8. Why rescheduling creates a replacement

Changing the original timestamps would erase audit truth. Rescheduling cancels the original and creates a replacement linked by `rescheduled_from_id`. The original symptom submission is copied because it describes the same requested visit; future product requirements may instead ask the patient to reconfirm it.

If replacement creation fails, rollback restores the original status and leaves it confirmed.

## 9. Cancellation and availability

Cancellation records actor, reason, timestamp and status history. `cancelled` is outside the active exclusion predicate and slot-preview filter, so the time becomes available without deleting audit data.

## 10. Leave conflicts

Preview converts the doctor's local leave date to UTC boundaries and returns only appointment identifiers, times and statuses. It performs no writes. Applying leave without confirmation returns structured `409` details. Confirmed application creates leave, marks conflicts `reschedule_required`, and writes one history entry per appointment atomically.

Notifications are not sent yet; affected identifiers are returned so a future outbox can consume the result.

## 11. Lock ordering

Booking and leave both lock the doctor profile before making schedule/leave decisions. Confirmation then locks the hold. Cancellation locks doctor then appointment. Rescheduling locks all involved doctors in sorted UUID order, then the original appointment and new hold. Stable ordering reduces deadlock cycles.

## 12. What the concurrency tests prove

Separate PostgreSQL sessions start together through a thread barrier. The tests prove one of two competing holds loses, one of two confirmations using the same hold loses, a direct overlapping appointment race is rejected by PostgreSQL, and booking-versus-leave cannot leave a confirmed appointment on an active leave date. The isolated schema protects development data.

## 13. Interview explanation

Be ready to explain the layered defense:

1. The UI labels previews honestly and treats countdowns as informational.
2. Services validate domain rules and translate expected conflicts.
3. Row locks serialize doctor-level booking and leave decisions.
4. One database transaction prevents partial appointment, symptom and history records.
5. PostgreSQL exclusion constraints remain correct even when application checks race.
6. Status history and replacement rows preserve auditability.

