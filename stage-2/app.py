"""Tablekeeper — HTTP service, stage 1.

Python standard library only: the image needs no outbound network at run time.
IANA timezone data is installed at build time, so restaurant-local time
resolution works offline.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

JSON_CONTENT_TYPE = "application/json; charset=utf-8"

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MAX_ID = 64
REFERENCE_RE = re.compile(r"^[A-Z0-9]{6,12}$")
LOCAL_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
HHMM_RE = re.compile(r"^(\d{2}):(\d{2})$")
DIGITS_RE = re.compile(r"^\d+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
REFERENCE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


def bad_request(msg=""):
    return ApiError(400, "malformed_request", msg)


def invalid(msg=""):
    return ApiError(422, "validation_failed", msg)


def not_found(msg=""):
    return ApiError(404, "not_found", msg)


# --- passwords ---------------------------------------------------------------

def hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                        r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"),
                            salt=base64.b64decode(salt_b64),
                            n=int(n), r=int(r), p=int(p), dklen=32)
    except Exception:
        return False
    return secrets.compare_digest(base64.b64encode(dk).decode(), dk_b64)


# --- time --------------------------------------------------------------------

def zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise invalid("unknown timezone %r" % (name,))


def parse_local(text):
    """A bare local `YYYY-MM-DDTHH:MM`. Anything else is validation_failed."""
    if not isinstance(text, str):
        raise bad_request("starts_at_local must be a string")
    m = LOCAL_RE.match(text)
    if not m:
        raise invalid("starts_at_local must be YYYY-MM-DDTHH:MM")
    y, mo, d, h, mi = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        raise invalid("impossible local time %r" % (text,))


def parse_date(text):
    if not isinstance(text, str):
        raise invalid("date must be a string")
    m = DATE_RE.match(text)
    if not m:
        raise invalid("date must be YYYY-MM-DD")
    y, mo, d = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d).date()
    except ValueError:
        raise invalid("impossible date %r" % (text,))


def parse_hhmm(text):
    m = HHMM_RE.match(text) if isinstance(text, str) else None
    if not m:
        raise invalid("opening hours must be HH:MM")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise invalid("impossible time %r" % (text,))
    return h * 60 + mi


def resolve_local(naive, tz):
    """Local wall clock -> absolute instant, first occurrence.

    Returns None when the local time does not exist (spring forward). Ambiguous
    local times (fall back) resolve to fold=0, the occurrence before the change.
    """
    aware = naive.replace(tzinfo=tz, fold=0)
    round_trip = aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    if round_trip != naive:
        return None
    return aware


def add_absolute(aware, minutes, tz):
    """Absolute-time arithmetic, then re-expressed in `tz`."""
    return (aware.astimezone(timezone.utc)
            + timedelta(minutes=minutes)).astimezone(tz)


def now_utc():
    return datetime.now(timezone.utc)


# --- model -------------------------------------------------------------------

def check_id(value, what):
    if not isinstance(value, str):
        raise bad_request("%s must be a string" % what)
    if not value or len(value) > MAX_ID:
        raise invalid("%s must be 1..%d characters" % (what, MAX_ID))
    return value


class Restaurant:
    def __init__(self, raw):
        if not isinstance(raw, dict):
            raise bad_request("restaurant must be an object")
        self.id = check_id(raw.get("id"), "restaurant id")
        self.name = raw.get("name")
        if not isinstance(self.name, str):
            raise bad_request("restaurant name must be a string")
        self.timezone = raw.get("timezone")
        if not isinstance(self.timezone, str):
            raise bad_request("timezone must be a string")
        self.tz = zone(self.timezone)
        self.slot_minutes = self._pos(raw, "slot_minutes")
        self.reservation_duration_minutes = self._pos(
            raw, "reservation_duration_minutes")
        cutoff = raw.get("cancellation_cutoff_minutes", 0)
        if isinstance(cutoff, bool) or not isinstance(cutoff, int):
            raise bad_request("cancellation_cutoff_minutes must be an integer")
        if cutoff < 0:
            raise invalid("cancellation_cutoff_minutes must not be negative")
        self.cancellation_cutoff_minutes = cutoff
        self.opening_hours = []
        hours = raw.get("opening_hours", [])
        if not isinstance(hours, list):
            raise bad_request("opening_hours must be a list")
        for entry in hours:
            if not isinstance(entry, dict):
                raise bad_request("opening_hours entry must be an object")
            wd = entry.get("weekday")
            if wd not in WEEKDAYS:
                raise invalid("weekday must be one of %s" % " ".join(WEEKDAYS))
            opens = parse_hhmm(entry.get("opens"))
            closes = parse_hhmm(entry.get("closes"))
            if closes <= opens:
                raise invalid("closes must be later than opens")
            self.opening_hours.append(
                {"weekday": wd, "opens": entry["opens"], "closes": entry["closes"],
                 "_opens": opens, "_closes": closes})
        self.tables = []
        tables = raw.get("tables", [])
        if not isinstance(tables, list):
            raise bad_request("tables must be a list")
        for t in tables:
            if not isinstance(t, dict):
                raise bad_request("table must be an object")
            tid = check_id(t.get("id"), "table id")
            cap = t.get("capacity")
            if isinstance(cap, bool) or not isinstance(cap, int):
                raise bad_request("capacity must be an integer")
            if cap < 1:
                raise invalid("capacity must be at least 1")
            self.tables.append({"id": tid, "label": t.get("label"), "capacity": cap})
        if len({t["id"] for t in self.tables}) != len(self.tables):
            raise invalid("duplicate table id")
        self.combinable = []
        pairs = raw.get("combinable", [])
        if not isinstance(pairs, list):
            raise bad_request("combinable must be a list")
        ids = {t["id"] for t in self.tables}
        for pair in pairs:
            if not isinstance(pair, list):
                raise bad_request("a combinable entry must be a list")
            if len(pair) != 2:
                raise invalid("a combinable entry must be a pair of exactly two tables")
            for tid in pair:
                if not isinstance(tid, str):
                    raise bad_request("a combinable entry must hold table ids")
                if tid not in ids:
                    raise invalid("combinable names a table this restaurant does not have")
            if pair[0] == pair[1]:
                raise invalid("a combinable entry must name two distinct tables")
            self.combinable.append([pair[0], pair[1]])

    @staticmethod
    def _pos(raw, field):
        v = raw.get(field)
        if isinstance(v, bool) or not isinstance(v, int):
            raise bad_request("%s must be an integer" % field)
        if v < 1:
            raise invalid("%s must be at least 1" % field)
        return v

    def is_combinable(self, table_ids):
        """A set of two is bookable only if declared. Pairs are unordered."""
        want = {table_ids[0], table_ids[1]}
        return any(set(p) == want for p in self.combinable)

    def capacity_of(self, table_ids):
        return sum(self.table(t)["capacity"] for t in table_ids)

    def table(self, table_id):
        for t in self.tables:
            if t["id"] == table_id:
                return t
        return None

    def hours_for(self, date):
        wd = WEEKDAYS[date.weekday()]
        for entry in self.opening_hours:
            if entry["weekday"] == wd:
                return entry
        return None

    def public(self):
        return {"id": self.id, "name": self.name, "timezone": self.timezone}

    def detail(self):
        return {
            "id": self.id,
            "name": self.name,
            "timezone": self.timezone,
            "slot_minutes": self.slot_minutes,
            "reservation_duration_minutes": self.reservation_duration_minutes,
            "cancellation_cutoff_minutes": self.cancellation_cutoff_minutes,
            "opening_hours": [{"weekday": e["weekday"], "opens": e["opens"],
                               "closes": e["closes"]} for e in self.opening_hours],
            "tables": [{"id": t["id"], "label": t["label"],
                        "capacity": t["capacity"]} for t in self.tables],
            "combinable": [list(p) for p in self.combinable],
        }

    def dump(self):
        return {"id": self.id, "name": self.name, "timezone": self.timezone,
                "slot_minutes": self.slot_minutes,
                "reservation_duration_minutes": self.reservation_duration_minutes,
                "cancellation_cutoff_minutes": self.cancellation_cutoff_minutes,
                "opening_hours": [{"weekday": e["weekday"], "opens": e["opens"],
                                   "closes": e["closes"]} for e in self.opening_hours],
                "tables": [dict(t) for t in self.tables],
                "combinable": [list(p) for p in self.combinable]}


class Reservation:
    __slots__ = ("id", "reference", "user_id", "restaurant_id", "table_ids",
                 "starts_at_local", "party_size", "status", "created_at")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def view(self, restaurant):
        naive = parse_local(self.starts_at_local)
        start = resolve_local(naive, restaurant.tz)
        end = add_absolute(start, restaurant.reservation_duration_minutes,
                           restaurant.tz)
        view = {
            "reservation_id": self.id,
            "reference": self.reference,
            "restaurant_id": self.restaurant_id,
            "table_ids": list(self.table_ids),
            "party_size": self.party_size,
            "status": self.status,
            "starts_at_local": self.starts_at_local,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "created_at": self.created_at,
        }
        # `table_id` is carried only when the set has exactly one member.
        if len(self.table_ids) == 1:
            view["table_id"] = self.table_ids[0]
        return view

    def interval(self, restaurant):
        start = resolve_local(parse_local(self.starts_at_local), restaurant.tz)
        start_utc = start.astimezone(timezone.utc)
        return start_utc, start_utc + timedelta(
            minutes=restaurant.reservation_duration_minutes)

    def dump(self):
        return {k: getattr(self, k) for k in self.__slots__}


class State:
    def __init__(self):
        self.users = {}
        self.emails = {}
        self.tokens = {}
        self.restaurants = {}
        self.restaurant_order = []
        self.reservations = {}
        self.references = {}
        self.receipts = {}
        self.counter = 0

    def next_counter(self):
        self.counter += 1
        return self.counter


# --- service -----------------------------------------------------------------

class Service:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = State()

    # -- fixtures ---------------------------------------------------------

    def reset(self, fixture):
        if not isinstance(fixture, dict):
            raise bad_request("fixture must be an object")
        fresh = State()
        users = fixture.get("users", [])
        if not isinstance(users, list):
            raise bad_request("users must be a list")
        for raw in users:
            if not isinstance(raw, dict):
                raise bad_request("user must be an object")
            uid = check_id(raw.get("id"), "user id")
            email = raw.get("email")
            if not isinstance(email, str):
                raise bad_request("email must be a string")
            password = raw.get("password")
            if not isinstance(password, str):
                raise bad_request("password must be a string")
            if uid in fresh.users or email in fresh.emails:
                raise invalid("duplicate user in fixture")
            fresh.users[uid] = {
                "id": uid, "email": email,
                "display_name": raw.get("display_name"),
                "password_hash": hash_password(password)}
            fresh.emails[email] = uid

        restaurants = fixture.get("restaurants", [])
        if not isinstance(restaurants, list):
            raise bad_request("restaurants must be a list")
        for raw in restaurants:
            r = Restaurant(raw)
            if r.id in fresh.restaurants:
                raise invalid("duplicate restaurant in fixture")
            fresh.restaurants[r.id] = r
            fresh.restaurant_order.append(r.id)

        reservations = fixture.get("reservations", [])
        if not isinstance(reservations, list):
            raise bad_request("reservations must be a list")
        for raw in reservations:
            if not isinstance(raw, dict):
                raise bad_request("reservation must be an object")
            rid = check_id(raw.get("id"), "reservation id")
            reference = raw.get("reference")
            if not isinstance(reference, str):
                raise bad_request("reference must be a string")
            if not REFERENCE_RE.match(reference):
                raise invalid("reference must match ^[A-Z0-9]{6,12}$")
            if len(reference) > MAX_ID:
                raise invalid("reference too long")
            user_id = check_id(raw.get("user_id"), "user_id")
            if user_id not in fresh.users:
                raise invalid("reservation names an unknown user")
            restaurant_id = check_id(raw.get("restaurant_id"), "restaurant_id")
            restaurant = fresh.restaurants.get(restaurant_id)
            if restaurant is None:
                raise invalid("reservation names an unknown restaurant")
            if "table_ids" in raw and "table_id" in raw:
                raise invalid("a seeded reservation carries table_id or table_ids, not both")
            if "table_ids" in raw:
                seeded = raw.get("table_ids")
                if not isinstance(seeded, list) or not seeded:
                    raise invalid("table_ids must be a non-empty list")
                table_ids = [check_id(t, "table_id") for t in seeded]
                if len(set(table_ids)) != len(table_ids):
                    raise invalid("a seeded reservation must not repeat a table")
                if len(table_ids) > 2:
                    raise invalid("tables may be combined in pairs only")
                if len(table_ids) == 2 and not restaurant.is_combinable(table_ids):
                    raise invalid("a seeded combination must be declared in combinable")
            else:
                table_ids = [check_id(raw.get("table_id"), "table_id")]
            for tid in table_ids:
                if restaurant.table(tid) is None:
                    raise invalid("reservation names an unknown table")
            party_size = raw.get("party_size")
            if isinstance(party_size, bool) or not isinstance(party_size, int):
                raise invalid("party_size must be an integer")
            if party_size < 1:
                raise invalid("party_size must be at least 1")
            local = raw.get("starts_at_local")
            naive = parse_local(local)
            if resolve_local(naive, restaurant.tz) is None:
                raise invalid("seeded reservation uses a local time that does not exist")
            if rid in fresh.reservations or reference in fresh.references:
                raise invalid("duplicate reservation in fixture")
            status = raw.get("status", "confirmed")
            if status not in ("confirmed", "cancelled"):
                raise invalid("status must be confirmed or cancelled")
            res = Reservation(id=rid, reference=reference, user_id=user_id,
                              restaurant_id=restaurant_id, table_ids=table_ids,
                              starts_at_local=local, party_size=party_size,
                              status=status,
                              created_at=raw.get("created_at")
                              or now_utc().isoformat())
            fresh.reservations[rid] = res
            fresh.references[reference] = rid

        with self.lock:
            self.state = fresh

    # -- export / import --------------------------------------------------

    def export(self):
        with self.lock:
            s = self.state
            return {
                "track": "tablekeeper",
                "format_version": 1,
                "state": {
                    "users": [dict(u) for u in s.users.values()],
                    "tokens": dict(s.tokens),
                    "restaurants": [s.restaurants[i].dump()
                                    for i in s.restaurant_order],
                    "reservations": [r.dump() for r in s.reservations.values()],
                    "receipts": [{"user_id": k[0], "method": k[1], "path": k[2],
                                  "key": k[3], "body": v["body"],
                                  "status": v["status"], "response": v["response"]}
                                 for k, v in s.receipts.items()],
                    "counter": s.counter,
                },
            }

    def import_state(self, payload):
        if not isinstance(payload, dict):
            raise bad_request("import body must be an object")
        if payload.get("track") != "tablekeeper":
            raise invalid("track must be tablekeeper")
        version = payload.get("format_version")
        if isinstance(version, bool) or version != 1:
            raise invalid("format_version must be 1")
        blob = payload.get("state")
        if not isinstance(blob, dict):
            raise invalid("state must be an object")

        fresh = State()
        try:
            for u in blob["users"]:
                fresh.users[u["id"]] = dict(u)
                fresh.emails[u["email"]] = u["id"]
            for token, uid in blob["tokens"].items():
                fresh.tokens[token] = uid
            for raw in blob["restaurants"]:
                r = Restaurant(raw)
                fresh.restaurants[r.id] = r
                fresh.restaurant_order.append(r.id)
            for raw in blob["reservations"]:
                raw = dict(raw)
                # A stage-1 snapshot records one `table_id` per reservation. An
                # upgraded service must accept it: the export is the migration.
                if "table_ids" not in raw and "table_id" in raw:
                    raw["table_ids"] = [raw["table_id"]]
                raw.pop("table_id", None)
                if not isinstance(raw.get("table_ids"), list) or not raw["table_ids"]:
                    raise invalid("a reservation in state names no table")
                res = Reservation(**raw)
                fresh.reservations[res.id] = res
                fresh.references[res.reference] = res.id
            for rec in blob["receipts"]:
                fresh.receipts[(rec["user_id"], rec["method"], rec["path"],
                                rec["key"])] = {
                    "body": rec["body"], "status": rec["status"],
                    "response": rec["response"]}
            fresh.counter = int(blob.get("counter", 0))
        except ApiError:
            raise invalid("state is not a valid tablekeeper snapshot")
        except Exception:
            raise invalid("state is not a valid tablekeeper snapshot")

        with self.lock:
            self.state = fresh

    # -- auth -------------------------------------------------------------

    def signup(self, body):
        email = body.get("email")
        password = body.get("password")
        display_name = body.get("display_name")
        if not isinstance(email, str):
            raise bad_request("email must be a string")
        if not isinstance(password, str):
            raise bad_request("password must be a string")
        if display_name is not None and not isinstance(display_name, str):
            raise bad_request("display_name must be a string")
        if not EMAIL_RE.match(email):
            raise invalid("email must be of the form local@domain")
        if len(password) < 8:
            raise invalid("password must be at least 8 characters")
        stored = hash_password(password)
        with self.lock:
            s = self.state
            if email in s.emails:
                raise ApiError(409, "email_taken", "email already registered")
            uid = "u_%s" % secrets.token_hex(8)
            while uid in s.users:
                uid = "u_%s" % secrets.token_hex(8)
            s.users[uid] = {"id": uid, "email": email,
                            "display_name": display_name,
                            "password_hash": stored}
            s.emails[email] = uid
            token = self._issue_token(uid)
            return 201, {"user_id": uid, "display_name": display_name,
                         "token": token}

    def login(self, body):
        email = body.get("email")
        password = body.get("password")
        if not isinstance(email, str):
            raise bad_request("email must be a string")
        if not isinstance(password, str):
            raise bad_request("password must be a string")
        with self.lock:
            uid = self.state.emails.get(email)
            stored = self.state.users[uid]["password_hash"] if uid else None
        if uid is None or not verify_password(password, stored):
            raise ApiError(401, "unauthenticated", "wrong email or password")
        with self.lock:
            user = self.state.users[uid]
            return 200, {"user_id": uid, "display_name": user["display_name"],
                         "token": self._issue_token(uid)}

    def _issue_token(self, uid):
        token = secrets.token_urlsafe(24)
        self.state.tokens[token] = uid
        return token

    def authenticate(self, header):
        if not isinstance(header, str):
            raise ApiError(401, "unauthenticated", "missing bearer token")
        parts = header.split(" ", 1)
        if len(parts) != 2 or parts[0] != "Bearer" or not parts[1].strip():
            raise ApiError(401, "unauthenticated", "malformed authorization header")
        with self.lock:
            uid = self.state.tokens.get(parts[1].strip())
        if uid is None:
            raise ApiError(401, "unauthenticated", "unknown bearer token")
        return uid

    # -- lookups ----------------------------------------------------------

    def restaurant_or_404(self, restaurant_id):
        r = self.state.restaurants.get(restaurant_id)
        if r is None:
            raise not_found("no such restaurant")
        return r

    def owned_reservation(self, user_id, reference):
        rid = self.state.references.get(reference)
        if rid is None:
            raise not_found("no such reservation")
        res = self.state.reservations[rid]
        if res.user_id != user_id:
            raise not_found("no such reservation")
        return res

    # -- availability -----------------------------------------------------

    def availability(self, query):
        restaurant_id = self._one(query, "restaurant_id")
        date_text = self._one(query, "date")
        party_text = self._one(query, "party_size")
        if restaurant_id is None or date_text is None or party_text is None:
            raise invalid("restaurant_id, date and party_size are required")
        if not DIGITS_RE.match(party_text):
            raise invalid("party_size must be plain decimal digits")
        party_size = int(party_text)
        if party_size < 1:
            raise invalid("party_size must be at least 1")
        date = parse_date(date_text)
        with self.lock:
            restaurant = self.restaurant_or_404(restaurant_id)
            slots = []
            entry = restaurant.hours_for(date)
            if entry is not None:
                taken = self._occupancy(restaurant)
                step = restaurant.slot_minutes
                duration = restaurant.reservation_duration_minutes
                minute = entry["_opens"]
                while minute + duration <= entry["_closes"]:
                    naive = datetime(date.year, date.month, date.day) + \
                        timedelta(minutes=minute)
                    start = resolve_local(naive, restaurant.tz)
                    minute += step
                    if start is None:
                        continue
                    start_utc = start.astimezone(timezone.utc)
                    end_utc = start_utc + timedelta(minutes=duration)
                    def is_free(tid):
                        return not any(s < end_utc and start_utc < e
                                       for s, e in taken.get(tid, ()))
                    # `available_table_ids` is single tables only, unchanged from
                    # stage 1. `available_options` adds the declared pairs after
                    # the singles, each group in its own declared order.
                    free = [t["id"] for t in restaurant.tables
                            if t["capacity"] >= party_size and is_free(t["id"])]
                    options = [{"table_ids": [t["id"]], "capacity": t["capacity"]}
                               for t in restaurant.tables
                               if t["capacity"] >= party_size and is_free(t["id"])]
                    for pair in restaurant.combinable:
                        if restaurant.capacity_of(pair) < party_size:
                            continue
                        if not all(is_free(tid) for tid in pair):
                            continue
                        options.append({"table_ids": list(pair),
                                        "capacity": restaurant.capacity_of(pair)})
                    slots.append({
                        "starts_at_local": naive.strftime("%Y-%m-%dT%H:%M"),
                        "starts_at": start.isoformat(),
                        "available_table_ids": free,
                        "available_options": options})
            return {"restaurant_id": restaurant.id,
                    "date": date.strftime("%Y-%m-%d"),
                    "timezone": restaurant.timezone,
                    "slots": slots}

    @staticmethod
    def _one(query, name):
        values = query.get(name)
        if not values:
            return None
        return values[0]

    def _occupancy(self, restaurant, exclude=()):
        taken = {}
        for res in self.state.reservations.values():
            if res.restaurant_id != restaurant.id or res.status != "confirmed":
                continue
            if res.id in exclude:
                continue
            span = res.interval(restaurant)
            for tid in res.table_ids:
                taken.setdefault(tid, []).append(span)
        return taken

    # -- reservations -----------------------------------------------------

    @staticmethod
    def resolve_table_set(body, current=None):
        """`table_ids`, or `table_id` meaning a set of one. Sending both is invalid."""
        has_ids = "table_ids" in body
        has_one = "table_id" in body
        if has_ids and has_one:
            raise invalid("send table_id or table_ids, not both")
        if has_ids:
            raw = body["table_ids"]
            if not isinstance(raw, list):
                raise invalid("table_ids must be a list of table ids")
            if not raw:
                raise invalid("table_ids must name at least one table")
            for tid in raw:
                if not isinstance(tid, str) or not tid:
                    raise invalid("table_ids must hold table ids")
            if len(set(raw)) != len(raw):
                raise invalid("table_ids must not repeat a table")
            return list(raw)
        if has_one:
            tid = body["table_id"]
            if not isinstance(tid, str) or not tid:
                raise bad_request("table_id must be a string")
            return [tid]
        if current is not None:
            return list(current)
        raise invalid("table_id or table_ids is required")

    def _validate_fields(self, restaurant_id, table_ids, local_text, party_size):
        """Non-occupancy validation, in the order the specification implies."""
        if isinstance(party_size, bool) or not isinstance(party_size, int):
            raise invalid("party_size must be an integer of at least 1")
        if party_size < 1:
            raise invalid("party_size must be at least 1")
        naive = parse_local(local_text)
        if not isinstance(restaurant_id, str):
            raise bad_request("restaurant_id must be a string")
        restaurant = self.state.restaurants.get(restaurant_id)
        if restaurant is None:
            raise not_found("no such restaurant")
        for tid in table_ids:
            if restaurant.table(tid) is None:
                raise not_found("no such table at this restaurant")
        # A set is bookable only as a single table or as a declared pair. The
        # combination rule is decided before capacity, so three tables whose
        # every pair is declared is still refused rather than measured.
        if len(table_ids) > 2:
            raise ApiError(422, "combination_not_allowed",
                           "tables may be combined in pairs only")
        if len(table_ids) == 2 and not restaurant.is_combinable(table_ids):
            raise ApiError(422, "combination_not_allowed",
                           "that pair of tables is not offered as a combination")
        if party_size > restaurant.capacity_of(table_ids):
            raise ApiError(422, "party_exceeds_capacity",
                           "party_size exceeds the combined capacity")
        entry = restaurant.hours_for(naive.date())
        if entry is None:
            raise ApiError(422, "outside_opening_hours", "the restaurant is closed")
        minute = naive.hour * 60 + naive.minute
        if minute < entry["_opens"] or minute > entry["_closes"]:
            raise ApiError(422, "outside_opening_hours",
                           "outside the restaurant's opening hours")
        if (minute - entry["_opens"]) % restaurant.slot_minutes != 0:
            raise ApiError(422, "not_on_slot_grid",
                           "start is not on the slot grid")
        if minute + restaurant.reservation_duration_minutes > entry["_closes"]:
            raise ApiError(422, "outside_opening_hours",
                           "the reservation would end after closing")
        start = resolve_local(naive, restaurant.tz)
        if start is None:
            raise ApiError(422, "invalid_local_time",
                           "that local time does not exist")
        return restaurant, start

    def _conflicts(self, restaurant, table_ids, start, exclude=()):
        start_utc = start.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(
            minutes=restaurant.reservation_duration_minutes)
        taken = self._occupancy(restaurant, exclude)
        for tid in table_ids:
            for s, e in taken.get(tid, ()):
                if s < end_utc and start_utc < e:
                    return True
        return False

    def _new_reference(self):
        while True:
            ref = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))
            if ref not in self.state.references:
                return ref

    def create_reservation(self, user_id, body):
        with self.lock:
            table_ids = self.resolve_table_set(body)
            restaurant, start = self._validate_fields(
                body.get("restaurant_id"), table_ids,
                body.get("starts_at_local"), body.get("party_size"))
            if self._conflicts(restaurant, table_ids, start):
                raise ApiError(409, "table_unavailable",
                               "the table is taken for an overlapping interval")
            n = self.state.next_counter()
            rid = "res_%d" % n
            while rid in self.state.reservations:
                n = self.state.next_counter()
                rid = "res_%d" % n
            res = Reservation(
                id=rid, reference=self._new_reference(), user_id=user_id,
                restaurant_id=restaurant.id, table_ids=table_ids,
                starts_at_local=body["starts_at_local"],
                party_size=body["party_size"], status="confirmed",
                created_at=now_utc().isoformat())
            self.state.reservations[rid] = res
            self.state.references[res.reference] = rid
            return 201, res.view(restaurant)

    def list_reservations(self, user_id):
        with self.lock:
            rows = []
            for res in self.state.reservations.values():
                if res.user_id != user_id:
                    continue
                restaurant = self.state.restaurants[res.restaurant_id]
                rows.append((res.interval(restaurant)[0], res.view(restaurant)))
            rows.sort(key=lambda row: row[0], reverse=True)
            return {"reservations": [view for _, view in rows]}

    def get_reservation(self, user_id, reference):
        with self.lock:
            res = self.owned_reservation(user_id, reference)
            return res.view(self.state.restaurants[res.restaurant_id])

    def _cutoff_passed(self, res, restaurant):
        start_utc = res.interval(restaurant)[0]
        return now_utc() >= start_utc - timedelta(
            minutes=restaurant.cancellation_cutoff_minutes)

    def cancel_reservation(self, user_id, reference):
        with self.lock:
            res = self.owned_reservation(user_id, reference)
            restaurant = self.state.restaurants[res.restaurant_id]
            if res.status == "cancelled":
                return res.view(restaurant)
            if self._cutoff_passed(res, restaurant):
                raise ApiError(409, "cutoff_passed",
                               "past the cancellation cutoff")
            res.status = "cancelled"
            return res.view(restaurant)

    def _amend(self, res, item):
        """Validate one amendment and return the pending change."""
        restaurant = self.state.restaurants[res.restaurant_id]
        if res.status == "cancelled":
            raise ApiError(409, "reservation_cancelled",
                           "the reservation is cancelled")
        if self._cutoff_passed(res, restaurant):
            raise ApiError(409, "cutoff_passed", "past the amendment cutoff")
        table_ids = self.resolve_table_set(item, current=res.table_ids)
        local_text = item.get("starts_at_local", res.starts_at_local)
        party_size = item.get("party_size", res.party_size)
        new_restaurant, start = self._validate_fields(
            res.restaurant_id, table_ids, local_text, party_size)
        return {"res": res, "restaurant": new_restaurant, "table_ids": table_ids,
                "starts_at_local": local_text, "party_size": party_size,
                "start": start}

    def patch_reservation(self, user_id, reference, body):
        with self.lock:
            res = self.owned_reservation(user_id, reference)
            change = self._amend(res, body)
            if self._conflicts(change["restaurant"], change["table_ids"],
                               change["start"], exclude={res.id}):
                raise ApiError(409, "table_unavailable",
                               "the table is taken for an overlapping interval")
            res.table_ids = change["table_ids"]
            res.starts_at_local = change["starts_at_local"]
            res.party_size = change["party_size"]
            return res.view(change["restaurant"])

    def reservation_moves(self, user_id, body):
        with self.lock:
            moves = body.get("moves")
            if not isinstance(moves, list) or not 1 <= len(moves) <= 8:
                raise invalid("moves must hold 1..8 objects")
            references = []
            for item in moves:
                if not isinstance(item, dict):
                    raise invalid("each move must be an object")
                reference = item.get("reference")
                if not isinstance(reference, str) or not reference:
                    raise invalid("each move needs a string reference")
                references.append(reference)
            if len(set(references)) != len(references):
                raise invalid("move references must be distinct")

            targets = [self.owned_reservation(user_id, r) for r in references]
            if len({res.restaurant_id for res in targets}) > 1:
                raise invalid("all bookings must belong to the same restaurant")

            changes = [self._amend(res, item) for res, item in zip(targets, moves)]

            moved = {c["res"].id for c in changes}
            restaurant = self.state.restaurants[targets[0].restaurant_id]
            occupied = {}
            for table_id, intervals in self._occupancy(restaurant, moved).items():
                occupied.setdefault(table_id, []).extend(intervals)
            for c in changes:
                start_utc = c["start"].astimezone(timezone.utc)
                end_utc = start_utc + timedelta(
                    minutes=c["restaurant"].reservation_duration_minutes)
                for tid in c["table_ids"]:
                    for s, e in occupied.get(tid, ()):
                        if s < end_utc and start_utc < e:
                            raise ApiError(409, "table_unavailable",
                                           "the batch would double-book a table")
                for tid in c["table_ids"]:
                    occupied.setdefault(tid, []).append((start_utc, end_utc))

            views = []
            for c in changes:
                res = c["res"]
                res.table_ids = c["table_ids"]
                res.starts_at_local = c["starts_at_local"]
                res.party_size = c["party_size"]
                views.append(res.view(c["restaurant"]))
            return 201, {"reservations": views}

    # -- idempotency ------------------------------------------------------

    def idempotent(self, user_id, method, path, key, body, run):
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        slot = (user_id, method, path, key)
        with self.lock:
            receipt = self.state.receipts.get(slot)
            if receipt is not None:
                if receipt["body"] != canonical:
                    raise ApiError(409, "idempotency_key_reuse",
                                   "key already used with a different body")
                return 200, receipt["response"]
            status, response = run()
            self.state.receipts[slot] = {"body": canonical, "status": status,
                                         "response": response}
            return status, response




# --- browser interface ------------------------------------------------------
# Served from the image: no font, script or stylesheet is fetched at run time.

UI_CSS = """*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;padding:0;max-width:100%;overflow-x:hidden}
body{background:#fffbf5;color:#1c1917;
  font:16px/1.55 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
a{color:#7a2617}
.wrap{max-width:62rem;margin:0 auto;padding:1rem 1rem 3rem}
header.bar{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:baseline;
  padding:.85rem 1rem;background:#7a2617;color:#fffbf5}
header.bar .brand{font-size:1.25rem;font-weight:700;letter-spacing:.01em;margin-right:auto}
header.bar nav{display:flex;flex-wrap:wrap;gap:.75rem}
header.bar nav a{color:#fffbf5;text-decoration:underline;text-underline-offset:3px}
.who{display:flex;flex-wrap:wrap;gap:.5rem;align-items:baseline}
.who .name{font-weight:700}
h1{font-size:1.6rem;margin:1.25rem 0 .35rem}
h2{font-size:1.15rem;margin:1.5rem 0 .5rem}
p.lede{margin:0 0 1.25rem;color:#44403c;max-width:44rem}
.card{background:#fff;border:1px solid #ddd6cc;border-radius:10px;padding:1rem;margin:0 0 1.25rem}
.field{display:block;margin:0 0 .85rem}
.field > span{display:block;font-weight:700;font-size:.95rem;margin:0 0 .3rem;color:#1c1917}
input,select{width:100%;max-width:22rem;font:inherit;color:#1c1917;background:#fff;
  border:1px solid #8a827a;border-radius:7px;padding:.5rem .6rem}
input:focus,select:focus,button:focus{outline:3px solid #0b3d91;outline-offset:2px}
button{font:inherit;font-weight:700;cursor:pointer;border-radius:7px;padding:.55rem 1rem;
  background:#7a2617;color:#fff;border:1px solid #5e1c11}
button.secondary{background:#fff;color:#7a2617;border:1px solid #7a2617}
button[disabled]{cursor:default;background:#8a827a;border-color:#6b645d}
.row{display:flex;flex-wrap:wrap;gap:.85rem;align-items:flex-end}
.gridwrap{overflow-x:auto;overflow-y:hidden;border:1px solid #ddd6cc;border-radius:10px;background:#fff}
table.grid{border-collapse:collapse;min-width:100%}
table.grid th,table.grid td{border-bottom:1px solid #eee7dd;padding:.3rem;text-align:left;
  white-space:nowrap;font-size:.95rem}
table.grid thead th{background:#f6efe4;position:sticky;top:0;font-size:.9rem}
table.grid th.time{font-variant-numeric:tabular-nums;font-weight:700}
.cellbtn{display:block;width:100%;min-width:7.5rem;text-align:left;font-size:.9rem;
  padding:.4rem .5rem;border-radius:6px;font-family:inherit}
.cellbtn .cap{display:block;font-size:.8rem;font-weight:400}
[data-available="true"]{background:#e9f7ef;border:1px solid #1f7a4d;color:#14532d;font-weight:600;
  text-decoration-line:none;opacity:1}
[data-available="false"]{background:#efedea;border:1px solid #b8b2ab;color:#44403c;font-weight:400;
  text-decoration-line:line-through;opacity:1;cursor:default}
[data-available="true"][aria-pressed="true"]{background:#14532d;border:1px solid #0b3d21;color:#fff;
  font-weight:700;text-decoration-line:none}
.note{border-radius:8px;padding:.8rem 1rem;margin:0 0 1rem;border:1px solid}
#no-slots,[data-testid="no-slots"]{background:#f6efe4;border-color:#a1887a;color:#4a352c;font-weight:400}
[data-testid="booking-loading"],[data-testid="search-loading"]{background:#fff7e6;
  border-color:#b45309;color:#7c2d12;font-weight:500;text-decoration-line:none;opacity:1}
[data-testid="confirmation"]{background:#e9f7ef;border-color:#14532d;color:#14532d;font-weight:700;
  text-decoration-line:none;opacity:1}
[data-testid="booking-error"],[data-testid="auth-error"],[data-testid="reservation-error"]{
  background:#fdeaea;border-color:#b91c1c;color:#7f1d1d;font-weight:600;
  text-decoration-line:none;opacity:1}
[data-testid="booking-uncertain"]{background:#fff7e6;border-color:#a16207;color:#713f12;
  font-weight:600;text-decoration-line:underline;opacity:1}
[data-testid="confirmation-reference"]{font-size:1.5rem;font-weight:700;letter-spacing:.06em;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.tables{font-weight:700}
dl.kv{margin:0}
dl.kv dt{font-weight:700;font-size:.9rem;color:#44403c}
dl.kv dd{margin:0 0 .6rem}
.muted{color:#44403c}
@media (max-width:480px){.wrap{padding:.75rem .75rem 2.5rem}h1{font-size:1.35rem}
  input,select{max-width:100%}.cellbtn{min-width:6.5rem}}
"""

UI_JS = """(function(){
var TK="tk.session";
function sess(){try{return JSON.parse(localStorage.getItem(TK)||"null")}catch(e){return null}}
function setSess(s){if(s)localStorage.setItem(TK,JSON.stringify(s));else localStorage.removeItem(TK)}
function el(t,a,kids){var e=document.createElement(t);a=a||{};
  for(var k in a){if(k==="text")e.textContent=a[k];else if(a[k]!==null&&a[k]!==undefined)e.setAttribute(k,a[k])}
  (kids||[]).forEach(function(c){if(c)e.appendChild(c)});return e}
function q(id){return document.querySelector('[data-testid="'+id+'"]')}
function slot(id){var n=q(id);if(n)n.remove()}
function note(id,tag,msg){var host=document.getElementById("feedback");if(!host)return;
  slot(id);if(msg===null)return;
  host.appendChild(el(tag||"p",{"class":"note","data-testid":id,text:msg}))}
function api(method,path,body,key){
  var s=sess(),h={"Content-Type":"application/json"};
  if(s&&s.token)h["Authorization"]="Bearer "+s.token;
  if(key)h["Idempotency-Key"]=key;
  return fetch(path,{method:method,headers:h,body:body?JSON.stringify(body):undefined})
    .then(function(r){return r.text().then(function(t){
      var j=null;try{j=t?JSON.parse(t):null}catch(e){}
      return {status:r.status,body:j}})})}
function errText(r,fallback){
  return (r&&r.body&&r.body.error&&r.body.error.message)?r.body.error.message:fallback}

/* ---- header: who is signed in, on every screen ---- */
function paintWho(){
  var host=document.getElementById("who");if(!host)return;
  host.textContent="";var s=sess();
  if(!s){host.appendChild(el("a",{href:"/login",text:"Sign in"}));
         host.appendChild(el("a",{href:"/signup",text:"Create an account"}));return}
  host.appendChild(el("span",{"class":"name","data-testid":"current-user",
    text:"Signed in as "+s.display_name}));
  var b=el("button",{"class":"secondary","data-testid":"logout-button",type:"button",text:"Sign out"});
  b.addEventListener("click",function(){setSess(null);paintWho();
    if(window.TKPAGE==="search"){resetBooking();}});
  host.appendChild(b)}

/* ---- auth ---- */
function wireAuth(kind){
  var btn=q(kind+"-submit");if(!btn)return;
  btn.addEventListener("click",function(ev){
    ev.preventDefault();note("auth-error",null,null);
    var body={email:(q(kind+"-email")||{}).value,password:(q(kind+"-password")||{}).value};
    if(kind==="signup")body.display_name=(q("signup-display-name")||{}).value;
    api("POST","/auth/"+(kind==="signup"?"signup":"login"),body).then(function(r){
      if(r.status===201||r.status===200){
        setSess({token:r.body.token,display_name:r.body.display_name,user_id:r.body.user_id});
        paintWho();note("auth-error",null,null);
        var d=document.getElementById("auth-done");
        if(d)d.textContent="Welcome, "+r.body.display_name+". You can book a table now.";
      }else{note("auth-error","p",errText(r,"That did not work. Check your details and try again."))}
    }).catch(function(){note("auth-error","p","We could not reach the restaurant. Try again.")})})}

/* ---- search + grid ---- */
var SEARCH_SEQ=0, LAST_APPLIED=0, REST={}, SEL=null, KEYS={}, PENDING=null;
function labelOf(rid,tid){var r=REST[rid];if(!r)return tid;
  for(var i=0;i<r.tables.length;i++)if(r.tables[i].id===tid)return r.tables[i].label||tid;return tid}
function labelsOf(rid,ids){return ids.map(function(t){return labelOf(rid,t)}).join(" + ")}
function resetBooking(){SEL=null;var f=document.getElementById("bookingzone");
  if(f)f.textContent="";note("booking-error",null,null);note("booking-uncertain",null,null);
  note("booking-loading",null,null)}

function paintGrid(rid,data,partySize){
  var zone=document.getElementById("results");zone.textContent="";
  zone.setAttribute("aria-busy","false");
  if(!data.slots.length){
    zone.appendChild(el("p",{"class":"note","data-testid":"no-slots",
      text:"No sittings on this date — the restaurant is closed. Try another date or a different party size."}));
    return}
  var pairs=(REST[rid]&&REST[rid].combinable)||[];
  var cols=[];
  (REST[rid].tables||[]).forEach(function(t){cols.push({ids:[t.id],label:t.label||t.id,cap:t.capacity})});
  pairs.forEach(function(p){cols.push({ids:[p[0],p[1]],
    label:labelsOf(rid,[p[0],p[1]]),cap:0})});
  zone.appendChild(el("h2",{id:"gridcap",text:"Availability"}));
  var head=el("tr",{},[el("th",{scope:"col",text:"Time"})]);
  cols.forEach(function(c){head.appendChild(el("th",{scope:"col",text:c.label}))});
  var body=el("tbody");
  data.slots.forEach(function(s){
    var hhmm=s.starts_at_local.slice(11);
    var tr=el("tr",{},[el("th",{scope:"row","class":"time",text:hhmm})]);
    cols.forEach(function(c){
      var ok;
      if(c.ids.length===1){ok=s.available_table_ids.indexOf(c.ids[0])>=0}
      else{ok=(s.available_options||[]).some(function(o){
        return o.table_ids.length===2&&o.table_ids[0]===c.ids[0]&&o.table_ids[1]===c.ids[1]})}
      var tid="slot-"+c.ids.join("+")+"-"+hhmm;
      var cap=(s.available_options||[]).filter(function(o){
        return o.table_ids.join("+")===c.ids.join("+")})[0];
      var b=el("button",{"class":"cellbtn","data-testid":tid,"data-available":ok?"true":"false",
        "aria-pressed":"false",type:"button",
        "aria-label":c.label+" at "+hhmm+(ok?" — available":" — not available")},
        [el("span",{text:ok?"Available":"Taken"}),
         el("span",{"class":"cap",text:cap?("seats up to "+cap.capacity):""})]);
      if(ok)b.addEventListener("click",function(){choose(rid,c,s,partySize)});
      tr.appendChild(el("td",{},[b]))});
    body.appendChild(tr)});
  var wrap=el("div",{"class":"gridwrap"},[
    el("table",{"class":"grid","data-testid":"availability-grid"},[el("thead",{},[head]),body])]);
  zone.appendChild(wrap)}

function ensureRest(rid){
  if(REST[rid])return Promise.resolve(REST[rid]);
  return api("GET","/restaurants/"+encodeURIComponent(rid)).then(function(d){
    if(d.status===200)REST[d.body.id]=d.body;return REST[rid]})}
function search(){
  var rid=q("restaurant-select").value,date=q("date-input").value,
      ps=q("party-size-input").value;
  var seq=++SEARCH_SEQ;
  var zone=document.getElementById("results");
  zone.setAttribute("aria-busy","true");
  var btn=q("search-button");btn.disabled=true;
  note("search-loading","p","Looking for tables…");
  api("GET","/availability?restaurant_id="+encodeURIComponent(rid)
      +"&date="+encodeURIComponent(date)+"&party_size="+encodeURIComponent(ps))
    .then(function(r){
      /* A response that started earlier but landed later must not win. */
      if(seq<LAST_APPLIED)return;
      LAST_APPLIED=seq;
      if(seq===SEARCH_SEQ){btn.disabled=false;note("search-loading",null,null)}
      resetBooking();
      if(r.status!==200){
        document.getElementById("results").textContent="";
        note("search-error","p",errText(r,"That search was not accepted."));return}
      note("search-error",null,null);
      return ensureRest(rid).then(function(){
        if(seq<LAST_APPLIED)return;
        paintGrid(rid,r.body,Number(ps))})})
    .catch(function(){if(seq===SEARCH_SEQ){btn.disabled=false;note("search-loading",null,null)}})}

/* ---- booking ---- */
function choose(rid,col,slotObj,partySize){
  if(!sess()){
    /* Booking needs an account: refuse at the click rather than at submit. */
    note("auth-error","p","Please sign in to reserve a table.");
    resetBooking();
    document.getElementById("confirmzone").textContent="";
    return}
  note("auth-error",null,null);
  SEL={rid:rid,ids:col.ids,label:col.label,at:slotObj.starts_at_local,hhmm:slotObj.starts_at_local.slice(11)};
  document.querySelectorAll('[data-testid^="slot-"]').forEach(function(n){
    n.setAttribute("aria-pressed","false")});
  var me=q("slot-"+col.ids.join("+")+"-"+SEL.hhmm);
  if(me)me.setAttribute("aria-pressed","true");
  note("booking-error",null,null);note("booking-uncertain",null,null);
  var zone=document.getElementById("bookingzone");zone.textContent="";
  var name=(REST[rid]&&REST[rid].name)||rid;
  var form=el("form",{"class":"card","data-testid":"booking-form"},[
    el("h2",{text:"Reserve this table"}),
    el("p",{"data-testid":"booking-summary",
      text:col.label+" at "+SEL.hhmm+" on "+SEL.at.slice(0,10)+" — "+name}),
    el("label",{"class":"field",for:"bps"},[el("span",{text:"How many guests?"}),
      el("input",{id:"bps","data-testid":"booking-party-size",type:"number",min:"1",
        value:String(partySize)})]),
    el("button",{"data-testid":"booking-submit",type:"submit",text:"Confirm reservation"})]);
  form.addEventListener("submit",function(ev){ev.preventDefault();submitBooking()});
  zone.appendChild(form)}

function bodyFor(){
  var ps=Number((q("booking-party-size")||{}).value);
  var b={restaurant_id:SEL.rid,starts_at_local:SEL.at,party_size:ps};
  if(SEL.ids.length===1)b.table_id=SEL.ids[0];else b.table_ids=SEL.ids.slice();
  return b}
function keyFor(body){
  var sig=JSON.stringify(body);
  /* One key per distinct body: an unchanged retry replays, an edited form books anew. */
  if(!KEYS[sig])KEYS[sig]="tk-"+Math.random().toString(36).slice(2)+Date.now().toString(36);
  return KEYS[sig]}

function showConfirmation(res){
  var name=(REST[res.restaurant_id]&&REST[res.restaurant_id].name)||res.restaurant_id;
  var labs=labelsOf(res.restaurant_id,res.table_ids);
  var zone=document.getElementById("confirmzone");zone.textContent="";
  zone.appendChild(el("div",{"class":"note","data-testid":"confirmation"},[
    el("h2",{text:"You're booked"}),
    el("p",{"data-testid":"confirmation-reference",text:res.reference}),
    el("p",{"data-testid":"confirmation-details",
      text:name+" — "+labs+" — "+res.starts_at_local.slice(11)+" on "+res.starts_at_local.slice(0,10)
        +" — "+res.party_size+" guests"}),
    el("p",{"class":"tables","data-testid":"confirmation-tables",text:labs}),
    el("p",{"class":"muted",text:"Keep the reference above — you can look it up any time."})]))}

function submitBooking(){
  if(!SEL)return;
  var s=sess();
  if(!s){note("auth-error","p","Please sign in to reserve a table.");return}
  var body=bodyFor(),key=keyFor(body);
  note("booking-error",null,null);
  note("booking-loading","p","Confirming your reservation…");
  var btn=q("booking-submit");if(btn)btn.disabled=true;
  api("POST","/reservations",body,key).then(function(r){
    note("booking-loading",null,null);if(btn)btn.disabled=false;
    if(r.status===201||r.status===200){
      note("booking-uncertain",null,null);note("booking-error",null,null);
      return ensureRest(r.body.restaurant_id).then(function(){
        showConfirmation(r.body);refreshAvailabilityKeepingForm()})}
    /* A definite refusal: say so, keep the diner's choice, refresh what is free. */
    note("booking-uncertain",null,null);
    document.getElementById("confirmzone").textContent="";
    note("booking-error","p",errText(r,"That table could not be reserved."));
    refreshAvailabilityKeepingForm()})
   .catch(function(){
    /* The response was lost. The booking may or may not exist; never guess. */
    note("booking-loading",null,null);if(btn)btn.disabled=false;
    note("booking-error",null,null);
    note("booking-uncertain","p",
      "We did not hear back, so we cannot tell whether this reservation was made. "
      +"Press Confirm reservation again — it is safe and will not book twice.")})}

function refreshAvailabilityKeepingForm(){
  var rid=q("restaurant-select").value,date=q("date-input").value,ps=q("party-size-input").value;
  var seq=++SEARCH_SEQ;
  api("GET","/availability?restaurant_id="+encodeURIComponent(rid)
      +"&date="+encodeURIComponent(date)+"&party_size="+encodeURIComponent(ps))
    .then(function(r){
      if(seq<LAST_APPLIED||r.status!==200)return;
      LAST_APPLIED=seq;
      var keep=SEL,form=document.getElementById("bookingzone").firstChild;
      var psv=(q("booking-party-size")||{}).value;
      paintGrid(rid,r.body,Number(ps));
      SEL=keep;
      if(form){document.getElementById("bookingzone").appendChild(form);
        if(psv!==undefined){var i=q("booking-party-size");if(i)i.value=psv}}
      var me=keep&&q("slot-"+keep.ids.join("+")+"-"+keep.hhmm);
      if(me)me.setAttribute("aria-pressed","true")})}

/* ---- lookup ---- */
function paintReservation(res){
  var zone=document.getElementById("detailzone");zone.textContent="";
  var name=(REST[res.restaurant_id]&&REST[res.restaurant_id].name)||res.restaurant_id;
  var labs=labelsOf(res.restaurant_id,res.table_ids);
  var dl=el("dl",{"class":"kv"},[
    el("dt",{text:"Reference"}),el("dd",{text:res.reference}),
    el("dt",{text:"Restaurant"}),el("dd",{text:name}),
    el("dt",{text:"Table"}),el("dd",{"class":"tables","data-testid":"reservation-tables",text:labs}),
    el("dt",{text:"When"}),el("dd",{text:res.starts_at_local.slice(11)+" on "+res.starts_at_local.slice(0,10)}),
    el("dt",{text:"Guests"}),el("dd",{text:String(res.party_size)}),
    el("dt",{text:"Status"}),el("dd",{},[el("span",{"data-testid":"reservation-status",text:res.status})])]);
  var card=el("div",{"class":"card","data-testid":"reservation-detail"},[
    el("h2",{text:"Your reservation"}),dl]);
  if(res.status==="confirmed"){
    var b=el("button",{"data-testid":"reservation-cancel-button",type:"button",
      text:"Cancel this reservation"});
    b.addEventListener("click",function(){
      note("reservation-error",null,null);b.disabled=true;
      api("POST","/reservations/"+encodeURIComponent(res.reference)+"/cancel").then(function(r){
        b.disabled=false;
        if(r.status===200){paintReservation(r.body);return}
        note("reservation-error","p",errText(r,"This reservation can no longer be cancelled."))})
       .catch(function(){b.disabled=false;
        note("reservation-error","p","We could not reach the restaurant. Try again.")})});
    card.appendChild(b)}
  zone.appendChild(card)}

function lookup(){
  var ref=(q("lookup-reference-input")||{}).value||"";
  note("reservation-error",null,null);
  document.getElementById("detailzone").textContent="";
  api("GET","/reservations/"+encodeURIComponent(ref.trim())).then(function(r){
    if(r.status===200){
      return ensureRest(r.body.restaurant_id).then(function(){paintReservation(r.body)})}
    note("reservation-error","p",
      r.status===401?"Please sign in to look up a reservation."
                    :"We could not find a reservation with that reference.")})
   .catch(function(){note("reservation-error","p","We could not reach the restaurant. Try again.")})}

/* ---- boot ---- */
function boot(){
  paintWho();
  if(window.TKPAGE==="signup")wireAuth("signup");
  if(window.TKPAGE==="login")wireAuth("login");
  if(window.TKPAGE==="lookup"){var lb=q("lookup-submit");
    if(lb)lb.addEventListener("click",function(e){e.preventDefault();lookup()})}
  if(window.TKPAGE==="search"){
    api("GET","/restaurants").then(function(r){
      var sel=q("restaurant-select");if(!sel)return;
      sel.textContent="";
      (r.body&&r.body.restaurants||[]).forEach(function(x){
        sel.appendChild(el("option",{value:x.id,text:x.name}))});
      var loaded=0,all=(r.body&&r.body.restaurants||[]);
      if(!all.length)return;
      all.forEach(function(x){api("GET","/restaurants/"+encodeURIComponent(x.id)).then(function(d){
        if(d.status===200)REST[d.body.id]=d.body;loaded++})})});
    var sb=q("search-button");
    if(sb)sb.addEventListener("click",function(e){e.preventDefault();search()})}}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();
"""

NAV = [("/", "Find a table"), ("/lookup", "My reservation")]


def page(title, page_key, body):
    nav = "".join('<a href="%s">%s</a>' % (h, t) for h, t in NAV)
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s &middot; Tablekeeper</title>
<style>%(css)s</style>
</head><body>
<header class="bar">
  <span class="brand">Tablekeeper</span>
  <nav>%(nav)s</nav>
  <span class="who" id="who"></span>
</header>
<main class="wrap">
%(body)s
<div id="feedback"></div>
</main>
<script>window.TKPAGE=%(key)s;</script>
<script>%(js)s</script>
</body></html>
""" % {"title": title, "css": UI_CSS, "js": UI_JS, "nav": nav,
       "key": json.dumps(page_key), "body": body}


SEARCH_BODY = """
<h1>Find a table</h1>
<p class="lede">Choose a restaurant, a date and how many of you are coming.
We will show every table and every pair of tables that can seat you.</p>
<form class="card" id="searchform">
  <div class="row">
    <label class="field" for="rsel"><span>Restaurant</span>
      <select id="rsel" data-testid="restaurant-select"></select></label>
    <label class="field" for="dinp"><span>Date</span>
      <input id="dinp" data-testid="date-input" type="date"></label>
    <label class="field" for="pinp"><span>Guests</span>
      <input id="pinp" data-testid="party-size-input" type="number" min="1" value="2"></label>
    <button data-testid="search-button" type="submit">Search</button>
  </div>
</form>
<div id="results" aria-live="polite" aria-busy="false"></div>
<div id="bookingzone"></div>
<div id="confirmzone"></div>
"""

SIGNUP_BODY = """
<h1>Create an account</h1>
<p class="lede">You need an account to hold a table. It takes a moment.</p>
<form class="card">
  <label class="field" for="se"><span>Email address</span>
    <input id="se" data-testid="signup-email" type="email" autocomplete="email"></label>
  <label class="field" for="sp"><span>Password</span>
    <input id="sp" data-testid="signup-password" type="password"
           autocomplete="new-password"></label>
  <label class="field" for="sn"><span>Your name</span>
    <input id="sn" data-testid="signup-display-name" type="text"
           autocomplete="name"></label>
  <button data-testid="signup-submit" type="submit">Create account</button>
</form>
<p id="auth-done" class="muted"></p>
"""

LOGIN_BODY = """
<h1>Sign in</h1>
<p class="lede">Welcome back. Sign in to book a table or manage a reservation.</p>
<form class="card">
  <label class="field" for="le"><span>Email address</span>
    <input id="le" data-testid="login-email" type="email" autocomplete="email"></label>
  <label class="field" for="lp"><span>Password</span>
    <input id="lp" data-testid="login-password" type="password"
           autocomplete="current-password"></label>
  <button data-testid="login-submit" type="submit">Sign in</button>
</form>
<p id="auth-done" class="muted"></p>
"""

LOOKUP_BODY = """
<h1>My reservation</h1>
<p class="lede">Enter the reference from your confirmation to see or cancel a booking.</p>
<form class="card">
  <label class="field" for="lref"><span>Reservation reference</span>
    <input id="lref" data-testid="lookup-reference-input" type="text"
           autocomplete="off" spellcheck="false"></label>
  <button data-testid="lookup-submit" type="submit">Find reservation</button>
</form>
<div id="detailzone"></div>
"""

SCREENS = {
    "/": ("Find a table", "search", SEARCH_BODY),
    "/signup": ("Create an account", "signup", SIGNUP_BODY),
    "/login": ("Sign in", "login", LOGIN_BODY),
    "/lookup": ("My reservation", "lookup", LOOKUP_BODY),
}


SERVICE = Service()


# --- HTTP --------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "tablekeeper"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    # -- plumbing ---------------------------------------------------------

    def _raw_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise bad_request("bad Content-Length")
        if length < 0:
            raise bad_request("bad Content-Length")
        return self.rfile.read(length) if length else b""

    def _json_object(self, raw):
        if not raw:
            raise bad_request("body must be a JSON object")
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception:
            raise bad_request("body is not valid JSON")
        if not isinstance(value, dict):
            raise bad_request("body must be a JSON object")
        return value

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send(self, status, payload):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _fail(self, err):
        self._send(err.status,
                   {"error": {"code": err.code, "message": err.message}})

    def _idempotency_key(self):
        key = self.headers.get("Idempotency-Key")
        if key is None or key == "":
            raise ApiError(400, "missing_idempotency_key",
                           "Idempotency-Key is required")
        if len(key) > 255:
            raise invalid("Idempotency-Key must be 1..255 characters")
        return key

    def _auth(self):
        return SERVICE.authenticate(self.headers.get("Authorization"))

    # -- dispatch ---------------------------------------------------------

    def _dispatch(self, method):
        try:
            raw = self._raw_body()
        except ApiError as err:
            self._fail(err)
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        query = parse_qs(parsed.query, keep_blank_values=True)
        try:
            self._route(method, path, query, raw)
        except ApiError as err:
            self._fail(err)
        except Exception:
            self._fail(ApiError(422, "validation_failed", "request could not be processed"))

    def _route(self, method, path, query, raw):
        parts = [p for p in path.split("/") if p]

        if method == "GET" and path == "/health":
            self._send(200, {"status": "ok"})
            return

        if method == "GET" and path in SCREENS:
            title, key, body = SCREENS[path]
            self._send_html(200, page(title, key, body))
            return

        if path == "/_test/reset":
            if method != "POST":
                raise not_found("no such resource")
            SERVICE.reset(self._json_object(raw))
            self._send(204, None)
            return

        if path == "/_test/export":
            if method != "GET":
                raise not_found("no such resource")
            self._send(200, SERVICE.export())
            return

        if path == "/_test/import":
            if method != "POST":
                raise not_found("no such resource")
            SERVICE.import_state(self._json_object(raw))
            self._send(204, None)
            return

        if path == "/auth/signup":
            if method != "POST":
                raise not_found("no such resource")
            status, payload = SERVICE.signup(self._json_object(raw))
            self._send(status, payload)
            return

        if path == "/auth/login":
            if method != "POST":
                raise not_found("no such resource")
            status, payload = SERVICE.login(self._json_object(raw))
            self._send(status, payload)
            return

        if method == "GET" and path == "/restaurants":
            with SERVICE.lock:
                s = SERVICE.state
                self._send(200, {"restaurants": [s.restaurants[i].public()
                                                 for i in s.restaurant_order]})
            return

        if method == "GET" and len(parts) == 2 and parts[0] == "restaurants":
            with SERVICE.lock:
                self._send(200, SERVICE.restaurant_or_404(parts[1]).detail())
            return

        if method == "GET" and path == "/availability":
            self._send(200, SERVICE.availability(query))
            return

        if path == "/reservations":
            if method == "GET":
                user_id = self._auth()
                self._send(200, SERVICE.list_reservations(user_id))
                return
            if method == "POST":
                user_id = self._auth()
                key = self._idempotency_key()
                body = self._json_object(raw)
                status, payload = SERVICE.idempotent(
                    user_id, "POST", path, key, body,
                    lambda: SERVICE.create_reservation(user_id, body))
                self._send(status, payload)
                return
            raise not_found("no such resource")

        if path == "/reservation-moves":
            if method != "POST":
                raise not_found("no such resource")
            user_id = self._auth()
            key = self._idempotency_key()
            body = self._json_object(raw)
            status, payload = SERVICE.idempotent(
                user_id, "POST", path, key, body,
                lambda: SERVICE.reservation_moves(user_id, body))
            self._send(status, payload)
            return

        if len(parts) == 3 and parts[0] == "reservations" and parts[2] == "cancel":
            if method != "POST":
                raise not_found("no such resource")
            user_id = self._auth()
            self._send(200, SERVICE.cancel_reservation(user_id, parts[1]))
            return

        if len(parts) == 2 and parts[0] == "reservations":
            user_id = self._auth()
            if method == "GET":
                self._send(200, SERVICE.get_reservation(user_id, parts[1]))
                return
            if method == "PATCH":
                body = self._json_object(raw) if raw else {}
                self._send(200, SERVICE.patch_reservation(
                    user_id, parts[1], body))
                return
            raise not_found("no such resource")

        raise not_found("no such resource")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def main():
    port = int(os.environ.get("PORT") or "8080")
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
