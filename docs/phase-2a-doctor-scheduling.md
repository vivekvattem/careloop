# Phase 2A: doctor profiles and scheduling

Phase 2A describes when a doctor normally works and when they are unavailable. It deliberately stops before appointment booking so the data rules can be understood and tested independently.

## 1. User versus doctor profile

Every person who signs in has a `users` row. It contains identity and security information: name, normalized email, password hash, role, and active status.

A doctor additionally has one `doctor_profiles` row. It contains healthcare-facing information such as specialisation, qualifications, biography, consultation details, timezone, and slot duration. Keeping these responsibilities separate prevents patient and admin users from accumulating meaningless nullable doctor columns.

The profile's unique `user_id` must point to a doctor-role user. The database enforces the one-profile-per-user relationship; the provisioning service enforces the role rule because an ordinary foreign key cannot inspect a referenced row's role.

## 2. Why provisioning is admin-controlled

Doctor status is privileged. Letting public registration request the doctor role would allow anyone to appear as a clinician. The admin endpoint accepts an initial password, but never returns or logs it. The service normalizes the email, hashes the password, fixes the role to `doctor`, and creates the user and profile in one transaction.

If either insert fails, the SQLAlchemy session rolls back both. There is no half-created doctor account and no public doctor registration route.

## 3. One-to-one and one-to-many relationships

`users → doctor_profiles` is one-to-one: a doctor user has at most one profile, enforced by a unique foreign key.

`doctor_profiles → doctor_working_hours` and `doctor_profiles → doctor_leaves` are one-to-many: one doctor can work in several intervals and have several leave dates. Child foreign keys use cascade deletion so schedule rows cannot become orphans if a profile is deliberately removed in a future administration workflow.

## 4. Working-hours representation

A working-hour row stores a doctor profile, weekday, start time, and end time. Weekdays use integers consistently:

```text
0 Monday   1 Tuesday   2 Wednesday   3 Thursday
4 Friday   5 Saturday  6 Sunday
```

Storing intervals instead of pre-generating slots keeps the database compact and lets a doctor have a lunch break, for example 09:00–12:00 and 13:00–17:00. Slots are derived from these rules when requested.

## 5. Overlap validation

Two half-open intervals overlap when `existing.start < new.end` and `existing.end > new.start`. This permits touching intervals such as 09:00–12:00 and 12:00–15:00.

Pydantic and a database check reject start times that are not before end times. A database unique constraint rejects an exact duplicate. The service queries for any broader overlap before insert or update and returns `409 Conflict`.

The overlap query is not a PostgreSQL exclusion constraint, so two truly simultaneous admin writes could race. This is acceptable for the current administrator-only assessment workflow but should be hardened with serialization or a PostgreSQL range/exclusion design if concurrent schedule administration becomes realistic.

## 6. How leave affects slots

Leave is a full local calendar date associated with the doctor profile. A unique constraint prevents two leave rows for the same doctor and date. Slot generation checks leave before working hours and returns an `on_leave` status with an empty list.

There are no appointments yet. The leave deletion service marks where Phase 2B must evaluate appointment conflicts and notifications.

## 7. Slot generation

Slot generation performs no writes:

1. Load the profile and current user state.
2. Return no slots if the account or booking availability is inactive.
3. Return no slots if the requested local date is leave.
4. Load intervals matching `requested_date.weekday()`.
5. Start at each interval's beginning and repeatedly add the slot duration.
6. Keep a slot only when its end does not pass the interval end.
7. Remove slots whose start is no longer in the future.
8. Deduplicate and sort the results.

Phase 2B will add appointment and active-hold filters at the explicit extension point before returning slots.

## 8. Why timestamps need timezones

`09:00` is not a global instant. It becomes one only when combined with a date and the doctor's IANA timezone, such as `Asia/Kolkata`. The API returns offsets in each ISO-8601 timestamp so browsers and other services can convert correctly.

IANA names are preferable to storing a fixed offset because many regions change offset for daylight saving time. The profile schema verifies names using Python's `zoneinfo` database.

## 9. Application-enforced rules

- A profile is created only for a newly created doctor-role user.
- Emails and required text are normalized.
- Password strength and Argon2 hashing are applied.
- Timezone names are valid IANA zones.
- Working intervals do not overlap.
- Patient discovery includes only active and available doctors.
- Patients cannot see email, account state, or leave reasons.
- Past, partial, leave, inactive, and duplicate slot previews are filtered.
- Role dependencies protect admin, patient, and doctor route groups.

## 10. Database-enforced rules

- Foreign keys prevent orphaned profiles, working hours, and leave.
- `doctor_profiles.user_id` is unique.
- Slot duration must be from 5 through 180 minutes.
- Specialisation cannot be blank and consultation mode is constrained.
- Weekday must be from 0 through 6.
- Working-hour start must precede end.
- Exact working intervals are unique per doctor.
- Leave dates are unique per doctor.
- Indexed profile/weekday access supports slot lookup.

Application validation gives useful errors; database constraints remain the final defense against invalid writes and races for the rules they can express.

## 11. Preparing for concurrency-safe booking

The schema provides stable doctor IDs, timezone rules, interval rules, leave dates, and deterministic candidate slots. Phase 2B can add appointments and short-lived holds referencing the doctor and a normalized start/end instant.

A booking transaction must not trust a previously displayed preview. It must lock or otherwise coordinate the contested slot, recalculate schedule/leave validity, exclude live holds and non-cancelled appointments, insert once, and rely on a database constraint to prevent double booking.

## 12. Interview checklist

You should be able to explain:

1. Why login data belongs on `User` while clinical directory data belongs on `DoctorProfile`.
2. How a unique foreign key creates a one-to-one relationship.
3. Why multiple interval rows are better than a string such as “weekdays 9–5”.
4. The exact boolean condition used to detect overlap.
5. Which validation belongs in Pydantic, the service, and PostgreSQL.
6. Why a slot preview is not proof that a slot can be booked.
7. How a local time becomes a timezone-aware timestamp.
8. Why doctor self-service derives identity from the token rather than a URL ID.
9. How rollback makes doctor provisioning atomic.
10. What must happen inside the future booking transaction to prevent two patients from winning the same slot.

