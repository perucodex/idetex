# idtx_stock_request – Requerimientos de almacén

Port del módulo OCA [`stock_request`](https://github.com/OCA/stock-logistics-request)
(ForgeFlow / Creu Blanca, rama 19.0, commit `72e0550`) renombrado a `idtx_stock_request`
y adaptado para IDETEX. Licencia LGPL-3; se conservan los avisos de copyright originales.

## Qué hace

Un usuario (sin permisos de Inventario) crea un **Requerimiento de almacén** con uno o
varios productos, cantidad y ubicación destino. Al **Confirmar**:

1. Si eligió una **ruta** (p. ej. *Elegir componentes*), se ejecuta el aprovisionamiento
   por esa ruta (comportamiento OCA).
2. Si **no** eligió ruta y el destino **no** es *Existencias* del almacén, se crea un
   **traslado interno directo** Existencias → destino, se confirma y se reserva: almacén
   lo ve en estado **Listo** (Inventario › Traslados internos / Código de barras).
   No se disparan las rutas Comprar/Fabricar del producto.
3. Si el destino es *Existencias* del almacén (el origen del traslado) y no hay regla de
   traslado ni ruta elegida, la confirmación **falla con un mensaje claro**: en Odoo 19 la
   ruta Comprar sin proveedor no crea nada ni avisa, y el requerimiento quedaría en el aire.
   Con el modo de traslado directo desactivado se mantiene el comportamiento OCA (reponer
   el almacén por rutas).

**Destino por defecto.** Con traslado directo activo, Existencias nunca se propone. Cada almacén
puede definir en Inventario › Configuración › Almacenes › *Requerimientos de almacén* la
ubicación que se propone al solicitante (p. ej. Preproducción); si está vacía, debe elegirla.

**Un traslado por requerimiento.** Al confirmar, el requerimiento recibe una referencia de stock
con su número y todas sus líneas se lanzan juntas, así que caen en el mismo traslado (por
rutas o directo). Sin esa referencia Odoo 19 abría un traslado por línea, porque solo agrupa
movimientos en un traslado existente cuando comparten referencias. Requerimientos distintos
nunca comparten traslado.

El traslado lleva como origen el número del requerimiento (`REQ/xxxxx`), como contacto al
solicitante y las observaciones del requerimiento en las notas. Al validar el traslado la
solicitud pasa a **Hecho** y el solicitante recibe un mensaje en el chatter.

## Cambios respecto a OCA

- Traslado interno directo (ajuste por compañía *Crear traslado interno cuando no se
  elige ruta*, activado por defecto).
- Destino por defecto por almacén y rechazo del destino Existencias sin regla de traslado.
- Un solo traslado por requerimiento (referencia de stock propia + lanzamiento en lote).
- Botón **Imprimir** en el requerimiento: PDF «Requerimiento de productos» con el formato papel
  (logo, ÁREA = departamento del solicitante o ubicación destino, SOLICITANTE, FECHA, N° BOLETA =
  número REQ, MOTIVO = observaciones, tabla ITEM/CANTIDAD/UND/DESCRIPCION/Ult Lote Cocina rellenada
  hasta 30 filas, firmas V°B° Jefe de área / Producción / Almacén). Plantilla
  `reports/report_stock_request_order.xml`, textos en español fijos.
- Requerimientos (varios productos por documento) activados por defecto.
- Solicitante y **Observaciones** visibles en el requerimiento; filtro *Mis requerimientos*.
- Menú *Requerimientos de almacén* dentro de Inventario › Operaciones para almacén.
- Ajustes limpiados: se quitaron los módulos OCA opcionales no disponibles
  (`stock_request_purchase/mrp/kanban/analytic/submit`).
- Secuencias `REQ/` (requerimiento) y `REQL/` (línea).
- Solo traducción `es_PE`.

## Grupos

- **Usuario de requerimientos**: crea y ve sus propios requerimientos.
- **Administrador de requerimientos**: ve y gestiona todos; implica Usuario de Inventario
  (es el grupo para el personal de almacén).

## Pruebas

```bash
odoo-venv/bin/odoo -c .odoorc -d <db> --no-http -i idtx_stock_request --test-enable --test-tags /idtx_stock_request --stop-after-init
```
