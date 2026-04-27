# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PrintingRecipeController(http.Controller):

    @http.route('/printing/recipe/<int:recipe_id>', type='http', auth='user', website=False)
    def printing_recipe_sheet(self, recipe_id, **kwargs):
        recipe = request.env['printing.design.rotary.line'].browse(recipe_id)
        if not recipe.exists():
            return request.not_found()

        return request.render('idtx_printing.printing_recipe_sheet_template', {
            'recipe': recipe,
        })