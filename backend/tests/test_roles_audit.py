"""SmartFix Services — Role/access-control audit tests.
Covers new roles SUPERVISOR/OPERATIONS/SUPPORT/FINANCE/VENDOR/TECHNICIAN and
/api/auth/permissions map, plus data isolation on addresses/bookings.
"""
import os
import time
import random
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://smartfix-pro-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DEV_OTP = "123456"

SEEDED = {
    "owner":       ("owner",       "Owner@12345", "OWNER"),
    "customer1":   ("customer1",   "Pass@123",    "CUSTOMER"),
    "supervisor1": ("supervisor1", "Pass@123",    "SUPERVISOR"),
    "ops1":        ("ops1",        "Pass@123",    "OPERATIONS"),
    "support1":    ("support1",    "Pass@123",    "SUPPORT"),
    "finance1":    ("finance1",    "Pass@123",    "FINANCE"),
    "vendor1":     ("vendor1",     "Pass@123",    "VENDOR"),
    "tech1":       ("tech1",       "Pass@123",    "TECHNICIAN"),
}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


def _login(s, identifier, password):
    r = s.post(f"{API}/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, f"login {identifier}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def tokens(s):
    out = {}
    for key, (u, p, _role) in SEEDED.items():
        out[key] = _login(s, u, p)
    return out


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- /api/auth/permissions ----------------
class TestPermissionsEndpoint:
    def _get(self, s, tok):
        r = s.get(f"{API}/auth/permissions", headers=H(tok))
        assert r.status_code == 200, r.text
        body = r.json()
        # response shape: {role, vendor_id, permissions: {...}}
        return body.get("permissions", body)

    def test_owner(self, s, tokens):
        p = self._get(s, tokens["owner"])
        assert p.get("admin") is True
        assert p.get("ops") is True
        assert p.get("support") is True
        assert p.get("finance") is True
        assert p.get("backoffice") is True
        assert p.get("field") is False

    def test_customer(self, s, tokens):
        p = self._get(s, tokens["customer1"])
        for k in ("admin", "ops", "support", "finance", "backoffice", "field"):
            assert p.get(k) is False, f"customer should not have {k}"

    def test_supervisor(self, s, tokens):
        p = self._get(s, tokens["supervisor1"])
        assert p.get("ops") is True
        assert p.get("backoffice") is True
        assert p.get("view_stats") is True
        assert p.get("admin") is False
        assert p.get("manage_services") is False

    def test_operations(self, s, tokens):
        p = self._get(s, tokens["ops1"])
        assert p.get("ops") is True
        assert p.get("backoffice") is True
        assert p.get("view_stats") is True
        assert p.get("admin") is False
        assert p.get("manage_services") is False

    def test_support(self, s, tokens):
        p = self._get(s, tokens["support1"])
        assert p.get("support") is True
        assert p.get("backoffice") is True
        assert p.get("ops") is False
        assert p.get("admin") is False

    def test_finance(self, s, tokens):
        p = self._get(s, tokens["finance1"])
        assert p.get("finance") is True
        assert p.get("backoffice") is True
        assert p.get("verify_payment") is True
        assert p.get("admin") is False

    def test_vendor(self, s, tokens):
        p = self._get(s, tokens["vendor1"])
        assert p.get("backoffice") is False
        assert p.get("field") is False

    def test_technician(self, s, tokens):
        p = self._get(s, tokens["tech1"])
        assert p.get("field") is True
        assert p.get("backoffice") is False


# ---------------- Booking fixture (customer1 -> assigned to tech1 by ops1) ----------------
@pytest.fixture(scope="session")
def assigned_booking(s, tokens):
    # get address for customer1
    r = s.get(f"{API}/addresses", headers=H(tokens["customer1"]))
    assert r.status_code == 200
    addrs = r.json()
    if not addrs:
        r = s.post(f"{API}/addresses", json={
            "label": "Home", "line1": "Flat 402, Sunrise Towers", "city": "Mumbai",
            "state": "MH", "pincode": "400001", "is_default": True,
        }, headers=H(tokens["customer1"]))
        addrs = [r.json()]
    addr_id = addrs[0]["id"]

    svcs = s.get(f"{API}/services").json()
    sched = (datetime.utcnow() + timedelta(days=3)).isoformat()
    r = s.post(f"{API}/bookings", json={
        "service_id": svcs[0]["id"], "address_id": addr_id,
        "scheduled_at": sched, "payment_method": "CASH", "notes": "role-audit test",
    }, headers=H(tokens["customer1"]))
    assert r.status_code == 200, r.text
    booking = r.json()

    # tech1 user id
    me_tech = s.get(f"{API}/auth/me", headers=H(tokens["tech1"])).json()
    tech_id = me_tech["id"]

    # ops1 assigns tech1
    r = s.post(f"{API}/bookings/{booking['id']}/assign",
               json={"provider_id": tech_id}, headers=H(tokens["ops1"]))
    assert r.status_code == 200, f"ops1 assign: {r.status_code} {r.text}"
    return {"booking": booking, "tech_id": tech_id, "addr_id": addr_id}


# ---------------- ops/support/finance/admin scope matrix ----------------
class TestScopeMatrix:
    def test_supervisor_stats_and_bookings(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["supervisor1"])).status_code == 200
        assert s.get(f"{API}/bookings", headers=H(tokens["supervisor1"])).status_code == 200

    def test_ops1_stats_and_bookings(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["ops1"])).status_code == 200
        assert s.get(f"{API}/bookings", headers=H(tokens["ops1"])).status_code == 200

    def test_supervisor_cannot_manage_services(self, s, tokens):
        cats = s.get(f"{API}/categories").json()
        r = s.post(f"{API}/admin/services", json={
            "name": f"NEG {random.randint(1,9999)}", "category_id": cats[0]["id"],
            "description": "x", "base_price": 100.0, "duration_minutes": 30,
        }, headers=H(tokens["supervisor1"]))
        assert r.status_code == 403

    def test_ops1_cannot_manage_coupons(self, s, tokens):
        r = s.post(f"{API}/admin/coupons", json={
            "code": f"NEG{random.randint(1000,9999)}", "discount_percent": 5,
            "max_discount": 50, "active": True, "description": "neg",
        }, headers=H(tokens["ops1"]))
        assert r.status_code == 403

    def test_support_stats_and_bookings(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["support1"])).status_code == 200
        assert s.get(f"{API}/bookings", headers=H(tokens["support1"])).status_code == 200

    def test_support_cannot_manage_services(self, s, tokens):
        cats = s.get(f"{API}/categories").json()
        r = s.post(f"{API}/admin/services", json={
            "name": f"NEG {random.randint(1,9999)}", "category_id": cats[0]["id"],
            "description": "x", "base_price": 100.0, "duration_minutes": 30,
        }, headers=H(tokens["support1"]))
        assert r.status_code == 403

    def test_support_cannot_assign(self, s, tokens, assigned_booking):
        r = s.post(f"{API}/bookings/{assigned_booking['booking']['id']}/assign",
                   json={"provider_id": assigned_booking["tech_id"]},
                   headers=H(tokens["support1"]))
        assert r.status_code == 403

    def test_support_cannot_verify_payment(self, s, tokens, assigned_booking):
        r = s.post(f"{API}/admin/bookings/{assigned_booking['booking']['id']}/verify-payment",
                   headers=H(tokens["support1"]))
        assert r.status_code == 403

    def test_finance_stats(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["finance1"])).status_code == 200

    def test_finance_cannot_manage_services(self, s, tokens):
        cats = s.get(f"{API}/categories").json()
        r = s.post(f"{API}/admin/services", json={
            "name": f"NEG {random.randint(1,9999)}", "category_id": cats[0]["id"],
            "description": "x", "base_price": 100.0, "duration_minutes": 30,
        }, headers=H(tokens["finance1"]))
        assert r.status_code == 403

    def test_finance_cannot_assign(self, s, tokens, assigned_booking):
        r = s.post(f"{API}/bookings/{assigned_booking['booking']['id']}/assign",
                   json={"provider_id": assigned_booking["tech_id"]},
                   headers=H(tokens["finance1"]))
        assert r.status_code == 403

    def test_finance_can_verify_payment(self, s, tokens, assigned_booking):
        # need a fresh UPI booking with awaiting-verification payment
        addr_id = assigned_booking["addr_id"]
        svcs = s.get(f"{API}/services").json()
        sched = (datetime.utcnow() + timedelta(days=4)).isoformat()
        r = s.post(f"{API}/bookings", json={
            "service_id": svcs[0]["id"], "address_id": addr_id,
            "scheduled_at": sched, "payment_method": "UPI", "notes": "finance verify",
        }, headers=H(tokens["customer1"]))
        assert r.status_code == 200, r.text
        b = r.json()
        r2 = s.post(f"{API}/bookings/{b['id']}/upi-confirm", json={"txn_ref": "FIN-TXN-1"},
                    headers=H(tokens["customer1"]))
        assert r2.status_code == 200
        r3 = s.post(f"{API}/admin/bookings/{b['id']}/verify-payment",
                    headers=H(tokens["finance1"]))
        assert r3.status_code == 200, r3.text
        assert r3.json()["payment_status"] == "PAID"

    def test_vendor_stats_forbidden(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["vendor1"])).status_code == 403

    def test_tech_stats_forbidden(self, s, tokens):
        assert s.get(f"{API}/admin/stats", headers=H(tokens["tech1"])).status_code == 403


# ---------------- Vendor scoping ----------------
class TestVendorScoping:
    def test_vendor_sees_assigned_booking(self, s, tokens, assigned_booking):
        r = s.get(f"{API}/bookings", headers=H(tokens["vendor1"]))
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert assigned_booking["booking"]["id"] in ids

    def test_vendor_can_get_scoped_booking(self, s, tokens, assigned_booking):
        r = s.get(f"{API}/bookings/{assigned_booking['booking']['id']}",
                  headers=H(tokens["vendor1"]))
        assert r.status_code == 200

    def test_vendor_forbidden_on_unassigned(self, s, tokens):
        # create a booking that is not assigned
        r = s.get(f"{API}/addresses", headers=H(tokens["customer1"]))
        addrs = r.json()
        addr_id = addrs[0]["id"]
        svcs = s.get(f"{API}/services").json()
        sched = (datetime.utcnow() + timedelta(days=5)).isoformat()
        r = s.post(f"{API}/bookings", json={
            "service_id": svcs[0]["id"], "address_id": addr_id,
            "scheduled_at": sched, "payment_method": "CASH",
        }, headers=H(tokens["customer1"]))
        bid = r.json()["id"]
        r2 = s.get(f"{API}/bookings/{bid}", headers=H(tokens["vendor1"]))
        assert r2.status_code == 403, f"expected 403 got {r2.status_code} {r2.text}"


# ---------------- Technician job lifecycle ----------------
class TestTechnicianLifecycle:
    def test_tech_sees_assigned_job(self, s, tokens, assigned_booking):
        r = s.get(f"{API}/bookings", headers=H(tokens["tech1"]))
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert assigned_booking["booking"]["id"] in ids

    def test_tech_status_progression(self, s, tokens, assigned_booking):
        bid = assigned_booking["booking"]["id"]
        for status in ("ACCEPTED", "ON_THE_WAY", "IN_PROGRESS", "COMPLETED"):
            r = s.patch(f"{API}/bookings/{bid}/status",
                        json={"status": status}, headers=H(tokens["tech1"]))
            assert r.status_code == 200, f"{status}: {r.status_code} {r.text}"
            assert r.json()["status"] == status
        # after COMPLETED with CASH payment_method it should auto-mark PAID
        r = s.get(f"{API}/bookings/{bid}", headers=H(tokens["tech1"]))
        assert r.status_code == 200
        assert r.json().get("payment_status") == "PAID", r.json()

    def test_tech_cannot_touch_other_booking(self, s, tokens):
        # create another booking, DON'T assign to tech1
        addrs = s.get(f"{API}/addresses", headers=H(tokens["customer1"])).json()
        addr_id = addrs[0]["id"]
        svcs = s.get(f"{API}/services").json()
        sched = (datetime.utcnow() + timedelta(days=6)).isoformat()
        r = s.post(f"{API}/bookings", json={
            "service_id": svcs[0]["id"], "address_id": addr_id,
            "scheduled_at": sched, "payment_method": "CASH",
        }, headers=H(tokens["customer1"]))
        bid = r.json()["id"]
        r2 = s.patch(f"{API}/bookings/{bid}/status",
                     json={"status": "ACCEPTED"}, headers=H(tokens["tech1"]))
        assert r2.status_code == 403


# ---------------- Data isolation ----------------
class TestDataIsolation:
    def test_new_customer_sees_no_data(self, s):
        mobile = f"+9199999{random.randint(10000, 99999)}"
        r = s.post(f"{API}/auth/register/request-otp", json={"mobile": mobile})
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/auth/register/verify-otp", json={"mobile": mobile, "otp": DEV_OTP})
        assert r.status_code == 200
        ft = r.json()["flow_token"]
        uname = f"iso{int(time.time())}{random.randint(100,999)}"
        r = s.post(f"{API}/auth/register/complete", json={
            "flow_token": ft, "name": "Iso Test", "username": uname,
            "password": "Pass@123", "email": f"{uname}@t.com",
        })
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]

        r = s.get(f"{API}/addresses", headers=H(tok))
        assert r.status_code == 200
        assert r.json() == []
        r = s.get(f"{API}/bookings", headers=H(tok))
        assert r.status_code == 200
        assert r.json() == []


# ---------------- OWNER unchanged ----------------
class TestOwnerUnchanged:
    def test_owner_services(self, s, tokens):
        cats = s.get(f"{API}/categories").json()
        r = s.post(f"{API}/admin/services", json={
            "name": f"OwnerSvc {random.randint(1,9999)}", "category_id": cats[0]["id"],
            "description": "owner test", "base_price": 199.0, "duration_minutes": 30,
        }, headers=H(tokens["owner"]))
        assert r.status_code == 200

    def test_owner_coupons(self, s, tokens):
        r = s.post(f"{API}/admin/coupons", json={
            "code": f"OWN{random.randint(1000,9999)}", "discount_percent": 10,
            "max_discount": 100, "active": True, "description": "owner",
        }, headers=H(tokens["owner"]))
        assert r.status_code == 200
