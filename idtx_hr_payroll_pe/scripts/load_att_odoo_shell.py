# Ejecutar en: odoo shell -d odoo_idtx  (expone 'env'). Re-importa SESIONES.
# Borra las asistencias del rango (empleados activos) y crea las nuevas sesiones.
import json
from datetime import datetime, timedelta

fmt = '%Y-%m-%d %H:%M:%S'
data = json.load(open('/tmp/att_grouped.json'))
print("Sesiones en JSON: %s" % len(data), flush=True)

emps = env['hr.employee'].search([('active', '=', True), ('identification_id', '!=', False)])
dni2emp = {}
for e in emps:
    d = (e.identification_id or '').strip()
    if d:
        dni2emp[d] = e.id
        dni2emp[d.lstrip('0')] = e.id
emp_ids = list(set(dni2emp.values()))
print("Empleados activos con DNI: %s" % len(emp_ids), flush=True)

# Borrar asistencias previas del rango (re-importación limpia)
Att = env['hr.attendance']
old = Att.search([('employee_id', 'in', emp_ids), ('check_in', '>=', '2026-01-01 00:00:00')])
print("Borrando asistencias previas en el rango: %s" % len(old), flush=True)
old.unlink()

# Construir vals de sesiones
vals_list = []
unmatched = 0
for dni, ci, co in data:
    emp_id = dni2emp.get(dni) or dni2emp.get(dni.lstrip('0'))
    if not emp_id:
        unmatched += 1
        continue
    if ci == co:  # sesión de una sola marca: salida nominal +1 min
        co = (datetime.strptime(ci, fmt) + timedelta(minutes=1)).strftime(fmt)
    vals_list.append({'employee_id': emp_id, 'check_in': ci, 'check_out': co})
print("A crear: %s | sesiones de DNIs no activos: %s" % (len(vals_list), unmatched), flush=True)

created = errors = 0
def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

for ch in chunks(vals_list, 200):
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
                    print("  ! %s %s: %s" % (v['employee_id'], v['check_in'], str(e)[:140]), flush=True)
env.cr.commit()
print("RESUMEN: creadas=%s no_match=%s errores=%s" % (created, unmatched, errors), flush=True)
