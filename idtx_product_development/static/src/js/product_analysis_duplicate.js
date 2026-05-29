/** @odoo-module **/
/**
 * Intercepta el boton "Duplicar" del engranaje (cog menu) en formularios
 * de product.analysis. Si el registro tiene 2+ weaving_data_ids, en vez
 * de llamar al copy() estandar (que copia todo) abre un wizard donde el
 * usuario selecciona cuales weaving_data copiar.
 *
 * Para 0 o 1 weaving_data, deja pasar el flujo estandar (copia directa
 * sin friccion).
 */
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    async duplicateRecord() {
        const root = this.model.root;
        if (root && root.resModel === "product.analysis") {
            const weaving = root.data?.weaving_data_ids;
            // En vista form, weaving_data_ids es un x2many record list.
            // .records es el array de lineas cargadas. Si hay >1
            // abrimos el wizard.
            const count = (weaving && weaving.records && weaving.records.length) || 0;
            if (count > 1 && root.resId) {
                const actionService = this.env.services.action;
                await actionService.doAction({
                    type: "ir.actions.act_window",
                    name: "Duplicar Analisis",
                    res_model: "product.analysis.copy.wizard",
                    view_mode: "form",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        default_source_id: root.resId,
                    },
                });
                return;
            }
        }
        return super.duplicateRecord(...arguments);
    },
});
