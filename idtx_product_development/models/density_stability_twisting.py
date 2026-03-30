from odoo import models, fields, api, _, tools

class DensityStabilityTwisting(models.Model):
    _name = 'density.stability.twisting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Density Stability Twisting Data'

    name = fields.Char('Name', required=True, default=lambda self: _('New'), copy=False)
    density = fields.Float('Density')
    width = fields.Float('Width')
    width_shrinkage_from = fields.Float('Width Shrinkage From')
    width_shrinkage_to = fields.Float('Width Shrinkage To')
    length_shrinkage_from = fields.Float('Length Shrinkage From')
    length_shrinkage_to = fields.Float('Length Shrinkage To')
    tilt_wash = fields.Float('Tilt Wash')
    twist = fields.Float('Twist')

    wash_cycle_type = fields.Selection([
        ('normal', 'Normal'),
        ('delicate', 'Delicate / Gentle'),
        ('permanent_press', 'Permanent Press'),
        ('hand', 'Hand Wash'),
        ('not_allowed', 'Do Not Wash'),
    ], string='Wash Cycle Type', default='normal')
    wash_temperature_level = fields.Selection([
        ('cold', '30°C'),
        ('warm', '40°C'),
        ('hot', '50°C'),
        ('very', '60°C'),
        ('super', '70°C'), 
        ('hyper', '95°C'),
    ], string='Wash Temperature Level', default='warm')
    bleaching = fields.Selection([
        ('any', 'Any Bleach'),
        ('only', 'Only Non-Chlorine / Oxygen Bleach'),
        ('not_allowed', 'Do Not Bleach'),
    ], string='Bleaching')
    drying_condition = fields.Selection([
        ('tumble_dry_normal', 'Tumble Dry Normal (Ai)'),
        ('tumble_dry_delicate', 'Tumble Dry Delicate (Aii)'),
        ('tumble_dry_permanent_press', 'Tumble Dry Permanent Press (Aiii)'),
        ('line_hang_dry', 'Line/Hang Dry'),
        ('drip_dry', 'Drip Dry'),
        ('dry_flat', 'Dry Flat'),
        ('not_allowed', 'Do Not Tumble Dry'),
    ], string='Drying Condition', default='tumble_dry_normal')
    in_the_shade = fields.Boolean('Dry in the Shade')
    drying_heat = fields.Selection([
        ('any', 'Any Heat'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('not_allowed', 'No Heat Air'),
    ], string='Drying Heat', default='medium')
    ironing = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('not_allowed', 'Do Not Iron'),
    ], string='Ironing')
    iron_steam = fields.Boolean('No Steam', default=False)
    profesional_textile_care_dry = fields.Selection([
        ('dry_clean_normal_any', 'Dry Clean Normal Any Solvent'),
        ('dry_clean_normal_f', 'Dry Clean Normal Gentle Solvent Petroleum or Silicone Solvent Only'),
        ('dry_clean_mild_any', 'Dry Clean Mild Any Solvent'),
        ('dry_clean_mild_f', 'Dry Clean Mild Gentle Solvent Petroleum or Silicone Solvent Only'),
        ('not_allowed', 'Do Not Dry Clean'),
    ], string='Dryclean')
    profesional_textile_care_wet = fields.Selection([
        ('wet_clean_n', 'Wet Clean Normal'),
        ('wet_clean_l', 'Wet Clean Mild'),
        ('wet_clean_h', 'Wet Clean Very Mild'),
        ('not_allowed', 'Do Not Wet Clean'),
    ], string='Wetclean')
    do_not_wring = fields.Boolean('Do Not Wring', default=False)
    laundering_ballast_type = fields.Selection([
        ('type_1', 'Type 1 - 100% Cotton'),
        ('type_3', 'Type 3 - 50% Cotton / 50% Polyester ± 3%'),
    ], string='Laundering Ballast Type', default='type_1')
    separately = fields.Boolean('Wash Separately')
    with_like_colors = fields.Boolean('Wash With Like Colors')
    wash_inside_out = fields.Boolean('Wash Inside Out')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], string='State', default='draft', tracking=True)
    care_wash_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Wash Care Icon URL')
    care_dry_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Dry Care Icon URL')
    care_bleaching_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Bleaching Care Icon URL')
    care_drying_heat_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Drying Heat Care Icon URL')
    care_ironing_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Ironing Care Icon URL')
    care_iron_steam_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Iron Steam Care Icon URL')
    care_profesional_dry_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Professional Dry Care Icon URL')
    care_profesional_wet_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Professional Wet Care Icon URL')
    care_do_not_wring_icon_url = fields.Char(compute='_compute_care_icon_urls', string='Do Not Wring Care Icon URL')
    care_icon_preview_html = fields.Html(compute='_compute_care_icon_preview_html', sanitize=False, string='Care Icons Preview')

    def _care_icon_url(self, filename):
        try:
            with tools.file_open(f"idtx_product_development/static/src/img/care/{filename}", mode="rb"):
                pass
            return f"/idtx_product_development/static/src/img/care/{filename}"
        except OSError:
            return False

    @api.depends(
        'wash_cycle_type',
        'wash_temperature_level',
        'bleaching',
        'drying_condition',
        'in_the_shade',
        'drying_heat',
        'ironing',
        'iron_steam',
        'profesional_textile_care_dry',
        'profesional_textile_care_wet',
        'do_not_wring',
    )
    def _compute_care_icon_urls(self):
        for rec in self:
            wash_cycle_key = (rec.wash_cycle_type or '')
            wash_temp_key = (rec.wash_temperature_level or '')
            bleaching_key = (rec.bleaching or '')
            dry_key = (rec.drying_condition or '')
            drying_heat_key = (rec.drying_heat or '')
            ironing_key = (rec.ironing or '')
            profesional_dry_key = (rec.profesional_textile_care_dry or '')
            profesional_wet_key = (rec.profesional_textile_care_wet or '')

            if not wash_temp_key or wash_cycle_key in ('hand', 'not_allowed'):
                wash_temp_key = ''
            else:
                wash_temp_key = '_' + wash_temp_key

            dry_suffix = ''
            if rec.in_the_shade and dry_key in ('line_hang_dry', 'drip_dry', 'dry_flat'):
                dry_suffix = '_in_the_shade'

            if dry_key in ('line_hang_dry', 'drip_dry', 'dry_flat', 'not_allowed'):
                drying_heat_key = ''

            if not drying_heat_key or drying_heat_key == 'any':
                drying_heat_suffix = ''
            else:
                drying_heat_suffix = '_' + drying_heat_key

            rec.care_wash_icon_url = rec._care_icon_url(f"wash/wash_{wash_cycle_key}{wash_temp_key}.svg") if wash_cycle_key else False
            rec.care_dry_icon_url = rec._care_icon_url(f"dry/dry_{dry_key}{drying_heat_suffix}{dry_suffix}.svg") if dry_key else False
            rec.care_bleaching_icon_url = rec._care_icon_url(f"bleach/bleaching_{bleaching_key}.svg") if bleaching_key else False
            rec.care_drying_heat_icon_url = False
            rec.care_ironing_icon_url = rec._care_icon_url(f"iron/ironing_{ironing_key}.svg") if ironing_key else False
            rec.care_iron_steam_icon_url = rec._care_icon_url("iron/iron_steam.svg") if rec.iron_steam else False
            rec.care_profesional_dry_icon_url = rec._care_icon_url(f"profesional/dry/profesional_textile_care_dry_{profesional_dry_key}.svg") if profesional_dry_key else False
            rec.care_profesional_wet_icon_url = rec._care_icon_url(f"profesional/wet/profesional_textile_care_wet_{profesional_wet_key}.svg") if profesional_wet_key else False
            rec.care_do_not_wring_icon_url = rec._care_icon_url("dry/do_not_wring.svg") if rec.do_not_wring else False

    @api.depends(
        'care_wash_icon_url',
        'care_dry_icon_url',
        'care_bleaching_icon_url',
        'care_drying_heat_icon_url',
        'care_ironing_icon_url',
        'care_iron_steam_icon_url',
        'care_profesional_dry_icon_url',
        'care_profesional_wet_icon_url',
        'care_do_not_wring_icon_url',
        'wash_cycle_type',
        'wash_temperature_level',
        'bleaching',
        'drying_condition',
        'drying_heat',
        'ironing',
        'profesional_textile_care_dry',
        'profesional_textile_care_wet',
        'iron_steam',
        'do_not_wring',
        'separately',
        'with_like_colors',
        'wash_inside_out',
    )
    def _compute_care_icon_preview_html(self):
        for rec in self:
            selection = {
                field_name: dict(rec._fields[field_name]._description_selection(rec.env))
                for field_name in (
                    'wash_cycle_type',
                    'wash_temperature_level',
                    'bleaching',
                    'drying_condition',
                    'drying_heat',
                    'ironing',
                    'profesional_textile_care_dry',
                    'profesional_textile_care_wet',
                )
            }

            wash_cycle_label = selection['wash_cycle_type'].get(rec.wash_cycle_type, '-')
            wash_temp_label = selection['wash_temperature_level'].get(rec.wash_temperature_level, '-')
            bleaching_label = selection['bleaching'].get(rec.bleaching, '-')
            dry_label = selection['drying_condition'].get(rec.drying_condition, '-')
            ironing_label = selection['ironing'].get(rec.ironing, '-')
            profesional_dry_label = selection['profesional_textile_care_dry'].get(rec.profesional_textile_care_dry, '-')
            profesional_wet_label = selection['profesional_textile_care_wet'].get(rec.profesional_textile_care_wet, '-')
            iron_steam_label = _('No Steam') if rec.iron_steam else _('N/A')
            do_not_wring_label = _('Do Not Wring') if rec.do_not_wring else _('N/A')

            wash_text = _("Washing: %s / %s") % (wash_cycle_label, wash_temp_label)
            bleaching_text = _("Bleaching: %s") % bleaching_label
            ironing_text = _("Ironing: %s") % ironing_label
            profesional_dry_text = _("Professional care (dry): %s") % profesional_dry_label
            profesional_wet_text = _("Professional care (wet): %s") % profesional_wet_label

            dry_text = _("Drying: %s") % dry_label
            if rec.drying_condition not in ('line_hang_dry', 'drip_dry', 'dry_flat', 'not_allowed') and rec.drying_heat:
                drying_heat_label = selection['drying_heat'].get(rec.drying_heat, '-')
                dry_text = _("Drying: %s / %s") % (dry_label, drying_heat_label)

            instruction_parts = []
            if rec.wash_cycle_type:
                instruction_parts.append(wash_text)
            if rec.drying_condition:
                instruction_parts.append(dry_text)
            if rec.bleaching:
                instruction_parts.append(bleaching_text)
            if rec.ironing:
                instruction_parts.append(ironing_text)
            if rec.iron_steam:
                instruction_parts.append(_("No Steam"))
            if rec.profesional_textile_care_dry:
                instruction_parts.append(profesional_dry_text)
            if rec.profesional_textile_care_wet:
                instruction_parts.append(profesional_wet_text)
            if rec.do_not_wring:
                instruction_parts.append(_("Do Not Wring"))
            if rec.separately:
                instruction_parts.append(_("Wash Separately"))
            if rec.with_like_colors:
                instruction_parts.append(_("Wash With Like Colors"))
            if rec.wash_inside_out:
                instruction_parts.append(_("Wash Inside Out"))

            instruction_text = " / ".join(instruction_parts)

            parts = [
                "<div style='display:flex;flex-direction:column;gap:8px;min-height:70px;'>",
                "<div style='display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;'>",
            ]

            icon_items = [
                ('Wash care', rec.care_wash_icon_url, wash_text),
                ('Dry care', rec.care_dry_icon_url, dry_text),
                ('Bleaching care', rec.care_bleaching_icon_url, bleaching_text),
                ('Ironing care', rec.care_ironing_icon_url, ironing_text),
                ('Iron steam care', rec.care_iron_steam_icon_url, _("Steam: %s") % iron_steam_label),
                ('Professional dry care', rec.care_profesional_dry_icon_url, profesional_dry_text),
                ('Professional wet care', rec.care_profesional_wet_icon_url, profesional_wet_text),
                ('Do not wring care', rec.care_do_not_wring_icon_url, do_not_wring_label),
            ]

            has_any_icon = False
            for alt, icon_url, text in icon_items:
                if not icon_url:
                    continue
                has_any_icon = True
                parts.append(
                    "<div style='display:flex;flex-direction:column;align-items:center;gap:4px;'>"
                    f"<img src='{icon_url}' alt='{alt}' style='height:44px;width:auto;'/>"
                    "</div>"
                )

            if not has_any_icon:
                parts.append(f"<span style='color:#6b7280;'>{_('No icon available for the selected combination.')}</span>")
            parts.append("</div>")
            if instruction_text:
                parts.append(f"<div style='font-size:12px;color:#374151;'>{instruction_text}</div>")
            parts.append("</div>")
            rec.care_icon_preview_html = "".join(parts)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('density.stability.twisting') or _('New')
        return super().create(vals_list)
    
    def mark_done(self):
        self.state = 'done'

    def mark_draft(self):
        self.state = 'draft'

    def get_aatcc_tm135_code(self):
        self.ensure_one()
        cycle_map = {
            'normal': '(1)',
            'delicate': '(2)',
            'permanent_press': '(3)',
        }
        temp_map = {
            'cold': '(I)',
            'warm': '(III)',
            'hot': '(IV)',
            'very': '(V)',
            'super': '(VI)',
            'hyper': '(VII)',
        }
        drying_map = {
            'tumble_dry': 'A',
            'tumble_dry_normal': 'Ai',
            'tumble_dry_delicate': 'Aii',
            'tumble_dry_permanent_press': 'Aiii',
            'line_hang_dry': 'B',
            'drip_dry': 'C',
            'dry_flat': 'D',
        }
        cycle_code = cycle_map.get(self.wash_cycle_type or 'normal', '(1)')
        temp_code = temp_map.get(self.wash_temperature_level or 'warm', '(III)')
        drying_code = drying_map.get(self.drying_condition or 'line_hang_dry', 'B')
        return f"{cycle_code} {temp_code} {drying_code}"

    def get_report_wash_notes(self):
        self.ensure_one()
        temp_label = {
            'cold': '27&#176;C &#177;3&#176;C',
            'warm': '41&#176;C &#177;3&#176;C',
            'hot': '50&#176;C &#177;3&#176;C',
            'very': '60&#176;C &#177;3&#176;C',
            'super': '70&#176;C &#177;3&#176;C',
            'hyper': '95&#176;C &#177;3&#176;C',
        }
        cycle_label = {
            'normal': 'Normal',
            'delicate': 'Delicate',
            'permanent_press': 'Permanent Press',
            'hand': 'Hand Wash',
            'not_allowed': 'Do Not Wash',
        }
        drying_label = {
            'tumble_dry': 'Tumble Dry',
            'tumble_dry_normal': 'Tumble Dry Normal',
            'tumble_dry_delicate': 'Tumble Dry Delicate',
            'tumble_dry_permanent_press': 'Tumble Dry Permanent Press',
            'line_hang_dry': 'Line/Hang Dry',
            'drip_dry': 'Drip Dry',
            'dry_flat': 'Dry Flat',
        }
        ballast_label = {
            'type_1': 'Type 1 - 100% Cotton',
            'type_3': 'Type 3 - 50% Cotton / 50% Polyester &#177;3%',
        }
        return [
            {'label': 'Washing Temperature', 'value': temp_label.get(self.wash_temperature_level or 'warm', '-')},
            {'label': 'Cycle', 'value': cycle_label.get(self.wash_cycle_type or 'normal', '-')},
            {'label': 'Drying', 'value': drying_label.get(self.drying_condition or 'line_hang_dry', '-')},
            {'label': 'Ballast', 'value': ballast_label.get(self.laundering_ballast_type or 'type_1', '-')},
        ]