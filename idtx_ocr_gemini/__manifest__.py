# -*- coding: utf-8 -*-
{
    'name': "OCR via Google Gemini API",
    'summary': "Reemplaza IAP Extract usando Google Gemini Vision (free tier). Mejor calidad y latencia que cualquier solucion on-prem CPU.",
    'description': """
Procesa extractos bancarios, facturas y rendiciones de gasto enviando
el PDF/imagen directo a Google Gemini API (gemini-2.5-flash u otro).
Devuelve datos estructurados con calidad estado-arte.

Cubre 3 modelos extract.mixin:
  * account.bank.statement
  * account.move (facturas / boletas)
  * hr.expense

Setup:
  1. Obtener API key en https://aistudio.google.com (free tier)
  2. Configurar idtx_ocr_gemini.api_key en Ajustes Tecnicos > Parametros
  3. Subir un documento -> Gemini lo procesa en 3-8s/pagina

Free tier (2026):
  - 1500 requests/dia, 1M tokens/dia
  - Sin tarjeta de credito requerida
  - Mas que suficiente para contabilidad SMB

Dependencias Python:
  pip install requests pypdf
""",
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Accounting',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'iap_extract',
        'hr_expense_extract',
        'account_invoice_extract',
        'account_bank_statement_extract',
        'pc_l10n_pe_vat_sunat',
    ],
    'external_dependencies': {
        'python': ['requests', 'pypdf'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/iap_account_data.xml',
        'data/ir_config_parameter_data.xml',
        'wizards/pdf_password_wizard_views.xml',
    ],
    'auto_install': False,
    'application': False,
}
