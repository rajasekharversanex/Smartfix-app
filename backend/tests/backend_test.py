"""SmartFix Service - Comprehensive Backend API Tests
Covers: auth, categories/services, addresses, bookings, coupons, providers, admin, RBAC.
"""
import os
import time
import random
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://smartfix-pro-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_ID = "owner"
OWNER_PW = "Owner@12345"
DEV_OTP = "123456"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def owner_token(s):
    r = s.post(f"{API}/auth/login", json={"identifier": OWNER_ID, "password": OWNER_PW})
    assert r.status_code == 200, f"Owner login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def owner_h(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="session")
def customer(s):
    """Register a fresh customer via the 3-step OTP flow."""
    suffix = f"{int(time.time())}{random.randint(100,999)}"
    mobile = f"+9198{suffix[-8:]}"
    r = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/auth/register/verify-otp", json={"mobile": mobile, "otp": DEV_OTP})
    assert r.status_code == 200, r.text
    flow_token = r.json()["flow_token"]
    username = f"testcust{suffix}"
    r = s.post(f"{API}/auth/register/complete", json={
        "flow_token": flow_token, "name": "Test Cust", "username": username,
        "password": "Pass@123", "email": f"{username}@t.com",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["access_token"], "user": body["user"], "mobile": mobile}


@pytest.fixture(scope="session")
def cust_h(customer):
    return {"Authorization": f"Bearer {customer['token']}"}


# ---------- auth ----------
class TestAuth:
    def test_owner_login(self, owner_token):
        assert owner_token

    def test_owner_me(self, s, owner_h):
        r = s.get(f"{API}/auth/me", headers=owner_h)
        assert r.status_code == 200
        assert r.json()["role"] == "OWNER"
        assert r.json()["username"] == "owner"

    def test_me_no_token(self, s):
        assert s.get(f"{API}/auth/me").status_code == 401

    def test_login_wrong_password(self, s):
        r = s.post(f"{API}/auth/login", json={"identifier": "owner", "password": "bad"})
        assert r.status_code == 401

    def test_request_otp_dev_mode(self, s):
        mobile = f"+9198{random.randint(10000000, 99999999)}"
        r = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        assert r.status_code == 200
        assert r.json().get("dev_otp") == DEV_OTP

    def test_verify_otp_invalid(self, s):
        mobile = f"+9198{random.randint(10000000, 99999999)}"
        s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        r = s.post(f"{API}/auth/register/verify-otp", json={"mobile": mobile, "otp": "000000"})
        assert r.status_code == 400

    def test_duplicate_mobile_registration(self, s, customer):
        r = s.post(f"{API}/auth/register/request-otp", json={"mobile": customer["mobile"]})
        assert r.status_code == 409

    def test_forgot_password_email_owner(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "owner@smartfix.in"})
        assert r.status_code == 200
        j = r.json()
        assert j.get("channel") == "email"
        assert "reset_token" in j

    def test_forgot_password_mobile_fallback(self, s, customer):
        # customer has email set, so should still resolve email — test mobile identifier
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": customer["mobile"]})
        assert r.status_code == 200
        # Customer registered with email, so channel is email
        assert r.json().get("channel") in ("email", "mobile")

    def test_reset_password_email_flow(self, s):
        # request reset for owner via email
        r = s.post(f"{API}/auth/forgot-password", json={"identifier": "owner@smartfix.in"})
        token = r.json()["reset_token"]
        # reset back to owner password to not break other tests
        r2 = s.post(f"{API}/auth/reset-password", json={"token": token, "new_password": OWNER_PW})
        assert r2.status_code == 200


# ---------- categories & services ----------
class TestCatalog:
    def test_list_categories(self, s):
        r = s.get(f"{API}/categories")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert "id" in data[0] and "name" in data[0]

    def test_list_services(self, s):
        r = s.get(f"{API}/services")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_service_category_filter(self, s):
        cats = s.get(f"{API}/categories").json()
        cid = cats[0]["id"]
        r = s.get(f"{API}/services", params={"category_id": cid})
        assert r.status_code == 200
        for svc in r.json():
            assert svc["category_id"] == cid

    def test_service_search(self, s):
        r = s.get(f"{API}/services", params={"q": "AC"})
        assert r.status_code == 200
        assert all("ac" in svc["name"].lower() for svc in r.json())

    def test_service_detail(self, s):
        svcs = s.get(f"{API}/services").json()
        r = s.get(f"{API}/services/{svcs[0]['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == svcs[0]["id"]

    def test_service_detail_404(self, s):
        assert s.get(f"{API}/services/nonexistent-id").status_code == 404


# ---------- addresses ----------
class TestAddresses:
    def test_addresses_crud(self, s, cust_h):
        # Create
        payload = {"label": "Home", "line1": "1 Test St", "city": "Bengaluru",
                   "state": "KA", "pincode": "560001", "is_default": True}
        r = s.post(f"{API}/addresses", json=payload, headers=cust_h)
        assert r.status_code == 200
        aid = r.json()["id"]
        # List
        r2 = s.get(f"{API}/addresses", headers=cust_h)
        assert r2.status_code == 200
        assert any(a["id"] == aid for a in r2.json())
        # Update
        payload["line1"] = "2 Updated St"
        r3 = s.patch(f"{API}/addresses/{aid}", json=payload, headers=cust_h)
        assert r3.status_code == 200
        assert r3.json()["line1"] == "2 Updated St"

    def test_addresses_no_auth(self, s):
        assert s.get(f"{API}/addresses").status_code == 401


# ---------- coupons ----------
class TestCoupons:
    def test_list_coupons(self, s):
        r = s.get(f"{API}/coupons")
        assert r.status_code == 200
        assert any(c["code"] == "SMARTFIX10" for c in r.json())

    def test_validate_coupon(self, s):
        r = s.get(f"{API}/coupons/validate", params={"code": "SMARTFIX10", "amount": 1000})
        assert r.status_code == 200
        data = r.json()
        assert data["discount"] == 100.0  # 10% capped at 200
        assert data["final"] == 900.0

    def test_validate_coupon_cap(self, s):
        r = s.get(f"{API}/coupons/validate", params={"code": "SMARTFIX10", "amount": 5000})
        assert r.status_code == 200
        assert r.json()["discount"] == 200.0  # capped

    def test_invalid_coupon(self, s):
        assert s.get(f"{API}/coupons/validate", params={"code": "NOPE", "amount": 100}).status_code == 404


# ---------- bookings full flow ----------
class TestBookings:
    @pytest.fixture(scope="class")
    def booking_ctx(self, s, cust_h, customer):
        # ensure an address
        addr = s.post(f"{API}/addresses", json={
            "label": "Home", "line1": "Book St", "city": "Bengaluru",
            "state": "KA", "pincode": "560001", "is_default": True
        }, headers=cust_h).json()
        svcs = s.get(f"{API}/services").json()
        svc = svcs[0]
        sched = (datetime.utcnow() + timedelta(days=1)).isoformat()
        r = s.post(f"{API}/bookings", json={
            "service_id": svc["id"], "address_id": addr["id"],
            "scheduled_at": sched, "notes": "Test", "payment_method": "UPI",
            "coupon_code": "SMARTFIX10",
        }, headers=cust_h)
        assert r.status_code == 200, r.text
        b = r.json()
        return {"booking": b, "svc": svc}

    def test_booking_created_with_coupon(self, booking_ctx):
        b = booking_ctx["booking"]
        assert b["coupon_code"] == "SMARTFIX10"
        assert b["discount"] > 0
        assert b["status"] == "PENDING"
        assert b["total"] == round(b["base_price"] - b["discount"], 2)

    def test_list_my_bookings(self, s, cust_h, booking_ctx):
        r = s.get(f"{API}/bookings", headers=cust_h)
        assert r.status_code == 200
        assert any(x["id"] == booking_ctx["booking"]["id"] for x in r.json())

    def test_get_booking(self, s, cust_h, booking_ctx):
        r = s.get(f"{API}/bookings/{booking_ctx['booking']['id']}", headers=cust_h)
        assert r.status_code == 200
        assert r.json()["service"] is not None
        assert r.json()["address"] is not None

    def test_upi_confirm(self, s, cust_h, booking_ctx):
        bid = booking_ctx["booking"]["id"]
        r = s.post(f"{API}/bookings/{bid}/upi-confirm", json={"txn_ref": "TXN123456"}, headers=cust_h)
        assert r.status_code == 200
        assert r.json()["upi_txn_ref"] == "TXN123456"
        assert r.json()["payment_status"] == "AWAITING_VERIFICATION"

    def test_admin_verify_payment(self, s, owner_h, booking_ctx):
        bid = booking_ctx["booking"]["id"]
        r = s.post(f"{API}/admin/bookings/{bid}/verify-payment", headers=owner_h)
        assert r.status_code == 200
        assert r.json()["payment_status"] == "PAID"

    def test_customer_cannot_change_to_accepted(self, s, cust_h, booking_ctx):
        bid = booking_ctx["booking"]["id"]
        r = s.patch(f"{API}/bookings/{bid}/status", json={"status": "ACCEPTED"}, headers=cust_h)
        assert r.status_code == 403

    def test_customer_can_cancel(self, s, cust_h, booking_ctx):
        # create a fresh booking to cancel
        addr = s.get(f"{API}/addresses", headers=cust_h).json()[0]
        svcs = s.get(f"{API}/services").json()
        sched = (datetime.utcnow() + timedelta(days=2)).isoformat()
        r = s.post(f"{API}/bookings", json={
            "service_id": svcs[1]["id"], "address_id": addr["id"],
            "scheduled_at": sched, "payment_method": "CASH",
        }, headers=cust_h)
        bid = r.json()["id"]
        r2 = s.patch(f"{API}/bookings/{bid}/status", json={"status": "CANCELLED"}, headers=cust_h)
        assert r2.status_code == 200
        assert r2.json()["status"] == "CANCELLED"


# ---------- providers ----------
class TestProviders:
    def test_provider_apply_and_approve(self, s, cust_h, customer, owner_h):
        r = s.post(f"{API}/providers/apply", json={
            "skills": ["AC", "Fan"], "service_areas": ["Bengaluru"],
            "experience_years": 3, "bio": "Experienced tech"
        }, headers=cust_h)
        assert r.status_code == 200
        aid = r.json()["id"]
        # admin listing
        r2 = s.get(f"{API}/admin/providers/applications", headers=owner_h)
        assert r2.status_code == 200
        assert any(a["id"] == aid for a in r2.json())
        # approve
        r3 = s.post(f"{API}/admin/providers/{aid}/approve", headers=owner_h)
        assert r3.status_code == 200
        # confirm role upgrade
        me = s.get(f"{API}/auth/me", headers=cust_h)
        assert me.status_code == 200
        assert me.json()["role"] == "PROVIDER"


# ---------- admin ----------
class TestAdmin:
    def test_admin_stats(self, s, owner_h):
        r = s.get(f"{API}/admin/stats", headers=owner_h)
        assert r.status_code == 200
        d = r.json()
        for k in ["todays_bookings", "pending_bookings", "active_bookings",
                  "completed_bookings", "cancelled_bookings", "total_customers",
                  "total_providers", "revenue_total", "revenue_today",
                  "pending_provider_applications"]:
            assert k in d, f"Missing stat: {k}"
            assert isinstance(d[k], (int, float)), f"{k} is not numeric"

    def test_customer_forbidden_from_admin(self, s, cust_h):
        # note: customer may have been promoted to PROVIDER in TestProviders;
        # PROVIDER is also forbidden from OWNER/ADMIN-only routes.
        r = s.get(f"{API}/admin/stats", headers=cust_h)
        assert r.status_code in (403,), f"Expected 403, got {r.status_code}"

    def test_admin_create_coupon(self, s, owner_h):
        code = f"TEST{random.randint(1000,9999)}"
        r = s.post(f"{API}/admin/coupons", json={
            "code": code, "discount_percent": 15, "max_discount": 300,
            "active": True, "description": "Test"
        }, headers=owner_h)
        assert r.status_code == 200
        assert r.json()["code"] == code

    def test_admin_create_service(self, s, owner_h):
        cats = s.get(f"{API}/categories").json()
        r = s.post(f"{API}/admin/services", json={
            "name": f"Test Svc {random.randint(1,9999)}", "category_id": cats[0]["id"],
            "description": "test", "base_price": 299.0, "duration_minutes": 30,
        }, headers=owner_h)
        assert r.status_code == 200
        assert r.json()["category_name"] == cats[0]["name"]

    def test_admin_list_providers(self, s, owner_h):
        r = s.get(f"{API}/admin/providers", headers=owner_h)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
