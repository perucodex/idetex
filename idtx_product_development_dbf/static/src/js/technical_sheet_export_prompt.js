/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    async beforeExecuteActionButton(clickParams) {
        if (
            this.props.resModel === "technical.sheet" &&
            clickParams.name === "action_export_to_foxpro"
        ) {
            const currentPrefix = (this.model.root.data.foxpro_article_prefix || "").trim().toUpperCase();
            let prefix = currentPrefix;
            if (!/^[MPS]$/.test(prefix)) {
                const input = window.prompt("Ingrese el prefijo para exportar: M, P o S", currentPrefix || "P");
                if (input === null) {
                    return false;
                }
                prefix = input.trim().toUpperCase();
            }
            if (!/^[MPS]$/.test(prefix)) {
                window.alert("Debe ingresar una sola letra valida: M, P o S.");
                return false;
            }
            clickParams.buttonContext = {
                ...(clickParams.buttonContext || {}),
                foxpro_article_prefix: prefix,
            };
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});