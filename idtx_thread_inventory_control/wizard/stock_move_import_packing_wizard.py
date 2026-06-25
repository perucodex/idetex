# -*- coding: utf-8 -*-
from odoo import models, fields


class StockMoveImportPackingWizard(models.TransientModel):
    _name = 'stock.move.import.packing.wizard'
    _description = 'Stock Move Import Packing Wizard'
