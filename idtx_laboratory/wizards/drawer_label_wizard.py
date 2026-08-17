# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LabDrawerLabelWizard(models.TransientModel):
    _name = 'lab.drawer.label.wizard'
    _description = 'Imprimir etiquetas de cajón'

    drawers = fields.Char(
        string='Cajones', required=True,
        help='Cajones a imprimir. Separa por coma o espacio (A, B, C) '
             'o usa un rango (A-F). Se expande automáticamente.')
    copies = fields.Integer(string='Copias', default=1, required=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)

    def _parse_drawers(self):
        """Convierte el texto libre en una lista de cajones (en mayúscula,
        sin repetir, respetando el orden). Soporta rangos tipo 'A-F'."""
        self.ensure_one()
        raw = (self.drawers or '').upper()
        tokens = [t for t in re.split(r'[,\s]+', raw) if t]
        result = []
        for tok in tokens:
            m = re.fullmatch(r'([A-Z])\s*-\s*([A-Z])', tok)
            if m:
                start, end = ord(m.group(1)), ord(m.group(2))
                step = 1 if start <= end else -1
                for code in range(start, end + step, step):
                    result.append(chr(code))
            else:
                result.append(tok)
        # Dedup preservando orden.
        seen = set()
        unique = []
        for d in result:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    def action_print(self):
        self.ensure_one()
        drawers = self._parse_drawers()
        if not drawers:
            raise UserError(_('Indica al menos un cajón.'))
        if self.copies < 1:
            raise UserError(_('Las copias deben ser al menos 1.'))
        ip = (self.company_id.zpl_printer_ip or '').strip()
        if not ip:
            raise UserError(_('La compañía "%s" no tiene configurada una '
                              'impresora de códigos de barras (IP). '
                              'Configúrala en Ajustes.') % self.company_id.name)
        zpl = ''.join(
            self._build_drawer_zpl(d)
            for d in drawers
            for _copy in range(self.copies))
        self.env['color.recipe']._print_zpl_to_network(zpl, ip)
        return {'type': 'ir.actions.act_window_close'}

    def _build_drawer_zpl(self, letter):
        """Etiqueta de cajón: letra grande centrada + código de barras
        (contiene la letra) centrado abajo."""
        text = (letter or '').replace('^', ' ').replace('~', ' ')[:6]
        # Letra grande centrada: se usa ^FB para centrar el texto en 600 dots.
        # Barcode Code128 forzado a subset B (">:") para ancho determinista y
        # centrado por posición X calculada (11 módulos/carácter + 35).
        module = 3
        bar_width = (11 * len(text) + 35) * module
        bar_x = max(0, (600 - bar_width) // 2)
        return f"""^XA
^CI28
^PW600
^LL400
^FO0,20^A0N,34,34^FB600,1,0,C,0^FDCajón^FS
^FO0,70^A0N,220,200^FB600,1,0,C,0^FD{text}^FS
^FO{bar_x},300^BY{module}^BCN,70,Y,N,N^FD>:{text}^FS
^XZ"""
