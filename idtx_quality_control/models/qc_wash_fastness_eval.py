from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ControlSolidezLavadoEval(models.Model):
    _name = 'qc.wash.fastness.eval'
    _description = 'Evaluacion Solidez del Color al Lavado'
    _order = 'fecha_eval desc, id desc'

    _TABLET_FIELDS = (
        'cambio_color_grado',
        'mig_acetato',
        'mig_algodon',
        'mig_nylon',
        'mig_poliester',
        'mig_acrilico',
        'mig_lana',
        'frote_seco',
        'frote_humedo',
    )

    _RESULT_RULES = (
        ('bool_cambio_color_grado', 'cambio_color_grado', 'color_change_degree'),
        ('bool_mig_acetato', 'mig_acetato', 'migration_acetate'),
        ('bool_mig_algodon', 'mig_algodon', 'migration_cotton'),
        ('bool_mig_nylon', 'mig_nylon', 'migration_nylon'),
        ('bool_mig_poliester', 'mig_poliester', 'migration_polyester'),
        ('bool_mig_acrilico', 'mig_acrilico', 'migration_acrylic'),
        ('bool_mig_lana', 'mig_lana', 'migration_wool'),
        ('bool_frote_seco', 'frote_seco', 'colorfastness_to_dry_rubbing'),
        ('bool_frote_humedo', 'frote_humedo', 'colorfastness_to_wet_rubbing'),
    )

    name = fields.Char(string='Referencia', required=True, copy=False, default='New', index=True)
    fecha_eval = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    batch_id = fields.Many2one('mrp.workorder.batch', string='Partida', required=True, ondelete='cascade', index=True)

    cambio_color_grado = fields.Float(string='Cambio de color grado', digits=(16, 4), required=True)
    mig_acetato = fields.Float(string='Migracion Acetato', digits=(16, 4), required=True)
    mig_algodon = fields.Float(string='Migracion Algodon', digits=(16, 4), required=True)
    mig_nylon = fields.Float(string='Migracion Nylon', digits=(16, 4), required=True)
    mig_poliester = fields.Float(string='Migracion Poliester', digits=(16, 4), required=True)
    mig_acrilico = fields.Float(string='Migracion Acrilico', digits=(16, 4), required=True)
    mig_lana = fields.Float(string='Migracion Lana', digits=(16, 4), required=True)
    frote_seco = fields.Float(string='Frote Seco', digits=(16, 4), required=True)
    frote_humedo = fields.Float(string='Frote Humedo', digits=(16, 4), required=True)

    bool_cambio_color_grado = fields.Boolean()
    bool_mig_acetato = fields.Boolean()
    bool_mig_algodon = fields.Boolean()
    bool_mig_nylon = fields.Boolean()
    bool_mig_poliester = fields.Boolean()
    bool_mig_acrilico = fields.Boolean()
    bool_mig_lana = fields.Boolean()
    bool_frote_seco = fields.Boolean()
    bool_frote_humedo = fields.Boolean()
    state = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('nodata', 'No Data'),
    ], string='Resultado', compute='_compute_result_state', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = seq.next_by_code('qc.wash.fastness.eval') or 'New'
        records = super().create(vals_list)

        laboratorio_model = self.env['qc.lab.record']
        for rec in records:
            exists = laboratorio_model.search([('solidez_lavado_eval_id', '=', rec.id)], limit=1)
            if exists:
                continue
            laboratorio_model.create({
                'batch_id': rec.batch_id.id,
                'fecha_eval': rec.fecha_eval,
                'user_id': rec.user_id.id,
                'test_type': 'solidez_lavado',
                'result_state': 'pasa',
                'solidez_lavado_eval_id': rec.id,
            })
        return records

    @api.model
    def action_tablet_get_partidas(self, query='', limit=50):
        return self.env['qc.dimstab.eval'].action_tablet_get_partidas(query, limit)

    def write(self, vals):
        res = super().write(vals)
        tracked_fields = set(self._TABLET_FIELDS)
        if tracked_fields.intersection(vals.keys()):
            laboratorio_records = self.env['qc.lab.record'].search([
                ('solidez_lavado_eval_id', 'in', self.ids),
            ])
            if laboratorio_records:
                laboratorio_records._sync_result_lines()
        return res

    def action_print_report(self):
        self.ensure_one()

        laboratorio_model = self.env['qc.lab.record']
        record = laboratorio_model.search([
            ('solidez_lavado_eval_id', '=', self.id),
        ], limit=1)

        if not record:
            record = laboratorio_model.create({
                'batch_id': self.batch_id.id,
                'fecha_eval': self.fecha_eval,
                'user_id': self.user_id.id,
                'test_type': 'solidez_lavado',
                'result_state': 'pasa',
                'solidez_lavado_eval_id': self.id,
            })

        return record.action_print_report()

    @api.model
    def action_tablet_finalize(self, batch_id, values):
        pedido_line = self.env['mrp.workorder.batch'].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_('Seleccione una partida valida.'))

        vals = {
            'batch_id': pedido_line.id,
            'user_id': self.env.user.id,
        }
        for field_name in self._TABLET_FIELDS:
            raw = (values or {}).get(field_name, '')
            if raw in (None, ''):
                raise UserError(_('Complete el campo %s.') % field_name)
            try:
                vals[field_name] = float(raw)
            except (TypeError, ValueError):
                raise UserError(_('El valor de %s no es numerico.') % field_name)

        rec = self.create(vals)

        laboratorio_records = self.env['qc.lab.record'].search([('solidez_lavado_eval_id', '=', rec.id)])
        if laboratorio_records:
            laboratorio_records._sync_result_lines()

        return {'ok': True, 'id': rec.id, 'name': rec.name}

    @api.depends(
        'cambio_color_grado',
        'mig_acetato',
        'mig_algodon',
        'mig_nylon',
        'mig_poliester',
        'mig_acrilico',
        'mig_lana',
        'frote_seco',
        'frote_humedo',
        'batch_id',
        'batch_id.color_code',
    )
    def _compute_result_state(self):
        for rec in self:
            result = 'pass'
            for bool_field, _rec_field, _lab_field in self._RESULT_RULES:
                rec[bool_field] = True
            labdev = rec.batch_id.lab_dev_line_id
            if not labdev:
                labdev = self.env['lab.dev.line'].search([
                    ('color_code', '=', rec.batch_id.color_code),
                ], limit=1)
            washing = labdev.colorfastness_washing_id

            if not washing:
                result = 'nodata'
            else:
                for bool_field, rec_field, lab_field in self._RESULT_RULES:
                    minimum_required = washing[lab_field]
                    if minimum_required and rec[rec_field] < minimum_required:
                        rec[bool_field] = False

            if any(not rec[bool_field] for bool_field, _rec_field, _lab_field in self._RESULT_RULES):
                result = 'fail'
            rec.state = result
