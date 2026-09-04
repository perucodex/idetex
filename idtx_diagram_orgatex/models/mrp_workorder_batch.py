import base64
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM_SHARED_PATH = 'idtx_diagram_orgatex.shared_path'
DEFAULT_SHARED_PATH = '/mnt/sysvol/OT/HISTORY'


class MrpWorkorderBatch(models.Model):
    """Diagrama de temperatura del teñido de la partida, leído del histórico
    de ORGATEX. Antes colgaba de control.pedido.line (TEXPLUS)."""
    _inherit = 'mrp.workorder.batch'

    diagram_ids = fields.One2many('diagram.orgatex', 'batch_id', string='Diagramas ORGATEX')
    diagram_count = fields.Integer(compute='_compute_diagram_count')

    @api.depends('diagram_ids')
    def _compute_diagram_count(self):
        for rec in self:
            rec.diagram_count = len(rec.diagram_ids)

    def _diagram_shared_path(self):
        path = self.env['ir.config_parameter'].sudo().get_param(PARAM_SHARED_PATH)
        return (path or '').strip() or DEFAULT_SHARED_PATH

    def _diagram_dyelot_numbers(self):
        """Dyelots que pueden corresponder a la partida: el registrado al
        enviar la receta desde Odoo y, si no, el calculado con la misma
        convención (dígitos de la partida + cantidad de reprocesos)."""
        self.ensure_one()
        numbers = []
        if self.orgatex_dyelot:
            numbers.append(self.orgatex_dyelot)
        try:
            computed = self._orgatex_dyelot_number()
        except UserError:
            computed = None
        if computed and computed not in numbers:
            numbers.append(computed)
        return numbers

    def action_create_diagram(self):
        self.ensure_one()
        dyelots = self._diagram_dyelot_numbers()
        if not dyelots:
            raise UserError(_("La partida %s no tiene un dyelot ORGATEX que buscar.") % self.name)

        shared_path = self._diagram_shared_path()
        if not os.path.isdir(shared_path):
            raise UserError(_("La carpeta de histórico de ORGATEX %s no es accesible.") % shared_path)

        conn = self._orgatex_connect()
        try:
            cursor = conn.cursor()
            marks = ', '.join('?' for _d in dyelots)
            cursor.execute(
                f"SELECT Dyelot, DyelotRefNo FROM Dyelots WHERE Dyelot IN ({marks})",
                dyelots)
            rows = cursor.fetchall()
            cursor.close()
        finally:
            conn.close()

        if not rows:
            raise UserError(_("No se encontró en ORGATEX ningún dyelot para la partida %(batch)s "
                              "(se buscó: %(dl)s).", batch=self.name, dl=', '.join(dyelots)))

        from . import diagram_parser

        Diagram = self.env['diagram.orgatex']
        created = 0
        for row in rows:
            dyelot = str(row.Dyelot or '').strip()
            ref_str = str(row.DyelotRefNo or '').strip()
            if not ref_str or ref_str == 'None':
                _logger.info("Diagrama ORGATEX: dyelot %s aún sin DyelotRefNo", dyelot)
                continue
            target_dir = os.path.join(shared_path, "HS%sxxx" % ref_str[:3])
            prg_path = os.path.join(target_dir, "BP%s.prg" % ref_str)
            log_path = os.path.join(target_dir, "PR%s.log" % ref_str)
            if not (os.path.isfile(prg_path) and os.path.isfile(log_path)):
                _logger.warning("Diagrama ORGATEX: faltan archivos para ref %s (%s / %s)",
                                ref_str, prg_path, log_path)
                continue
            try:
                with open(prg_path, 'rb') as f_prg, open(log_path, 'rb') as f_log:
                    img_bytes = diagram_parser.generate_diagram_from_files(f_prg.read(), f_log.read())
            except Exception as exc:
                _logger.error("Diagrama ORGATEX: error generando ref %s: %s", ref_str, exc)
                continue
            vals = {
                'batch_id': self.id,
                'dyelot': dyelot,
                'ref_no': ref_str,
                'diagram_image': base64.b64encode(img_bytes),
            }
            existing = self.diagram_ids.filtered(lambda d: d.ref_no == ref_str)
            if existing:
                existing.write(vals)
            else:
                Diagram.create(vals)
            created += 1

        if not created:
            raise UserError(_("ORGATEX tiene el dyelot pero aún no hay archivos de diagrama "
                              "válidos (.prg/.log) para la partida %s.") % self.name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Diagramas actualizados'),
                'message': _('%(n)s diagrama(s) para la partida %(batch)s.', n=created, batch=self.name),
                'sticky': False,
            },
        }
