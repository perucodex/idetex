# Proceso APARTE (sin Odoo): parsea el .mdb y vuelca grupos a JSON chico.
import json
import pytz
from datetime import datetime, date as date_cls
from access_parser import AccessParser

LIMA = pytz.timezone('America/Lima'); UTC = pytz.UTC
SINCE = date_cls(2026, 1, 1)

db = AccessParser('/tmp/att2000.mdb')
ui = db.parse_table('USERINFO')
co = db.parse_table('CHECKINOUT')

badge = {}
for uid, b in zip(ui.get('USERID', []), ui.get('Badgenumber', [])):
    if uid is None:
        continue
    badge[str(uid)] = '' if b is None else str(b).strip()

groups = {}
total = 0
for uid, t in zip(co.get('USERID', []), co.get('CHECKTIME', [])):
    if uid is None or t is None:
        continue
    s = str(t).strip()
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue
    dni = badge.get(str(uid))
    if not dni:
        continue
    local = LIMA.localize(dt)
    if local.date() < SINCE:
        continue
    key = dni + '|' + local.date().isoformat()
    groups.setdefault(key, []).append(local.astimezone(UTC).replace(tzinfo=None))
    total += 1

out = []
for key, times in groups.items():
    dni, ds = key.split('|')
    times.sort()
    ci = times[0]
    cox = times[-1] if (len(times) > 1 and times[-1] > times[0]) else times[0]
    out.append([dni, ds, ci.strftime('%Y-%m-%d %H:%M:%S'), cox.strftime('%Y-%m-%d %H:%M:%S')])

json.dump(out, open('/tmp/att_grouped.json', 'w'))
print("Marcaciones >= %s: %s | grupos (DNI-día): %s | DNIs distintos: %s" % (
    SINCE, total, len(out), len({r[0] for r in out})), flush=True)
