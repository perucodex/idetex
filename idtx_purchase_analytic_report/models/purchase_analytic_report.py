from odoo import models, fields, tools


class PurchaseOrderLineAnalyticReport(models.Model):
    _name = 'purchase.order.line.analytic.report'
    _description = 'Purchase Order Line Analytic Report'
    _auto = False
    _rec_name = 'analytic_account_id'

    order_id = fields.Many2one('purchase.order', readonly=True)
    order_line_id = fields.Many2one('purchase.order.line', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', readonly=True)
    code = fields.Char(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    date_order = fields.Datetime(readonly=True)
    product_qty = fields.Float(readonly=True)
    price_subtotal = fields.Monetary(readonly=True)
    price_total = fields.Monetary(readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW purchase_order_line_analytic_report AS (
                SELECT
                    row_number() OVER () AS id,
                    pol.id AS order_line_id,
                    po.id AS order_id,
                    pol.product_id,
                    aa.id AS analytic_account_id,
                    aa.code AS code,
                    po.company_id,
                    po.date_order,
                    po.currency_id,
                    -- pol.product_qty,
                    (
                        pol.product_qty
                        * (dist.value::numeric / 100.0)
                    ) AS product_qty,
                    (
                        pol.price_subtotal
                        * (dist.value::numeric / 100.0)
                    ) AS price_subtotal,
                    (
                        pol.price_total
                        * (dist.value::numeric / 100.0)
                    ) AS price_total
                FROM purchase_order_line pol
                JOIN purchase_order po
                    ON po.id = pol.order_id
                JOIN LATERAL jsonb_each(pol.analytic_distribution) dist(key, value)
                    ON TRUE
                JOIN account_analytic_account aa
                    ON aa.id = dist.key::int
                WHERE pol.display_type IS NULL
                  AND po.state IN ('purchase', 'done')
                  AND pol.analytic_distribution IS NOT NULL
            )
        """)
