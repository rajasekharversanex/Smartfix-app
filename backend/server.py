from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import List, Optional, Annotated, Literal
from datetime import datetime, timedelta, timezone
from enum import Enum
from html import escape
from pathlib import Path
import os, re, uuid, secrets, hashlib, logging, httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.environ.get("JWT_ISSUER", "smartfix-api")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "smartfix-app")
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "SmartFix Service")
RESET_URL = os.environ.get("RESET_URL", "")
# DEV_MODE gates dev-only response fields (dev_otp, reset_token).
# MUST be "false" (or unset) in production so recovery secrets never leak
# through the API and are delivered only via email/SMS.
DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"
# CORS origin regex — default (dev) allows the Emergent preview host + localhost.
# In production, override to your explicit domain(s) via env.
CORS_ORIGIN_REGEX = os.environ.get(
    "CORS_ORIGIN_REGEX",
    r"https://.*\.emergentagent\.com|http://localhost(:\d+)?",
)

import bcrypt, jwt

ALGORITHM = "HS256"
JWT_DAYS = 7
OTP_TTL = timedelta(minutes=10)
RESET_TTL = timedelta(minutes=30)
EMAIL_BASE_URL = "https://integrations.emergentagent.com"

# Fail-fast if JWT_SECRET still contains a placeholder string. Prevents
# accidentally shipping the development signing key to production.
if any(bad in JWT_SECRET.lower() for bad in ("changeme", "change-in-prod", "placeholder")):
    raise RuntimeError(
        "JWT_SECRET looks like a placeholder — generate a fresh value with "
        "`python -c 'import secrets;print(secrets.token_urlsafe(48))'` and set it "
        "in Deployment → Secrets before starting the app."
    )

if DEV_MODE:
    # Loud, unmissable banner so nobody deploys with the dev gate on and
    # accidentally re-opens SEC-001 (recovery-secret disclosure).
    logging.getLogger("smartfix").warning(
        "\n"
        "  ############################################################\n"
        "  ##  DEV_MODE=true — DO NOT USE THIS BUILD FOR PRODUCTION  ##\n"
        "  ##  Recovery tokens are exposed in API responses for      ##\n"
        "  ##  testing. Set DEV_MODE=false in Deployment > Secrets.  ##\n"
        "  ############################################################"
    )

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
users = db.users
flows = db.auth_flows
resets = db.password_resets
categories_c = db.categories
services_c = db.services
addresses_c = db.addresses
bookings_c = db.bookings
providers_c = db.providers
coupons_c = db.coupons
reviews_c = db.reviews
quotations_c = db.quotations
booking_history_c = db.booking_status_history
tickets_c = db.support_tickets
audit_c = db.audit_logs
notifications_c = db.notifications
amc_plans_c = db.amc_plans
amc_subs_c = db.amc_subscriptions

app = FastAPI(title="SmartFix API")
api = APIRouter(prefix="/api")
BEARER = HTTPBearer(auto_error=False)

# --- Rate limiter (sliding-window, in-memory, per client IP) ---
# Behind Emergent/Kubernetes ingress the direct `request.client.host` is the
# proxy edge, not the real user, which would collapse everyone into the same
# bucket. TRUSTED_PROXY_HOPS controls how many trailing hops of
# X-Forwarded-For we peel off — the value at that position is the actual
# client IP because our proxy always appends and cannot be bypassed by an
# attacker prepending fake hops. Default 1 = single reverse proxy in front.
TRUSTED_PROXY_HOPS = max(1, int(os.environ.get("TRUSTED_PROXY_HOPS", "1")))


def _client_ip_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        # Real client IP = XFF[len - TRUSTED_PROXY_HOPS]. Our trusted proxies
        # always APPEND the caller they saw to XFF, so the rightmost N values
        # are proxy-authoritative and cannot be forged. With N=1 that's the
        # rightmost value (the client as seen by our single proxy). Prepended
        # attacker hops sit on the LEFT and are ignored.
        idx = max(0, len(hops) - TRUSTED_PROXY_HOPS)
        return hops[idx]
    real = request.headers.get("x-real-ip")
    return real.strip() if real else get_remote_address(request)


limiter = Limiter(key_func=_client_ip_key, default_limits=[])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartfix")


def gen_otp() -> str:
    """Cryptographically-random 6-digit OTP (SEC-002 fix). Never a constant."""
    return f"{secrets.randbelow(1_000_000):06d}"


def dev_only_field(value):
    """Return the value when running in DEV_MODE, else None.
    Used to gate response fields (dev_otp / reset_token) that must not leak
    in production. SEC-001 fix."""
    return value if DEV_MODE else None


# ---------- helpers ----------
def now_utc():
    # Naive UTC datetime to match how MongoDB round-trips BSON datetimes,
    # so comparisons in queries and Python don't mix tz-aware and naive.
    return datetime.utcnow()


def uid() -> str:
    return str(uuid.uuid4())


def norm_mobile(v: str) -> str:
    v = re.sub(r"[ ()-]", "", (v or "").strip())
    # Accept 10-digit Indian format too
    if re.fullmatch(r"\d{10}", v):
        v = "+91" + v
    if not re.fullmatch(r"\+[1-9]\d{7,14}", v):
        raise HTTPException(422, "Mobile must be in E.164 format e.g. +91XXXXXXXXXX")
    return v


def norm_email(v: Optional[str]) -> Optional[str]:
    return v.lower().strip() if v else None


def norm_login(v: str) -> str:
    v = (v or "").strip()
    return v.lower() if "@" in v else v


def digest(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def hash_password(p: str) -> str:
    # Minimum length 8 (was 6): P3 hardening from security audit.
    if len(p) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt(rounds=12)).decode()


def check_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def issue_token(user: dict) -> str:
    t = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "role": user["role"],
        "iat": t,
        "exp": t + timedelta(days=JWT_DAYS),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


async def current_user(c: Annotated[Optional[HTTPAuthorizationCredentials], Depends(BEARER)]):
    if not c:
        raise HTTPException(401, "Missing bearer token")
    try:
        p = jwt.decode(
            c.credentials, JWT_SECRET, algorithms=[ALGORITHM],
            issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
            options={"require": ["sub", "role", "exp"]},
        )
        u = await users.find_one({"id": p["sub"]}, {"_id": 0, "password_hash": 0})
    except (jwt.PyJWTError, ValueError):
        u = None
    if not u:
        raise HTTPException(401, "Invalid or expired token")
    # SEC-003 fix: refuse tokens for accounts an admin has deactivated.
    # `active` defaults to True for legacy accounts that predate the flag.
    if u.get("active") is False:
        raise HTTPException(401, "Account is deactivated")
    return u


def require_roles(*allowed):
    async def dep(u=Depends(current_user)):
        if u["role"] not in allowed:
            raise HTTPException(403, "Insufficient role")
        return u
    return dep


# Scoped convenience wrappers used across the app so a new role picked up in
# permissions_for() is automatically allowed on the right endpoints.
def require_admin():   return require_roles(*ADMIN_ROLES)
def require_ops():     return require_roles(*OPS_ROLES)
def require_support(): return require_roles(*SUPPORT_ROLES)
def require_finance(): return require_roles(*FINANCE_ROLES)
def require_backoffice(): return require_roles(*BACKOFFICE_ROLES)


# ---------- email helper (Resend via Emergent proxy) ----------
async def send_reset_email(to: str, name: str, reset_link: str):
    if not EMAIL_KEY:
        logger.warning("No EMERGENT_EMAIL_KEY configured; skipping email")
        return None
    subject = f"Reset your {EMAIL_FROM_NAME} password"
    safe_name = escape(name or "there")
    html = (
        f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#1A1D1C">'
        f'<h2 style="color:#0F7A49;margin:0 0 12px 0">Reset your password</h2>'
        f'<p>Hi {safe_name},</p>'
        f'<p>We received a request to reset the password for your {escape(EMAIL_FROM_NAME)} account. '
        f'Click the button below to choose a new password. This link expires in 30 minutes.</p>'
        f'<p style="margin:24px 0"><a href="{escape(reset_link)}" '
        f'style="background:#0F7A49;color:#FFFFFF;padding:12px 24px;text-decoration:none;border-radius:8px;display:inline-block">Reset password</a></p>'
        f'<p style="font-size:12px;color:#707A76">If you did not request this, you can ignore this email. '
        f'We never ask for your password or card details by email.</p>'
        f'<p style="font-size:12px;color:#707A76">Sent by {escape(EMAIL_FROM_NAME)} — by Versanex India.</p>'
        f'</td></tr></table>'
    )
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json={"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME},
            )
            r.raise_for_status()
            return r.json().get("id")
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return None


# ---------- pydantic models ----------
class Role(str, Enum):
    OWNER = "OWNER"; ADMIN = "ADMIN"; STAFF = "STAFF"
    SUPERVISOR = "SUPERVISOR"; OPERATIONS = "OPERATIONS"
    SUPPORT = "SUPPORT"; FINANCE = "FINANCE"
    VENDOR = "VENDOR"; TECHNICIAN = "TECHNICIAN"
    PROVIDER = "PROVIDER"   # legacy: individual field technician
    CUSTOMER = "CUSTOMER"


# Scope groups for authorisation. Roles that satisfy a scope share the same
# access checks so future operational/support/finance users work without
# touching every endpoint.
ADMIN_ROLES     = ("OWNER", "ADMIN")
OPS_ROLES       = ("OWNER", "ADMIN", "STAFF", "SUPERVISOR", "OPERATIONS")
SUPPORT_ROLES   = ("OWNER", "ADMIN", "STAFF", "SUPPORT")
FINANCE_ROLES   = ("OWNER", "ADMIN", "STAFF", "FINANCE")
# Union of everyone who can see the /admin control center (any back-office role).
BACKOFFICE_ROLES = tuple(sorted(set(ADMIN_ROLES + OPS_ROLES + SUPPORT_ROLES + FINANCE_ROLES)))
# Roles that can actually deliver a job on the ground.
FIELD_ROLES = ("PROVIDER", "TECHNICIAN")


# Fine-grained permission map exposed via /api/auth/permissions so the
# frontend can gate UI without hard-coding role strings.
def permissions_for(role: str) -> dict:
    return {
        "backoffice": role in BACKOFFICE_ROLES,
        "admin": role in ADMIN_ROLES,
        "ops": role in OPS_ROLES,
        "support": role in SUPPORT_ROLES,
        "finance": role in FINANCE_ROLES,
        "field": role in FIELD_ROLES,
        "manage_services": role in ADMIN_ROLES,
        "manage_categories": role in ADMIN_ROLES,
        "manage_coupons": role in ADMIN_ROLES,
        "manage_users": role in ADMIN_ROLES,
        "manage_providers": role in ADMIN_ROLES,
        "assign_jobs": role in OPS_ROLES,
        "verify_payment": role in FINANCE_ROLES,
        "view_stats": role in BACKOFFICE_ROLES,
        "view_all_bookings": role in BACKOFFICE_ROLES,
    }


class RequestOtpIn(BaseModel):
    mobile: str


class VerifyOtpIn(BaseModel):
    mobile: str
    otp: str = Field(pattern=r"^\d{6}$")


class CompleteRegIn(BaseModel):
    flow_token: str
    name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(min_length=8)
    email: Optional[EmailStr] = None


class LoginIn(BaseModel):
    identifier: str
    password: str


class ForgotIn(BaseModel):
    identifier: str


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8)
    otp: Optional[str] = None


class CategoryIn(BaseModel):
    name: str
    icon: str = "construct-outline"
    image_url: Optional[str] = None
    sort_order: int = 0
    active: bool = True


class ServiceIn(BaseModel):
    name: str
    category_id: str
    description: str = ""
    image_url: Optional[str] = None
    base_price: float
    promo_price: Optional[float] = None
    duration_minutes: int = 60
    active: bool = True


class AddressIn(BaseModel):
    label: str  # Home / Office / Other
    line1: str
    line2: Optional[str] = ""
    city: str
    state: str = ""
    pincode: str
    landmark: Optional[str] = ""
    is_default: bool = False


class BookingIn(BaseModel):
    service_id: str
    address_id: str
    scheduled_at: datetime
    notes: Optional[str] = ""
    payment_method: Literal["CASH", "UPI"] = "CASH"
    coupon_code: Optional[str] = None


class BookingStatusIn(BaseModel):
    status: Literal["PENDING", "ACCEPTED", "ON_THE_WAY", "IN_PROGRESS", "COMPLETED", "CANCELLED"]


class AssignProviderIn(BaseModel):
    provider_id: str


class UpiConfirmIn(BaseModel):
    txn_ref: str


class ReviewIn(BaseModel):
    booking_id: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = ""


class CouponIn(BaseModel):
    code: str
    discount_percent: float = Field(ge=0, le=100)
    max_discount: Optional[float] = None
    active: bool = True
    description: str = ""


class ProviderApplyIn(BaseModel):
    skills: List[str] = []
    service_areas: List[str] = []
    experience_years: int = 0
    bio: str = ""


class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


# ---------- startup ----------
@app.on_event("startup")
async def startup():
    await users.create_index("username", unique=True, sparse=True)
    await users.create_index("email", unique=True, sparse=True)
    await users.create_index("mobile", unique=True)
    await users.create_index("id", unique=True)
    await flows.create_index("mobile")
    await flows.create_index("expires_at", expireAfterSeconds=0)
    await resets.create_index("expires_at", expireAfterSeconds=0)
    await categories_c.create_index("id", unique=True)
    await services_c.create_index("id", unique=True)
    await bookings_c.create_index("id", unique=True)
    await addresses_c.create_index("id", unique=True)
    await providers_c.create_index("id", unique=True)
    await coupons_c.create_index("code", unique=True)
    await reviews_c.create_index("id", unique=True)
    await seed_defaults()


async def seed_defaults():
    # Seed owner if none exists
    if await users.count_documents({"role": "OWNER"}) == 0:
        owner_id = uid()
        # Seed owner with a fresh random password so a leaked default cannot
        # be reused against a real deployment. The password is printed to
        # server logs only, so operators can retrieve it once from the log.
        if DEV_MODE:
            pw = "Owner@12345"
        else:
            pw = secrets.token_urlsafe(18)
        await users.insert_one({
            "id": owner_id, "name": "SmartFix Owner", "username": "owner",
            "email": "owner@smartfix.in", "mobile": "+919999900001",
            "password_hash": hash_password(pw),
            "role": "OWNER", "active": True,
            "created_at": now_utc(), "mobile_verified": True,
        })
        logger.info(f"Seeded default owner: owner@smartfix.in / {pw}")

    # Seed categories
    if await categories_c.count_documents({}) == 0:
        cats = [
            {"name": "AC Service", "icon": "snow-outline", "image_url": "https://images.unsplash.com/photo-1562259929-b4e1fd3aef09?w=600&q=80", "sort_order": 1},
            {"name": "Electrical", "icon": "flash-outline", "image_url": "https://images.unsplash.com/photo-1676311396794-f14881e9daaa?w=600&q=80", "sort_order": 2},
            {"name": "Plumbing", "icon": "water-outline", "image_url": "https://images.unsplash.com/photo-1607472586893-edb57bdc0e39?w=600&q=80", "sort_order": 3},
            {"name": "Cleaning", "icon": "sparkles-outline", "image_url": "https://images.pexels.com/photos/6196694/pexels-photo-6196694.jpeg?w=600", "sort_order": 4},
            {"name": "Appliance Repair", "icon": "hardware-chip-outline", "image_url": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=600&q=80", "sort_order": 5},
            {"name": "Watchman/Security", "icon": "shield-checkmark-outline", "image_url": "https://images.unsplash.com/photo-1582139329536-e7284fece509?w=600&q=80", "sort_order": 6},
            {"name": "Facility Maintenance", "icon": "business-outline", "image_url": "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=600&q=80", "sort_order": 7},
            {"name": "Manpower Supply", "icon": "people-outline", "image_url": "https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&q=80", "sort_order": 8},
        ]
        cat_docs = []
        for c in cats:
            cat_docs.append({"id": uid(), "active": True, **c, "created_at": now_utc()})
        await categories_c.insert_many(cat_docs)
        # Seed services
        services_seed = [
            ("AC Service", [("AC General Service", 499, 60), ("AC Deep Clean", 899, 90), ("AC Gas Refill", 2499, 120)]),
            ("Electrical", [("Switch/Socket Repair", 199, 30), ("Fan Installation", 299, 45), ("Wiring Check", 499, 60)]),
            ("Plumbing", [("Tap/Faucet Repair", 199, 30), ("Blockage Clearing", 349, 45), ("Water Tank Cleaning", 999, 90)]),
            ("Cleaning", [("Home Deep Clean (2BHK)", 1999, 240), ("Bathroom Cleaning", 499, 60), ("Kitchen Cleaning", 699, 90)]),
            ("Appliance Repair", [("Washing Machine Repair", 399, 60), ("Refrigerator Repair", 449, 60), ("Microwave Repair", 349, 45)]),
            ("Watchman/Security", [("Day Guard (12h)", 899, 720), ("Night Guard (12h)", 999, 720)]),
            ("Facility Maintenance", [("Monthly AMC (Home)", 1499, 60), ("Office Maintenance Visit", 1999, 120)]),
            ("Manpower Supply", [("Helper (per day)", 799, 480), ("Skilled Technician (per day)", 1499, 480)]),
        ]
        svc_docs = []
        for cat_name, items in services_seed:
            cat = next((c for c in cat_docs if c["name"] == cat_name), None)
            if not cat: continue
            for name, price, dur in items:
                svc_docs.append({
                    "id": uid(), "name": name, "category_id": cat["id"],
                    "category_name": cat_name,
                    "description": f"Professional {name.lower()} by verified experts.",
                    "image_url": cat["image_url"], "base_price": float(price),
                    "promo_price": None, "duration_minutes": dur,
                    "active": True, "rating": 4.7, "bookings_count": 0,
                    "created_at": now_utc(),
                })
        await services_c.insert_many(svc_docs)
        logger.info(f"Seeded {len(cat_docs)} categories and {len(svc_docs)} services")

    if await coupons_c.count_documents({}) == 0:
        await coupons_c.insert_many([
            {"id": uid(), "code": "SMARTFIX10", "discount_percent": 10, "max_discount": 200, "active": True, "description": "10% off up to ₹200", "created_at": now_utc()},
            {"id": uid(), "code": "FIRST100", "discount_percent": 20, "max_discount": 100, "active": True, "description": "First booking flat ₹100 off", "created_at": now_utc()},
        ])


# =========================================================
# AUTH ENDPOINTS
# =========================================================
@api.get("/")
async def root():
    return {"app": "SmartFix Service", "by": "Versanex India"}


@api.post("/auth/register/request-otp")
@limiter.limit("5/minute")
async def register_request_otp(request: Request, x: RequestOtpIn):
    mobile = norm_mobile(x.mobile)
    # SEC-002 hardening (user enumeration): return the same generic response
    # for "already registered" and "OTP sent" so an attacker cannot enumerate
    # which mobile numbers own SmartFix accounts. The real OTP is only created
    # for actually-unregistered numbers.
    if await users.find_one({"mobile": mobile}):
        logger.info(f"[SEC] register_request_otp for already-registered {mobile}")
        return {"message": "If the mobile is eligible, an OTP has been sent"}
    code = gen_otp()  # SEC-002: random per request, no more hardcoded 123456
    await flows.replace_one(
        {"mobile": mobile},
        {"mobile": mobile, "otp_hash": digest(code), "expires_at": now_utc() + OTP_TTL, "verified": False},
        upsert=True,
    )
    logger.info(f"[OTP] {mobile}: {code}")   # always logged for ops
    resp = {"message": "If the mobile is eligible, an OTP has been sent"}
    # SEC-001: OTP is never returned to clients in production.
    if DEV_MODE:
        resp["dev_otp"] = code
    return resp


@api.post("/auth/register/verify-otp")
@limiter.limit("10/minute")
async def register_verify_otp(request: Request, x: VerifyOtpIn):
    mobile = norm_mobile(x.mobile)
    f = await flows.find_one({"mobile": mobile})
    if not f or f["expires_at"] < now_utc() or not secrets.compare_digest(f.get("otp_hash", ""), digest(x.otp)):
        # Count wrong attempts on the flow doc — 5 strikes and the flow is
        # invalidated so an attacker can't brute-force the 6-digit space
        # within the 10-minute OTP TTL.
        if f:
            await flows.update_one({"_id": f["_id"]}, {"$inc": {"attempts": 1}})
            if f.get("attempts", 0) + 1 >= 5:
                await flows.delete_one({"_id": f["_id"]})
        raise HTTPException(400, "Invalid or expired OTP")
    flow_token = secrets.token_urlsafe(32)
    await flows.update_one(
        {"_id": f["_id"]},
        {"$set": {"verified": True, "flow_hash": digest(flow_token), "expires_at": now_utc() + timedelta(minutes=15), "attempts": 0},
         "$unset": {"otp_hash": ""}},
    )
    return {"flow_token": flow_token}


@api.post("/auth/register/complete")
async def register_complete(x: CompleteRegIn):
    f = await flows.find_one({"flow_hash": digest(x.flow_token), "verified": True, "expires_at": {"$gt": now_utc()}})
    if not f:
        raise HTTPException(400, "Invalid or expired registration flow. Please restart.")
    user_id = uid()
    doc = {
        "id": user_id, "mobile": f["mobile"], "mobile_verified": True,
        "name": x.name.strip(), "username": x.username.lower().strip(),
        "email": norm_email(str(x.email) if x.email else None),
        "password_hash": hash_password(x.password),
        "role": Role.CUSTOMER.value, "active": True,
        "created_at": now_utc(),
    }
    try:
        await users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Username or email already exists")
    await flows.delete_one({"_id": f["_id"]})
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return {"access_token": issue_token(doc), "token_type": "bearer", "user": doc}


@api.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, x: LoginIn):
    i = norm_login(x.identifier)
    q = {"$or": [{"username": i.lower()}, {"email": norm_email(i)}]}
    if re.fullmatch(r"\+?\d{7,15}", i):
        try:
            q["$or"].append({"mobile": norm_mobile(i)})
        except HTTPException:
            pass
    u = await users.find_one(q)
    if not u or not check_password(x.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    # SEC-003: block deactivated accounts at login time.
    if u.get("active") is False:
        raise HTTPException(401, "Account is deactivated")
    return {
        "access_token": issue_token(u), "token_type": "bearer",
        "user": {"id": u["id"], "name": u.get("name"), "username": u["username"],
                 "email": u.get("email"), "mobile": u["mobile"], "role": u["role"]},
    }


@api.get("/auth/me")
async def me(u=Depends(current_user)):
    return u


@api.get("/auth/permissions")
async def my_permissions(u=Depends(current_user)):
    """Fine-grained permission map for the current caller. The frontend can
    key UI gates off this instead of hard-coding role strings, so new roles
    (SUPERVISOR/OPERATIONS/SUPPORT/FINANCE/TECHNICIAN/VENDOR) work
    automatically."""
    return {"role": u["role"], "vendor_id": u.get("vendor_id"),
            "permissions": permissions_for(u["role"])}


@api.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def forgot(request: Request, x: ForgotIn):
    i = norm_login(x.identifier)
    q = {"$or": [{"email": norm_email(i)}, {"username": i.lower()}]}
    if re.fullmatch(r"\+?\d{7,15}", i):
        try:
            q["$or"].append({"mobile": norm_mobile(i)})
        except HTTPException:
            pass
    u = await users.find_one(q)
    # Always return the SAME generic message, regardless of whether the
    # account exists or which recovery channel is configured. User
    # enumeration hardening.
    generic = {"message": "If the account exists, recovery instructions were sent"}
    if not u:
        return generic
    raw = secrets.token_urlsafe(32)
    kind = "email" if u.get("email") else "mobile"
    doc = {"user_id": u["id"], "token_hash": digest(raw), "kind": kind, "expires_at": now_utc() + RESET_TTL}
    otp_plain = None
    if kind == "mobile":
        otp_plain = gen_otp()
        doc["otp_hash"] = digest(otp_plain)
    await resets.insert_one(doc)
    if kind == "email":
        link = f"{RESET_URL}?token={raw}"
        await send_reset_email(u["email"], u.get("name", ""), link)
    else:
        logger.info(f"[OTP] password-reset {u['mobile']}: {otp_plain}")
    # SEC-001 gate: recovery secrets ONLY leave the server when DEV_MODE=true
    # (preview / automated testing). Production always returns just `generic`.
    if DEV_MODE:
        resp = {**generic, "channel": kind, "reset_token": raw}
        if otp_plain is not None:
            resp["dev_otp"] = otp_plain
        return resp
    return generic


@api.post("/auth/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, x: ResetIn):
    r = await resets.find_one({"token_hash": digest(x.token), "expires_at": {"$gt": now_utc()}})
    if not r:
        raise HTTPException(400, "Invalid or expired reset token")
    if r["kind"] == "mobile":
        if not x.otp or not secrets.compare_digest(digest(x.otp), r.get("otp_hash", "")):
            # Same 5-strike lock-out as register/verify: brute-force the
            # 6-digit OTP is only 100k tries, well within a 30-min TTL.
            await resets.update_one({"_id": r["_id"]}, {"$inc": {"attempts": 1}})
            if r.get("attempts", 0) + 1 >= 5:
                await resets.delete_one({"_id": r["_id"]})
            raise HTTPException(400, "Invalid OTP")
    await users.update_one({"id": r["user_id"]}, {"$set": {"password_hash": hash_password(x.new_password)}})
    await resets.delete_one({"_id": r["_id"]})
    return {"message": "Password reset successful"}


@api.patch("/auth/profile")
async def update_profile(x: ProfileUpdateIn, u=Depends(current_user)):
    upd = {}
    if x.name is not None: upd["name"] = x.name.strip()
    if x.email is not None: upd["email"] = norm_email(str(x.email))
    if upd:
        try:
            await users.update_one({"id": u["id"]}, {"$set": upd})
        except DuplicateKeyError:
            raise HTTPException(409, "Email already used")
    return await users.find_one({"id": u["id"]}, {"_id": 0, "password_hash": 0})


# =========================================================
# CATEGORIES & SERVICES
# =========================================================
@api.get("/categories")
async def list_categories():
    rows = await categories_c.find({"active": True}, {"_id": 0}).sort("sort_order", 1).to_list(200)
    return rows


@api.post("/admin/categories")
async def create_category(x: CategoryIn, u=Depends(require_admin())):
    doc = {"id": uid(), **x.dict(), "created_at": now_utc()}
    await categories_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/categories/{cid}")
async def update_category(cid: str, x: CategoryIn, u=Depends(require_admin())):
    await categories_c.update_one({"id": cid}, {"$set": x.dict()})
    return await categories_c.find_one({"id": cid}, {"_id": 0})


@api.delete("/admin/categories/{cid}")
async def delete_category(cid: str, u=Depends(require_admin())):
    await categories_c.delete_one({"id": cid})
    return {"ok": True}


@api.get("/services")
async def list_services(category_id: Optional[str] = None, q: Optional[str] = None):
    query = {"active": True}
    if category_id:
        query["category_id"] = category_id
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    rows = await services_c.find(query, {"_id": 0}).sort("bookings_count", -1).to_list(500)
    return rows


@api.get("/services/{sid}")
async def get_service(sid: str):
    s = await services_c.find_one({"id": sid}, {"_id": 0})
    if not s: raise HTTPException(404, "Service not found")
    return s


@api.post("/admin/services")
async def create_service(x: ServiceIn, u=Depends(require_admin())):
    cat = await categories_c.find_one({"id": x.category_id}, {"_id": 0})
    if not cat: raise HTTPException(400, "Invalid category")
    doc = {"id": uid(), **x.dict(), "category_name": cat["name"], "rating": 5.0, "bookings_count": 0, "created_at": now_utc()}
    await services_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/services/{sid}")
async def update_service(sid: str, x: ServiceIn, u=Depends(require_admin())):
    cat = await categories_c.find_one({"id": x.category_id}, {"_id": 0})
    if not cat: raise HTTPException(400, "Invalid category")
    await services_c.update_one({"id": sid}, {"$set": {**x.dict(), "category_name": cat["name"]}})
    return await services_c.find_one({"id": sid}, {"_id": 0})


@api.delete("/admin/services/{sid}")
async def delete_service(sid: str, u=Depends(require_admin())):
    await services_c.delete_one({"id": sid})
    return {"ok": True}


# =========================================================
# ADDRESSES
# =========================================================
@api.get("/addresses")
async def list_addresses(u=Depends(current_user)):
    return await addresses_c.find({"user_id": u["id"]}, {"_id": 0}).sort("is_default", -1).to_list(50)


@api.post("/addresses")
async def create_address(x: AddressIn, u=Depends(current_user)):
    # If this is the user's very first address, force it to be the default so that
    # the booking flow can auto-select it without any extra UX step.
    existing = await addresses_c.count_documents({"user_id": u["id"]})
    is_default = x.is_default or existing == 0
    if is_default:
        await addresses_c.update_many({"user_id": u["id"]}, {"$set": {"is_default": False}})
    data = x.dict()
    data["is_default"] = is_default
    doc = {"id": uid(), "user_id": u["id"], **data, "created_at": now_utc()}
    await addresses_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/addresses/{aid}")
async def update_address(aid: str, x: AddressIn, u=Depends(current_user)):
    # Owner-scope both the update and the follow-up read so a caller who
    # guesses another user's address UUID cannot read or mutate it.
    if x.is_default:
        await addresses_c.update_many({"user_id": u["id"]}, {"$set": {"is_default": False}})
    r = await addresses_c.update_one({"id": aid, "user_id": u["id"]}, {"$set": x.dict()})
    if r.matched_count == 0:
        raise HTTPException(404, "Address not found")
    return await addresses_c.find_one({"id": aid, "user_id": u["id"]}, {"_id": 0})


@api.delete("/addresses/{aid}")
async def delete_address(aid: str, u=Depends(current_user)):
    await addresses_c.delete_one({"id": aid, "user_id": u["id"]})
    return {"ok": True}


# =========================================================
# COUPONS
# =========================================================
@api.get("/coupons")
async def list_coupons():
    return await coupons_c.find({"active": True}, {"_id": 0}).to_list(50)


@api.get("/coupons/validate")
async def validate_coupon(code: str, amount: float):
    c = await coupons_c.find_one({"code": code.upper(), "active": True}, {"_id": 0})
    if not c: raise HTTPException(404, "Invalid coupon")
    discount = amount * (c["discount_percent"] / 100.0)
    if c.get("max_discount"):
        discount = min(discount, c["max_discount"])
    return {"coupon": c, "discount": round(discount, 2), "final": round(amount - discount, 2)}


@api.post("/admin/coupons")
async def create_coupon(x: CouponIn, u=Depends(require_admin())):
    doc = {"id": uid(), **x.dict(), "code": x.code.upper(), "created_at": now_utc()}
    try:
        await coupons_c.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Coupon code exists")
    doc.pop("_id", None)
    return doc


@api.delete("/admin/coupons/{cid}")
async def delete_coupon(cid: str, u=Depends(require_admin())):
    await coupons_c.delete_one({"id": cid})
    return {"ok": True}


# =========================================================
# BOOKINGS
# =========================================================
async def enrich_booking(b: dict) -> dict:
    b.pop("_id", None)
    if b.get("service_id"):
        s = await services_c.find_one({"id": b["service_id"]}, {"_id": 0, "name": 1, "image_url": 1, "duration_minutes": 1})
        b["service"] = s
    if b.get("address_id"):
        a = await addresses_c.find_one({"id": b["address_id"]}, {"_id": 0})
        b["address"] = a
    if b.get("provider_id"):
        p = await users.find_one({"id": b["provider_id"]}, {"_id": 0, "name": 1, "mobile": 1, "id": 1})
        b["provider"] = p
    if b.get("customer_id"):
        c = await users.find_one({"id": b["customer_id"]}, {"_id": 0, "name": 1, "mobile": 1, "id": 1})
        b["customer"] = c
    return b


@api.post("/bookings")
async def create_booking(x: BookingIn, u=Depends(current_user)):
    s = await services_c.find_one({"id": x.service_id}, {"_id": 0})
    if not s: raise HTTPException(400, "Invalid service")
    a = await addresses_c.find_one({"id": x.address_id, "user_id": u["id"]}, {"_id": 0})
    if not a: raise HTTPException(400, "Invalid address")
    price = s.get("promo_price") or s["base_price"]
    discount = 0.0
    coupon = None
    if x.coupon_code:
        c = await coupons_c.find_one({"code": x.coupon_code.upper(), "active": True}, {"_id": 0})
        if c:
            discount = price * (c["discount_percent"] / 100.0)
            if c.get("max_discount"):
                discount = min(discount, c["max_discount"])
            coupon = c["code"]
    total = round(price - discount, 2)
    doc = {
        "id": uid(), "customer_id": u["id"], "service_id": x.service_id, "service_name": s["name"],
        "address_id": x.address_id, "scheduled_at": x.scheduled_at, "notes": x.notes or "",
        "payment_method": x.payment_method, "status": "PENDING",
        "provider_id": None, "provider_name": None,
        "base_price": price, "discount": discount, "total": total,
        "coupon_code": coupon, "payment_status": "PENDING",
        "upi_txn_ref": None, "created_at": now_utc(),
    }
    await bookings_c.insert_one(doc)
    await services_c.update_one({"id": x.service_id}, {"$inc": {"bookings_count": 1}})
    await booking_history(doc["id"], None, "PENDING", u, "Booking created")
    await audit_log(u, "BOOKING_CREATED", "booking", doc["id"], None, {"total": total})
    await notify(u["id"], "BOOKING_CREATED", ["IN_APP"], {"booking_id": doc["id"], "total": total})
    return await enrich_booking(doc)


@api.get("/bookings")
async def list_my_bookings(status_filter: Optional[str] = Query(None, alias="status"), u=Depends(current_user)):
    if u["role"] in FIELD_ROLES:                       # PROVIDER / TECHNICIAN see their own assigned jobs
        q = {"provider_id": u["id"]}
    elif u["role"] == "VENDOR":                        # VENDOR sees every job assigned to any of their technicians
        team = await users.find({"vendor_id": u["id"]}, {"_id": 0, "id": 1}).to_list(500)
        q = {"provider_id": {"$in": [t["id"] for t in team]}}
    elif u["role"] in BACKOFFICE_ROLES:                # back-office roles see every booking
        q = {}
    else:                                              # CUSTOMER (default) → own only
        q = {"customer_id": u["id"]}
    if status_filter:
        q["status"] = status_filter
    rows = await bookings_c.find(q).sort("created_at", -1).to_list(200)
    return [await enrich_booking(r) for r in rows]


@api.get("/bookings/{bid}")
async def get_booking(bid: str, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    if u["role"] == "CUSTOMER" and b["customer_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    if u["role"] in FIELD_ROLES and b.get("provider_id") != u["id"]:
        raise HTTPException(403, "Forbidden")
    if u["role"] == "VENDOR":
        prov = await users.find_one({"id": b.get("provider_id")}, {"_id": 0, "vendor_id": 1}) if b.get("provider_id") else None
        if not prov or prov.get("vendor_id") != u["id"]:
            raise HTTPException(403, "Forbidden")
    return await enrich_booking(b)


@api.patch("/bookings/{bid}/status")
async def update_status(bid: str, x: BookingStatusIn, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    # authz: customer can cancel own; provider/technician can advance own; ops-scope free
    if u["role"] == "CUSTOMER":
        if b["customer_id"] != u["id"] or x.status != "CANCELLED":
            raise HTTPException(403, "Only cancel your own booking")
    elif u["role"] in FIELD_ROLES:
        if b.get("provider_id") != u["id"]:
            raise HTTPException(403, "Not your job")
        if x.status not in ("ACCEPTED", "ON_THE_WAY", "IN_PROGRESS", "COMPLETED"):
            raise HTTPException(400, "Invalid provider status")
    elif u["role"] not in OPS_ROLES:
        raise HTTPException(403, "Forbidden")
    upd = {"status": x.status, "updated_at": now_utc()}
    if x.status == "COMPLETED" and b["payment_method"] == "CASH":
        upd["payment_status"] = "PAID"
    await bookings_c.update_one({"id": bid}, {"$set": upd})
    await booking_history(bid, b.get("status"), x.status, u)
    await audit_log(u, f"BOOKING_{x.status}", "booking", bid, b.get("status"), x.status)
    return await enrich_booking(await bookings_c.find_one({"id": bid}))


@api.post("/bookings/{bid}/assign")
async def assign_provider(bid: str, x: AssignProviderIn, u=Depends(require_ops())):
    # Accept either a PROVIDER (legacy solo field-tech) or a TECHNICIAN.
    p = await users.find_one({"id": x.provider_id, "role": {"$in": list(FIELD_ROLES)}}, {"_id": 0})
    if not p: raise HTTPException(400, "Invalid provider/technician")
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    await bookings_c.update_one({"id": bid}, {"$set": {"provider_id": p["id"], "provider_name": p.get("name"), "status": "ACCEPTED", "updated_at": now_utc()}})
    await booking_history(bid, b.get("status"), "ACCEPTED", u, f"Assigned to {p.get('name')}")
    await audit_log(u, "TECHNICIAN_ASSIGNED", "booking", bid, b.get("provider_id"), p["id"])
    await notify(p["id"], "TECHNICIAN_ASSIGNED", ["IN_APP"], {"booking_id": bid})
    await notify(b["customer_id"], "TECHNICIAN_ASSIGNED", ["IN_APP"], {"booking_id": bid, "provider_name": p.get("name")})
    return await enrich_booking(await bookings_c.find_one({"id": bid}))


@api.post("/bookings/{bid}/upi-confirm")
async def upi_confirm(bid: str, x: UpiConfirmIn, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    if b["customer_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    await bookings_c.update_one({"id": bid}, {"$set": {"upi_txn_ref": x.txn_ref.strip(), "payment_status": "AWAITING_VERIFICATION", "updated_at": now_utc()}})
    return await enrich_booking(await bookings_c.find_one({"id": bid}))


@api.post("/admin/bookings/{bid}/verify-payment")
async def verify_payment(bid: str, u=Depends(require_finance())):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    await bookings_c.update_one({"id": bid}, {"$set": {"payment_status": "PAID", "updated_at": now_utc()}})
    await audit_log(u, "PAYMENT_VERIFIED", "booking", bid, b.get("payment_status"), "PAID",
                    {"amount": b.get("total"), "method": b.get("payment_method")})
    return await enrich_booking(await bookings_c.find_one({"id": bid}))


# =========================================================
# REVIEWS
# =========================================================
@api.post("/reviews")
async def create_review(x: ReviewIn, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": x.booking_id})
    if not b or b["customer_id"] != u["id"]:
        raise HTTPException(400, "Invalid booking")
    if b["status"] != "COMPLETED":
        raise HTTPException(400, "Only completed bookings can be reviewed")
    doc = {"id": uid(), "user_id": u["id"], "user_name": u.get("name"), "booking_id": x.booking_id,
           "service_id": b["service_id"], "provider_id": b.get("provider_id"),
           "rating": x.rating, "comment": x.comment or "", "created_at": now_utc()}
    await reviews_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/reviews/service/{sid}")
async def reviews_for_service(sid: str):
    return await reviews_c.find({"service_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(50)


# =========================================================
# PROVIDERS
# =========================================================
@api.post("/providers/apply")
async def provider_apply(x: ProviderApplyIn, u=Depends(current_user)):
    doc = {"id": uid(), "user_id": u["id"], **x.dict(), "status": "PENDING", "created_at": now_utc()}
    await providers_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/admin/providers/applications")
async def list_applications(u=Depends(require_admin())):
    apps = await providers_c.find({"status": "PENDING"}, {"_id": 0}).to_list(100)
    for a in apps:
        usr = await users.find_one({"id": a["user_id"]}, {"_id": 0, "name": 1, "mobile": 1, "email": 1})
        a["user"] = usr
    return apps


@api.post("/admin/providers/{aid}/approve")
async def approve_provider(aid: str, u=Depends(require_admin())):
    a = await providers_c.find_one({"id": aid})
    if not a: raise HTTPException(404, "Not found")
    await providers_c.update_one({"id": aid}, {"$set": {"status": "APPROVED"}})
    await users.update_one({"id": a["user_id"]}, {"$set": {"role": "PROVIDER"}})
    return {"ok": True}


@api.get("/admin/providers")
async def list_providers(u=Depends(require_ops())):
    rows = await users.find({"role": "PROVIDER"}, {"_id": 0, "password_hash": 0}).to_list(500)
    return rows


# =========================================================
# ADMIN DASHBOARD
# =========================================================
@api.get("/admin/stats")
async def admin_stats(u=Depends(require_backoffice())):
    today_start = datetime.combine(now_utc().date(), datetime.min.time())
    total_customers = await users.count_documents({"role": "CUSTOMER"})
    total_providers = await users.count_documents({"role": "PROVIDER"})
    todays = await bookings_c.count_documents({"created_at": {"$gte": today_start}})
    pending = await bookings_c.count_documents({"status": "PENDING"})
    active = await bookings_c.count_documents({"status": {"$in": ["ACCEPTED", "ON_THE_WAY", "IN_PROGRESS"]}})
    completed = await bookings_c.count_documents({"status": "COMPLETED"})
    cancelled = await bookings_c.count_documents({"status": "CANCELLED"})
    # revenue
    pipeline = [{"$match": {"payment_status": "PAID"}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
    rev = await bookings_c.aggregate(pipeline).to_list(1)
    revenue = rev[0]["total"] if rev else 0
    pipeline_today = [{"$match": {"payment_status": "PAID", "created_at": {"$gte": today_start}}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
    rev_today = await bookings_c.aggregate(pipeline_today).to_list(1)
    revenue_today = rev_today[0]["total"] if rev_today else 0
    pending_apps = await providers_c.count_documents({"status": "PENDING"})
    return {
        "todays_bookings": todays, "pending_bookings": pending, "active_bookings": active,
        "completed_bookings": completed, "cancelled_bookings": cancelled,
        "total_customers": total_customers, "total_providers": total_providers,
        "revenue_total": round(revenue, 2), "revenue_today": round(revenue_today, 2),
        "pending_provider_applications": pending_apps,
    }


@api.get("/admin/users")
async def admin_list_users(role: Optional[str] = None, u=Depends(require_admin())):
    q = {}
    if role: q["role"] = role
    return await users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)


# =========================================================
# AUDIT LOG + NOTIFICATION HELPERS
# =========================================================
# Every important state change goes through audit_log(...) so we can build
# a "who did what and when" trail without changing every business endpoint.
async def audit_log(actor: dict, action: str, entity_type: str, entity_id: str,
                    previous_value=None, new_value=None, meta: Optional[dict] = None):
    await audit_c.insert_one({
        "id": uid(), "actor_user_id": actor["id"], "actor_role": actor["role"],
        "action": action, "entity_type": entity_type, "entity_id": entity_id,
        "previous_value": previous_value, "new_value": new_value,
        "meta": meta or {}, "timestamp": now_utc(),
    })


# Channel-agnostic notification writer. External providers (WhatsApp Business
# API, Firebase Cloud Messaging, MSG91 SMS, Resend email) plug in later by
# reading rows from this collection; the app still functions without them.
async def notify(user_id: Optional[str], event: str, channels: list, payload: dict):
    await notifications_c.insert_one({
        "id": uid(), "user_id": user_id, "event": event, "channels": channels,
        "payload": payload, "status": "QUEUED", "created_at": now_utc(),
    })


# Booking status transitions get their own history row for the timeline UI.
async def booking_history(bid: str, old_status: Optional[str], new_status: str,
                          actor: dict, notes: Optional[str] = None):
    await booking_history_c.insert_one({
        "id": uid(), "booking_id": bid, "old_status": old_status,
        "new_status": new_status, "changed_by_user_id": actor["id"],
        "changed_by_role": actor["role"], "notes": notes or "",
        "timestamp": now_utc(),
    })


# =========================================================
# QUOTATIONS (technician → customer via secure public token)
# =========================================================
class QuotationItem(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    kind: Literal["LABOUR", "PART", "OTHER"] = "PART"


class QuotationIn(BaseModel):
    booking_id: str
    service_description: str = Field(min_length=1, max_length=500)
    items: List[QuotationItem]
    labour_charge: float = Field(ge=0, default=0)
    tax_percent: float = Field(ge=0, le=50, default=18)
    discount: float = Field(ge=0, default=0)
    valid_days: int = Field(ge=1, le=30, default=3)
    technician_notes: Optional[str] = None


def _quotation_totals(items: List[QuotationItem], labour: float, tax_percent: float, discount: float):
    parts = round(sum(i.qty * i.unit_price for i in items if i.kind != "LABOUR"), 2)
    labour_from_items = round(sum(i.qty * i.unit_price for i in items if i.kind == "LABOUR"), 2)
    labour_total = round(labour + labour_from_items, 2)
    subtotal = round(parts + labour_total - discount, 2)
    if subtotal < 0: subtotal = 0
    tax = round(subtotal * (tax_percent / 100), 2)
    total = round(subtotal + tax, 2)
    return parts, labour_total, subtotal, tax, total


async def _next_quotation_no() -> str:
    # Human-friendly quotation number, e.g. SF-Q-2026-0001. Not the security
    # token; token stays cryptographic.
    year = now_utc().year
    count = await quotations_c.count_documents({"quotation_no": {"$regex": f"^SF-Q-{year}-"}})
    return f"SF-Q-{year}-{count + 1:04d}"


@api.post("/quotations")
async def create_quotation(x: QuotationIn, u=Depends(current_user)):
    if u["role"] not in FIELD_ROLES:
        raise HTTPException(403, "Only field roles can create quotations")
    b = await bookings_c.find_one({"id": x.booking_id})
    if not b: raise HTTPException(404, "Booking not found")
    if b.get("provider_id") != u["id"]:
        raise HTTPException(403, "Not your booking")
    parts_total, labour_total, subtotal, tax, total = _quotation_totals(
        x.items, x.labour_charge, x.tax_percent, x.discount)
    token = secrets.token_urlsafe(32)
    # SEC-audit P3 hardening: store ONLY the SHA-256 hash of the token in the
    # DB. The raw token is returned to the owning technician in memory here
    # (and re-derivable on /send, which rotates it) but is never persisted.
    doc = {
        "id": uid(), "quotation_no": await _next_quotation_no(),
        "token_hash": digest(token),
        "booking_id": b["id"], "customer_id": b["customer_id"],
        "customer_name": b.get("customer_name") or "",
        "customer_phone": b.get("customer_mobile") or "",
        "technician_id": u["id"], "technician_name": u.get("name") or "",
        "service_description": x.service_description,
        "items": [i.dict() for i in x.items],
        "labour_charge": labour_total, "parts_charge": parts_total,
        "tax_percent": x.tax_percent, "tax": tax,
        "discount": x.discount, "subtotal": subtotal, "total": total,
        "technician_notes": x.technician_notes or "",
        "status": "DRAFT",
        "valid_until": now_utc() + timedelta(days=x.valid_days),
        "created_at": now_utc(), "updated_at": now_utc(),
        "sent_at": None, "viewed_at": None, "responded_at": None,
    }
    await quotations_c.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(u, "QUOTATION_CREATED", "quotation", doc["id"], None, {"total": total})
    await notify(b["customer_id"], "QUOTATION_CREATED", ["IN_APP"],
                 {"quotation_id": doc["id"], "total": total})
    # Return the raw token exactly once — the technician stores it in-app or
    # copies the public URL now. No further endpoint reveals the raw token.
    public_url = (os.environ.get("PUBLIC_URL") or "").rstrip("/") + f"/quote/{token}"
    resp = _safe_quotation(doc)
    resp["token"] = token
    resp["public_url"] = public_url
    return resp


def _safe_quotation(doc: dict) -> dict:
    """Strip persistence-only and secret fields before returning to any caller.
    The raw `token` is *never* stored in DB (see create_quotation) so this
    also masks any legacy row that might still carry it."""
    return {k: v for k, v in doc.items() if k not in ("token_hash", "token", "_id")}


@api.get("/quotations")
async def list_quotations(u=Depends(current_user)):
    if u["role"] in FIELD_ROLES:
        q = {"technician_id": u["id"]}
    elif u["role"] == "CUSTOMER":
        q = {"customer_id": u["id"], "status": {"$ne": "DRAFT"}}
    elif u["role"] == "VENDOR":
        team = await users.find({"vendor_id": u["id"]}, {"_id": 0, "id": 1}).to_list(500)
        q = {"technician_id": {"$in": [t["id"] for t in team]}}
    elif u["role"] in BACKOFFICE_ROLES:
        q = {}
    else:
        q = {"customer_id": u["id"]}
    rows = await quotations_c.find(q).sort("created_at", -1).to_list(200)
    return [_safe_quotation(r) for r in rows]


@api.get("/quotations/{qid}")
async def get_quotation(qid: str, u=Depends(current_user)):
    q = await quotations_c.find_one({"id": qid})
    if not q: raise HTTPException(404, "Not found")
    if u["role"] == "CUSTOMER" and q["customer_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    if u["role"] in FIELD_ROLES and q["technician_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    if u["role"] == "VENDOR":
        tech = await users.find_one({"id": q["technician_id"]}, {"_id": 0, "vendor_id": 1})
        if not tech or tech.get("vendor_id") != u["id"]:
            raise HTTPException(403, "Forbidden")
    # No caller — not even the owning technician — receives the raw token via
    # GET after creation. To resend, call POST /quotations/{id}/send which
    # rotates the token.
    return _safe_quotation(q)


class QuotationSendIn(BaseModel):
    channel: Literal["WHATSAPP", "SMS", "COPY"] = "WHATSAPP"


@api.post("/quotations/{qid}/send")
async def send_quotation(qid: str, x: QuotationSendIn, u=Depends(current_user)):
    q = await quotations_c.find_one({"id": qid})
    if not q: raise HTTPException(404, "Not found")
    if u["role"] not in FIELD_ROLES or q["technician_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    # SEC-audit P3: rotate the public token on every send so a previously
    # copied link stops working. Only the hash is stored — the raw token is
    # returned to the technician in memory for this response.
    new_token = secrets.token_urlsafe(32)
    upd = {
        "status": "SENT" if q["status"] == "DRAFT" else q["status"],
        "sent_at": now_utc(), "updated_at": now_utc(),
        "token_hash": digest(new_token),
    }
    await quotations_c.update_one({"id": qid}, {"$set": upd})
    await audit_log(u, "QUOTATION_SENT", "quotation", qid, q["status"], upd["status"], {"channel": x.channel})
    public_url = (os.environ.get("PUBLIC_URL") or "").rstrip("/") + f"/quote/{new_token}"
    message = (
        f"SmartFix Services\n"
        f"Hello {q.get('customer_name') or 'Customer'},\n"
        f"Your quotation for the additional work is ready.\n\n"
        f"Quotation No: {q['quotation_no']}\n"
        f"Amount: \u20b9{q['total']}\n\n"
        f"View and respond: {public_url}\n\n"
        f"Regards,\nSmartFix Services"
    )
    phone = re.sub(r"\D", "", q.get("customer_phone") or "")
    from urllib.parse import quote as _uq
    wa_link = f"https://wa.me/{phone}?text={_uq(message)}" if phone else None
    await notify(q["customer_id"], "QUOTATION_SENT", [x.channel, "IN_APP"],
                 {"quotation_id": qid, "url": public_url, "message": message})
    return {"ok": True, "public_url": public_url, "message": message, "wa_link": wa_link}


# --------- PUBLIC quotation endpoints (no login, token in URL) ---------
@api.get("/public/quotations/{token}")
async def public_view_quotation(token: str):
    q = await quotations_c.find_one({"token_hash": digest(token)})
    if not q: raise HTTPException(404, "Quotation not found")
    if q["valid_until"] < now_utc() and q["status"] not in ("ACCEPTED", "REJECTED"):
        await quotations_c.update_one({"id": q["id"]}, {"$set": {"status": "EXPIRED"}})
        q["status"] = "EXPIRED"
    # Auto-mark VIEWED on the first read (but keep ACCEPTED/REJECTED sticky).
    if q["status"] == "SENT":
        await quotations_c.update_one({"id": q["id"]}, {"$set": {"status": "VIEWED", "viewed_at": now_utc()}})
        q["status"] = "VIEWED"
    return _safe_quotation(q)


class QuotationDecisionIn(BaseModel):
    decision: Literal["ACCEPT", "REJECT", "CLARIFY"]
    customer_notes: Optional[str] = None


@api.post("/public/quotations/{token}/respond")
async def public_respond_quotation(token: str, x: QuotationDecisionIn):
    q = await quotations_c.find_one({"token_hash": digest(token)})
    if not q: raise HTTPException(404, "Quotation not found")
    if q["status"] in ("ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED"):
        raise HTTPException(400, f"Quotation already {q['status'].lower()}")
    if q["valid_until"] < now_utc():
        await quotations_c.update_one({"id": q["id"]}, {"$set": {"status": "EXPIRED"}})
        raise HTTPException(400, "Quotation expired")
    mapping = {"ACCEPT": "ACCEPTED", "REJECT": "REJECTED", "CLARIFY": "VIEWED"}
    new_status = mapping[x.decision]
    upd = {"status": new_status, "responded_at": now_utc(), "customer_notes": x.customer_notes or "", "updated_at": now_utc()}
    await quotations_c.update_one({"id": q["id"]}, {"$set": upd})
    # Synthetic actor because the customer is not authenticated on the public route.
    actor = {"id": q["customer_id"], "role": "CUSTOMER"}
    await audit_log(actor, f"QUOTATION_{new_status}", "quotation", q["id"], q["status"], new_status, {"via": "public_link"})
    await notify(q["technician_id"], f"QUOTATION_{new_status}", ["IN_APP"], {"quotation_id": q["id"]})
    return {"ok": True, "status": new_status}


# =========================================================
# BOOKING STATUS HISTORY (audit trail for the timeline UI)
# =========================================================
@api.get("/bookings/{bid}/history")
async def booking_status_history(bid: str, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    if u["role"] == "CUSTOMER" and b["customer_id"] != u["id"]:
        raise HTTPException(403, "Forbidden")
    if u["role"] in FIELD_ROLES and b.get("provider_id") != u["id"]:
        raise HTTPException(403, "Forbidden")
    rows = await booking_history_c.find({"booking_id": bid}, {"_id": 0}).sort("timestamp", 1).to_list(100)
    return rows


# =========================================================
# SUPPORT TICKETS
# =========================================================
class TicketIn(BaseModel):
    booking_id: Optional[str] = None
    subject: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=2000)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"


@api.post("/tickets")
async def create_ticket(x: TicketIn, u=Depends(current_user)):
    doc = {
        "id": uid(), "customer_id": u["id"], "customer_name": u.get("name"),
        "booking_id": x.booking_id, "subject": x.subject, "description": x.description,
        "priority": x.priority, "status": "OPEN", "assigned_to": None,
        "resolution": None, "created_at": now_utc(), "updated_at": now_utc(),
    }
    await tickets_c.insert_one(doc); doc.pop("_id", None)
    await audit_log(u, "TICKET_CREATED", "ticket", doc["id"], None, {"priority": x.priority})
    return doc


@api.get("/tickets")
async def list_tickets(u=Depends(current_user)):
    if u["role"] in SUPPORT_ROLES:
        q = {}
    else:
        q = {"customer_id": u["id"]}
    return await tickets_c.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)


class TicketUpdateIn(BaseModel):
    status: Optional[Literal["OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"]] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
    priority: Optional[Literal["LOW", "NORMAL", "HIGH", "URGENT"]] = None


@api.patch("/tickets/{tid}")
async def update_ticket(tid: str, x: TicketUpdateIn, u=Depends(require_support())):
    t = await tickets_c.find_one({"id": tid})
    if not t: raise HTTPException(404, "Not found")
    upd = {k: v for k, v in x.dict().items() if v is not None}
    if upd:
        upd["updated_at"] = now_utc()
        await tickets_c.update_one({"id": tid}, {"$set": upd})
        await audit_log(u, "TICKET_UPDATED", "ticket", tid, {k: t.get(k) for k in upd}, upd)
    return await tickets_c.find_one({"id": tid}, {"_id": 0})


# =========================================================
# VENDOR: manage own technicians
# =========================================================
@api.get("/vendor/technicians")
async def vendor_technicians(u=Depends(require_roles("VENDOR", "OWNER", "ADMIN"))):
    # Owner/Admin can also list technicians grouped by vendor for oversight.
    if u["role"] == "VENDOR":
        rows = await users.find({"vendor_id": u["id"], "role": "TECHNICIAN"},
                                {"_id": 0, "password_hash": 0}).to_list(500)
    else:
        rows = await users.find({"role": "TECHNICIAN"},
                                {"_id": 0, "password_hash": 0}).to_list(500)
    return rows


class LinkTechnicianIn(BaseModel):
    user_id: str


@api.post("/vendor/technicians/link")
async def vendor_link_technician(x: LinkTechnicianIn, u=Depends(require_roles("VENDOR"))):
    # A vendor "claims" an existing technician account into their team.
    # Ownership transfer between vendors is intentionally forbidden.
    target = await users.find_one({"id": x.user_id, "role": "TECHNICIAN"})
    if not target: raise HTTPException(404, "Technician not found")
    if target.get("vendor_id") and target["vendor_id"] != u["id"]:
        raise HTTPException(403, "Technician already belongs to another vendor")
    await users.update_one({"id": x.user_id}, {"$set": {"vendor_id": u["id"]}})
    await audit_log(u, "TECHNICIAN_LINKED", "user", x.user_id, target.get("vendor_id"), u["id"])
    return {"ok": True}


# =========================================================
# ADMIN: role management (audited)
# =========================================================
class RoleChangeIn(BaseModel):
    role: Literal["CUSTOMER", "TECHNICIAN", "VENDOR", "PROVIDER", "SUPERVISOR",
                  "OPERATIONS", "SUPPORT", "FINANCE", "STAFF", "ADMIN", "OWNER"]
    vendor_id: Optional[str] = None


@api.patch("/admin/users/{uid}/role")
async def change_user_role(uid: str, x: RoleChangeIn, u=Depends(require_admin())):
    target = await users.find_one({"id": uid})
    if not target: raise HTTPException(404, "User not found")
    # OWNER promotion is reserved to OWNER only.
    if x.role == "OWNER" and u["role"] != "OWNER":
        raise HTTPException(403, "Only OWNER can promote another user to OWNER")
    if target["role"] == "OWNER" and u["role"] != "OWNER":
        raise HTTPException(403, "Only OWNER can modify an OWNER account")
    upd = {"role": x.role}
    if x.role == "TECHNICIAN" and x.vendor_id:
        v = await users.find_one({"id": x.vendor_id, "role": "VENDOR"})
        if not v: raise HTTPException(400, "Invalid vendor_id")
        upd["vendor_id"] = x.vendor_id
    if x.role != "TECHNICIAN":
        upd["vendor_id"] = None
    await users.update_one({"id": uid}, {"$set": upd})
    await audit_log(u, "ROLE_CHANGED", "user", uid,
                    {"role": target["role"], "vendor_id": target.get("vendor_id")}, upd)
    safe_target = {k: v for k, v in target.items() if k not in ("_id", "password_hash")}
    return {"ok": True, "user": {**safe_target, **upd}}


class UserStatusIn(BaseModel):
    active: bool


@api.patch("/admin/users/{uid}/status")
async def toggle_user_status(uid: str, x: UserStatusIn, u=Depends(require_admin())):
    target = await users.find_one({"id": uid})
    if not target: raise HTTPException(404, "User not found")
    if target["role"] == "OWNER":
        raise HTTPException(403, "Cannot deactivate OWNER")
    await users.update_one({"id": uid}, {"$set": {"active": x.active}})
    await audit_log(u, "USER_STATUS_CHANGED", "user", uid, target.get("active", True), x.active)
    return {"ok": True}


# =========================================================
# FINANCE
# =========================================================
@api.get("/finance/ledger")
async def finance_ledger(u=Depends(require_finance())):
    rows = await bookings_c.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    out = []
    for r in rows:
        out.append({
            "booking_id": r["id"], "customer_name": r.get("customer_name"),
            "provider_name": r.get("provider_name"),
            "payment_method": r.get("payment_method"), "payment_status": r.get("payment_status"),
            "total": r.get("total"), "upi_txn_ref": r.get("upi_txn_ref"),
            "status": r.get("status"), "created_at": r.get("created_at"),
        })
    return out


@api.get("/finance/summary")
async def finance_summary(u=Depends(require_finance())):
    async def sum_where(match: dict) -> float:
        p = [{"$match": match}, {"$group": {"_id": None, "t": {"$sum": "$total"}}}]
        r = await bookings_c.aggregate(p).to_list(1)
        return round(r[0]["t"], 2) if r else 0.0
    return {
        "revenue_paid": await sum_where({"payment_status": "PAID"}),
        "cash_paid":    await sum_where({"payment_status": "PAID", "payment_method": "CASH"}),
        "upi_paid":     await sum_where({"payment_status": "PAID", "payment_method": "UPI"}),
        "awaiting_verification": await sum_where({"payment_status": "AWAITING_VERIFICATION"}),
        "pending":      await sum_where({"payment_status": "PENDING"}),
    }


# =========================================================
# AUDIT LOG (read-only, admin scope)
# =========================================================
@api.get("/admin/audit")
async def admin_audit(entity_type: Optional[str] = None, u=Depends(require_admin())):
    q = {}
    if entity_type: q["entity_type"] = entity_type
    return await audit_c.find(q, {"_id": 0}).sort("timestamp", -1).to_list(200)


# =========================================================
# AMC (architecture only — no billing engine yet)
# =========================================================
class AmcPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: float = Field(ge=0)
    visits: int = Field(ge=1, le=52)
    validity_days: int = Field(ge=30, le=1825)
    service_ids: List[str] = []
    description: Optional[str] = None


@api.get("/amc/plans")
async def list_amc_plans():
    return await amc_plans_c.find({"active": {"$ne": False}}, {"_id": 0}).to_list(100)


@api.post("/admin/amc/plans")
async def create_amc_plan(x: AmcPlanIn, u=Depends(require_admin())):
    doc = {"id": uid(), **x.dict(), "active": True, "created_at": now_utc()}
    await amc_plans_c.insert_one(doc); doc.pop("_id", None)
    await audit_log(u, "AMC_PLAN_CREATED", "amc_plan", doc["id"], None, doc)
    return doc


# =========================================================
# NOTIFICATIONS (in-app inbox — real channels wire in later)
# =========================================================
@api.get("/notifications")
async def my_notifications(u=Depends(current_user)):
    return await notifications_c.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


# =========================================================
# mount
# =========================================================
app.include_router(api)

# SEC-audit hardening: pin CORS to configured origin(s) instead of "*".
# The token is a bearer header (no cookies), so allow_credentials=False is
# both safe and avoids the browser-side ignore-with-wildcard footgun.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
