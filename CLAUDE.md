# idetex – addons Odoo 19 (IDETEX / Codex Development)

Responde siempre en español. Este repo contiene ~55 módulos con prefijo `idtx_` para una
empresa textil peruana (producción, laboratorio, planilla PE, facturación electrónica, POS).

## Entorno de desarrollo

- Odoo **19.0** (community + enterprise), Python 3.10, venv: `~/odoo/odoo19/odoo-venv`
- Config: `~/odoo/odoo19/.odoorc` · puerto **http://127.0.0.1:8019** · `max_cron_threads = 0`
- Base de datos de desarrollo: **`odoo19`** (42 de los 52 módulos idtx instalados). Las BDs
  `idetex`, `prueba`, `prueba_idtx` mencionadas en versiones previas de este archivo ya no
  existen en este servidor Postgres (solo quedan `odoo19` y `postgres`).
- El servidor Odoo corre en la **terminal del usuario** (`odoo -c .odoorc`), sin `logfile`:
  el log sale por stdout ahí. Yo no lo veo directamente; para depurar uso un segundo
  proceso con `--stop-after-init --no-http` (ver comandos).
- Tras cambiar código **Python** el servidor debe reiniciarse: pedírselo al usuario
  (puede usar `! <comando>` en el prompt). Cambios en XML/CSV/datos requieren `-u` del módulo.
- Esta máquina es solo **dev**; producción es otro servidor (ver memoria).

## Comandos (ejecutar desde `~/odoo/odoo19`)

```bash
ODOO="odoo-venv/bin/odoo -c .odoorc -d odoo19 --no-http"
$ODOO -u <modulo> --stop-after-init                                 # actualizar módulo
$ODOO -i <modulo> --stop-after-init                                 # instalar módulo
$ODOO -u <modulo> --test-enable --test-tags /<modulo> --stop-after-init   # tests del módulo
odoo-venv/bin/odoo shell -c .odoorc -d odoo19 --no-http          # shell interactivo
$ODOO -u <modulo> --stop-after-init 2>&1 | grep -E "WARNING|ERROR|CRITICAL|Traceback"
```

Después de cada `-u`, revisar warnings/errores y reportarlos al usuario. Una actualización
con `Traceback` NO está terminada aunque el proceso termine.

## Estructura y convenciones de módulos

```
idtx_<nombre>/
  __manifest__.py   # author "Codex Development", website https://www.perucodex.com,
                    # license LGPL-3, version "19.0.x.y.z" (subir el patch al cambiar)
  models/           # un archivo por modelo: <modelo_con_guiones_bajos>.py
  views/            # <modelo>_views.xml, menús en <modulo>_menu.xml
  wizards/          # .py y _views.xml juntos en la misma carpeta
  reports/          # QWeb (report_*.xml) y paperformat
  security/ir.model.access.csv  (+ security.xml si hay grupos/reglas)
  data/             # secuencias, categorías, datos maestros (noupdate="1")
  i18n/es_PE.po
  static/src/       # OWL/JS/SCSS (19 módulos lo tienen)
  controllers/
```

- Nombres técnicos (modelos, campos, xml_id, métodos) en **inglés**; `string=`, labels,
  mensajes de error y ayudas en **español**. Nuevos modelos: `_description` obligatorio.
- Nuevo módulo: copiar `static/description/icon.png` de un módulo existente; registrar
  archivos en `__manifest__.py` en orden (security → data → views → reports → wizards).
- Siempre añadir la fila en `ir.model.access.csv` al crear un modelo (incluidos wizards
  `TransientModel`, que en Odoo 19 no requieren ACL pero los modelos normales sí).
- **No tocar** `idtx_orgatex_old` (legado, no instalado). `idtx_plan_general` fue
  reemplazado por `idtx_plan_general_alpha`. `idtx_sire_sunat` no está instalado en dev.

## Grafo de dependencias (cadena base)

```
idtx_maintenance → idtx_mrp → idtx_product_development → idtx_laboratory → idtx_sale_order
                     ↑              ↑                        ↑
     idtx_mrp_shop, idtx_batch_control, idtx_thread_codigo, idtx_printing, idtx_pos_*, ...
```

~20 módulos dependen (directa o transitivamente) de `idtx_mrp`, `idtx_product_development`
y `idtx_laboratory`. Antes de cambiar un campo/método de esos módulos, buscar sus usos en
todo el repo (`grep -rn "<nombre>" --include=*.py --include=*.xml .`) y actualizar con `-u`
también los dependientes afectados. Para ver dependencias: `grep -A8 depends <mod>/__manifest__.py`.

## Integración TEXPLUS / ORGATEX (SQL Server)

Varios módulos leen/escriben un SQL Server externo (TEXPLUS: FASPRO/MAQFAS/PROCES/PROLIN;
ORGATEX: planta de tintorería) vía `pyodbc` + FreeTDS.

- `.odoorc` tiene `texplus_write_enabled = False`: en dev **nunca** se escribe en TEXPLUS
  (es el mismo servidor SQL que producción). Las lecturas sí funcionan.
- Todo código nuevo que haga INSERT/UPDATE/DELETE externo debe pasar por una guarda de
  escritura. Patrón de referencia: `idtx_orgatex/models/orgatex_connection.py`
  (`_orgatex_write_enabled`, `_orgatex_connect`). No inventar conexiones ad hoc.
- La cadena de conexión necesita `ClientCharset` y `Encryption=off` con FreeTDS; reutilizar
  el mixin/helper existente en vez de copiar strings de conexión.

## Odoo 19 – errores frecuentes a evitar

- Vistas: `<list>` (no `<tree>`), `invisible="expr"` / `readonly="expr"` / `required="expr"`
  (no `attrs`, no `states`). `<form>` con `<sheet>`; botones de estado en `<header>`.
- `@api.depends` debe listar TODOS los campos usados en el compute (incluidos los de
  relaciones: `'line_ids.qty'`). Campos computados almacenados → `store=True` + depends.
- `Many2one`: definir `ondelete` explícito cuando el modelo referenciado se borra con
  frecuencia; `check_company=True` en modelos multi-compañía.
- No usar `sudo()` salvo necesidad justificada; preferir permisos en `ir.model.access.csv`.
- No `search()` sin dominio ni límite en loops; usar `read_group`/`_read_group` o
  `mapped`/`filtered` sobre recordsets.
- `_sql_constraints` → en Odoo 19 usar `models.Constraint` / `models.UniqueIndex`.
- Al heredar vistas, apuntar con `xpath` a campos estables (no a posiciones).

## Datos sensibles

- `~/odoo/odoo19/*.csv` (backups y `adjuntos_huerfanos_odoo_prod_*.csv`) contienen datos
  de producción: no leerlos, copiarlos ni incluirlos en salidas.
- `idtx_hr_payroll_pe*`, `idtx_hr_*`: datos personales de trabajadores. `idtx_l10n_pe_efact`,
  `idtx_sire_sunat`, `idtx_l10n_pe_detraction`: integraciones con SUNAT/OSE. No llamar a
  endpoints de SUNAT ni del OSE desde dev sin que el usuario lo pida explícitamente.
- Credenciales (`db_password`, `admin_passwd`, cadenas SQL Server) nunca en commits ni en
  respuestas.

## Flujo de trabajo esperado

1. Editar `.py` / `.xml` / `.csv` con las herramientas **Edit/Write** (no `sed`/heredoc):
   el hook `PostToolUse` valida la sintaxis al instante. Al terminar el turno, un hook
   `Stop` vuelve a validar todo lo modificado según `git`.
2. Actualizar el módulo con `-u` y revisar warnings/errores.
3. Verificar en el navegador (Chrome, `http://127.0.0.1:8019`, BD `odoo19`) que la
   vista/flujo funciona; revisar consola JS si hay OWL.
4. Si hay lógica de negocio (cálculos, liquidaciones, consumos), añadir/ejecutar tests en
   `<modulo>/tests/` (`TransactionCase`, `@tagged('post_install', '-at_install')`).
5. **No hacer commit** salvo que el usuario lo pida. Mensajes en español, descriptivos
   ("Liquidación de tejido: cálculo de merma por rollo"), nunca genéricos ("Warnings", "Cambios").
6. Al terminar, resumir: qué archivos cambiaron, qué módulo hay que actualizar/reiniciar y
   cómo probarlo.
