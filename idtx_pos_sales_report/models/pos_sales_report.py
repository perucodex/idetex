# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class IdtxPosSalesReport(models.Model):
    """
    Reporte de Ventas Tienda: vista SQL de SOLO LECTURA, una fila por venta POS.

    Clasifica cada venta por su tipo de comprobante mirando la factura
    vinculada (account_move → l10n_latam_document_type):
      - '01' → Factura electrónica
      - '03' → Boleta electrónica
      - '07'/'08' → Nota de crédito/débito (devoluciones con comprobante)
      - sin factura → Sin comprobante (venta con PROFORMA)

    Los montos salen del propio pos_order (lo que realmente se cobró en caja):
    subtotal = total - IGV. Las devoluciones aparecen en negativo.
    """
    _name = 'idtx.pos.sales.report'
    _description = 'Reporte Ventas Tienda (POS)'
    _auto = False                      # respaldado por una VIEW SQL, no una tabla
    _rec_name = 'pos_reference'
    _order = 'date_order desc'

    # ===== Identificación de la venta =====
    order_id = fields.Many2one('pos.order', string='Pedido POS', readonly=True)
    pos_reference = fields.Char(string='Pedido', readonly=True)
    date_order = fields.Datetime(string='Fecha', readonly=True)
    session_id = fields.Many2one('pos.session', string='Sesión', readonly=True)
    config_id = fields.Many2one('pos.config', string='Caja', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)

    # ===== Clasificación por comprobante =====
    tipo_venta = fields.Selection([
        ('factura', 'Factura electrónica'),
        ('boleta', 'Boleta electrónica'),
        ('nota_credito', 'Nota de crédito'),
        ('nota_debito', 'Nota de débito'),
        ('devolucion', 'Devolución sin comprobante'),
        ('sin_comprobante', 'Sin comprobante'),
        ('otro', 'Otro documento'),
    ], string='Tipo de venta', readonly=True)
    doc_name = fields.Char(string='Serie y Número', readonly=True)
    # Para notas de crédito/débito: comprobante original que rectifican
    doc_rectificado = fields.Char(string='Comprobante rectificado', readonly=True)
    # Para devoluciones sin comprobante: pedido original que se devuelve
    pedido_devuelto = fields.Char(string='Pedido devuelto', readonly=True)
    move_id = fields.Many2one('account.move', string='Comprobante', readonly=True)
    estado_sunat = fields.Selection([
        ('to_send', 'Por enviar'),
        ('sent', 'Enviado / Aceptado'),
        ('to_cancel', 'Por anular'),
        ('cancelled', 'Anulado'),
    ], string='Estado SUNAT', readonly=True)

    # ===== Cliente =====
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    partner_vat = fields.Char(string='RUC / DNI', readonly=True)

    # ===== Montos (lo cobrado en caja; devoluciones en negativo) =====
    subtotal = fields.Monetary(string='Subtotal', readonly=True, currency_field='currency_id')
    igv = fields.Monetary(string='IGV', readonly=True, currency_field='currency_id')
    total = fields.Monetary(string='Total', readonly=True, currency_field='currency_id')
    kilos = fields.Float(string='Kilos', readonly=True, digits=(16, 2))

    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    def init(self):
        """(Re)crea la VIEW SQL que respalda el modelo."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    o.id                                   AS id,
                    o.id                                   AS order_id,
                    o.pos_reference                        AS pos_reference,
                    o.date_order                           AS date_order,
                    o.session_id                           AS session_id,
                    s.config_id                            AS config_id,
                    o.user_id                              AS user_id,
                    -- Clasificación por tipo de documento SUNAT del comprobante
                    CASE
                        -- Devolución sin comprobante: reembolsa a otro pedido y no tiene documento
                        WHEN m.id IS NULL AND dev.pos_reference IS NOT NULL THEN 'devolucion'
                        WHEN m.id IS NULL          THEN 'sin_comprobante'
                        WHEN dt.code = '01'        THEN 'factura'
                        WHEN dt.code = '03'        THEN 'boleta'
                        WHEN dt.code = '07'        THEN 'nota_credito'
                        WHEN dt.code = '08'        THEN 'nota_debito'
                        ELSE 'otro'
                    END                                    AS tipo_venta,
                    m.name                                 AS doc_name,
                    rev.name                               AS doc_rectificado,
                    dev.pos_reference                      AS pedido_devuelto,
                    m.id                                   AS move_id,
                    m.edi_state                            AS estado_sunat,
                    o.partner_id                           AS partner_id,
                    p.vat                                  AS partner_vat,
                    (o.amount_total - o.amount_tax)        AS subtotal,
                    o.amount_tax                           AS igv,
                    o.amount_total                         AS total,
                    -- Kilos vendidos (suma de qty de las líneas de producto)
                    COALESCE(kg.kilos, 0.0)                AS kilos,
                    c.currency_id                          AS currency_id,
                    o.company_id                           AS company_id
                FROM pos_order o
                JOIN pos_session s              ON s.id = o.session_id
                JOIN res_company c              ON c.id = o.company_id
                LEFT JOIN account_move m        ON m.id = o.account_move
                LEFT JOIN l10n_latam_document_type dt ON dt.id = m.l10n_latam_document_type_id
                -- Comprobante original que la nota de crédito/débito rectifica
                LEFT JOIN account_move rev      ON rev.id = m.reversed_entry_id
                LEFT JOIN res_partner p         ON p.id = o.partner_id
                LEFT JOIN LATERAL (
                    SELECT SUM(l.qty) AS kilos
                    FROM pos_order_line l
                    WHERE l.order_id = o.id
                ) kg ON true
                -- Pedido original al que esta orden le devuelve productos (si aplica)
                LEFT JOIN LATERAL (
                    SELECT oo.pos_reference
                    FROM pos_order_line l
                    JOIN pos_order_line ol ON ol.id = l.refunded_orderline_id
                    JOIN pos_order oo ON oo.id = ol.order_id
                    WHERE l.order_id = o.id
                    LIMIT 1
                ) dev ON true
                -- Solo ventas concretadas (no borradores ni canceladas)
                WHERE o.state IN ('paid', 'done', 'invoiced')
            )
        """ % self._table)
