#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill ÚNICO de asistencias desde el att2000.mdb (ZKTeco) hacia Odoo.

- Baja el .mdb por smbclient (NO monta el recurso).
- Lee CHECKINOUT + USERINFO (Badgenumber = DNI).
- Empareja por (empleado, día local Lima): primera marca = entrada, última = salida.
- Crea hr.attendance en Odoo por XML-RPC (idempotente: no duplica por día).

Tras este backfill, la actualización continua la hace el reloj (módulo zk.device).

Configuración por variables de entorno (no se hardcodean credenciales):
  SMB_HOST   (def 172.16.64.5)   SMB_SHARE (def sistemas)
  SMB_PATH   (def BDRELOJMARCADOR\\att2000.mdb)
  SMB_USER   SMB_PASS            SMB_DOMAIN (opcional)
  ODOO_URL   (def http://localhost:8019)
  ODOO_DB    ODOO_LOGIN  ODOO_PASSWORD
  ATT_DATE_FROM  ATT_DATE_TO     (YYYY-MM-DD, opcionales; filtran por fecha)
  ATT_DNIS       (opcional, lista separada por comas; si se omite, todos los
                  empleados activos con DNI)
  MDB_LOCAL      (opcional: ruta a un .mdb ya local; si se da, no usa smbclient)

Uso:  python3 backfill_att_mdb.py
"""
import os
import sys
import subprocess
import tempfile
import xmlrpc.client
from datetime import datetime, timedelta

import pytz

try:
    from access_parser import AccessParser
except ImportError:
    sys.exit("Falta access-parser. Instálelo:  pip install access-parser")

LIMA = pytz.timezone('America/Lima')
UTC = pytz.UTC


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1) Obtener el .mdb
# ---------------------------------------------------------------------------
def fetch_mdb():
    local = os.environ.get('MDB_LOCAL')
    if local:
        log(f"Usando .mdb local: {local}")
        return local, False
    host = os.environ.get('SMB_HOST', '172.16.64.5')
    share = os.environ.get('SMB_SHARE', 'sistemas')
    path = os.environ.get('SMB_PATH', r'BDRELOJMARCADOR\att2000.mdb')
    user = os.environ.get('SMB_USER')
    pwd = os.environ.get('SMB_PASS', '')
    domain = os.environ.get('SMB_DOMAIN')
    if not user:
        sys.exit("Falta SMB_USER (credencial del recurso \\\\%s\\%s)." % (host, share))
    dest = tempfile.NamedTemporaryFile(prefix='att2000_', suffix='.mdb', delete=False).name
    auth = f"{domain}\\{user}" if domain else user
    cmd = ['smbclient', f'//{host}/{share}', '-U', f'{auth}%{pwd}',
           '-c', f'get "{path}" "{dest}"']
    log(f"Descargando //{host}/{share}/{path} ...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.getsize(dest):
        sys.exit(f"smbclient falló:\n{r.stdout}\n{r.stderr}")
    log(f"Descargado a {dest} ({os.path.getsize(dest)} bytes)")
    return dest, True


# ---------------------------------------------------------------------------
# 2) Leer el .mdb
# ---------------------------------------------------------------------------
def read_punches(mdb_path):
    db = AccessParser(mdb_path)
    userinfo = db.parse_table('USERINFO')
    checkinout = db.parse_table('CHECKINOUT')

    # USERID -> Badgenumber (DNI)
    badge_by_userid = {}
    uids = userinfo.get('USERID', [])
    badges = userinfo.get('Badgenumber', [])
    for uid, badge in zip(uids, badges):
        if uid is None:
            continue
        badge_by_userid[str(uid)] = str(badge).strip() if badge is not None else ''

    rows = []
    cu = checkinout.get('USERID', [])
    ct = checkinout.get('CHECKTIME', [])
    for uid, t in zip(cu, ct):
        if uid is None or t is None:
            continue
        dni = badge_by_userid.get(str(uid))
        if not dni:
            continue
        if not isinstance(t, datetime):
            # access_parser suele devolver datetime; si no, intentar parsear
            try:
                t = datetime.fromisoformat(str(t))
            except Exception:
                continue
        rows.append((dni, t))
    log(f"Leídas {len(rows)} marcaciones con DNI desde el .mdb "
        f"({len(badge_by_userid)} usuarios en USERINFO)")
    return rows


# ---------------------------------------------------------------------------
# 3) Odoo XML-RPC
# ---------------------------------------------------------------------------
def odoo_connect():
    url = os.environ.get('ODOO_URL', 'http://localhost:8019')
    db = os.environ.get('ODOO_DB')
    login = os.environ.get('ODOO_LOGIN')
    pwd = os.environ.get('ODOO_PASSWORD')
    if not (db and login and pwd):
        sys.exit("Faltan ODOO_DB / ODOO_LOGIN / ODOO_PASSWORD.")
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, login, pwd, {})
    if not uid:
        sys.exit("Autenticación Odoo fallida (revise db/login/password).")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    log(f"Conectado a Odoo {url} (db={db}, uid={uid})")
    return models, db, uid, pwd


def emp_by_dni(models, db, uid, pwd, only_dnis):
    domain = [('identification_id', '!=', False)]
    emps = models.execute_kw(db, uid, pwd, 'hr.employee', 'search_read',
                             [domain], {'fields': ['id', 'identification_id', 'name']})
    mapping = {}
    for e in emps:
        dni = (e['identification_id'] or '').strip()
        if not dni:
            continue
        mapping[dni] = e['id']
        mapping[dni.lstrip('0')] = e['id']
    if only_dnis:
        keep = set()
        for d in only_dnis:
            keep.add(d.strip()); keep.add(d.strip().lstrip('0'))
        mapping = {k: v for k, v in mapping.items() if k in keep}
    log(f"Empleados mapeados por DNI: {len(set(mapping.values()))}")
    return mapping


# ---------------------------------------------------------------------------
# 4) Backfill
# ---------------------------------------------------------------------------
def main():
    date_from = os.environ.get('ATT_DATE_FROM')
    date_to = os.environ.get('ATT_DATE_TO')
    df = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
    dt = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
    only = [x for x in os.environ.get('ATT_DNIS', '').split(',') if x.strip()] or None

    mdb_path, tmp = fetch_mdb()
    try:
        rows = read_punches(mdb_path)
    finally:
        if tmp:
            try:
                os.unlink(mdb_path)
            except OSError:
                pass

    models, db, uid, pwd = odoo_connect()
    dni2emp = emp_by_dni(models, db, uid, pwd, only)

    # Agrupar por (emp_id, día local)
    groups = {}
    for dni, t in rows:
        emp_id = dni2emp.get(dni) or dni2emp.get(dni.lstrip('0'))
        if not emp_id:
            continue
        local_dt = LIMA.localize(t) if t.tzinfo is None else t.astimezone(LIMA)
        d = local_dt.date()
        if df and d < df:
            continue
        if dt and d > dt:
            continue
        utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
        groups.setdefault((emp_id, d), []).append(utc_dt)

    log(f"Días-empleado a procesar: {len(groups)}")
    created = skipped = errors = 0
    for (emp_id, d), times in sorted(groups.items(), key=lambda k: (k[0][0], k[0][1])):
        times.sort()
        check_in = times[0]
        check_out = times[-1] if (len(times) > 1 and times[-1] > times[0]) else times[0]
        ds = LIMA.localize(datetime(d.year, d.month, d.day)).astimezone(UTC).replace(tzinfo=None)
        de = (LIMA.localize(datetime(d.year, d.month, d.day)) + timedelta(days=1)).astimezone(UTC).replace(tzinfo=None)
        fmt = '%Y-%m-%d %H:%M:%S'
        existing = models.execute_kw(db, uid, pwd, 'hr.attendance', 'search',
                                     [[('employee_id', '=', emp_id),
                                       ('check_in', '>=', ds.strftime(fmt)),
                                       ('check_in', '<', de.strftime(fmt))]], {'limit': 1})
        if existing:
            skipped += 1
            continue
        try:
            models.execute_kw(db, uid, pwd, 'hr.attendance', 'create',
                              [{'employee_id': emp_id,
                                'check_in': check_in.strftime(fmt),
                                'check_out': check_out.strftime(fmt)}])
            created += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            log(f"  ! error emp {emp_id} {d}: {e}")

    log(f"\nRESUMEN: creadas={created}  ya_existían={skipped}  errores={errors}")


if __name__ == '__main__':
    main()
