# SmartFix Services — Role, Access Control & Workflow Audit

## A. Roles currently implemented (in `backend/server.py`)
`Role` enum: **OWNER, ADMIN, STAFF, PROVIDER, CUSTOMER**.
- Seeded automatically on backend startup: one OWNER (`owner / Owner@12345`).
- New registrations always land as `CUSTOMER`.
- Role promotion happens only through `/api/admin/providers/{aid}/approve` (customer → PROVIDER).

## B. Roles partially implemented
- **PROVIDER** — currently one flat role that behaves like a solo technician (individual). No parent-vendor concept; a provider cannot own or manage a team of technicians.
- **STAFF** — a generic operational role. Backend allows STAFF on: `assign_provider`, `verify_payment`, `list_providers`, `admin_stats`. Blocked from: services CRUD, categories CRUD, coupons CRUD, provider approval, `admin/users`. Frontend routes STAFF into the same `/admin` screen as OWNER/ADMIN (no separate UI, no permission gating inside the screen).

## C. Roles missing entirely
- **TECHNICIAN / WORKER** (distinct from PROVIDER company)
- **VENDOR / SERVICE PARTNER** (parent-of-technicians model)
- **SUPERVISOR** (field ops monitoring)
- **OPERATIONS / DISPATCHER**
- **CUSTOMER SUPPORT**
- **FINANCE / ACCOUNTS**

## D. Current permission model
- FastAPI dependency `current_user` verifies JWT (issuer, audience, exp, signature). ✅
- Coarse dependency `require_roles(*allowed)` gates every admin-facing endpoint. ✅
- Every user-scoped endpoint filters by `user_id`. ✅
- No fine-grained permission map; a role is either allowed or not.
- No caller-visible "what am I allowed to do" endpoint.

## E. Permission / security findings
| # | Finding | Severity |
|---|---------|----------|
| 1 | Role enum is closed; adding SUPERVISOR/OPERATIONS/SUPPORT/FINANCE/TECHNICIAN/VENDOR requires a code change every time. | Architecture |
| 2 | No scoped helpers (`require_admin_scope`, `require_ops_scope`, `require_support_scope`, `require_finance_scope`). Every route lists roles inline, so a new role won't be picked up without touching every endpoint. | Architecture |
| 3 | Frontend has no `/api/auth/permissions` — UI role-gating relies on the raw role string. | Minor |
| 4 | `admin_list_users` returns full name/mobile/email to any OWNER/ADMIN — fine, but the same shape is intended to be reused by SUPPORT/FINANCE later, which must be prevented. | Minor |
| 5 | JWT payload contains only `role` (single value). Fine today, but multi-role users (e.g. an OWNER who is also a TECHNICIAN) can't be modelled without a schema tweak. | Deferred |
| 6 | `dev_otp` and `reset_token` are still returned in dev mode. | Pre-prod cleanup only |

## F. Data-isolation findings
- `/api/addresses` filters by `user_id = current_user.id`. ✅
- `/api/bookings` filters:
  - PROVIDER → `provider_id == self`
  - OWNER/ADMIN/STAFF → all
  - CUSTOMER (default) → `customer_id == self`
- `/api/bookings/{id}` re-checks ownership before returning. ✅
- `/api/bookings/{id}/status`: CUSTOMER can only CANCEL own; PROVIDER only ACCEPT/ON_THE_WAY/IN_PROGRESS/COMPLETED on own; admin scope free. ✅
- No vendor-scoping today because vendors don't exist.

## G. Vendor / provider architecture
Missing. The PROVIDER row is a single user document (`users` collection). To support **SmartFix → Vendor → Technicians → Jobs**, we need:
1. A **VENDOR** role at the user level.
2. A `vendor_id` foreign key on **TECHNICIAN** users so the vendor's dashboard can list only its team.
3. Existing PROVIDER records can be treated as "direct SmartFix technicians" (i.e. `vendor_id = null`) — no data migration needed.

## H. Technician architecture
Missing. Today `PROVIDER == individual technician`. To distinguish company-vs-worker properly we need a **TECHNICIAN** role separate from **VENDOR**, and the assignment endpoint (`/api/bookings/{id}/assign`) should accept either.

## I. Supervisor / Operations architecture
Missing. Both roles conceptually collapse into the existing STAFF today. Recommended: keep STAFF as a legacy alias but add SUPERVISOR + OPERATIONS with a shared scope helper so we don't have to modify every endpoint later.

## J. Admin / Super Admin architecture
Working. OWNER = super admin, ADMIN = admin. Only OWNER creation is protected (auto-seed); ADMIN promotion goes through `admin/users` writes (not yet exposed as a UI, deferred as per audit rules).

## K. Recommended minimum changes
Following the user's directive ("do not build modules that aren't currently required"):

1. **Extend `Role` enum** with `SUPERVISOR, OPERATIONS, SUPPORT, FINANCE, TECHNICIAN, VENDOR`. Backward compatible; old records keep their existing roles.
2. **Add scoped role dependencies** so future roles work without editing every endpoint:
   - `admin_scope` = OWNER, ADMIN
   - `ops_scope`   = OWNER, ADMIN, STAFF, SUPERVISOR, OPERATIONS
   - `support_scope` = OWNER, ADMIN, STAFF, SUPPORT
   - `finance_scope` = OWNER, ADMIN, STAFF, FINANCE
   - `assign_scope` = ops_scope (used by `/bookings/{id}/assign`)
3. **Refactor existing endpoints** to use scopes instead of hard-coded role lists (no behaviour change for OWNER/ADMIN/STAFF).
4. **Introduce `vendor_id` optional field on users** — null for direct SmartFix technicians, set for vendor-owned technicians. No forced migration; existing PROVIDER accounts continue to work.
5. **Add `/api/auth/permissions`** so the frontend can gate UI without hard-coding role strings.
6. **Update `/api/bookings/{id}/assign`** to also accept a technician (`role IN (PROVIDER, TECHNICIAN)`) and, when the caller is a VENDOR, restrict `technician.vendor_id == vendor.id`.
7. **Update frontend index redirect** so new operational roles land on `/admin` and don't get 403 loops.

Explicitly **out of scope** (per instructions):
- Building any UI for the new roles.
- SMS/WhatsApp/UPI gateway/ratings/AMC.
- Restructuring the working customer booking flow.

## Verification requirement
After implementing K.1–K.7, call `testing_agent` to:
- Run the full backend regression suite.
- Assert the recently-fixed customer address-in-booking flow still works.
- Assert new role scopes (SUPERVISOR / OPERATIONS / SUPPORT / FINANCE / TECHNICIAN / VENDOR) return 200 on their scoped endpoints and 403 on out-of-scope endpoints.
