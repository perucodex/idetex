# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class IdtxPosProductSalesReport(models.Model):
    """
    Reporte "Ventas por Producto": vista SQL de SOLO LECTURA, una fila por
    LÍNEA de venta POS (a diferencia de idtx.pos.sales.report, que es una
    fila por pedido completo). Permite filtrar por tela/color específico
    y ver qué cliente compró más de ese producto.

    Filtro de "basura" pedido por el usuario (2026-07-21): pedidos
    CANCELADOS o en BORRADOR nunca aparecen aquí (excluidos en el WHERE
    de la vista, no dependen de que alguien marque un filtro). Las líneas
    que sí se vendieron pero luego se devolvieron (por NC o por devolución
    sin comprobante) SÍ se muestran, pero marcadas con `devuelto=True`
    para resaltarlas en la vista (ambas: la línea original vendida y la
    línea de la devolución).
    """
    _name = 'idtx.pos.product.sales.report'
    _description = 'Reporte Ventas por Producto (POS)'
    _auto = False
    _rec_name = 'pos_reference'
    _order = 'date_order desc'

    # ===== Identificación =====
    line_id = fields.Many2one('pos.order.line', string='Línea', readonly=True)
    order_id = fields.Many2one('pos.order', string='Pedido POS', readonly=True)
    pos_reference = fields.Char(string='Pedido', readonly=True)
    date_order = fields.Datetime(string='Fecha', readonly=True)
    session_id = fields.Many2one('pos.session', string='Sesión', readonly=True)
    config_id = fields.Many2one('pos.config', string='Caja', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)

    # ===== Cliente =====
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    partner_vat = fields.Char(string='RUC / DNI', readonly=True)

    # ===== Producto =====
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    color_name = fields.Char(string='Color', readonly=True)
    kilos = fields.Float(string='Kilos', readonly=True, digits=(16, 2))
    price_unit = fields.Monetary(string='Precio Unit.', readonly=True, currency_field='currency_id')
    total = fields.Monetary(string='Total línea', readonly=True, currency_field='currency_id')

    # ===== Clasificación por comprobante (igual que idtx.pos.sales.report) =====
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
    doc_rectificado = fields.Char(string='Comprobante rectificado', readonly=True)
    # Pedido original que esta línea devuelve (solo si esta línea ES una devolución)
    pedido_devuelto = fields.Char(string='Pedido devuelto', readonly=True)
    # Se activa en la línea vendida original Y en su línea de devolución
    devuelto = fields.Boolean(string='¿Devuelto?', readonly=True)

    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id                                    AS id,
                    l.id                                    AS line_id,
                    o.id                                    AS order_id,
                    o.pos_reference                         AS pos_reference,
                    o.date_order                            AS date_order,
                    o.session_id                            AS session_id,
                    s.config_id                             AS config_id,
                    o.user_id                               AS user_id,
                    o.partner_id                            AS partner_id,
                    p.vat                                   AS partner_vat,
                    l.product_id                             AS product_id,
                    l.color_name                            AS color_name,
                    l.qty                                   AS kilos,
                    l.price_unit                            AS price_unit,
                    -- Odoo guarda price_subtotal_incl como magnitud SIEMPRE
                    -- positiva, incluso en líneas de devolución (qty negativo);
                    -- se le devuelve el signo real (igual que hace el reporte
                    -- nativo point_of_sale.report.pos.order) para que las
                    -- devoluciones resten y no sumen al total.
                    (SIGN(l.qty) * SIGN(l.price_unit) * ABS(l.price_subtotal_incl)) AS total,
                    CASE
                        -- Esta línea ES una devolución sin comprobante (reembolsa otra línea, sin factura)
                        WHEN m.id IS NULL AND origord.pos_reference IS NOT NULL THEN 'devolucion'
                        WHEN m.id IS NULL          THEN 'sin_comprobante'
                        WHEN dt.code = '01'        THEN 'factura'
                        WHEN dt.code = '03'        THEN 'boleta'
                        WHEN dt.code = '07'        THEN 'nota_credito'
                        WHEN dt.code = '08'        THEN 'nota_debito'
                        ELSE 'otro'
                    END                                     AS tipo_venta,
                    m.name                                  AS doc_name,
                    rev.name                                AS doc_rectificado,
                    origord.pos_reference                   AS pedido_devuelto,
                    -- Resaltar: esta línea es una devolución, O es la línea vendida
                    -- original que después alguien devolvió (buscando quién le apunta)
                    (
                        l.refunded_orderline_id IS NOT NULL
                        OR EXISTS (
                            SELECT 1 FROM pos_order_line rl
                            WHERE rl.refunded_orderline_id = l.id
                        )
                    )                                       AS devuelto,
                    c.currency_id                           AS currency_id,
                    o.company_id                            AS company_id
                FROM pos_order_line l
                JOIN pos_order o                 ON o.id = l.order_id
                JOIN pos_session s                ON s.id = o.session_id
                JOIN res_company c                 ON c.id = o.company_id
                LEFT JOIN res_partner p             ON p.id = o.partner_id
                LEFT JOIN account_move m            ON m.id = o.account_move
                LEFT JOIN l10n_latam_document_type dt ON dt.id = m.l10n_latam_document_type_id
                LEFT JOIN account_move rev          ON rev.id = m.reversed_entry_id
                -- Pedido original que esta línea devuelve (si esta línea ES una devolución)
                LEFT JOIN pos_order_line origl      ON origl.id = l.refunded_orderline_id
                LEFT JOIN pos_order origord         ON origord.id = origl.order_id
                -- Solo ventas concretadas: nunca borradores ni canceladas
                WHERE o.state IN ('paid', 'done', 'invoiced')
                  AND l.product_id IS NOT NULL
            )
        """ % self._table)
