# Deferred features

Scheduled, not dropped. Each entry is recorded here until it gets its own
decision entry and a phase. Read this only when a task touches one of them.

---

## Email-OTP verification (registration hardening)

Verify ownership of the email before an account becomes active, to reduce fake
accounts and email squatting. Explicitly **not** a substitute for phone
verification: it proves ownership of the email, not the phone.

**Scope when picked up:** an OTP/token model, lazy expiry (D6 — no scheduler),
an email-sending path (console backend locally), resend + throttling, and a
multi-step registration contract (register → inactive → verify → activate),
which changes the `/api/auth/register/` contract.

**Why deferred:** the core project does not need it; it is a hardening feature.
Related: D23 (phone is not an auth factor).

---

## Regional administration

An Administrator who supervises the lots and Managers of one region, with
region-scoped rather than global authority.

**Scope when picked up:** a `Region` entity, a conditional `role=ADMIN ⇒ region`
constraint, region-scoped authorization across accounts/parking/reports, and a
region-aware demotion guard. A Manager whose lots span several regions makes it
more involved still.

**Why deferred:** considered and deliberately deferred until after the core
project (D24). Global Administrators are sufficient for the academic build
(PROJECT.md §47).

---

## Audit logging

Record who changed a user's role, suspended an account, changed a tariff, etc.
(`AuditLog`, PROJECT.md §15).

**Why deferred:** the role-change endpoint already exists (D27), so this is a
matter of writing the audit records it should produce. Revisit once the core
domain phases (parking, booking, payment) have settled, so the audit shape is
not guessed.

---

## Frontend implementation

Delegated to the agent (PROJECT.md §11), but explicitly **Phase 9**. No frontend
work starts before its backend contract is settled (PROJECT.md §23).

---

## Advanced pricing structures

Beyond the flat hourly rate D34 defines: progressive hour tiers (e.g. first hour
₹40, each additional ₹30), a daily cap ("max ₹250/day"), and time-of-day / peak
or demand-based rates.

**Scope when picked up:** extend the `Tariff` model with the rate structure and
extend `apps/bookings/services.quote_booking` — the single pricing seam created
in 4.2 — to return an itemised `BookingQuote`. Because `Booking.base_amount` is a
stored snapshot (D39 revised in 4.2), a new rate structure does not rewrite
existing bookings.

**Why deferred:** the SRS specifies an hourly rate only. The storage model
(`Decimal` money, `(lot, slot_type)` tariff) and the pricing seam are already in
place, so this can be added without a redesign (D42, PROJECT.md §47).

---

## Walk-in / gate lookup by booking reference

The public, unauthenticated lookup that lets a walk-in (no account) or a
barrier/QR scanner retrieve a booking from its `reference`. The field itself is
already stored and exposed on the authenticated read (D52, increment 4.6); only
the endpoint is deferred.

**Scope when picked up:** an unauthenticated `GET` by reference, the exact
response subset (a bearer key must return no more than the gate/reception needs),
rate-limiting against enumeration, and how it composes with the manager walk-in
flow and Phase 6 occupancy. The authenticated single-booking read
`GET /api/bookings/{id}/` is separately scheduled for increment 4.9.

**Why deferred:** the response shape is a function of the walk-in/gate feature
that will consume it; inventing it before that feature exists would guess the
contract (D52/§47).

---

## Repository hygiene

- `requirements.txt` pins `redis==8.1.0` and `pillow==12.3.0`, neither of which
  is imported anywhere. D6 avoids Redis and §12 forbids introducing it without
  approval. Left in place pending a decision; they are currently misleading.
