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