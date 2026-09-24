# Backlog — funcionalidades para después de la implementación

Ítems que se pidieron, se prototiparon o se discutieron y quedaron **fuera del alcance
congelado** de la implementación Odoo 19 (Big Bang 27-nov-2026). Se retoman después del
go-live + hypercare. Cada ítem dice qué se quería, qué quedó decidido, qué falta decidir
y dónde está el material guardado.

## 1. Aviso de capacidad de teñido en el pedido de venta

**Pedido (JP, 24-sep-2026).** Al ingresar la cantidad de una línea en el pedido de venta,
verificar contra las capacidades de las teñidoras (mínimos y máximos de carga) que la
cantidad cuadre en alguna máquina; si no cuadra, mostrar una advertencia en la parte
superior del pedido. Fuente: Excel "Tablas Maestras de Capacidades para Ventas y PCP - V2"
(4 hojas = bandas de gramaje <160 / 160–200 / 200–300 / ≥300 gr/m²; por máquina: nivel
T1–T5, capacidad nominal, códigos TEXPLUS, cuerdas, rollos y **kg crudo** mín/máx, % de
carga, observaciones; rollo = 20 kg acabado / 22.5 kg crudo).

**Decidido.** Las capacidades NO van en un modelo nuevo: se cargan en `maintenance.equipment`
(pestaña Datos de teñido) como datos de la máquina (nivel, nominal, cuerdas) más una fila
por banda de gramaje (rollos y kg crudo mín/máx, %, observaciones). La banda del artículo
sale de la densidad del análisis (`product.analysis.density`). Solo aplica al pedido
(`is_quote = False`), a líneas de tejido cuya ruta tenga fase de teñido.

**Pendiente de decidir (motivo del retiro).**
- Si la cantidad del pedido es kg **acabado** (convertir ×22.5/20 a crudo) o kg **crudo**
  (comparar directo). Con 100 kg del cuello de 300 gr/m², acabado → 112.5 crudo cuadra
  justo en la MCS 150; crudo → cae en el hueco 90–112.5 y debería avisar.
- La regla de "cuadra": el prototipo aceptaba repartir en varias cargas de máquinas
  distintas y casi nunca avisaba (todo se arma con las Fong's de 22.5 kg). Propuesta:
  cuadra si UNA máquina la cubre con n cargas completas (n·mín ≤ crudo ≤ n·máx); así los
  pedidos grandes pasan y las cantidades chicas raras avisan. Alternativa estricta: solo
  una carga.
- Datos maestros: MAQ 20 y MAQ 32 son MCS en Odoo pero Brazzoli 1250/400 en el Excel;
  MAQ 35 está duplicada (ids 13 y 16); MAQ 6 FONG no tiene código en el Excel (usa Fong's
  14–17); las teñidoras 14–19 y 36 del Excel no existen en Odoo.

**Variables que el chequeo real debe considerar (JP, 24-sep-2026).** El tema es más
complejo que comparar la cantidad contra los rangos de la tabla; es un cálculo de
**planeamiento** sobre el conjunto:
- **Merma del producto**: la cantidad a cargar en la teñidora es la cantidad pedida más la
  merma del artículo (no un factor fijo 22.5/20), y esa merma varía por producto/proceso.
- **Cuerdas**: la carga debe repartirse en el número de cuerdas de la máquina sin
  desbalancearla; una carga desbalanceada produce **diferencias de tonalidad** entre
  cuerdas. La cantidad debe cuadrar por cuerda, no solo en el total de la máquina.
- **Complementos que se tiñen juntos**: el producto y sus complementos (cuellos, puños,
  ribs del mismo color) van en la misma partida, así que el cálculo se hace **por el todo**
  (tela + complementos), no línea por línea.
- **Cola de la máquina**: cuántas partidas tiene programadas la teñidora candidata, para
  calcular los **días de entrega** que se pueden ofrecer al cliente; si la máquina está
  muy cargada la entrega se retrasa aunque la cantidad cuadre.
- Todo esto lo maneja Planeamiento; el aviso en Ventas sería la salida de ese cálculo, no
  una regla propia. Se conecta con la programación de partidas desde OPs/opciones
  (máquina de la partida y relación de baño), también en backlog.

**Material guardado (dev, `/home/jpc/odoo/odoo19/scripts/dye_capacities/`).**
- `parked/idtx_mrp_shop_dye_capacity.patch` + `parked/sale_order.py` +
  `parked/sale_order_views.xml`: prototipo completo en `idtx_mrp_shop` (modelo de
  capacidad por banda, campos en el equipo, cómputo `sale.order.dye_capacity_warning`
  con motor de intervalos, vistas, accesos). Se aplica con `git apply` y se copian los dos
  archivos nuevos.
- `import_dye_capacities.py`: carga del Excel a los equipos (odoo shell < script),
  re-ejecutable; mapea códigos TEXPLUS → "TEÑIDORA MAQ N" (Thies TTP40N = MAQ N), con
  opción de crear las máquinas faltantes.
- Factor crudo/acabado previsto como parámetro `idtx_mrp_shop.dye_raw_kg_factor` (1.125).

**Estimación al retomar.** Ya no es un aviso de ~1 día: con merma, cuerdas, complementos
en conjunto y cola de máquina es un módulo de **programación de partidas para PCP**, a
dimensionar con Planeamiento después del go-live. El prototipo guardado sirve como base de
datos de capacidades (equipo + banda) y como punto de partida del cálculo. Retirado del
código y de la base dev el 24-sep-2026 (sin rastro en `idtx_mrp_shop`).
