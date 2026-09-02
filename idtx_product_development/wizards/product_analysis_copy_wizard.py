# -*- coding: utf-8 -*-
"""Wizard para duplicar product.analysis seleccionando que weaving_data_ids
copiar.

Flujo:
  1. Usuario abre un product.analysis -> click boton "Duplicar (seleccion)".
  2. Se abre el wizard precargado con TODOS los weaving_data_ids del origen
     pre-seleccionados.
  3. Usuario deselecciona los que no quiere.
  4. Submit -> .copy() del analisis SIN sus weaving_data_ids (vacios) +
     .copy() de cada weaving_data seleccionado apuntando al nuevo analisis
     (records nuevos, no links).
"""
from odoo import Command, _, api, fields, models


class ProductAnalysisCopyWizard(models.TransientModel):
    _name = 'product.analysis.copy.wizard'
    _description = 'Wizard para duplicar product.analysis con seleccion de Weaving Data'

    source_id = fields.Many2one(
        'product.analysis',
        string='Origen',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    weaving_data_ids = fields.Many2many(
        'analysis.weaving.data',
        relation='product_analysis_copy_wiz_weaving_rel',
        column1='wizard_id',
        column2='weaving_data_id',
        string='Weaving Data a copiar',
        domain="[('analysis_id', '=', source_id)]",
        help='Solo se copiaran al nuevo analisis los que selecciones aqui. '
             'Por defecto vienen todos pre-seleccionados.',
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        source_id = (
            self.env.context.get('default_source_id')
            or (self.env.context.get('active_id')
                if self.env.context.get('active_model') == 'product.analysis'
                else None)
        )
        if source_id:
            source = self.env['product.analysis'].browse(source_id).exists()
            if source:
                defaults['source_id'] = source.id
                # Pre-seleccionar todos los weaving_data del origen.
                defaults['weaving_data_ids'] = [(6, 0, source.weaving_data_ids.ids)]
        return defaults

    def action_copy(self):
        """Crea el nuevo product.analysis y duplica solo las weaving_data
        seleccionadas. Cada una se duplica con .copy() para garantizar
        records NUEVOS (no link al original).
        """
        self.ensure_one()
        source = self.source_id
        if not source:
            return False
        # 1. Copia del analisis SIN weaving_data NI routing_ids — ambos
        # los manejamos manualmente despues. El name se omite del
        # default para que use el comportamiento estandar (campo con
        # `copy=False` y default _('New') que dispara la secuencia).
        new_analysis = source.with_context(
            product_analysis_skip_copy_wizard=True,
        ).copy(default={
            'weaving_data_ids': [Command.clear()],
            'routing_ids': [Command.clear()],
        })
        # 2. .copy() de cada weaving_data seleccionada apuntando al
        # nuevo analisis. Crea registros NUEVOS, incluyendo sus
        # fiber_ids (One2many anidado que Odoo copia automaticamente).
        for wd in self.weaving_data_ids:
            # skip_fiber_weight_check: copia fiel aunque el origen tenga
            # fibras legacy con peso 0 (mismo criterio que action_duplicate).
            wd.with_context(skip_fiber_weight_check=True).copy(
                default={'analysis_id': new_analysis.id})
        # 3. Re-poblar routing_ids desde el mrp.base.process.
        # Esto replica lo que hace _onchange_mrp_base_process_id en UI:
        # cada line del base process se convierte en una linea de ruta
        # nueva apuntando al nuevo analisis.
        if new_analysis.mrp_base_process_id:
            new_analysis.routing_ids = [
                Command.create({
                    'operation_id': line.operation_id.id,
                    'sequence': line.sequence,
                })
                for line in new_analysis.mrp_base_process_id.process_ids
                if line.operation_id
            ]
        # 4. Abre el nuevo analisis para que el usuario continue
        # editandolo.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nuevo analisis'),
            'res_model': 'product.analysis',
            'view_mode': 'form',
            'res_id': new_analysis.id,
            'target': 'current',
        }
