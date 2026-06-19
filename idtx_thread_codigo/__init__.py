# -*- coding: utf-8 -*-
import logging

from . import models

_logger = logging.getLogger(__name__)


# def post_init_hook(env):
#     """Al instalar, importa desde SITPRO.codigohilocrud los hilados con código
#     regenerable y catálogos presentes (ver _import_clean_from_sitpro). Si SITPRO
#     no está accesible, registra el error pero NO aborta la instalación."""
#     try:
#         env['idtx.thread.code']._import_clean_from_sitpro()
#     except Exception:
#         _logger.exception(
#             "post_init_hook: no se pudo importar hilados desde SITPRO "
#             "(la instalación continúa).")
