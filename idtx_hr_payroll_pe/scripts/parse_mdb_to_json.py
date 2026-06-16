# Proceso APARTE (sin Odoo): parsea el .mdb y arma SESIONES (entrada->salida)
# emparejando cada marca con la siguiente dentro de <= MAX_SHIFT horas. Maneja
# turnos que cruzan medianoche y tolera marcas mal tipeadas / faltantes.
import json
import pytz
from datetime import datetime, date as date_cls
from access_parser import AccessParser

LIMA = pytz.timezone('America/Lima'); UTC = pytz.UTC
SINCE = date_cls(2026, 1, 1)
MAX_SHIFT = 16.0  # horas máximas de una sesión

db = AccessParser('/tmp/att2000.mdb')
ui = db.parse_table('USERINFO')
co = db.parse_table('CHECKINOUT')

badge = {}
for uid, b in zip(ui.get('USERID', []), ui.get('Badgenumber', [])):
    if uid is not None:
        badge[str(uid)] = '' if b is None else str(b).strip()

def parse_dt(s):
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None

# Agrupar marcas por DNI: (datetime, tipo I/O)
punches = {}
us = co.get('USERID', [])
tm = co.get('CHECKTIME', [])
ct = co.get('CHECKTYPE', [])
for uid, t, c in zip(us, tm, ct):
    dni = badge.get(str(uid))
    if not dni:
        continue
    dt = parse_dt(t)
    if not dt:
        continue
    typ = str(c).strip().upper()
    typ = typ if typ in ('I', 'O') else ''
    punches.setdefault(dni, []).append((dt, typ))

out = []
def emit(dni, ci, cox):
    if ci.date() < SINCE:
        return
    ci_u = LIMA.localize(ci).astimezone(UTC).replace(tzinfo=None)
    co_u = LIMA.localize(cox).astimezone(UTC).replace(tzinfo=None)
    out.append([dni, ci_u.strftime('%Y-%m-%d %H:%M:%S'), co_u.strftime('%Y-%m-%d %H:%M:%S')])

singles = 0
for dni, plist in punches.items():
    plist.sort(key=lambda x: x[0])
    open_in = None
    for dt, typ in plist:
        if open_in is None:
            if typ != 'O':      # 'I' o sin tipo inicia sesión; 'O' huérfano se omite
                open_in = dt
        else:
            gap = (dt - open_in).total_seconds() / 3600.0
            if gap <= MAX_SHIFT:
                emit(dni, open_in, dt)      # cierra la sesión con esta marca
                open_in = None
            else:
                emit(dni, open_in, open_in)  # marca solitaria (sin salida)
                singles += 1
                open_in = dt if typ != 'O' else None
    if open_in is not None:
        emit(dni, open_in, open_in)
        singles += 1

json.dump(out, open('/tmp/att_grouped.json', 'w'))
print("Sesiones >= %s: %s | sesiones de una sola marca: %s | DNIs: %s" % (
    SINCE, len(out), singles, len({r[0] for r in out})), flush=True)
