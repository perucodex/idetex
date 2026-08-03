from odoo import _, api, fields, models


class ControlTonoEvalLog(models.Model):
    _name = "control.tono.eval.log"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Historial Evaluación Tono"
    _order = "fecha_eval asc, id asc"
    _rec_name = "pedido_line_id"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partida = fields.Char(
        string="Partida Ref",
        related="pedido_line_id.batch",
        readonly=True,
        store=False,
    )
    cliente = fields.Char(
        string="Cliente",
        related="pedido_line_id.pedido_id.customer",
        readonly=True,
        store=False,
    )
    color = fields.Char(
        string="Color",
        related="pedido_line_id.colorname",
        readonly=True,
        store=False,
    )
    eval_group_id = fields.Many2one(
        "control.tono.eval.group",
        string="Evaluacion Grupal",
        ondelete="cascade",
        index=True,
    )
    fecha_eval = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        default=lambda self: self.env.user,
        required=True,
    )
    tono = fields.Selection(
        [("tacho", "Tacho"), ("secado", "Secado"), ("acabado", "Acabado")],
        string="Tipo de Tono",
        required=True,
    )
    motivo_tono = fields.Boolean(string="Tono")
    motivo_tacto = fields.Boolean(string="Tacto")
    motivo_apariencia = fields.Boolean(string="Apariencia")
    resultado = fields.Selection(
        [("aprobado", "APROBADO"), ("concesionado", "CONCESIONADO"), ("rechazado", "RECHAZADO"),("pendiente", "PENDIENTE")],
        string="Resultado",
        required=True,
        index=True,
        tracking=True,
    )
    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono", readonly=True)
    barcodreo = fields.Char(string="Reprocess", readonly=True)
    user_has_group_quality_manager = fields.Boolean(compute="_compute_user_has_group_quality_manager")

    def _get_quality_manager_users(self):
        group = self.env.ref("quality.group_quality_manager", raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        return group.all_user_ids.filtered(lambda user: user.active and user.partner_id)

    def _get_sale_manager_users(self):
        group = self.env.ref("sales_team.group_sale_manager", raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        return group.all_user_ids.filtered(lambda user: user.active and user.partner_id)

    def _get_salesperson_user(self):
        self.ensure_one()
        salesperson = self.pedido_line_id.pedido_id.user_id
        return salesperson.filtered(lambda user: user.active and user.partner_id)

    def _get_internal_notification_partners(self):
        self.ensure_one()
        return (self._get_quality_manager_users().partner_id | self._get_salesperson_user().partner_id)

    def _get_quality_manager_notification_partners(self):
        self.ensure_one()
        return self._get_quality_manager_users().partner_id

    def _get_pending_notification_partners(self):
        self.ensure_one()
        return (
            self._get_internal_notification_partners()
            | self._get_sale_manager_users().partner_id
        )

    def _get_follower_partners(self):
        self.ensure_one()
        return self._get_pending_notification_partners()

    def _get_notification_emails(self, partners):
        emails = []
        for partner in partners.filtered(lambda partner: partner.email):
            if partner.email not in emails:
                emails.append(partner.email)
        return ",".join(emails)

    def _get_internal_notification_emails(self):
        self.ensure_one()
        return self._get_notification_emails(self._get_internal_notification_partners())

    def _get_quality_manager_notification_emails(self):
        self.ensure_one()
        return self._get_notification_emails(self._get_quality_manager_notification_partners())

    def _get_pending_notification_emails(self):
        self.ensure_one()
        return self._get_notification_emails(self._get_pending_notification_partners())

    def _get_resultado_label(self):
        self.ensure_one()
        return dict(self._fields["resultado"].selection).get(self.resultado, self.resultado)

    def _subscribe_internal_followers(self):
        for rec in self:
            partner_ids = rec._get_follower_partners().ids
            if partner_ids:
                rec.sudo().message_subscribe(partner_ids=partner_ids)

    def _post_message_from_template(self, template_xmlid, email_getter):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        for rec in self:
            if getattr(rec, email_getter)():
                rec.with_context(
                    default_composition_mode="comment",
                    default_model=rec._name,
                    default_res_ids=rec.ids,
                    default_template_id=template.id,
                    default_email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                    email_notification_allow_footer=True,
                    force_email=True,
                ).message_post_with_source(
                    template,
                    subtype_xmlid="mail.mt_comment",
                    email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                )

    def _send_pending_notification(self):
        self._post_message_from_template(
            "idtx_batch_quality.mail_template_tono_eval_pending",
            "_get_pending_notification_emails",
        )

    def _send_client_response_notification(self):
        self._post_message_from_template(
            "idtx_batch_quality.mail_template_tono_eval_client_response",
            "_get_quality_manager_notification_emails",
        )

    @api.depends_context("uid")
    def _compute_user_has_group_quality_manager(self):
        has_group = self.env.user.has_group("quality.group_quality_manager")
        for rec in self:
            rec.user_has_group_quality_manager = has_group

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._subscribe_internal_followers()
        pending_records = records.filtered(lambda rec: rec.resultado == "pendiente")
        if pending_records:
            pending_records._send_pending_notification()
        return records

    def write(self, vals):
        previous_results = {}
        if "resultado" in vals:
            previous_results = {rec.id: rec.resultado for rec in self}

        result = super().write(vals)

        if "resultado" in vals:
            changed_records = self.filtered(lambda rec: previous_results.get(rec.id) != rec.resultado)
            pending_records = changed_records.filtered(lambda rec: rec.resultado == "pendiente")
            if pending_records:
                pending_records._send_pending_notification()

            client_response_records = changed_records.filtered(lambda rec: rec.resultado in ("aprobado", "rechazado"))
            if self.env.context.get("notify_tono_eval_client_response") and client_response_records:
                client_response_records._send_client_response_notification()

        return result

    def unlink(self):
        if self.env.context.get("allow_group_eval_log_unlink"):
            return super().unlink()

        # Keep track of grouped records to clean the group lines after deleting logs.
        grouped_pairs = [
            (log.eval_group_id.id, log.pedido_line_id.id)
            for log in self
            if log.eval_group_id and log.pedido_line_id
        ]
        grouped_ids = list({group_id for group_id, _line_id in grouped_pairs})

        result = super().unlink()

        if grouped_pairs:
            line_model = self.env["control.tono.eval.group.line"]
            log_model = self.env["control.tono.eval.log"]
            for group_id, line_id in set(grouped_pairs):
                remaining = log_model.search_count([
                    ("eval_group_id", "=", group_id),
                    ("pedido_line_id", "=", line_id),
                ])
                if not remaining:
                    line_model.search([
                        ("group_id", "=", group_id),
                        ("pedido_line_id", "=", line_id),
                    ]).unlink()

            group_model = self.env["control.tono.eval.group"]
            for group in group_model.browse(grouped_ids).exists():
                has_logs = log_model.search_count([("eval_group_id", "=", group.id)])
                if not has_logs and not group.line_ids:
                    group.unlink()

        return result
    
    # =========================
    # Reporte "Evaluación de Tono en Producción" (FULL-SGCC-FO-09)
    # =========================
    def _get_print_header(self):
        """Cabecera del formato para el conjunto de registros seleccionados:
        auditor(es), fecha (o rango) en tz del usuario y la etiqueta del grupo
        de columnas (TACHO / ACABADO según los tipos seleccionados)."""
        fechas = sorted({
            fields.Datetime.context_timestamp(rec, rec.fecha_eval).date()
            for rec in self if rec.fecha_eval})
        if not fechas:
            fecha = ''
        elif fechas[0] == fechas[-1]:
            fecha = fechas[0].strftime('%d/%m/%Y')
        else:
            fecha = '%s - %s' % (fechas[0].strftime('%d/%m/%Y'),
                                 fechas[-1].strftime('%d/%m/%Y'))
        labels = dict(self._fields['tono'].selection)
        tonos = [labels[t].upper() for t in ('tacho', 'secado', 'acabado')
                 if t in set(self.mapped('tono'))]
        return {
            'auditor': ', '.join(self.user_id.sorted('name').mapped('name')),
            'fecha': fecha,
            'grupo': ' / '.join(tonos) or 'TACHO',
        }

    def _get_observacion(self):
        """Texto de la columna OBSERVACIÓN: motivos marcados (concesionado),
        reproceso y si está pendiente de respuesta del cliente."""
        self.ensure_one()
        partes = []
        if self.resultado == 'pendiente':
            partes.append(_('Pendiente respuesta cliente'))
        motivos = [label for flag, label in (
            (self.motivo_tono, _('Tono')),
            (self.motivo_tacto, _('Tacto')),
            (self.motivo_apariencia, _('Apariencia')),
        ) if flag]
        if motivos:
            partes.append(_('Motivo: %s') % ', '.join(motivos))
        # BarCodReo '0' = sin reproceso (convención TEXPLUS): no se imprime.
        if self.barcodreo and self.barcodreo.strip() not in ('0', ''):
            partes.append(_('Reproceso: %s') % self.barcodreo)
        return ' — '.join(partes)

    def _build_tono_eval_xlsx(self):
        """Excel del formato 'Evaluación de Tono en Producción' (misma
        estructura que el PDF) para los registros seleccionados. Devuelve los
        bytes del .xlsx."""
        import io
        import xlsxwriter

        header = self._get_print_header()
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Evaluación de Tono')

        borde = {'border': 1, 'valign': 'vcenter'}
        f_title = wb.add_format({**borde, 'bold': True, 'align': 'center',
                                 'font_size': 12, 'text_wrap': True})
        f_label = wb.add_format({**borde, 'bold': True, 'font_size': 8})
        f_meta = wb.add_format({**borde, 'align': 'center', 'font_size': 8})
        f_th = wb.add_format({**borde, 'bold': True, 'align': 'center',
                              'text_wrap': True, 'font_size': 9})
        f_td = wb.add_format({**borde, 'font_size': 9})
        f_check = wb.add_format({**borde, 'bold': True, 'align': 'center',
                                 'font_size': 10})
        f_fecha = wb.add_format({**borde, 'align': 'center', 'font_size': 9,
                                 'num_format': 'dd/mm/yyyy hh:mm'})

        ws.set_column('A:A', 16)   # Fecha
        ws.set_column('B:B', 12)   # Partida
        ws.set_column('C:C', 28)   # Cliente
        ws.set_column('D:D', 22)   # Color
        ws.set_column('E:G', 12)   # Aprobado / Rechazado / Concesionado
        ws.set_column('H:H', 12)   # Receta
        ws.set_column('I:I', 32)   # Observación

        # Cabecera del formato: logo de la compañía (como el PDF); si no
        # tiene logo, su nombre.
        company = self.env.company
        logo_puesto = False
        if company.logo:
            try:
                import base64
                from PIL import Image
                raw = base64.b64decode(company.logo)
                img = Image.open(io.BytesIO(raw))
                # Área combinada A1:B4 ≈ 280x76 px: escalar para que quepa.
                escala = min(240.0 / img.width, 62.0 / img.height, 1.0)
                ws.merge_range('A1:B4', '', f_title)
                ws.insert_image('A1', 'logo.png', {
                    'image_data': io.BytesIO(raw),
                    'x_scale': escala, 'y_scale': escala,
                    'x_offset': 10, 'y_offset': 8,
                })
                logo_puesto = True
            except Exception:
                pass
        if not logo_puesto:
            ws.merge_range('A1:B4', company.name, f_title)
        ws.merge_range('C1:G4', 'FORMATO\nEVALUACION DE TONO EN PRODUCCION', f_title)
        for row, (label, value) in enumerate([
                ('codigo:', 'FULL-SGCC-FO-09'),
                ('fecha:', header['fecha']),
                ('vision:', '2'),
                ('pagina:', '')]):
            ws.write(row, 7, label, f_label)
            ws.write(row, 8, value, f_meta)

        ws.merge_range('A5:C5', 'AUDITOR: %s' % header['auditor'], f_label)
        ws.merge_range('D5:G5', 'TURNO:', f_label)
        ws.merge_range('H5:I5', 'FECHA: %s' % header['fecha'], f_label)

        # Cabecera de la tabla
        ws.merge_range('A6:A7', 'FECHA', f_th)
        ws.merge_range('B6:B7', 'PARTIDA', f_th)
        ws.merge_range('C6:C7', 'CLIENTE', f_th)
        ws.merge_range('D6:D7', 'COLOR', f_th)
        ws.merge_range('E6:H6', header['grupo'], f_th)
        ws.write('E7', 'APROBADO', f_th)
        ws.write('F7', 'RECHAZADO', f_th)
        ws.write('G7', 'CONCESIONADO', f_th)
        ws.write('H7', 'RECETA', f_th)
        ws.merge_range('I6:I7', 'OBSERVACION', f_th)

        row = 7
        col_por_resultado = {'aprobado': 4, 'rechazado': 5, 'concesionado': 6}
        for rec in self.sorted('fecha_eval'):
            if rec.fecha_eval:
                # Datetime real (ordenable en Excel) en hora local del usuario.
                local = fields.Datetime.context_timestamp(
                    rec, rec.fecha_eval).replace(tzinfo=None)
                ws.write_datetime(row, 0, local, f_fecha)
            else:
                ws.write(row, 0, '', f_fecha)
            ws.write(row, 1, rec.partida or '', f_td)
            ws.write(row, 2, rec.cliente or '', f_td)
            ws.write(row, 3, rec.color or '', f_td)
            for col in (4, 5, 6):
                ws.write(row, col, '', f_check)
            check_col = col_por_resultado.get(rec.resultado)
            if check_col is not None:
                ws.write(row, check_col, '✔', f_check)
            ws.write(row, 7, rec.receta_tono or rec.receta or '', f_meta)
            ws.write(row, 8, rec._get_observacion(), f_td)
            row += 1
        # Filas en blanco para completar a mano, como el formato en papel.
        for _i in range(max(0, 18 - len(self))):
            for col in range(9):
                ws.write(row, col, '', f_td)
            row += 1

        wb.close()
        return output.getvalue()

    def action_export_tono_eval_xlsx(self):
        """Descarga el Excel del formato con los registros seleccionados
        (acción de servidor del menú de la lista). La compañía ACTIVA viaja en
        la URL: el GET del controller no hereda la compañía elegida en el
        cliente web y caería en la compañía por defecto del usuario."""
        return {
            'type': 'ir.actions.act_url',
            'url': '/idtx_batch_quality/tono_eval_xlsx?ids=%s&company_id=%s'
                   % (','.join(map(str, self.ids)), self.env.company.id),
            'target': 'self',
        }

    def action_approve(self):
        self.write({
            "motivo_tono": False,
            "motivo_tacto": False,
            "motivo_apariencia": False,
            "resultado": "aprobado",
        })

    def action_conciliate(self):
        self.write({"resultado": "concesionado"})

    def action_reject(self):
        self.write({
            "motivo_tono": False,
            "motivo_tacto": False,
            "motivo_apariencia": False,
            "resultado": "rechazado",
        })

    def action_send(self):
        self.write({"resultado": "pendiente"})

    def action_client_approve(self):
        self.with_context(notify_tono_eval_client_response=True).write({"resultado": "aprobado"})

    def action_client_reject(self):
        self.with_context(notify_tono_eval_client_response=True).write({"resultado": "rechazado"})