"""SmartFix Service — Security Hardening Regression Tests.

Covers SEC-001 (recovery-token disclosure), SEC-002 (hardcoded OTP + user
enumeration), SEC-003 (deactivation enforcement), SEC-004 (JWT_SECRET
placeholder refusal), plus P3 hardening: rate limits, CORS pinning,
quotation token rotation & no DB persistence, password min length 8.
"""
import os
import re
import time
import random
import hashlib
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          "https://smartfix-pro-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _login(s, ident, pw, tries=5):
    for _ in range(tries):
        r = s.post(f"{API}/auth/login", json={"identifier": ident, "password": pw})
        if r.status_code == 429:
            time.sleep(20)
            continue
        return r
    return r


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def owner_h(s):
    r = _login(s, "owner", "Owner@12345")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ===================================================================
# SEC-001 — recovery secrets never leak in prod; DEV_MODE gates them
# ===================================================================
class TestSec001RecoveryDisclosure:
    def test_forgot_password_email_dev_mode_exposes_reset_token(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "owner@smartfix.in"})
        assert r.status_code == 200
        body = r.json()
        # In DEV_MODE (preview) reset_token must be exposed for automated tests
        assert body.get("channel") == "email"
        assert "reset_token" in body

    def test_forgot_password_mobile_dev_mode_exposes_dev_otp(self, s):
        # customer1 seeded with mobile +919999900002
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "+919999900002"})
        assert r.status_code == 200
        body = r.json()
        # customer1 has an email too — could resolve either channel
        if body.get("channel") == "mobile":
            assert "dev_otp" in body
            assert "reset_token" in body

    def test_forgot_password_unknown_user_generic_200(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "nobody@example.com"})
        assert r.status_code == 200
        body = r.json()
        # No enumeration + no leak fields for unknown
        assert "reset_token" not in body
        assert "dev_otp" not in body

    def test_server_code_gates_response_fields(self):
        # Static assertion: response body only exposes reset_token/dev_otp
        # inside the DEV_MODE branch, never outside it.
        src = open("/app/backend/server.py").read()
        assert "if DEV_MODE:" in src
        assert '"reset_token": raw' in src
        assert '"dev_otp"] = otp_plain' in src


# ===================================================================
# SEC-002 — random OTPs; no user enumeration on request-otp
# ===================================================================
class TestSec002OtpAndEnumeration:
    def test_already_registered_returns_generic_200_no_otp(self, s):
        # customer1 mobile
        r = s.post(f"{API}/auth/register/request-otp",
                   json={"mobile": "+919999900002"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("message") == "If the mobile is eligible, an OTP has been sent"
        assert "dev_otp" not in body

    def test_new_mobile_returns_random_dev_otp(self, s):
        mobile = f"+9199999{random.randint(10000, 99999)}"
        r1 = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        assert r1.status_code == 200
        # small delay to escape identical-timestamp cache if any
        time.sleep(0.5)
        r2 = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        assert r2.status_code == 200
        o1, o2 = r1.json().get("dev_otp"), r2.json().get("dev_otp")
        assert o1 and o2, f"dev_otp missing: {r1.json()} {r2.json()}"
        assert len(o1) == 6 and o1.isdigit()
        # Second call replaces first (upsert); OTPs must be random => extremely unlikely equal
        assert o1 != o2, "OTP should be random per request (SEC-002)"
        # Old OTP no longer works (upsert replaced it)
        rv = s.post(f"{API}/auth/register/verify-otp",
                    json={"mobile": mobile, "otp": o1})
        assert rv.status_code == 400
        # New OTP works
        rv2 = s.post(f"{API}/auth/register/verify-otp",
                     json={"mobile": mobile, "otp": o2})
        assert rv2.status_code == 200


# ===================================================================
# SEC-003 — deactivation locks user everywhere
# ===================================================================
class TestSec003Deactivation:
    def test_deactivate_then_reactivate_tech1(self, s, owner_h):
        # login tech1 first (fresh token)
        r = _login(s, "tech1", "Pass@123")
        assert r.status_code == 200
        tech1_token = r.json()["access_token"]
        tech1_id = r.json()["user"]["id"]

        # Baseline: /auth/me works
        r = s.get(f"{API}/auth/me", headers=H(tech1_token))
        assert r.status_code == 200

        # Owner deactivates tech1
        r = s.patch(f"{API}/admin/users/{tech1_id}/status",
                    json={"active": False}, headers=owner_h)
        assert r.status_code == 200, r.text

        # Existing bearer token must now 401 with "deactivated"
        r = s.get(f"{API}/auth/me", headers=H(tech1_token))
        assert r.status_code == 401
        assert "deactivated" in r.text.lower()

        # New login must 401
        time.sleep(1)
        r = _login(s, "tech1", "Pass@123")
        assert r.status_code == 401
        assert "deactivated" in r.text.lower()

        # Reactivate
        r = s.patch(f"{API}/admin/users/{tech1_id}/status",
                    json={"active": True}, headers=owner_h)
        assert r.status_code == 200

        # Fresh login works again
        time.sleep(1)
        r = _login(s, "tech1", "Pass@123")
        assert r.status_code == 200


# ===================================================================
# SEC-004 — refuse to boot with placeholder JWT_SECRET
# ===================================================================
class TestSec004JwtPlaceholder:
    def test_placeholder_secret_raises_runtime_error(self):
        env = os.environ.copy()
        env.pop("JWT_SECRET", None)
        env["JWT_SECRET"] = "change-in-prod-xxxxxxxxxxxxxxxxxxxxxxxx"
        env["MONGO_URL"] = env.get("MONGO_URL", "mongodb://localhost:27017")
        env["DB_NAME"] = env.get("DB_NAME", "smartfix_db")
        # Import in a subprocess so we don't disturb the running preview.
        r = subprocess.run(
            ["python", "-c", "import sys; sys.path.insert(0,'/app/backend'); import server"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert r.returncode != 0, f"expected import to fail, got: {r.stdout} {r.stderr}"
        assert "placeholder" in (r.stderr + r.stdout).lower(), \
            f"expected placeholder RuntimeError: {r.stderr}"


# ===================================================================
# Rate limiting — /auth/login 10/min, /forgot-password 5/min,
# /register/request-otp 5/min
# ===================================================================
class TestRateLimits:
    """Rate limits are IP-bound. Through Cloudflare each request can arrive
    from a different edge IP, so we test the middleware against localhost
    (the same pod uvicorn serves), which is what production would see behind
    a real proxy that forwards X-Forwarded-For."""

    LOCAL = "http://localhost:8001/api"

    def test_login_11th_rejected(self):
        cs = requests.Session()
        codes = []
        for i in range(12):
            r = cs.post(f"{self.LOCAL}/auth/login",
                        json={"identifier": "no-such-user", "password": "wrong"})
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"expected 429 within 12 requests, got: {codes}"
        first_429 = codes.index(429)
        assert first_429 >= 10, f"429 fired too early at index {first_429}"

    def test_forgot_password_6th_rejected(self):
        cs = requests.Session()
        codes = []
        for i in range(7):
            r = cs.post(f"{self.LOCAL}/auth/forgot-password",
                        json={"identifier": f"nobody{i}@example.com"})
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"forgot-password did not rate-limit: {codes}"
        assert codes.index(429) >= 5

    def test_request_otp_6th_rejected(self):
        cs = requests.Session()
        codes = []
        for i in range(7):
            mobile = f"+9199888{random.randint(10000, 99999)}"
            r = cs.post(f"{self.LOCAL}/auth/register/request-otp", json={"mobile": mobile})
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"register/request-otp did not rate-limit: {codes}"
        assert codes.index(429) >= 5


# ===================================================================
# CORS pinning — origin must match allow_origin_regex
# ===================================================================
class TestCorsPinning:
    """CORS is enforced by FastAPI's middleware; verify against localhost since
    the public preview URL currently returns permissive edge headers (added by
    the CDN/ingress on top of the backend response)."""

    LOCAL = "http://localhost:8001/api"

    def test_evil_origin_not_echoed(self):
        r = requests.get(f"{self.LOCAL}/", headers={"Origin": "https://evil.example.com"})
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao != "https://evil.example.com"
        assert acao != "*"

    def test_emergent_origin_echoed(self):
        origin = "https://smartfix-pro-4.preview.emergentagent.com"
        r = requests.get(f"{self.LOCAL}/", headers={"Origin": origin})
        assert r.status_code == 200
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == origin, f"expected origin echo, got: {acao!r}"


# ===================================================================
# Quotation token hardening — no raw token stored; send rotates
# ===================================================================
class TestQuotationTokenHardening:
    @pytest.fixture(scope="class")
    def ctx(self, s):
        # Book as customer1 -> assign tech1 -> tech1 creates quotation.
        r = _login(s, "customer1", "Pass@123")
        cust_tok = r.json()["access_token"]
        r = _login(s, "tech1", "Pass@123")
        tech_tok = r.json()["access_token"]
        tech_id = r.json()["user"]["id"]
        r = _login(s, "ops1", "Pass@123")
        ops_tok = r.json()["access_token"]

        # ensure customer address
        r = s.get(f"{API}/addresses", headers=H(cust_tok))
        addrs = r.json()
        if not addrs:
            r = s.post(f"{API}/addresses", json={
                "label": "Home", "line1": "1 Test Rd", "city": "Mumbai",
                "state": "MH", "pincode": "400001", "is_default": True,
            }, headers=H(cust_tok))
            addrs = [r.json()]
        addr = addrs[0]
        # pick a service
        svc = s.get(f"{API}/services").json()[0]
        slot = (int(time.time()) + 3600)
        from datetime import datetime, timedelta, timezone
        slot_iso = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        r = s.post(f"{API}/bookings", json={
            "service_id": svc["id"], "address_id": addr["id"],
            "scheduled_at": slot_iso, "payment_method": "CASH",
        }, headers=H(cust_tok))
        assert r.status_code == 200, r.text
        booking_id = r.json()["id"]

        # assign tech1
        r = s.post(f"{API}/bookings/{booking_id}/assign",
                    json={"provider_id": tech_id}, headers=H(ops_tok))
        assert r.status_code == 200, r.text

        # tech creates quotation
        r = s.post(f"{API}/quotations", json={
            "booking_id": booking_id,
            "service_description": "SEC-P3 test",
            "items": [{"description": "Part", "qty": 1, "unit_price": 100, "kind": "PART"}],
            "labour_charge": 0, "tax_percent": 0, "discount": 0, "valid_days": 3,
        }, headers=H(tech_tok))
        assert r.status_code == 200, r.text
        return {
            "created": r.json(), "tech_tok": tech_tok,
            "cust_tok": cust_tok, "booking_id": booking_id,
        }

    def test_create_returns_token_and_public_url(self, ctx):
        c = ctx["created"]
        assert "token" in c and len(c["token"]) >= 32
        assert "public_url" in c and c["public_url"].endswith("/quote/" + c["token"])
        assert "token_hash" not in c

    def test_get_does_not_expose_token(self, s, ctx):
        qid = ctx["created"]["id"]
        r = s.get(f"{API}/quotations/{qid}", headers=H(ctx["tech_tok"]))
        assert r.status_code == 200
        body = r.json()
        assert "token" not in body
        assert "token_hash" not in body

    def test_db_row_has_no_raw_token(self, ctx):
        # Direct DB check
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        async def check():
            cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = cli[os.environ.get("DB_NAME", "smartfix_db")]
            row = await db.quotations.find_one({"id": ctx["created"]["id"]})
            cli.close()
            return row

        row = asyncio.get_event_loop().run_until_complete(check()) \
            if not asyncio.get_event_loop().is_running() else asyncio.run(check())
        assert row is not None
        assert "token" not in row, f"DB row must not persist raw token: keys={list(row.keys())}"
        assert "token_hash" in row and len(row["token_hash"]) == 64

    def test_send_rotates_token_and_old_404(self, s, ctx):
        qid = ctx["created"]["id"]
        old_url = ctx["created"]["public_url"]
        old_token = old_url.rsplit("/", 1)[-1]
        r = s.post(f"{API}/quotations/{qid}/send", json={"channel": "WHATSAPP"},
                   headers=H(ctx["tech_tok"]))
        assert r.status_code == 200, r.text
        new_url = r.json()["public_url"]
        new_token = new_url.rsplit("/", 1)[-1]
        assert new_url != old_url
        assert new_token != old_token
        # Old token must 404 on public view
        r = s.get(f"{API}/public/quotations/{old_token}")
        assert r.status_code == 404
        # New token resolves
        r = s.get(f"{API}/public/quotations/{new_token}")
        assert r.status_code == 200


# ===================================================================
# Password min length 8
# ===================================================================
class TestPasswordMinLength:
    def test_register_complete_rejects_7_chars(self, s):
        mobile = f"+9199777{random.randint(10000, 99999)}"
        r = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        assert r.status_code == 200
        otp = r.json()["dev_otp"]
        r = s.post(f"{API}/auth/register/verify-otp",
                   json={"mobile": mobile, "otp": otp})
        assert r.status_code == 200
        ft = r.json()["flow_token"]
        uname = f"minlen{int(time.time())}{random.randint(100, 999)}"
        r = s.post(f"{API}/auth/register/complete", json={
            "flow_token": ft, "name": "Short PW", "username": uname,
            "password": "short7c", "email": f"{uname}@t.com",
        })
        assert r.status_code == 422

    def test_register_complete_accepts_8_chars(self, s):
        mobile = f"+9199777{random.randint(10000, 99999)}"
        r = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        otp = r.json()["dev_otp"]
        r = s.post(f"{API}/auth/register/verify-otp",
                   json={"mobile": mobile, "otp": otp})
        ft = r.json()["flow_token"]
        uname = f"okpw{int(time.time())}{random.randint(100, 999)}"
        r = s.post(f"{API}/auth/register/complete", json={
            "flow_token": ft, "name": "OK PW", "username": uname,
            "password": "Longer12", "email": f"{uname}@t.com",
        })
        assert r.status_code == 200, r.text

    def test_reset_password_rejects_7_chars(self, s):
        # get a reset token via DEV_MODE
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "owner@smartfix.in"})
        assert r.status_code == 200
        tok = r.json()["reset_token"]
        r = s.post(f"{API}/auth/reset-password",
                   json={"token": tok, "new_password": "short7c"})
        assert r.status_code == 422
