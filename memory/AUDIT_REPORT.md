# SmartFix Services — Audit + Bug-Fix Report

## Reported Bug (RESOLVED ✅)
**Saved address not available on booking screen.**

### Root cause
`app/book/[id].tsx` was using `useEffect(() => { load(); }, [load])`, but with Expo Router's stack navigator the Book screen stays mounted while the user pushes into `/addresses`. On `router.back()` no effect fires, so the addresses list stays stale (empty).

### Fixes (verified by testing agent — iteration_2)
1. `app/book/[id].tsx` — switched to `useFocusEffect(useCallback(() => { load() }, [load]))` so it re-fetches on every focus.
2. Auto-selects the address flagged `is_default`; falls back to the first; preserves the user's manual choice if still valid.
3. When addresses exist, we render each with a green **DEFAULT** pill on the default one, plus a dashed "+ Add or manage addresses" pressable — so users always know how to add another without dead-ending.
4. `POST /api/addresses` now force-marks the user's very first address as default, guaranteeing auto-selection on Book from a first-time customer without extra UX.
5. `app/addresses.tsx` form's initial `is_default` is now `false` so subsequent adds don't silently un-default an existing default; the "first-time" case is handled by backend rule 4.

## Branding — Official SmartFix Services Logo (APPLIED ✅)
Approved logo is stored at `frontend/assets/brand/smartfix-logo.png` (and derived PNGs `smartfix-icon.png`, `smartfix-splash.png`, `smartfix-favicon.png`). Original .webp is preserved as `smartfix-logo.webp` for reference.

- `src/brand.tsx` exports a `<Logo />` component with `sm/md/lg/xl` sizes at the correct ~3.4:1 aspect (no distortion, no re-drawing, no AI regen).
- Rendered on: Login (xl), Register (lg), Forgot Password (lg), Home tab header (sm, top-right), Profile footer (sm), Admin header (sm), Splash / /index route (xl).
- `app.json` — app icon, adaptive icon, splash image and favicon all point to `assets/brand/*`. App display name changed to "SmartFix Service".

## What was already working (confirmed)
- Auth: register 3-step OTP mock (`123456`), login (username/email/mobile + password, no OTP), forgot password (email via Resend, mobile fallback), reset-password, JWT session persistence (SecureStore native / localStorage web).
- Profile view + edit hooks + data isolation (user-scoped).
- Addresses CRUD (list, create, update, delete) — user-scoped.
- Categories & Services listing, category filter, service detail, ratings, prices in ₹.
- Coupons: SMARTFIX10 (10% up to ₹200) and FIRST100 (₹100 flat, min ₹499). Discount is validated server-side and re-applied on booking creation — not just client-side.
- Booking creation → assign provider → status transitions (PENDING → ACCEPTED → ON_THE_WAY → IN_PROGRESS → COMPLETED); cancellation by customer; admin verify UPI payment.
- Provider apply → admin approve → user role upgraded to PROVIDER → provider dashboard shows assigned jobs & earnings.
- Admin dashboard: KPIs, Bookings (assign / verify-payment), Services CRUD, Coupons CRUD, Providers approval, Users list.
- Role-based access enforced on all admin routes (customer → 403).

## Data & backend integrity
- MongoDB uses UUID `id` fields; `_id` is excluded from every response.
- All persistence verified end-to-end (35/35 pytest suite in `/app/backend/tests/backend_test.py`).
- Foreign keys: `addresses.user_id`, `bookings.customer_id`, `bookings.address_id`, `bookings.service_id`, `bookings.provider_id` all populated and reachable.

## Features that require external credentials / real APIs before production
1. **Real SMS OTP** — currently `MOCK` (`123456` returned as `dev_otp`). Swap the `send_sms_otp` helper to MSG91/Twilio and remove `dev_otp` from the response.
2. **Real UPI verification** — currently the customer submits the txn reference and an admin verifies from the dashboard. To go fully automatic you'd wire Razorpay UPI-Collect or a UPI recon feed (out of scope for this audit; user explicitly rejected payment gateways).
3. **Emergent-managed Resend** — already integrated; production reset link uses `RESET_URL` env var. During dev, `reset_token` is also echoed in the response; remove that before production launch.
4. **Real email/mobile in production** — dev only echoes tokens for testability.

## Portability / GitHub / AWS migration
- Configuration is 100 % via `.env` (`MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `RESEND_API_KEY` via `X-Email-Key` header, `RESET_URL`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`).
- No Emergent-specific hardcoding in `backend/server.py` or `frontend/src/*`. The Resend proxy uses a header injected at deploy time; on AWS you can point directly to `api.resend.com` and use a plain Resend key.
- Frontend calls only `EXPO_PUBLIC_BACKEND_URL + /api`, so switching to an AWS API Gateway endpoint is a one-line env change.
- Approved logo assets ship inside the repo (`frontend/assets/brand/*`).
- No third-party proprietary SDKs that block export.

## Security / user isolation
- All `/api/addresses`, `/api/bookings`, and `/api/providers/me` endpoints filter by `user_id = current_user.id`.
- Admin routes require `role IN {OWNER, ADMIN, STAFF}` via FastAPI dependency.
- `JWT_SECRET` is env-driven, no hardcoded secrets.
- Passwords bcrypt-hashed (12 rounds).

## Known dev-only leaks (must be closed before production)
- `dev_otp` returned in `/api/auth/register/request-otp` and `/api/auth/forgot-password` (mobile channel).
- `reset_token` returned in `/api/auth/forgot-password` (email channel).
Both are guarded by comments and are trivial to remove — they're intentional dev conveniences.

## Final end-to-end verification
- Backend: 35/35 pytest passing (`/app/test_reports/iteration_2.json`).
- Frontend E2E: login → home → service → book (auto-picks Home · DEFAULT) → confirm → booking detail with correct address; add 2nd address via profile without restarting app → returning to Book flow shows both addresses; multi-address selection swap works; branding logo renders on every listed screen. All PASS.
