# -*- coding: utf-8 -*-
import datetime
import pytz
import dbf

def _safe_str(v):
    if v is None:
        return False
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    try:
        return str(v).strip()
    except Exception:
        return False

def _safe_float(v):
    if v is None or v is False:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0

def _safe_date(v, user_tz=None):
    if not v:
        return False
    user_tz = user_tz or pytz.UTC
    if isinstance(v, datetime.datetime):
        dt = v
    elif isinstance(v, datetime.date):
        dt = datetime.datetime.combine(v, datetime.time.min)
    else:
        s = str(v).strip()
        try:
            dt = datetime.datetime.fromisoformat(s[:19])
        except Exception:
            try:
                d = datetime.date.fromisoformat(s[:10])
                dt = datetime.datetime.combine(d, datetime.time.min)
            except Exception:
                return False
    if dt.tzinfo is None:
        dt = user_tz.localize(dt)
    dt_utc = dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return dt_utc

def _safe_bool(v):
    if v in (True, False):
        return bool(v)
    if v is None:
        return False
    s = str(v).strip().upper()
    return s in ("T", "Y", "1", "SI", "S", "TRUE")
