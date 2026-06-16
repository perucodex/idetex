# Ejecutar en: odoo shell -d odoo_idtx  (expone 'env'). Lee el JSON liviano.
import json
import pytz
from datetime import datetime, timedelta

LIMA = pytz.timezone('America/Lima'); UTC = pytz.UTC
fmt = '%Y-%m-%d %H:%M:%S'
data = json.load(open('/tmp/att_grouped.json'))
print("Grupos en JSON: %s" % len(data), flush=True)

emps = env['hr.employee'].search([('active', '=', True), ('identification_id', '!=', False)])
dni2emp = {}
for e in emps:
    d = (e.identification_id or '').strip()
    if d:
        dni2emp[d] = e.id
        dni2emp[d.lstrip('0')] = e.id
emp_ids = list(set(dni2emp.values()))
print("Empleados activos con DNI en Odoo: %s" % len(emp_ids), flush=True)

Att = env['hr.attendance']
existing = set()
if emp_ids:
    ex = Att.search([('employee_id', 'in', emp_ids), ('check_in', '>=', '2026-01-01 00:00:00')])
    for a in ex:
        ld = UTC.localize(a.check_in).astimezone(LIMA).date().isoformat()
        existing.add((a.employee_id.id, ld))
print("Asistencias ya existentes en rango: %s" % len(existing), flush=True)

vals = []
skipped = unmatched = 0
for dni, ds, ci, co in data:
    emp_id = dni2emp.get(dni) or dni2emp.get(dni.lstrip('0'))
    if not emp_id:
        unmatched += 1
        continue
    if (emp_id, ds) in existing:
        skipped += 1
        continue
    if ci == co:  # una sola marca ese día: checkout nominal +1 min
        co = (datetime.strptime(ci, fmt) + timedelta(minutes=1)).strftime(fmt)
    vals.append({'employee_id': emp_id, 'check_in': ci, 'check_out': co})
print("A crear: %s | saltadas(ya existen): %s | grupos de DNIs no activos/no en Odoo: %s" % (
    len(vals), skipped, unmatched), flush=True)

created = errors = 0
def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

i = 0
for ch in chunks(vals, 200):
    try:
        Att.create(ch)
        created += len(ch)
    except Exception:
        for v in ch:
            try:
                Att.create(v)
                created += 1
            except Exception as e:
                errors += 1
                if errors <= 15:
                    print("  ! emp %s %s: %s" % (v['employee_id'], v['check_in'], str(e)[:140]), flush=True)
    i += 1
    if i % 20 == 0:
        env.cr.commit()
        print("  ...creadas: %s" % created, flush=True)

env.cr.commit()
print("RESUMEN: creadas=%s  saltadas=%s  no_match=%s  errores=%s" % (
    created, skipped, unmatched, errors), flush=True)
