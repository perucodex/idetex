# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAnalysisProductionState(TransactionCase):
    """Estado de producción a nivel de ANÁLISIS (JP, 21-sep-2026): avanza al
    terminar una OF según su tipo, nunca retrocede; venta/servicio solo se
    confirma con piloto terminado; en producción no se admite muestra ni
    piloto; un piloto fallido se puede repetir."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.analysis = cls.env['product.analysis'].create({
            'standard_width': 180, 'density': 200})
        cls.product = cls.env['product.template'].create({
            'name': 'TELA ESTADO (test)', 'type': 'consu',
            'analysis_id': cls.analysis.id})
        cls.variant = cls.product.product_variant_id

    def _mo(self, production_type):
        return self.env['mrp.production'].create({
            'product_id': self.variant.id, 'product_qty': 10,
            'production_type': production_type,
        })

    def _finish(self, mo):
        mo.action_confirm()
        mo.qty_producing = mo.product_qty
        mo.button_mark_done()
        self.assertEqual(mo.state, 'done')

    def test_state_advances_and_never_goes_back(self):
        analysis = self.analysis
        self.assertEqual(analysis.production_state, 'product')
        self.assertEqual(analysis.production_indicator, 'none')

        sample = self._mo('sample')
        self.assertEqual(analysis.production_indicator, 'sample',
                         'muestra en curso: rojo con M')
        self._finish(sample)
        self.assertEqual(analysis.production_state, 'sample')
        self.assertEqual(analysis.production_indicator, 'sample_done',
                         'muestra terminada: verde con M')

        pilot = self._mo('pilot')
        self.assertEqual(analysis.production_indicator, 'pilot', 'piloto en curso')
        self._finish(pilot)
        self.assertEqual(analysis.production_state, 'pilot')
        self.assertEqual(analysis.production_indicator, 'pilot_done')

        # Si el piloto no salió bien se puede volver a crear piloto, y el
        # estado no retrocede.
        self._mo('pilot')
        self.assertEqual(analysis.production_state, 'pilot')
        self.assertEqual(analysis.production_indicator, 'pilot_done')
        # Muestra después de piloto: no (sería ir hacia atrás).
        with self.assertRaises(UserError):
            self._mo('sample')

        sale = self._mo('sale')
        self._finish(sale)
        self.assertEqual(analysis.production_state, 'production')
        self.assertEqual(analysis.production_indicator, 'production')

        # Ya en producción: ni piloto ni muestra.
        with self.assertRaises(UserError):
            self._mo('pilot')
        with self.assertRaises(UserError):
            self._mo('sample')
        # Nunca hacia atrás.
        analysis._advance_production_state('sample')
        analysis._advance_production_state('pilot')
        self.assertEqual(analysis.production_state, 'production')

    def test_sale_and_service_blocked_until_pilot_done(self):
        sale = self._mo('sale')
        with self.assertRaises(UserError) as cm:
            sale.action_confirm()
        self.assertIn('PILOTO', str(cm.exception), 'el mensaje pide terminar un piloto')
        self.assertEqual(sale.state, 'draft')
        self.assertFalse(sale._production_state_allows_confirm())
        service = self._mo('service')
        with self.assertRaises(UserError) as cm:
            service.action_confirm()
        self.assertIn('PILOTO', str(cm.exception))

        self._finish(self._mo('pilot'))
        self.assertTrue(sale._production_state_allows_confirm())
        sale.action_confirm()
        self.assertEqual(sale.state, 'confirmed')
        service.action_confirm()
        self.assertEqual(service.state, 'confirmed')

    def test_effective_state_heals_lagging_stored_state(self):
        """Si el estado almacenado quedó atrás (OF terminada sin que corriera el
        gancho de Hecho), el estado vigente sale de las OF terminadas: el
        semáforo y las reglas lo usan, y la sincronización lo guarda."""
        analysis = self.analysis
        self._finish(self._mo('pilot'))
        self.assertEqual(analysis.production_state, 'pilot')
        # Simula el rezago forzando el almacenado hacia atrás.
        analysis.with_context(tracking_disable=True).write({'production_state': 'product'})
        self.assertEqual(analysis._get_effective_production_state(), 'pilot')
        self.assertEqual(analysis.production_indicator, 'pilot_done')
        self.assertTrue(self._mo('sale')._production_state_allows_confirm())
        analysis._sync_production_state_from_productions()
        self.assertEqual(analysis.production_state, 'pilot')

    def test_product_without_analysis_has_no_rule(self):
        plain = self.env['product.template'].create({
            'name': 'SIN ANÁLISIS (test)', 'type': 'consu'})
        mo = self.env['mrp.production'].create({
            'product_id': plain.product_variant_id.id, 'product_qty': 1,
            'production_type': 'sale'})
        mo.action_confirm()
        self.assertEqual(mo.state, 'confirmed')
