/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState, onMounted, useRef } from "@odoo/owl";

export class SelectScaleDialog extends ConfirmationDialog {

    static template = "idtx_mrp_shop.SelectScaleDialog";
    static props = {
        ...ConfirmationDialog.props,
        body: { type: String, optional: true },
        scales: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        equipments: { type: Array, optional: true },
        employee_ids: { type: Array, optional: true },
        equipment_ids: { type: Array, optional: true },
        disabled: { type: Array, optional: true },
        active: { type: Array, optional: true },
        radioMode: { type: Boolean, default: false, optional: true },
        showWarning: { type: Boolean, default: false, optional: true },
        selectedEmployee: { type: [Number, String], optional: true },   
        selectedEquipment: { type: [Number, String], optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.scales = this.props.scales || [];
        this.employees = this.props.employees || [];    
        this.equipments = this.props.equipments || [];
        this.state = useState({
            selectedEmployee: this.props.selectedEmployee || "",
            selectedEquipment: this.props.selectedEquipment || "",
            selectedMode: "manual",
            selectedScaleId: null,
            manualWeight: "",
            isManualAuthorized: false,

            // 👇 NUEVO: auth dentro del dialog
            authLogin: "",
            authPassword: "",
            authError: "",
            isAuthChecking: false,
        });
        this.isDisplayStandalone = isDisplayStandalone();

        this.manualInputRef = useRef("manualInput");

        // 👇 NUEVO: refs para auth
        this.authLoginRef = useRef("authLogin");
        this.authPasswordRef = useRef("authPassword");

        onMounted(() => {
            if (this.manualInputRef.el) {
                this.manualInputRef.el.focus();
                this.manualInputRef.el.select();
            }
        });

        onWillStart(async () => {
            if (!this.scales.length) {
                await this._loadScales();
            }
            if (!this.employees.length) {
                await this._loadEmployees();
            }
            if (!this.equipments.length) {
                await this._loadEquipments();
            }

            // 👇 seleccionar primera balanza por defecto
            if (this.scales.length && !this.state.selectedScaleId) {
                this.state.selectedMode = "scale";
                this.state.selectedScaleId = this.scales[0].id;
            }

            // 👇 NUEVO: recuperar autorización desde la sesión (persiste hasta logout)
            try {
                const ok = await this.ormService.call("res.users", "is_manual_access_enabled", []);
                this.state.isManualAuthorized = !!ok;
            } catch (e) {
                // si no existe el método aún o falla, no rompe el dialog
                this.state.isManualAuthorized = false;
            }
        });
    }

    get appName() {
        return encodeURIComponent(this.menu.getCurrentApp().name);
    }
    
    get isConfirmEnabled() {
        if (this.state.selectedMode === "scale") {
            return !!this.state.selectedScaleId;
        }
        // 👇 manual requiere autorización
        if (!this.state.isManualAuthorized) {
            return false;
        }
        const w = parseFloat((this.state.manualWeight || ""));
        return !isNaN(w) && w > 0;
    }

    async selectManual() {
        this.state.selectedMode = "manual";
        this.state.selectedScaleId = null;
        this.state.manualWeight = "";
        this.state.authError = "";
        this.state.isAuthChecking = false;

        // Si ya está autorizado en sesión, enfocamos el input manual.
        // Si no, enfocamos el usuario.
        setTimeout(() => {
            if (this.state.isManualAuthorized) {
                if (this.manualInputRef.el) {
                    this.manualInputRef.el.focus();
                    this.manualInputRef.el.select();
                }
            } else {
                if (this.authLoginRef.el) {
                    this.authLoginRef.el.focus();
                    this.authLoginRef.el.select();
                }
            }
        }, 0);
    }

    // 👇 NUEVO: validar credenciales (sin prompt)
    async confirmManualAuth() {
        if (!this.state.authLogin || !this.state.authPassword) return;

        this.state.isAuthChecking = true;
        this.state.authError = "";

        try {
            await this.ormService.call("res.users", "validate_manual_access", [this.state.authLogin, this.state.authPassword]);

            this.state.isManualAuthorized = true;
            this.state.authPassword = ""; // limpiar password en memoria

            setTimeout(() => {
                if (this.manualInputRef.el) {
                    this.manualInputRef.el.focus();
                    this.manualInputRef.el.select();
                }
            }, 0);

        } catch (e) {
            this.state.isManualAuthorized = false;
            this.state.authError = _t("Acceso denegado: se requiere MRP Manager.");
        } finally {
            this.state.isAuthChecking = false;
        }
    }

    // 👇 NUEVO: Enter para validar auth
    onAuthKeyDown(ev) {
        if (ev.key === "Enter") {
            this.confirmManualAuth();
        }
    }

    // 👇 NUEVO: desactivar manual (borra sesión y vuelve a pedir credenciales)
    async deactivateManual() {
        try {
            await this.ormService.call("res.users", "disable_manual_access", []);
        } catch (e) {
            // no rompe si no existe aún
        }
        this.state.isManualAuthorized = false;
        this.state.manualWeight = "";
        this.state.authLogin = "";
        this.state.authPassword = "";
        this.state.authError = "";
        this.state.isAuthChecking = false;

        // se queda en manual, mostrando auth form
        this.state.selectedMode = "manual";

        setTimeout(() => {
            if (this.authLoginRef.el) {
                this.authLoginRef.el.focus();
                this.authLoginRef.el.select();
            }
        }, 0);
    }

    onManualInput(ev) {
        let v = ev.target.value;
        v = v.replace(/,/g, "");
        v = v.replace(/[^0-9.]/g, "");
        v = v.replace(/^([^.]*\.)|\./g, (m, g1) => g1 || "");
        this.state.manualWeight = v;
    }

    onInputKeyDown(ev) {
        if (ev.key === "Enter" && this.isConfirmEnabled) {
            this.confirm();
        }
    }

    selectScale(scale) {
        this.state.selectedMode = "scale";
        this.state.selectedScaleId = scale.id;

        // 👇 NO reseteamos isManualAuthorized (debe persistir en la sesión)
        this.state.manualWeight = "";
        this.state.authError = "";
        this.state.isAuthChecking = false;
        this.state.authPassword = ""; // por seguridad
    }

    confirm() {
        if (!this.state.selectedEmployee) {
            this.notification.add(_t("You must select an employee."), { type: "danger" });
            return;
        }
        if (!this.state.selectedEquipment) {
            this.notification.add(_t("You must select an equipment."), { type: "danger" });
            return;
        }
        const payload = {
            scale_id: this.state.selectedMode === "scale" ? this.state.selectedScaleId : false,
            employee_id: this.state.selectedEmployee || false,
            equipment_id: this.state.selectedEquipment || false,
            manual_weight: (this.state.selectedMode === "manual" && this.state.isManualAuthorized)
                ? parseFloat(this.state.manualWeight)
                : false,
        };
        this.props.confirm(payload);
        this.props.close();
    }

    async _loadScales() {
        const scales = await this.ormService.searchRead("scale.registry", [], ["equipment_id"]);
        const equipmentIds = scales.map(s => s.equipment_id?.[0]).filter(Boolean);

        const equipments = await this.ormService.read("maintenance.equipment", equipmentIds, ["name"]);
        const equipmentMap = Object.fromEntries(equipments.map(e => [e.id, e.name]));
        
        this.scales = scales.map(s => ({
            ...s,
            equipment_name: equipmentMap[s.equipment_id?.[0]] || "",
        }));
        
        if (!this.scales.length) {
            this.notification.add(
                _t("No scales are available, please create one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEmployees() {
        const employee_ids = this.props.employee_ids || [];
        this.employees = await this.ormService.searchRead("hr.employee", [['id','in',employee_ids]], ["name"]);
        if (!this.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEquipments() {
        const equipment_ids = this.props.equipment_ids || [];
        this.equipments = await this.ormService.searchRead("maintenance.equipment", [['id','in',equipment_ids]], ["name"]);
        if (!this.equipments.length) {
            this.notification.add(
                _t("No equipments are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }
}
