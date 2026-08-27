#!/usr/bin/env bash
# Valida sintaxis de archivos del proyecto. Uso: check-syntax.sh <archivo>...
#   .py                 -> ast.parse con el python del venv de Odoo (no genera .pyc)
#   .xml                -> xmllint --noout
#   ir.model.access.csv -> todas las filas con el mismo nº de columnas que la cabecera
# Sale con 2 si hay errores (Claude Code reenvía stderr al modelo), 0 si todo está bien.

PY="/home/jpc/odoo/odoo19/odoo-venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

status=0
for f in "$@"; do
    [ -f "$f" ] || continue
    case "$f" in
        *.py)
            if ! out=$("$PY" -c 'import ast,sys
with open(sys.argv[1], encoding="utf-8") as fh:
    ast.parse(fh.read(), sys.argv[1])' "$f" 2>&1); then
                echo "❌ Python: $f" >&2
                echo "$out" | tail -n 6 >&2
                status=2
            fi
            ;;
        *.xml)
            if ! out=$(xmllint --noout "$f" 2>&1); then
                echo "❌ XML: $f" >&2
                echo "$out" | head -n 8 >&2
                status=2
            fi
            ;;
        *ir.model.access.csv)
            if ! out=$("$PY" -c 'import csv,sys
path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as fh:
    rows = list(csv.reader(fh))
if not rows:
    sys.exit(0)
n = len(rows[0])
bad = [(i + 1, len(r)) for i, r in enumerate(rows[1:], 1) if r and len(r) != n]
for line, cols in bad:
    print(f"{path}:{line}: {cols} columnas, la cabecera tiene {n}")
sys.exit(1 if bad else 0)' "$f" 2>&1); then
                echo "❌ CSV: $f" >&2
                echo "$out" | head -n 8 >&2
                status=2
            fi
            ;;
    esac
done
exit $status
