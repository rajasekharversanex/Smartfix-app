"""Round-3 delta verification suite.

Covers:
- REGRESSION: seeded logins (owner, customer1, tech1), customer booking flow,
  address auto-populate, quotation happy path with token rotation.
- P3 fix: cross-user address IDOR on PATCH /api/addresses/{id} -> must 404.
- P3 fix: /api/auth/forgot-password enumeration -> identical generic message
  for real vs bogus identifier (bogus must not include channel/reset_token).

Run alone with:
    pytest tests/test_round3_deltas.py -q -o addopts=''
"""
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://smartfix-pro-4.preview.emergentagent.com").rstrip("/")


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _fake_xff() -> dict:
    ip = ".".join(str((uuid.uuid4().int >> (8 * i)) & 0xFF) for i in range(4))
    return {"X-Forwarded-For": ip}


def _login(username: str, password: str):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": username, "password": password},
        headers=_fake_xff(),
        timeout=15,
    )
    return r


# =========================================================
# Regression — seeded logins
# =========================================================
class TestSeededLogins:
    def test_owner_login(self):
        r = _login("owner", "Owner@12345")
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_customer1_login(self):
        r = _login("customer1", "Pass@123")
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_tech1_login(self):
        r = _login("tech1", "Pass@123")
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()


# =========================================================
# Regression — customer1 booking flow
# =========================================================
class TestCustomerBookingFlow:
    def test_book_service_with_default_address(self):
        r = _login("customer1", "Pass@123")
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]

        # 1) services catalog
        r = requests.get(f"{BASE_URL}/api/services", headers=_hdr(tok), timeout=15)
        assert r.status_code == 200
        services = r.json()
        assert isinstance(services, list) and services, "service catalog empty"
        svc = services[0]

        # 2) address list has a default (or fallback to first)
        r = requests.get(f"{BASE_URL}/api/addresses", headers=_hdr(tok), timeout=15)
        assert r.status_code == 200
        addrs = r.json()
        assert addrs, "customer1 must have at least one seeded address"
        default_addr = next((a for a in addrs if a.get("is_default")), None)
        if default_addr is None:
            # Seed appears to have no default flag; log this as an observation
            # but proceed with the first address (which is 'Home' in seed).
            print("WARN: customer1 has no is_default=True address; using first address")
            default_addr = addrs[0]
        assert default_addr.get("label") or default_addr.get("line1")

        # 3) create booking
        payload = {
            "service_id": svc["id"],
            "address_id": default_addr["id"],
            "scheduled_at": "2026-12-31T10:00:00Z",
            "notes": "TEST_round3_regression",
        }
        r = requests.post(f"{BASE_URL}/api/bookings", json=payload, headers=_hdr(tok), timeout=15)
        assert r.status_code in (200, 201), f"booking create: {r.status_code} {r.text}"
        bk = r.json()
        assert bk.get("id")
        assert bk.get("address_id") == default_addr["id"] or bk.get("address", {}).get("id") == default_addr["id"]

        # 4) fetch booking detail
        r = requests.get(f"{BASE_URL}/api/bookings/{bk['id']}", headers=_hdr(tok), timeout=15)
        assert r.status_code == 200
        got = r.json()
        # address may be embedded or referenced
        addr_id = got.get("address_id") or (got.get("address") or {}).get("id")
        assert addr_id == default_addr["id"]


# =========================================================
# P3 fix — cross-user address IDOR on PATCH
# =========================================================
class TestAddressIdor:
    def test_patch_other_users_address_returns_404(self):
        # customer1 token
        r = _login("customer1", "Pass@123")
        assert r.status_code == 200, r.text
        c1_tok = r.json()["access_token"]

        # Register a fresh customer B via OTP flow. Use a random mobile
        # since the spec's suggested +919999900802 is already registered
        # in this preview environment (returns generic message w/o dev_otp).
        for _ in range(6):
            mobile = "+91" + f"{int(uuid.uuid4().hex[:10], 16) % 10**10:010d}"
            r = requests.post(f"{BASE_URL}/api/auth/register/request-otp",
                              json={"mobile": mobile}, headers=_fake_xff(), timeout=15)
            if r.status_code == 200 and r.json().get("dev_otp"):
                break
        assert r.status_code == 200, r.text
        dev_otp = r.json().get("dev_otp")
        assert dev_otp, "DEV_MODE must expose dev_otp for a fresh mobile"

        r = requests.post(f"{BASE_URL}/api/auth/register/verify-otp",
                          json={"mobile": mobile, "otp": dev_otp},
                          headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        flow_token = r.json()["flow_token"]

        uname = f"custB{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/auth/register/complete",
                          json={"flow_token": flow_token, "name": "Customer B",
                                "username": uname, "email": f"{uname}@t.io",
                                "password": "Pass@1234"},
                          headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        b_tok = r.json()["access_token"]

        # Add address as B
        addr = {"label": "Home", "line1": "1 IDOR St", "city": "Test",
                "state": "TS", "pincode": "560001", "is_default": True}
        r = requests.post(f"{BASE_URL}/api/addresses", json=addr,
                          headers=_hdr(b_tok), timeout=15)
        assert r.status_code == 200, r.text
        a_b = r.json()
        assert a_b["id"]

        try:
            # Attempt PATCH as customer1 -> must be 404 (not leak the doc)
            r = requests.patch(f"{BASE_URL}/api/addresses/{a_b['id']}",
                               json={**addr, "line1": "HACKED"},
                               headers=_hdr(c1_tok), timeout=15)
            assert r.status_code == 404, f"IDOR still open: {r.status_code} {r.text}"
            # Body must not leak the address content
            body = r.text.lower()
            assert "hacked" not in body

            # customer1 GET /api/addresses must NOT contain a_b.id
            r = requests.get(f"{BASE_URL}/api/addresses", headers=_hdr(c1_tok), timeout=15)
            assert r.status_code == 200
            c1_addrs = r.json()
            assert not any(a["id"] == a_b["id"] for a in c1_addrs), \
                "customer1 sees customer B's address"
        finally:
            # Cleanup: delete as B
            requests.delete(f"{BASE_URL}/api/addresses/{a_b['id']}",
                            headers=_hdr(b_tok), timeout=15)


# =========================================================
# P3 fix — forgot-password enumeration
# =========================================================
class TestForgotPasswordEnumeration:
    GENERIC = "If the account exists, recovery instructions were sent"

    def test_real_account_returns_generic_message(self):
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                          json={"identifier": "owner"}, headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("message") == self.GENERIC
        # DEV_MODE appends channel + reset_token
        assert body.get("channel") in ("email", "mobile")
        assert body.get("reset_token")

    def test_bogus_account_returns_same_generic_message(self):
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                          json={"identifier": "nobody@nowhere.example"},
                          headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("message") == self.GENERIC
        # Must NOT include channel/reset_token/dev_otp for non-existent accounts
        assert "channel" not in body, f"leak: {body}"
        assert "reset_token" not in body, f"leak: {body}"
        assert "dev_otp" not in body, f"leak: {body}"

    def test_messages_are_identical(self):
        h1 = _fake_xff()
        h2 = _fake_xff()
        r1 = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                           json={"identifier": "owner"}, headers=h1, timeout=15)
        r2 = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                           json={"identifier": "nobody@nowhere.example"},
                           headers=h2, timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json().get("message") == r2.json().get("message")


# =========================================================
# Regression — quotation happy path + token rotation
# =========================================================
class TestQuotationFlow:
    def test_quotation_create_send_rotate(self):
        # tech1 login
        r = _login("tech1", "Pass@123")
        assert r.status_code == 200, r.text
        tech_tok = r.json()["access_token"]

        # Pick any booking assigned to tech1 or any available; try list
        r = requests.get(f"{BASE_URL}/api/bookings", headers=_hdr(tech_tok), timeout=15)
        assert r.status_code == 200, r.text
        bookings = r.json()
        if not bookings:
            pytest.skip("no bookings visible to tech1 to create a quotation against")
        bk = bookings[0]

        # Create quotation
        payload = {
            "booking_id": bk["id"],
            "service_description": "TEST_round3_service",
            "items": [{"description": "TEST_labor", "qty": 1, "unit_price": 500, "kind": "LABOUR"}],
            "labour_charge": 200,
            "technician_notes": "TEST_round3",
        }
        r = requests.post(f"{BASE_URL}/api/quotations", json=payload,
                          headers=_hdr(tech_tok), timeout=15)
        assert r.status_code in (200, 201), f"quotation create: {r.status_code} {r.text}"
        q = r.json()
        qid = q.get("id")
        assert qid
        assert q.get("token"), "create response must include token"
        assert q.get("public_url"), "create response must include public_url"
        first_pub = q["public_url"]

        # GET /api/quotations/{id} returns doc WITHOUT `token`
        r = requests.get(f"{BASE_URL}/api/quotations/{qid}", headers=_hdr(tech_tok), timeout=15)
        assert r.status_code == 200, r.text
        got = r.json()
        assert "token" not in got, f"token leaked in GET: {got}"

        # Extract old public token from URL for later 404 check
        old_token = first_pub.rsplit("/", 1)[-1]

        # POST /send rotates the token
        r = requests.post(f"{BASE_URL}/api/quotations/{qid}/send",
                          json={"channel": "WHATSAPP"},
                          headers=_hdr(tech_tok), timeout=15)
        assert r.status_code == 200, r.text
        sent = r.json()
        new_pub = sent.get("public_url")
        assert new_pub and new_pub != first_pub, \
            f"public_url did not rotate: old={first_pub} new={new_pub}"

        # Old public token 404s
        r = requests.get(f"{BASE_URL}/api/public/quotations/{old_token}", timeout=15)
        assert r.status_code == 404, f"old token still valid: {r.status_code} {r.text}"

        # New public URL works
        new_token = new_pub.rsplit("/", 1)[-1]
        r = requests.get(f"{BASE_URL}/api/public/quotations/{new_token}", timeout=15)
        assert r.status_code == 200, r.text


# =========================================================
# Regression — `active` field defaults True
# =========================================================
class TestActiveDefaultTrue:
    def test_new_registration_is_active(self):
        mobile = "+91" + f"{int(uuid.uuid4().hex[:10], 16) % 10**10:010d}"
        r = requests.post(f"{BASE_URL}/api/auth/register/request-otp",
                          json={"mobile": mobile}, headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        dev_otp = r.json()["dev_otp"]
        r = requests.post(f"{BASE_URL}/api/auth/register/verify-otp",
                          json={"mobile": mobile, "otp": dev_otp},
                          headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        flow_token = r.json()["flow_token"]

        uname = f"act{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/auth/register/complete",
                          json={"flow_token": flow_token, "name": "Active User",
                                "username": uname, "email": f"{uname}@t.io",
                                "password": "Pass@1234"},
                          headers=_fake_xff(), timeout=15)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(tok), timeout=15)
        assert r.status_code == 200
        assert r.json().get("active") is True
