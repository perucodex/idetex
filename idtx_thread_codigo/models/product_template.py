# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Atributos del hilado. La FUENTE de edición es idtx.thread.code (pantalla
    # propia "Hilado"); aquí se reciben y se muestran en SOLO LECTURA. Para
    # productos is_thread heredados (creados fuera de Odoo) se rellenan con
    # _sync_thread_from_sitpro desde codigohilocrud por código.
    thread_titulo_id = fields.Many2one('product.thread.titulo', string='Título')
    thread_cabos_id = fields.Many2one('product.thread.cabos', string='Cabos')
    thread_proceso_id = fields.Many2one('product.thread.proceso', string='Proceso')
    thread_composicion_id = fields.Many2one('product.thread.composicion', string='Composición')
    thread_linea_id = fields.Many2one('product.thread.linea', string='Línea')
    thread_diseno_id = fields.Many2one('product.thread.diseno', string='Diseño')
    thread_desarrollo = fields.Boolean('Desarrollo')
    thread_descrip2 = fields.Char('Descripción 2')

    # ---- Sincronización de los campos nuevos desde SITPRO (codigohilocrud) ----

    @api.model
    def _sync_thread_from_sitpro(self, products=None):
        """Para productos is_thread con código, lee codigohilocrud en SITPRO y
        rellena los campos de hilado (match de catálogos por código). Devuelve
        el número de productos actualizados."""
        if products is None:
            products = self.search([('is_thread', '=', True), ('default_code', '!=', False)])
        products = products.filtered(lambda p: p.is_thread and p.default_code)
        if not products:
            return 0
        conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo, titulo, cabo, proceso, linea, composicion, descrip2, "
            "desarrollo "
            "FROM SITPRO.dbo.codigohilocrud")
        by_code = {}
        for row in cursor.fetchall():
            by_code[(row.codigo or '').strip()] = row
        try:
            conn.close()
        except Exception:
            pass

        def code_map(model_name):
            return {r.code: r.id for r in
                    self.env[model_name].with_context(active_test=False).search([])}
        m_tit = code_map('product.thread.titulo')
        m_cab = code_map('product.thread.cabos')
        m_pro = code_map('product.thread.proceso')
        m_com = code_map('product.thread.composicion')
        m_lin = code_map('product.thread.linea')
        updated = 0
        for product in products:
            row = by_code.get((product.default_code or '').strip())
            if not row:
                continue
            vals = {
                'thread_titulo_id': m_tit.get((row.titulo or '').strip()),
                'thread_cabos_id': m_cab.get((row.cabo or '').strip()),
                'thread_proceso_id': m_pro.get((row.proceso or '').strip()),
                'thread_composicion_id': m_com.get((row.composicion or '').strip()),
                'thread_linea_id': m_lin.get((row.linea or '').strip()),
                'thread_descrip2': (row.descrip2 or '').strip() or False,
                'thread_desarrollo': bool(row.desarrollo),
            }
            to_write = {}
            for key, value in vals.items():
                current = product[key]
                current = (current.id if hasattr(current, 'id') else current) or False
                if current != (value or False):
                    to_write[key] = value
            if to_write:
                product.write(to_write)
                updated += 1
        _logger.info("Hilado: sincronizados %s de %s productos is_thread desde SITPRO",
                     updated, len(products))
        return updated
