from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError
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

import bcrypt, jwt

ALGORITHM = "HS256"
JWT_DAYS = 7
OTP_TTL = timedelta(minutes=10)
RESET_TTL = timedelta(minutes=30)
DEV_OTP = "123456"
EMAIL_BASE_URL = "https://integrations.emergentagent.com"

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

app = FastAPI(title="SmartFix API")
api = APIRouter(prefix="/api")
BEARER = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartfix")


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
    if len(p) < 6:
        raise HTTPException(422, "Password must be at least 6 characters")
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
    return u


def require_roles(*allowed):
    async def dep(u=Depends(current_user)):
        if u["role"] not in allowed:
            raise HTTPException(403, "Insufficient role")
        return u
    return dep


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
    OWNER = "OWNER"; ADMIN = "ADMIN"; STAFF = "STAFF"; PROVIDER = "PROVIDER"; CUSTOMER = "CUSTOMER"


class RequestOtpIn(BaseModel):
    mobile: str


class VerifyOtpIn(BaseModel):
    mobile: str
    otp: str = Field(pattern=r"^\d{6}$")


class CompleteRegIn(BaseModel):
    flow_token: str
    name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(min_length=6)
    email: Optional[EmailStr] = None


class LoginIn(BaseModel):
    identifier: str
    password: str


class ForgotIn(BaseModel):
    identifier: str


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)
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
        await users.insert_one({
            "id": owner_id, "name": "SmartFix Owner", "username": "owner",
            "email": "owner@smartfix.in", "mobile": "+919999900001",
            "password_hash": hash_password("Owner@12345"),
            "role": "OWNER", "created_at": now_utc(), "mobile_verified": True,
        })
        logger.info("Seeded default owner: owner@smartfix.in / Owner@12345")

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
async def register_request_otp(x: RequestOtpIn):
    mobile = norm_mobile(x.mobile)
    if await users.find_one({"mobile": mobile}):
        raise HTTPException(409, "Mobile already registered. Please login.")
    code = DEV_OTP  # MOCK: replace with real SMS provider before launch
    await flows.replace_one(
        {"mobile": mobile},
        {"mobile": mobile, "otp_hash": digest(code), "expires_at": now_utc() + OTP_TTL, "verified": False},
        upsert=True,
    )
    logger.info(f"[DEV] OTP for {mobile}: {code}")
    return {"message": "OTP sent to your mobile", "dev_otp": code}


@api.post("/auth/register/verify-otp")
async def register_verify_otp(x: VerifyOtpIn):
    mobile = norm_mobile(x.mobile)
    f = await flows.find_one({"mobile": mobile})
    if not f or f["expires_at"] < now_utc() or not secrets.compare_digest(f.get("otp_hash", ""), digest(x.otp)):
        raise HTTPException(400, "Invalid or expired OTP")
    flow_token = secrets.token_urlsafe(32)
    await flows.update_one(
        {"_id": f["_id"]},
        {"$set": {"verified": True, "flow_hash": digest(flow_token), "expires_at": now_utc() + timedelta(minutes=15)},
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
        "role": Role.CUSTOMER.value, "created_at": now_utc(),
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
async def login(x: LoginIn):
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
    return {
        "access_token": issue_token(u), "token_type": "bearer",
        "user": {"id": u["id"], "name": u.get("name"), "username": u["username"],
                 "email": u.get("email"), "mobile": u["mobile"], "role": u["role"]},
    }


@api.get("/auth/me")
async def me(u=Depends(current_user)):
    return u


@api.post("/auth/forgot-password")
async def forgot(x: ForgotIn):
    i = norm_login(x.identifier)
    q = {"$or": [{"email": norm_email(i)}, {"username": i.lower()}]}
    if re.fullmatch(r"\+?\d{7,15}", i):
        try:
            q["$or"].append({"mobile": norm_mobile(i)})
        except HTTPException:
            pass
    u = await users.find_one(q)
    if not u:
        return {"message": "If the account exists, recovery instructions were sent"}
    raw = secrets.token_urlsafe(32)
    kind = "email" if u.get("email") else "mobile"
    doc = {"user_id": u["id"], "token_hash": digest(raw), "kind": kind, "expires_at": now_utc() + RESET_TTL}
    if kind == "mobile":
        doc["otp_hash"] = digest(DEV_OTP)
    await resets.insert_one(doc)
    if kind == "email":
        link = f"{RESET_URL}?token={raw}"
        await send_reset_email(u["email"], u.get("name", ""), link)
        return {"message": "Password reset link sent to email", "channel": "email", "reset_token": raw}
    return {"message": "Recovery OTP sent to mobile", "channel": "mobile", "reset_token": raw, "dev_otp": DEV_OTP}


@api.post("/auth/reset-password")
async def reset_password(x: ResetIn):
    r = await resets.find_one({"token_hash": digest(x.token), "expires_at": {"$gt": now_utc()}})
    if not r:
        raise HTTPException(400, "Invalid or expired reset token")
    if r["kind"] == "mobile":
        if not x.otp or not secrets.compare_digest(digest(x.otp), r.get("otp_hash", "")):
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
async def create_category(x: CategoryIn, u=Depends(require_roles("OWNER", "ADMIN"))):
    doc = {"id": uid(), **x.dict(), "created_at": now_utc()}
    await categories_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/categories/{cid}")
async def update_category(cid: str, x: CategoryIn, u=Depends(require_roles("OWNER", "ADMIN"))):
    await categories_c.update_one({"id": cid}, {"$set": x.dict()})
    return await categories_c.find_one({"id": cid}, {"_id": 0})


@api.delete("/admin/categories/{cid}")
async def delete_category(cid: str, u=Depends(require_roles("OWNER", "ADMIN"))):
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
async def create_service(x: ServiceIn, u=Depends(require_roles("OWNER", "ADMIN"))):
    cat = await categories_c.find_one({"id": x.category_id}, {"_id": 0})
    if not cat: raise HTTPException(400, "Invalid category")
    doc = {"id": uid(), **x.dict(), "category_name": cat["name"], "rating": 5.0, "bookings_count": 0, "created_at": now_utc()}
    await services_c.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/admin/services/{sid}")
async def update_service(sid: str, x: ServiceIn, u=Depends(require_roles("OWNER", "ADMIN"))):
    cat = await categories_c.find_one({"id": x.category_id}, {"_id": 0})
    if not cat: raise HTTPException(400, "Invalid category")
    await services_c.update_one({"id": sid}, {"$set": {**x.dict(), "category_name": cat["name"]}})
    return await services_c.find_one({"id": sid}, {"_id": 0})


@api.delete("/admin/services/{sid}")
async def delete_service(sid: str, u=Depends(require_roles("OWNER", "ADMIN"))):
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
    if x.is_default:
        await addresses_c.update_many({"user_id": u["id"]}, {"$set": {"is_default": False}})
    await addresses_c.update_one({"id": aid, "user_id": u["id"]}, {"$set": x.dict()})
    return await addresses_c.find_one({"id": aid}, {"_id": 0})


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
async def create_coupon(x: CouponIn, u=Depends(require_roles("OWNER", "ADMIN"))):
    doc = {"id": uid(), **x.dict(), "code": x.code.upper(), "created_at": now_utc()}
    try:
        await coupons_c.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Coupon code exists")
    doc.pop("_id", None)
    return doc


@api.delete("/admin/coupons/{cid}")
async def delete_coupon(cid: str, u=Depends(require_roles("OWNER", "ADMIN"))):
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
    return await enrich_booking(doc)


@api.get("/bookings")
async def list_my_bookings(status_filter: Optional[str] = Query(None, alias="status"), u=Depends(current_user)):
    if u["role"] == "PROVIDER":
        q = {"provider_id": u["id"]}
    elif u["role"] in ("OWNER", "ADMIN", "STAFF"):
        q = {}
    else:
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
    if u["role"] == "PROVIDER" and b.get("provider_id") != u["id"]:
        raise HTTPException(403, "Forbidden")
    return await enrich_booking(b)


@api.patch("/bookings/{bid}/status")
async def update_status(bid: str, x: BookingStatusIn, u=Depends(current_user)):
    b = await bookings_c.find_one({"id": bid})
    if not b: raise HTTPException(404, "Not found")
    # authz: customer can cancel own; provider can set ACCEPTED..COMPLETED on own; admin all
    if u["role"] == "CUSTOMER":
        if b["customer_id"] != u["id"] or x.status != "CANCELLED":
            raise HTTPException(403, "Only cancel your own booking")
    elif u["role"] == "PROVIDER":
        if b.get("provider_id") != u["id"]:
            raise HTTPException(403, "Not your job")
        if x.status not in ("ACCEPTED", "ON_THE_WAY", "IN_PROGRESS", "COMPLETED"):
            raise HTTPException(400, "Invalid provider status")
    upd = {"status": x.status, "updated_at": now_utc()}
    if x.status == "COMPLETED" and b["payment_method"] == "CASH":
        upd["payment_status"] = "PAID"
    await bookings_c.update_one({"id": bid}, {"$set": upd})
    return await enrich_booking(await bookings_c.find_one({"id": bid}))


@api.post("/bookings/{bid}/assign")
async def assign_provider(bid: str, x: AssignProviderIn, u=Depends(require_roles("OWNER", "ADMIN", "STAFF"))):
    p = await users.find_one({"id": x.provider_id, "role": "PROVIDER"}, {"_id": 0})
    if not p: raise HTTPException(400, "Invalid provider")
    await bookings_c.update_one({"id": bid}, {"$set": {"provider_id": p["id"], "provider_name": p.get("name"), "status": "ACCEPTED", "updated_at": now_utc()}})
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
async def verify_payment(bid: str, u=Depends(require_roles("OWNER", "ADMIN", "STAFF"))):
    await bookings_c.update_one({"id": bid}, {"$set": {"payment_status": "PAID", "updated_at": now_utc()}})
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
async def list_applications(u=Depends(require_roles("OWNER", "ADMIN"))):
    apps = await providers_c.find({"status": "PENDING"}, {"_id": 0}).to_list(100)
    for a in apps:
        usr = await users.find_one({"id": a["user_id"]}, {"_id": 0, "name": 1, "mobile": 1, "email": 1})
        a["user"] = usr
    return apps


@api.post("/admin/providers/{aid}/approve")
async def approve_provider(aid: str, u=Depends(require_roles("OWNER", "ADMIN"))):
    a = await providers_c.find_one({"id": aid})
    if not a: raise HTTPException(404, "Not found")
    await providers_c.update_one({"id": aid}, {"$set": {"status": "APPROVED"}})
    await users.update_one({"id": a["user_id"]}, {"$set": {"role": "PROVIDER"}})
    return {"ok": True}


@api.get("/admin/providers")
async def list_providers(u=Depends(require_roles("OWNER", "ADMIN", "STAFF"))):
    rows = await users.find({"role": "PROVIDER"}, {"_id": 0, "password_hash": 0}).to_list(500)
    return rows


# =========================================================
# ADMIN DASHBOARD
# =========================================================
@api.get("/admin/stats")
async def admin_stats(u=Depends(require_roles("OWNER", "ADMIN", "STAFF"))):
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
async def admin_list_users(role: Optional[str] = None, u=Depends(require_roles("OWNER", "ADMIN"))):
    q = {}
    if role: q["role"] = role
    return await users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)


# =========================================================
# mount
# =========================================================
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
