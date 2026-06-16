# Ejecutar en: odoo shell -d odoo_idtx  (DESPUÉS de -u, con los 3 calendarios creados).
# Asigna a cada trabajador su horario de trabajo según el turno detectado.
day = env.ref('idtx_hr_payroll_pe.calendar_pe_dia_07_16')
rot = env.ref('idtx_hr_payroll_pe.calendar_pe_rotativo')          # wt0=día,  wt1=noche
inv = env.ref('idtx_hr_payroll_pe.calendar_pe_rotativo_inv')      # wt0=noche, wt1=día
MAP = {
    '47246417': day, '42532375': day, '75974652': day, '73989902': day,  # día fijo
    '70880259': inv, '10460597': inv, '74542600': inv, '40496169': inv,  # rotan, noche en wt0
    '74200522': rot, '42331331': rot,                                    # rotan, noche en wt1 (mixtos)
}
for dni, cal in MAP.items():
    e = env['hr.employee'].search([('identification_id', '=', dni)], limit=1)
    if not e:
        print("  ! no existe empleado DNI", dni, flush=True); continue
    v = e.version_id
    if not v:
        print("  ! sin contrato:", e.name, flush=True); continue
    v.resource_calendar_id = cal.id
    print("  %-24s -> %s" % (e.name[:24], cal.name), flush=True)
env.cr.commit()
print("Asignación de calendarios completada.", flush=True)
