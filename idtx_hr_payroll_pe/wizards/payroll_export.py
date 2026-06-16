# -*- coding: utf-8 -*-
"""Exportación estructurada de planilla para PLAME (SUNAT) y AFPNet (SBS/AFP).

Genera un CSV con los datos por trabajador y concepto. NO es el archivo binario
oficial del PDT (cuyo layout es versionado por SUNAT/SBS); es un export de datos
correcto y legible que el contador carga/adapta al PDT. Cuando se disponga del
layout/sample exacto, la serialización final se ajusta aquí.
"""
import base64
import csv
import io

from odoo import models, fields, _


class L10nPePayrollExportWizard(models.TransientModel):
    _name = 'l10n.pe.payroll.export.wizard'
    _description = 'Exportar Planilla (PLAME / AFPNet)'

    company_id = fields.Many2one(
        'res.company', string='Empresa',
        default=lambda self: self.env.company, required=True)
    date_from = fields.Date(string='Desde', required=True)
    date_to = fields.Date(string='Hasta', required=True)
    export_type = fields.Selection(
        selection=[
            ('plame', 'PLAME - conceptos por trabajador'),
            ('afpnet', 'AFPNet - aportes AFP'),
        ],
        string='Tipo de Exportación', default='plame', required=True)
    file = fields.Binary(string='Archivo', readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    def _get_payslips(self):
        return self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', self.date_from),
            ('date_to', '<=', self.date_to),
            ('state', 'not in', ('draft', 'cancel')),
        ])

    def _build_plame_csv(self, payslips):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow([
            'RUC_Empleador', 'Periodo', 'Tipo_Doc', 'Nro_Doc', 'Trabajador',
            'Cod_Concepto_PLAME', 'Cod_Regla', 'Concepto', 'Monto',
        ])
        for slip in payslips:
            emp = slip.employee_id
            period = slip.date_to and slip.date_to.strftime('%Y%m') or ''
            for line in slip.line_ids:
                if not line.total:
                    continue
                w.writerow([
                    slip.company_id.vat or '',
                    period,
                    '01',  # 01 = DNI (ajustar según tipo de documento real)
                    emp.identification_id or '',
                    emp.name or '',
                    line.salary_rule_id.l10n_pe_plame_concept or '',
                    line.code or '',
                    line.name or '',
                    '%.2f' % line.total,
                ])
        return buf.getvalue()

    def _build_afpnet_csv(self, payslips):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow([
            'RUC_Empleador', 'Periodo', 'AFP', 'Tipo_Doc', 'Nro_Doc', 'Trabajador',
            'Rem_Asegurable', 'Aporte_Fondo', 'Comision', 'Prima_Seguro',
        ])

        def _line(slip, code):
            ln = slip.line_ids.filtered(lambda l: l.code == code)[:1]
            return abs(ln.total) if ln else 0.0

        for slip in payslips:
            emp = slip.employee_id
            if emp.pension_system != 'afp' or not emp.afp_id:
                continue
            period = slip.date_to and slip.date_to.strftime('%Y%m') or ''
            w.writerow([
                slip.company_id.vat or '',
                period,
                emp.afp_id.name or '',
                '01',
                emp.identification_id or '',
                emp.name or '',
                '%.2f' % _line(slip, 'GROSS'),
                '%.2f' % _line(slip, 'AFP_APORTE'),
                '%.2f' % _line(slip, 'AFP_COMISION'),
                '%.2f' % _line(slip, 'AFP_SEGURO'),
            ])
        return buf.getvalue()

    def action_generate(self):
        self.ensure_one()
        payslips = self._get_payslips()
        if self.export_type == 'afpnet':
            content = self._build_afpnet_csv(payslips)
            name = 'afpnet'
        else:
            content = self._build_plame_csv(payslips)
            name = 'plame'
        data = content.encode('utf-8-sig')  # BOM para Excel
        self.file = base64.b64encode(data)
        self.filename = '%s_%s_%s.csv' % (
            name,
            self.date_from.strftime('%Y%m%d') if self.date_from else '',
            self.date_to.strftime('%Y%m%d') if self.date_to else '',
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
