# SmartFix Service — PRD

**Brand**: SmartFix Services (by Versanex India). Approved logo at `frontend/assets/brand/smartfix-logo.png`.

## Roles (enforced backend + frontend)
CUSTOMER · TECHNICIAN · SUPERVISOR · OPERATIONS · SUPPORT · FINANCE · VENDOR · PROVIDER (legacy) · STAFF (legacy) · ADMIN · OWNER.
Permissions map exposed at `GET /api/auth/permissions`.

## Core flows
1. **Customer**: register (mobile OTP once, mock `123456`) → password login → browse services → pick address (auto-select default) → schedule → CASH or UPI deep-link → track status → review → contact support.
2. **Ops / Supervisor**: dispatch board in `/admin` → assign TECHNICIAN to a booking. Assignment writes booking status history + audit log + queues notifications.
3. **Technician** (`/provider` → tap job → `/tech/[id]`): view customer & address, advance status (Accept → On the way → Start → Complete), create additional-work quotation with items, send via WhatsApp deep-link (`wa.me/<phone>?text=...`).
4. **No-app customer** (`/quote/<secure_token>`): open link in any browser, no login, see full quotation, Accept / Reject / Ask for clarification. Token = `secrets.token_urlsafe(32)`, only its SHA-256 is stored (`token_hash`); the raw token is only returned to the owning technician.
5. **Support**: customers file tickets from Profile → Contact Support; SUPPORT / OWNER / ADMIN work them from Admin → Support.
6. **Finance**: revenue KPIs + ledger + UPI verification button in Admin → Finance (FINANCE / OWNER / ADMIN).
7. **Admin**: role management (change any user's role with audit log), coupons CRUD, services CRUD, provider applications, audit-log viewer.

## Payments
- Only **Cash** and **UPI**. UPI opens `upi://pay?pa=...&am=...` intent on Android/iOS; customer submits transaction ref; FINANCE/OWNER verifies → `payment_status = PAID`.
- Cash bookings auto-mark PAID on `COMPLETED`.
- Every payment/status change writes `booking_status_history` + `audit_logs`.

## Data model (MongoDB)
`users` (with optional `vendor_id`), `addresses`, `categories`, `services`, `coupons`, `bookings`, `booking_status_history`, `quotations` (token_hash, items, totals server-computed), `support_tickets`, `audit_logs`, `notifications`, `amc_plans`, `amc_subscriptions`, `reviews`, `providers` (applications), `auth_flows`, `password_resets`.

## Integrations
- Emergent-managed Resend for password-reset emails.
- Emergent LLM key configured but not used in flows yet.
- WhatsApp: `wa.me` deep-link + queued row in `notifications`. Official WhatsApp Business API is a future config swap — no fake credentials.
- SMS OTP: mocked (`123456`). Replace with MSG91 by reading `MSG91_AUTH_KEY` + `MSG91_TEMPLATE_ID` from env and calling their `/api/v5/otp` endpoint from `send_otp()` — code path already isolated.

## Not yet built (architecture-ready)
- AMC subscription billing (plans CRUD in place).
- Real WhatsApp Business API send.
- Push notifications (only on native build after deploy).
- Provider photo uploads (Emergent object storage hook).
- Ratings/reviews UI (backend endpoint `POST /api/reviews` exists).
