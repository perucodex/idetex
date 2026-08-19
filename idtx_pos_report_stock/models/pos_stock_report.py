# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _

class IdtxPosStockReport(models.Model):
    _name = "idtx.pos.stock.report"
    _inherit = "pos.load.mixin"
    _description = "Reporte de Existencias PdV"
    _auto = False
    _table = "idtx_pos_stock_report"
    # Orden por defecto: lo más recientemente cargado primero, NULLS al final.
    # Los rollos sin fecha de carga (vienen de producción/partición y no de
    # Quant Import) caen al final, no rompen la lista.
    _order = "import_date DESC NULLS LAST, lot_name"

    # Campos de Navegación (IDs)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lote', readonly=True)
    roll_id = fields.Many2one('mrp.production.roll', string='Referencia', readonly=True)
    
    # Campos de Búsqueda/Texto (JSONB Logic)
    product_name = fields.Char('Descripción Producto', readonly=True)
    product_code = fields.Char('Código Producto', readonly=True)
    product_label = fields.Char('Producto Detallado', readonly=True)
    lot_name = fields.Char('Número de Lote', readonly=True)
    partida = fields.Char('Partida', readonly=True)
    partida_label = fields.Char('Partida Detallada', readonly=True)
    roll_name = fields.Char('Número de Referencia', readonly=True)

    # Campos de Color (Manejados vía SQL Join en init)
    color_code = fields.Char('Código Color', readonly=True)
    color_name = fields.Char('Nombre Color', readonly=True)
    
    quantity = fields.Float('Stock (Kg)', readonly=True)
    # Atributos físicos del rollo expuestos vía JOIN con mrp.production.roll.
    # 0 significa "sin dato" (rollos cargados antes de que el Excel trajera estas columnas).
    width = fields.Float('Ancho (m)', readonly=True)
    density = fields.Integer('Densidad (g/m²)', readonly=True)
    # Fecha de carga: viene del stock.quant.import.date del import que creó
    # el rollo (vía mrp.production.roll.import_id). NULL para rollos que no
    # vinieron de Quant Import (producción interna, partición). Ese NULL es
    # intencional — el filtro por fecha solo debe afectar rollos cargados.
    import_date = fields.Date('Fecha de carga', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    write_date = fields.Datetime('Última Actualización', readonly=True)

    # Campos de reserva: indican si el rollo está bloqueado por un pedido POS guardado
    is_reserved = fields.Boolean('Bloqueado', readonly=True,
        help='True cuando el rollo está reservado por un pedido POS guardado y no se puede vender.')
    reserved_by_order_id = fields.Many2one('pos.order', string='Reservado por pedido', readonly=True,
        help='Pedido POS que tiene este rollo bloqueado.')

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            'id', 'product_id', 'product_name', 'product_code', 'product_label',
            'lot_id', 'lot_name', 'partida', 'partida_label', 'roll_id', 'roll_name',
            'color_code', 'color_name', 'quantity', 'location_id', 'write_date',
            'is_reserved', 'reserved_by_order_id',   # campos de bloqueo para el POS
            'width', 'density',                       # atributos físicos del rollo
            'import_date',                            # fecha del Quant Import de origen
        ]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _server_date_to_domain(self, domain):
        # Evitar que Odoo inyecte un filtro de 'write_date' para carga incremental si no queremos,
        # pero ahora que lo tenemos en la vista, podemos dejarlo o controlarlo.
        return domain

    def reprint(self):
        """ Lógica de reimpresión movida aquí para evitar modificar módulos externos.

        OJO: el ID de las filas de este reporte es el ID del LOTE (ver init(),
        "lot_id como ID estable"), NO el de stock.quant. Antes se hacía
        stock.quant.browse(self.ids), que funcionaba de casualidad mientras los
        IDs de lote y quant coincidían; tras la recarga de rollos del 2026-07-07
        dejaron de coincidir y toda impresión fallaba con "Registro faltante".
        Ahora el rollo se resuelve por el lote de la fila y el peso se toma de
        la propia fila (stock neto del lote), sin tocar stock.quant.
        """
        import socket
        import ipaddress
        from odoo.exceptions import UserError

        printer_ip = self.env.company.zpl_printer_ip
        if not printer_ip:
            raise UserError("La IP de la impresora no está configurada en la compañía.")

        Roll = self.env['mrp.production.roll']
        for rec in self:
            if not rec.lot_id:
                continue
            # roll_id ya viene resuelto en la vista SQL; el search es solo respaldo
            roll = rec.roll_id or Roll.search([('lot_id', '=', rec.lot_id.id)], limit=1)
            if roll:
                zpl_code = roll.create_zpl(rec.quantity)
                try:
                    ip = str(ipaddress.ip_address(printer_ip.strip()))
                    with socket.create_connection((ip, 9100), timeout=5) as sock:
                        sock.sendall(zpl_code.encode('utf-8'))
                except (socket.error, UnicodeError, ValueError) as e:
                    raise UserError("No se pudo imprimir (verificá IP): %s" % e)

    def action_reubicar(self):
        """ Llama al asistente estándar de Odoo para reubicar quants.

        Igual que en reprint(): el ID de la fila es el del LOTE, por lo que los
        quants reales del rollo se buscan por lote (en ubicaciones internas),
        no por el ID de la fila.
        """
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.mapped('lot_id').ids),
            ('location_id.usage', '=', 'internal'),
        ])
        res = quants.action_stock_quant_relocate()
        res['context'].update({'from_pos_stock_report': True})
        return res

    def action_inventory_adjust(self):
        """
        Abre la vista NATIVA editable de ajustes de inventario
        (`stock.view_stock_quant_tree_inventory_editable`) filtrada al quant
        exacto del rollo seleccionado (lote + ubicación).

        Esta es la misma vista que el cajero ve en
        `Inventario → Operaciones → Ajustes físicos`. Solo aplicamos el
        dominio para que vea UNA fila (la del rollo) y le pasamos defaults
        en context para que si no existe quant aún (rollo scrapeado al 100%)
        el botón 'Nuevo' aparezca precargado.

        Casos de uso típicos:
          - Devolución de una muestra (cliente la regresa) → subir cantidad.
          - Corrección por merma / error de recuento → bajar cantidad.
          - Reingreso completo de un rollo scrapeado → crear quant con 'Nuevo'.
        """
        self.ensure_one()  # un rollo a la vez

        # Resolver la vista nativa una sola vez (xml_id estable del core).
        view = self.env.ref('stock.view_stock_quant_tree_inventory_editable')

        # Defaults para el caso "Nuevo" (si no hubiera quant en la ubicación).
        # Si el quant existe, la vista lo muestra para editar; si no, el
        # botón 'New' aparece con estos campos ya precargados.
        ctx = {
            'default_product_id': self.product_id.id,
            'default_lot_id': self.lot_id.id,
            'default_location_id': self.location_id.id,
            # Activa los botones de Apply/Apply All en el header de la vista.
            'inventory_mode': True,
            # Bandera propia: si en el futuro queremos redirigir post-apply.
            'from_pos_stock_report': True,
        }

        return {
            'name': _('Ajustar stock - %s') % (self.lot_name or self.product_code or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'list',
            'views': [(view.id, 'list')],
            # Filtro estricto: el cajero solo ve el quant del rollo elegido.
            'domain': [
                ('lot_id', '=', self.lot_id.id),
                ('location_id', '=', self.location_id.id),
            ],
            'context': ctx,
            'target': 'current',
        }

    def action_scrap_muestra(self):
        """
        Abre el wizard NATIVO de Odoo `stock.scrap` (vista
        `stock.stock_scrap_form_view2`) precargado con:
          - producto y lote del rollo seleccionado
          - ubicación origen = la actual del rollo
          - tag 'Muestra' preseleccionado (vía xml_id estable)

        El cajero solo ingresa la cantidad (kg que entrega como muestra) y
        confirma. Es 100% el wizard nativo del core — solo le pasamos
        defaults por contexto.

        Soporta selección múltiple: por convención, el wizard nativo
        stock.scrap es por-producto, así que abrimos uno por cada fila
        seleccionada en secuencia. Si se selecciona una sola, va directo.

        ──────────────────────────────────────────────────────────────────
        PENDIENTE DE CONFIGURACIÓN (no es un bug del código):
          La compañía IDETEX S.A.C. (id=1) NO tiene una ubicación tipo
          'inventory' llamada 'Scrap' dedicada. Solo tiene 'Inventory
          adjustment' (id=11). Por eso, cuando se desecha un rollo desde
          este botón, el movimiento queda con destino 'Inventory adjustment'
          en lugar de una ubicación 'Scrap' propia.

          Consecuencia: en el kardex se mezclan los desechos (scrap) con
          los ajustes manuales en el mismo bucket. Para reportar muestras
          hoy hay que filtrar por `scrap_id IS NOT NULL` o por
          `origin LIKE 'Muestra:%%'` en stock.move, no por ubicación.

          Las otras 8 compañías del grupo (AGRO PIMA, FULL PIMA, etc.)
          sí tienen su ubicación 'Scrap' separada — IDETEX se quedó atrás
          en esa configuración.

          RECOMENDACIÓN: crear en Inventario → Configuración → Ubicaciones
          un registro:
              - name           = 'Scrap'
              - usage          = 'inventory'
              - company_id     = 1 (IDETEX S.A.C.)
              - location_id    = warehouse view de IDETEX
          Después de crearla, el método nativo _compute_scrap_location_id
          de stock.scrap la elegirá automáticamente (toma el MIN(id) con
          usage='inventory' por compañía → al haber dos, conviene que la
          'Scrap' tenga id menor, o bien forzar `default_scrap_location_id`
          aquí en este método).

          Reportado por sistemas@idetex.com.pe el 2026-06-25 durante la
          validación post-migración del flujo custom de muestras al nativo
          stock.scrap.
        ──────────────────────────────────────────────────────────────────
        """
        self.ensure_one()  # por ahora limitamos a un rollo a la vez

        # Buscar el tag 'Muestra' por xml_id estable. Si por alguna razón no
        # existiera (ej. data XML no cargada todavía), graceful fallback: el
        # wizard se abre sin tag y el cajero lo selecciona a mano.
        tag = self.env.ref(
            'idtx_pos_report_stock.scrap_reason_tag_muestra',
            raise_if_not_found=False,
        )

        # Construir el contexto con defaults del wizard nativo.
        # Las claves 'default_<field>' son la forma estándar de precargar
        # campos al abrir un form en target='new'.
        ctx = {
            'default_product_id': self.product_id.id,
            'default_lot_id': self.lot_id.id,
            'default_location_id': self.location_id.id,
            # Origin descriptivo para auditoría (aparece en el wizard)
            'default_origin': _('Muestra: %(rollo)s — lote %(lote)s') % {
                'rollo': self.roll_name or self.product_code or '',
                'lote': self.lot_name or '',
            },
        }
        if tag:
            # Many2many: se pasa con sintaxis [(6, 0, [ids])]
            ctx['default_scrap_reason_tag_ids'] = [(6, 0, [tag.id])]

        # Reutilizamos la VISTA NATIVA del wizard de scrap. No replicamos UI.
        return {
            'name': _('Desechar como muestra'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'view_mode': 'form',
            'view_id': self.env.ref('stock.stock_scrap_form_view2').id,
            'target': 'new',
            'context': ctx,
        }

    def action_screen_barcode(self):
        wizard = self.env['pos.stock.barcode.wizard'].create({
            'report_ids': [(6, 0, self.ids)]
        })
        return {
            'name': 'Screen Bar Code',
            'type': 'ir.actions.act_window',
            'res_model': 'pos.stock.barcode.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sub.lot_id AS id,                   -- lot_id como ID estable: un lote = una fila, sin importar cuántos quants existan
                    sub.product_id AS product_id,
                    pt.default_code AS product_code,
                    '[' || pt.default_code || '] ' || COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') AS product_label,
                    COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') AS product_name,
                    sub.lot_id AS lot_id,
                    l.name AS lot_name,
                    CASE
                        WHEN LENGTH(l.name) > 4 THEN LEFT(l.name, LENGTH(l.name) - 4)
                        ELSE l.name
                    END AS partida,
                    '[' || pt.default_code || '] ' || COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') || ' | ' || COALESCE(ldl.color_name, l.color_description, 'S/C') || ' | P:' ||
                    CASE
                        WHEN LENGTH(l.name) > 4 THEN LEFT(l.name, LENGTH(l.name) - 4)
                        ELSE l.name
                    END AS partida_label,
                    ldl.color_code AS color_code,
                    -- Color mostrado: si el lote tiene receta -> nombre de la receta;
                    -- si no (rollo tejido con hilo de color) -> descripción libre del lote.
                    COALESCE(ldl.color_name, l.color_description) AS color_name,
                    r.id AS roll_id,
                    r.name AS roll_name,
                    sub.quantity AS quantity,           -- stock NETO (suma de todos los quants del lote en ubicaciones internas)
                    -- Atributos físicos del rollo: COALESCE para que rollos huérfanos (sin r.id) no muestren NULL
                    COALESCE(r.width, 0) AS width,
                    COALESCE(r.density, 0) AS density,
                    -- Fecha del Quant Import que cargó este rollo (NULL si vino
                    -- de otra vía: producción, partición). NULL es intencional
                    -- para que el filtro por fecha en la search view solo
                    -- afecte a rollos cargados por Excel.
                    sqi.date AS import_date,
                    sub.location_id AS location_id,
                    GREATEST(sub.write_date, COALESCE(l.write_date, sub.write_date)) AS write_date,
                    -- ^ usamos el write_date más reciente entre el quant y el lote, para que cuando se reserve/libere
                    --   el lote (write en stock.lot), la sincronización incremental del POS lo detecte y refresque is_reserved.
                    (l.pos_reserved_order_id IS NOT NULL) AS is_reserved,       -- flag para bloquear en frontend
                    l.pos_reserved_order_id AS reserved_by_order_id             -- referencia al pedido que lo bloquea
                FROM (
                    -- Subconsulta de agregación: suma todos los quants del mismo lote en ubicaciones internas
                    -- Esto evita que un quant positivo "tape" a otro quant negativo del mismo lote
                    SELECT
                        q.lot_id,
                        q.product_id,
                        SUM(q.quantity) AS quantity,    -- stock neto real del lote
                        MIN(q.location_id) AS location_id,
                        MAX(q.write_date) AS write_date -- cualquier cambio en cualquier quant del lote dispara la sincronización
                    FROM stock_quant q
                    JOIN stock_location sl ON sl.id = q.location_id
                    JOIN product_product pp ON pp.id = q.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE
                        pt.available_in_pos = True
                        AND sl.usage = 'internal'
                        AND q.lot_id IS NOT NULL        -- productos sin lote se excluyen (todos los textiles tienen lote)
                    GROUP BY q.lot_id, q.product_id
                    HAVING SUM(q.quantity) >= 0         -- >= 0 permite que los lotes vendidos (stock=0) aparezcan en la sincronización incremental
                ) sub
                JOIN product_product pp ON pp.id = sub.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN stock_lot l ON l.id = sub.lot_id
                LEFT JOIN color_recipe cr ON cr.id = l.color_recipe_id
                LEFT JOIN lab_dev_line ldl ON ldl.id = cr.lab_dev_line_id
                LEFT JOIN mrp_production_roll r ON r.id = l.roll_id
                -- JOIN al import que originó el rollo (puede ser NULL: rollos
                -- de producción interna o partición no tienen import_id).
                LEFT JOIN stock_quant_import sqi ON sqi.id = r.import_id
            )
        """ % self._table)

class StockQuantRelocate(models.TransientModel):
    _inherit = 'stock.quant.relocate'

    def action_relocate_quants(self):
        res = super(StockQuantRelocate, self).action_relocate_quants()
        if self.env.context.get('from_pos_stock_report'):
            return self.env.ref('idtx_pos_report_stock.action_idtx_pos_stock_report').read()[0]
        return res

class PosStockBarcodeWizard(models.TransientModel):
    _name = 'pos.stock.barcode.wizard'
    _description = 'Screen Barcode Wizard'

    report_ids = fields.Many2many('idtx.pos.stock.report', string='Reports')
    label_html = fields.Html('Etiquetas', compute='_compute_label_html')

    @api.depends('report_ids')
    def _compute_label_html(self):
        import qrcode
        import base64
        from io import BytesIO
        
        for wizard in self:
            html = "<div style='display: flex; flex-direction: column; gap: 20px; align-items: center;'>"
            for rep in wizard.report_ids:
                weight = rep.quantity or 0.0
                barcode = rep.product_id.barcode or ''
                barcode_data = f"01{barcode}3102{str(int(round(weight * 100))).zfill(6)}10{rep.lot_name or ''}"
                
                # Generar QR localmente
                qr = qrcode.QRCode(version=1, box_size=4, border=0)
                qr.add_data(barcode_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                qr_url = f"data:image/png;base64,{qr_base64}"
                
                html += f'''
                <div style="width: 480px; border: 1px solid #000; padding: 15px; border-radius: 4px; font-family: 'Arial', sans-serif; background: #fff; margin-bottom: 20px; color: #000;">
                    <div style="font-size: 22px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">
                        {rep.product_name or ''}
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <!-- Columna Izquierda: QR y Número de Rollo -->
                        <div style="display: flex; flex-direction: column; align-items: center; justify-content: flex-start; width: 40%;">
                            <img src="{qr_url}" style="width: 160px; height: 160px; margin-bottom: 5px;"/>
                            <div style="font-size: 14px; font-weight: bold;">
                                {rep.roll_name or ''}
                            </div>
                        </div>

                        <!-- Columna Derecha: Detalles -->
                        <div style="display: flex; flex-direction: column; width: 55%; font-size: 14px; line-height: 1.2;">
                            <div style="margin-bottom: 2px;"><strong>Código:</strong> {rep.product_code or ''}</div>
                            <div style="margin-bottom: 2px;"><strong>Color:</strong> [{rep.color_code or ''}]</div>
                            <div style="font-size: 18px; font-weight: bold; margin-bottom: 4px;">{rep.color_name or ''}</div>
                            <div style="font-size: 16px; margin-bottom: 12px;"><strong>Partida:</strong> {rep.lot_name or ''}</div>
                            
                            <div style="text-align: center;">
                                <div style="font-size: 16px;">Peso</div>
                                <div style="font-size: 38px; font-weight: bold; margin-top: -2px;">{weight:.2f}</div>
                            </div>
                        </div>
                    </div>
                </div>
                '''
            html += "</div>"
            wizard.label_html = html

    def action_print(self):
        self.ensure_one()
        self.report_ids.reprint()
        return {'type': 'ir.actions.act_window_close'}

