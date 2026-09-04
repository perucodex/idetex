# -*- coding: utf-8 -*-
"""Diagnostico (SOLO LECTURA) de fases repetidas en rutas y fichas tecnicas.

NO modifica nada. Solo reporta para que el usuario decida que limpiar.

Distingue dos casos:
  * CONSECUTIVAS: la misma operacion aparece varias veces SEGUIDAS en la ruta
    (ej. CEPILLADO; CEPILLADO; CEPILLADO). Es el patron tipico de un duplicado
    espurio (lo que se ve en la captura).
  * NO CONSECUTIVAS: la misma operacion aparece repetida pero en etapas
    separadas. Puede ser LEGITIMO (una fase que se hace dos veces a proposito),
    asi que solo se informa para revision manual.

Uso con odoo shell:
    ./odoo-bin shell -d <BD> -c <odoo.conf>
    >>> exec(open('extra-addons/idetex/idtx_product_development/scripts/detect_duplicate_route_phases.py').read())

Tambien se puede pegar el cuerpo en una Accion de Servidor (model=mrp.base.process,
estado=code); ahi `env` ya existe.
"""

# `env` lo provee odoo shell / la accion de servidor.
try:
    env  # noqa: F821
except NameError:  # pragma: no cover - solo para edicion estatica
    raise SystemExit('Este script debe ejecutarse dentro de `odoo shell` o una accion de servidor.')


def _ops_in_order(lines):
    """Lista de operaciones en orden de ruta (ignora lineas sin operacion)."""
    ordered = lines.sorted(key=lambda l: (l.sequence, l.id))
    return [l.operation_id for l in ordered if l.operation_id]


def _consecutive_runs(ops):
    """Tramos de la misma operacion repetida SEGUIDA. Devuelve [(op, n), ...]
    con n >= 2."""
    runs = []
    prev = None
    count = 0
    for op in ops:
        if op == prev:
            count += 1
        else:
            if count >= 2:
                runs.append((prev, count))
            prev = op
            count = 1
    if count >= 2:
        runs.append((prev, count))
    return runs


def _non_consecutive_repeats(ops):
    """Operaciones que aparecen >1 vez en total pero NO de forma consecutiva.
    Devuelve [(op, total), ...]."""
    from collections import Counter
    totals = Counter(ops)
    consecutive_ops = {op for op, _ in _consecutive_runs(ops)}
    out = []
    for op, total in totals.items():
        if total > 1 and op not in consecutive_ops:
            out.append((op, total))
    return out


def _fmt(op):
    return '%s [id=%s]' % (op.name or '?', op.id)


print('=' * 80)
print('DIAGNOSTICO DE FASES REPETIDAS  (solo lectura, no modifica nada)')
print('=' * 80)

# ---------------------------------------------------------------------------
# 1) Rutas base (mrp.base.process)
# ---------------------------------------------------------------------------
Base = env['mrp.base.process']
bases = Base.search([])
sospechosas = []   # consecutivas
revisar = []       # no consecutivas

for bp in bases:
    ops = _ops_in_order(bp.process_ids)
    runs = _consecutive_runs(ops)
    rep = _non_consecutive_repeats(ops)
    if runs:
        sospechosas.append((bp, runs))
    if rep:
        revisar.append((bp, rep))

print('\n### RUTAS con fases CONSECUTIVAS repetidas (PROBABLE DUPLICADO) ###')
print('Total: %s rutas\n' % len(sospechosas))
for bp, runs in sorted(sospechosas, key=lambda t: -t[0].product_count):
    print('- Ruta "%s" (id=%s, productos=%s)' % (bp.name, bp.id, bp.product_count))
    for op, n in runs:
        print('      x%s seguidas: %s' % (n, _fmt(op)))

print('\n### RUTAS con repeticiones NO consecutivas (REVISAR, puede ser valido) ###')
print('Total: %s rutas\n' % len(revisar))
for bp, rep in sorted(revisar, key=lambda t: -t[0].product_count):
    print('- Ruta "%s" (id=%s, productos=%s)' % (bp.name, bp.id, bp.product_count))
    for op, total in rep:
        print('      x%s en total: %s' % (total, _fmt(op)))

# ---------------------------------------------------------------------------
# 2) Fichas tecnicas (technical.sheet) — el sync por articulo exporta SUS
#    route_line_ids al ProCod compartido, asi que una ficha sucia contamina
#    la ruta de todos los productos que la comparten.
# ---------------------------------------------------------------------------
Sheet = env['technical.sheet']
sheets = Sheet.search([])
sheet_susp = []
for sheet in sheets:
    ops = _ops_in_order(sheet.route_line_ids)
    runs = _consecutive_runs(ops)
    if runs:
        sheet_susp.append((sheet, runs))

print('\n### FICHAS TECNICAS con fases CONSECUTIVAS repetidas ###')
print('Total: %s fichas\n' % len(sheet_susp))
for sheet, runs in sheet_susp:
    prod = sheet.product_id.display_name or sheet.product_code or '?'
    print('- Ficha id=%s producto=%s (analisis=%s)' % (
        sheet.id, prod, sheet.analysis_id.name or '-'))
    for op, n in runs:
        print('      x%s seguidas: %s' % (n, _fmt(op)))

print('\n' + '=' * 80)
print('RESUMEN: %s rutas sospechosas (consecutivas), %s a revisar, %s fichas sospechosas' % (
    len(sospechosas), len(revisar), len(sheet_susp)))
print('Recuerda: el cron horario reescribe las rutas desde TEXPLUS (PROLIN).')
print('Para una correccion duradera hay que limpiar PROLIN en TEXPLUS y/o la')
print('ficha tecnica que contamina, no solo las lineas en Odoo.')
print('=' * 80)
