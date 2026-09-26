# SmartFix Service — PRD

**Brand**: SmartFix Service (by Versanex India)
**Type**: Doorstep home-services marketplace (Indian market)

## Roles
OWNER, ADMIN, STAFF, PROVIDER, CUSTOMER — sharing one FastAPI + MongoDB backend and one Expo Router app.

## Core User Flows (MVP built)
- Register: mobile + one-time mock OTP → set name, username, email (optional), password.
- Login: username/email/mobile + password (no OTP, no reCAPTCHA on normal login).
- Forgot password: email reset link (Emergent-managed Resend) or mobile-OTP fallback.
- Customer: browse categories/services → book (address + slot + payment) → track status → pay UPI (deep link) or Cash → review.
- Provider: apply → get approved by admin → accept assigned jobs → advance status → complete → view earnings.
- Owner/Admin: KPI dashboard, bookings CRUD & provider assignment, services & categories CRUD, coupons CRUD, provider approvals, users list, UPI payment verification.

## Payments
- CASH only, or UPI via `upi://pay?...` deep-link into GPay/PhonePe/Paytm/BHIM. Customer submits transaction reference; admin verifies. No payment gateway, no gateway fees.

## Notable Backend Endpoints (all under `/api`)
- `POST /auth/register/request-otp` `/verify-otp` `/complete`
- `POST /auth/login`, `GET /auth/me`, `POST /auth/forgot-password`, `POST /auth/reset-password`
- `GET /categories`, `GET /services?category_id=&q=`, `GET /services/{id}`
- `GET/POST/PATCH/DELETE /addresses`
- `GET /coupons`, `GET /coupons/validate?code=&amount=`
- `POST /bookings`, `GET /bookings`, `GET /bookings/{id}`, `PATCH /bookings/{id}/status`, `POST /bookings/{id}/upi-confirm`
- Admin: `/admin/services`, `/admin/categories`, `/admin/coupons`, `/admin/providers`, `/admin/bookings/{id}/verify-payment`, `/admin/stats`, `/admin/users`, `/bookings/{id}/assign`

## Tech
- Expo Router 57 + React 19 + React Native 0.86; expo-image, expo-secure-store, @gorhom/bottom-sheet-candidate, react-native-vector-icons/ionicons.
- FastAPI + Motor (MongoDB), bcrypt, PyJWT (HS256, 7-day tokens), httpx for Resend proxy.
- Emergent managed Resend integration (`X-Email-Key` header) for password reset emails.

## Deferred / Future
- Real SMS provider (MSG91/Twilio) — currently mock OTP `123456`.
- Ratings/reviews UI on customer side (backend endpoint ready).
- Push notifications (only on native build after deploy).
- Provider photo uploads (Emergent object storage) — backend hook ready to add.
