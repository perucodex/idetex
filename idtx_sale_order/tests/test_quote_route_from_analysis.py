# -*- coding: utf-8 -*-
import json

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQuoteRouteFromAnalysis(TransactionCase):
    """Cotización con la ruta del ANÁLISIS del producto (21-sep-2026): los
    procesos a cotizar, sus precios y los flags de la línea salen de
    analysis_id.routing_ids (fases del maestro), no de la ficha/LdM."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.usd = env.ref('base.USD')
        cls.company.is_company_produce = True
        cls.pricelist = env['product.pricelist'].create({
            'name': 'Cotización USD (test)', 'currency_id': cls.usd.id})
        cls.company.sales_pricelist_id = cls.pricelist

        WC = env['mrp.workcenter']
        cls.wc = {
            t: WC.create({'name': 'CT %s (test)' % t, 'operation_type': t})
            for t in ('weaving', 'dyeing', 'finishing', 'quality', 'printing')
        }
        cls.color = env['product.color'].create({'name': 'ROJO (test)'})
        OP = env['mrp.routing.workcenter.operation']
        cls.op_weaving = OP.create({
            'name': 'TEJIDO (test)', 'workcenter_id': cls.wc['weaving'].id})
        cls.op_dyeing = OP.create({
            'name': 'TEÑIDO (test)', 'workcenter_id': cls.wc['dyeing'].id,
            'type_prices': 'col', 'gives_color': True, 'currency_id': cls.usd.id,
            'product_color_price_ids': [Command.create({
                'product_color_id': cls.color.id, 'unit_price': 2.5})],
        })
        cls.op_finishing = OP.create({
            'name': 'ACABADO (test)', 'workcenter_id': cls.wc['finishing'].id,
            'unit_price': 1.25, 'currency_id': cls.usd.id})
        # Auxiliar sin precio: está en la ruta pero no se cotiza.
        cls.op_quality = OP.create({
            'name': 'CONTROL (test)', 'workcenter_id': cls.wc['quality'].id})
        cls.op_printing = OP.create({
            'name': 'ESTAMPADO (test)', 'workcenter_id': cls.wc['printing'].id,
            'unit_price': 0.9, 'currency_id': cls.usd.id, 'prints_product': True})

        cls.analysis = env['product.analysis'].create({
            'standard_width': 180, 'density': 200,
            'currency_id': cls.usd.id, 'weaving_price': 1.0,
            'routing_ids': [
                Command.create({'sequence': 10, 'operation_id': cls.op_weaving.id}),
                Command.create({'sequence': 20, 'operation_id': cls.op_dyeing.id}),
                Command.create({'sequence': 30, 'operation_id': cls.op_finishing.id}),
                Command.create({'sequence': 40, 'operation_id': cls.op_quality.id}),
            ],
        })
        cls.product = env['product.template'].create({
            'name': 'JERSEY (test)', 'type': 'consu', 'list_price': 0,
            'analysis_id': cls.analysis.id,
        })
        # is_weaving lo fija la categoría de tejido de la compañía; aquí se
        # marca directo (mismo camino que res.company.write) para no tocar
        # todos los productos de la base.
        cls.product.is_weaving = True
        cls.partner = env['res.partner'].create({
            'name': 'Cliente (test)', 'is_company': True})

    def _new_quote(self, sale_type='sale'):
        quote = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'is_quote': True,
            'sale_type': sale_type, 'pricelist_id': self.pricelist.id,
        })
        line = self.env['sale.order.line'].create({
            'order_id': quote.id,
            'product_id': self.product.product_variant_id.id,
            'product_uom_qty': 100,
            'product_color_id': self.color.id,
        })
        return quote, line

    def _op_keys(self, line):
        items = json.loads(line.price_items or '{}')
        return [k for k, v in items.items()
                if not k.startswith('__') and isinstance(v, dict)]

    def test_route_and_flags_from_analysis_without_bom(self):
        quote, line = self._new_quote()
        self.assertFalse(line.bom_id, 'la ficha no interviene en la cotización')
        self.assertEqual(
            line.available_operation_ids.ids,
            [self.op_weaving.id, self.op_dyeing.id, self.op_finishing.id],
            'fases con precio de la ruta del análisis, en su orden; '
            'la auxiliar sin precio no')
        line._onchange_route_operations()
        self.assertEqual(set(line.operation_ids.ids),
                         set(line.available_operation_ids.ids))
        # Orden de la ruta completa (con la auxiliar) para pintar las etiquetas.
        self.assertEqual(
            json.loads(line.route_operation_order),
            [self.op_weaving.id, self.op_dyeing.id, self.op_finishing.id, self.op_quality.id])
        self.assertTrue(line.has_weaving_operation)
        self.assertTrue(line.is_lab_color, 'TEÑIDO da color en la ruta del análisis')
        self.assertFalse(line.is_printing)

    def test_price_from_analysis_route(self):
        quote, line = self._new_quote()
        line._onchange_route_operations()
        line.price_items = '{}'
        total = line.get_weaving_price_unit()
        self.assertEqual(self._op_keys(line),
                         ['TEJIDO (test)', 'TEÑIDO (test)', 'ACABADO (test)'])
        items = json.loads(line.price_items)
        self.assertAlmostEqual(items['TEJIDO (test)']['price'], 1.0, 2,
                               'precio de tejido del análisis')
        self.assertAlmostEqual(items['TEÑIDO (test)']['price'], 2.5, 2,
                               'precio por color de la fase')
        self.assertAlmostEqual(items['ACABADO (test)']['price'], 1.25, 2,
                               'precio por proceso')
        self.assertAlmostEqual(total, 4.75, 2)

    def test_service_subset_keeps_route_order(self):
        quote, line = self._new_quote('service')
        # El vendedor quita el tejido (tela del cliente) y elige en desorden.
        line.operation_ids = [Command.set([self.op_finishing.id, self.op_dyeing.id])]
        self.assertEqual(line._get_quoted_operations().ids,
                         [self.op_dyeing.id, self.op_finishing.id])
        self.assertFalse(line.has_weaving_operation,
                         'sin tejido seleccionado no hay operación de tejido')
        line.price_items = '{}'
        total = line.get_weaving_price_unit()
        self.assertEqual(self._op_keys(line), ['TEÑIDO (test)', 'ACABADO (test)'])
        self.assertAlmostEqual(total, 3.75, 2)

    def test_analysis_route_change_updates_line(self):
        quote, line = self._new_quote()
        self.assertFalse(line.is_printing)
        self.analysis.routing_ids = [Command.create({
            'sequence': 35, 'operation_id': self.op_printing.id})]
        self.assertTrue(line.is_printing, 'el flag sigue a la ruta del análisis')
        self.assertEqual(
            line.available_operation_ids.ids,
            [self.op_weaving.id, self.op_dyeing.id,
             self.op_finishing.id, self.op_printing.id])

    def test_line_production_indicator_follows_analysis(self):
        """Semáforo de la línea = estado de producción del análisis."""
        quote, line = self._new_quote()
        self.assertEqual(line.analysis_production_indicator, 'none',
                         'producto nunca fabricado: rojo sin letra')
        self.analysis._advance_production_state('sample')
        self.assertEqual(line.analysis_production_indicator, 'sample_done',
                         'muestra terminada: verde con M')
        self.analysis._advance_production_state('pilot')
        self.assertEqual(line.analysis_production_indicator, 'pilot_done', 'verde con P')
        self.analysis._advance_production_state('production')
        self.assertEqual(line.analysis_production_indicator, 'production', 'verde sin letra')
        # Nunca hacia atrás.
        self.analysis._advance_production_state('sample')
        self.assertEqual(line.analysis_production_indicator, 'production')

    def test_switch_order_production_to_pilot_and_back(self):
        """Botones de la OF con pedido: convertir en piloto (permite confirmar
        sin piloto previo) y revertir al tipo del pedido; solo Desarrollo de
        Producto / Administrador."""
        from odoo.exceptions import AccessError, UserError
        quote, line = self._new_quote('service')
        production = self.env['mrp.production'].create({
            'product_id': self.product.product_variant_id.id, 'product_qty': 100,
            'sale_order_line_id': line.id, 'production_type': 'service',
        })
        self.assertEqual(production.order_id, quote)
        self.assertFalse(production._production_state_allows_confirm(),
                         'servicio sin piloto terminado: no se confirma')

        admin = self.env.ref('base.user_admin')
        self.assertTrue(admin.has_group(
            'idtx_product_development.group_module_product_development_manager'))
        dev_user = self.env['res.users'].create({
            'name': 'Desarrollo usuario (test)', 'login': 'dev_user_test',
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('idtx_product_development.group_module_product_development_user').id,
                self.env.ref('mrp.group_mrp_user').id,
            ])],
        })
        with self.assertRaises(AccessError):
            production.with_user(dev_user).action_set_pilot_production_type()

        production.with_user(admin).action_set_pilot_production_type()
        self.assertEqual(production.production_type, 'pilot')
        self.assertTrue(production._production_state_allows_confirm(),
                        'como piloto se puede confirmar sin piloto previo')

        production.with_user(admin).action_revert_production_type()
        self.assertEqual(production.production_type, 'service', 'vuelve al tipo del pedido')

        # Producto ya en producción: no se puede convertir en piloto.
        self.analysis._advance_production_state('production')
        with self.assertRaises(UserError):
            production.with_user(admin).action_set_pilot_production_type()
        self.assertEqual(production.production_type, 'service')

    def test_thread_price_date_from_pricelist_rules(self):
        """Fecha de precios de hilado: última modificación de las reglas de la
        lista de precios de los hilos (componentes de hilado de la LdM) de la
        cotización, con detalle por hilo."""
        thread_categ = self.env['product.category'].create({'name': 'HILADO (test)'})
        self.company.thread_category_ids = [Command.link(thread_categ.id)]
        thread_a = self.env['product.template'].create({
            'name': 'HILO A (test)', 'default_code': 'HA-T', 'type': 'consu',
            'categ_id': thread_categ.id})
        thread_b = self.env['product.template'].create({
            'name': 'HILO B (test)', 'default_code': 'HB-T', 'type': 'consu',
            'categ_id': thread_categ.id})
        rule = self.env['product.pricelist.item'].create({
            'pricelist_id': self.pricelist.id, 'applied_on': '1_product',
            'product_tmpl_id': thread_a.id, 'compute_price': 'fixed', 'fixed_price': 9.5})
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product.id, 'product_qty': 1, 'type': 'normal',
            'bom_line_ids': [
                Command.create({'product_id': thread_a.product_variant_id.id, 'product_qty': 0.6}),
                Command.create({'product_id': thread_b.product_variant_id.id, 'product_qty': 0.4}),
            ],
        })
        quote, line = self._new_quote()
        line.bom_id = bom
        rows = quote._get_thread_price_rows()
        by_code = {r['code']: r for r in rows}
        self.assertEqual(set(by_code), {'HA-T', 'HB-T'})
        self.assertTrue(by_code['HA-T']['has_rule'])
        self.assertEqual(by_code['HA-T']['date'], fields.Datetime.to_string(rule.write_date))
        self.assertFalse(by_code['HB-T']['has_rule'], 'hilo sin regla: se avisa, sin fecha')
        self.assertFalse(by_code['HB-T']['date'])
        quote.invalidate_recordset(['thread_price_count', 'thread_price_date', 'thread_price_info'])
        self.assertEqual(quote.thread_price_count, 2, 'badge "2 Hilos cotizados"')
        self.assertEqual(quote.thread_price_date,
                         fields.Date.context_today(quote, timestamp=rule.write_date))
        self.assertEqual(len(json.loads(quote.thread_price_info)), 2)

    def test_cancel_order_blocked_when_production_advanced(self):
        """Candado: un pedido cuya OF ya tiene rollos del cliente recibidos (o
        rollos, partidas, operaciones) no se cancela; sin avance sí, y la OF
        se cancela con él."""
        from odoo.exceptions import UserError
        quote, line = self._new_quote('service')
        production = self.env['mrp.production'].create({
            'product_id': self.product.product_variant_id.id, 'product_qty': 100,
            'sale_order_line_id': line.id, 'production_type': 'service',
        })
        reception = self.env['mrp.roll.reception'].create({
            'production_id': production.id, 'guide_number': 'G-TEST-001'})
        self.assertNotEqual(reception.state, 'cancel')
        with self.assertRaises(UserError) as cm:
            quote.action_cancel()
        self.assertIn('recepción', str(cm.exception))
        self.assertNotEqual(quote.state, 'cancel', 'el pedido no cambia si algo bloquea')
        self.assertNotEqual(production.state, 'cancel', 'la OF tampoco')
        # La OF tampoco se puede cancelar directamente.
        with self.assertRaises(UserError):
            production.action_cancel()

        # Sin avance (recepción cancelada) sí se cancela, y arrastra la OF.
        reception.write({'state': 'cancel'})
        quote.action_cancel()
        self.assertEqual(quote.state, 'cancel')
        self.assertEqual(production.state, 'cancel')

    def test_unpriced_printing_operation_always_selectable(self):
        """Las fases que ESTAMPAN (toggle prints_product) se cotizan aparte
        (precio del diseño): aunque su precio por proceso sea 0 siempre están
        disponibles y elegidas. Una auxiliar del centro de estampado sin el
        toggle y sin precio no se ofrece ni marca la línea como estampado."""
        OP = self.env['mrp.routing.workcenter.operation']
        op_free = OP.create({
            'name': 'ESTAMPADO REACTIVO (test)', 'workcenter_id': self.wc['printing'].id,
            'unit_price': 0, 'prints_product': True})
        op_aux = OP.create({
            'name': 'CEPILLADO DE TELA (test)', 'workcenter_id': self.wc['printing'].id,
            'unit_price': 0})
        self.analysis.routing_ids = [
            Command.create({'sequence': 34, 'operation_id': op_aux.id}),
            Command.create({'sequence': 36, 'operation_id': op_free.id}),
        ]
        quote, line = self._new_quote('service')
        self.assertIn(op_free, line.available_operation_ids)
        self.assertNotIn(op_aux, line.available_operation_ids,
                         'auxiliar tipo estampado sin toggle ni precio: no se cotiza')
        line._onchange_route_operations()
        self.assertIn(op_free, line.operation_ids)
        self.assertTrue(line.is_printing)
        line.price_items = '{}'
        line.get_weaving_price_unit()
        self.assertNotIn(op_free.name, self._op_keys(line),
                         'sin precio por proceso no genera ítem de precio propio')
        line.operation_ids = [Command.unlink(op_free.id)]
        self.assertFalse(line.is_printing)

    def test_service_removing_printing_clears_design(self):
        """Servicio: al quitar la fase de estampado de las operaciones la línea
        deja de estampar (is_printing) y se limpia el diseño; al volver a
        agregarla vuelve a estampar."""
        self.analysis.routing_ids = [Command.create({
            'sequence': 35, 'operation_id': self.op_printing.id})]
        quote, line = self._new_quote('service')
        line._onchange_route_operations()
        self.assertIn(self.op_printing, line.operation_ids)
        self.assertTrue(line.is_printing)
        design = self.env['printing.design'].create({
            'printing_type': 'rotary', 'process_type_rotary': 'reactive',
            'cylinder_qty': 4, 'printing_date': fields.Date.context_today(quote)})
        line.printing_design_id = design
        self.assertEqual(line.printing_design_id, design)

        line.operation_ids = [Command.unlink(self.op_printing.id)]
        self.assertFalse(line.is_printing, 'sin fase de estampado elegida no estampa')
        self.assertFalse(line.printing_design_id, 'el diseño se limpia solo')

        line.operation_ids = [Command.link(self.op_printing.id)]
        self.assertTrue(line.is_printing)
        self.assertFalse(line.printing_design_id, 'el diseño se vuelve a elegir a mano')

    def test_production_workorders_follow_selected_operations(self):
        quote, line = self._new_quote('service')
        line.operation_ids = [Command.set([self.op_dyeing.id, self.op_finishing.id])]
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product.id, 'product_qty': 1, 'type': 'normal',
            'operation_ids': [
                Command.create({
                    'name': op.name, 'workcenter_id': op.workcenter_id.id,
                    'operation_id': op.id, 'sequence': seq})
                for seq, op in enumerate(
                    (self.op_weaving, self.op_dyeing, self.op_finishing, self.op_quality), 1)
            ],
        })
        production = self.env['mrp.production'].create({
            'product_id': self.product.product_variant_id.id, 'product_qty': 100,
            'bom_id': bom.id, 'sale_order_line_id': line.id,
            'production_type': 'service',
        })
        wo_ops = production.workorder_ids.mapped('operation_id.operation_id')
        self.assertNotIn(self.op_weaving, wo_ops,
                         'la fase quitada en la línea no genera OT')
        self.assertIn(self.op_dyeing, wo_ops)
        self.assertIn(self.op_finishing, wo_ops)
        self.assertIn(self.op_quality, wo_ops,
                      'las auxiliares sin precio se conservan')
