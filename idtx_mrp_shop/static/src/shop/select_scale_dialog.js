/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState, onMounted, useRef, onPatched } from "@odoo/owl";

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
        selectedOption: { type: [Number, String], optional: true },
        options: { type: Array, optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.scales = this.props.scales || [];
        this.employees = this.props.employees || [];    
        this.equipments = this.props.equipments || [];
        this.options = this.props.options || [];
        
        // Initialize selectedOption from props when provided (e.g., last roll)
        const initialOption = this.props.selectedOption ? String(this.props.selectedOption) : "";
        
        this.state = useState({
            selectedEmployee: this.props.selectedEmployee || "",
            selectedEquipment: this.props.selectedEquipment || "",
            selectedOption: initialOption,
            optionTouched: !!initialOption,
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
 
        // NOTE: persistent selection is restored after options are loaded in onWillStart

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
            if (!this.options.length) {
                await this._loadOptions();
            }

            // After loading options, restore persisted selection for this workorder (if any)
            try {
                const workorderId = this.props.active && this.props.active.length ? this.props.active[0] : null;
                if (workorderId) {
                    const LS_KEY = `idtx_mrp.last_selection.${workorderId}`;
                    const raw = window.localStorage.getItem(LS_KEY);
                    if (raw) {
                        const parsed = JSON.parse(raw);
                        if (!this.state.selectedEmployee && parsed.employee_id) this.state.selectedEmployee = String(parsed.employee_id);
                        if (!this.state.selectedEquipment && parsed.equipment_id) this.state.selectedEquipment = String(parsed.equipment_id);
                        if (parsed.option_id) {
                            const found = (this.options || []).some(o => String(o.id) === String(parsed.option_id));
                            if (found) {
                                this.state.selectedOption = String(parsed.option_id);
                                this.state.optionTouched = true;
                            }
                        }
                    }
                }
            } catch (e) {
                // ignore
            }
            try { console.log('SelectScaleDialog:onWillStart -> after _loadOptions selectedOption=', this.state.selectedOption, 'options=', this.options, 'isConfirmEnabled=', this.isConfirmEnabled); } catch (e) {}

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
            // Ensure confirm button reflects current state (OWL template binding will handle it)
        });

        // No DOM forcing here; rely on OWL template binding for the Confirm button.
    }

    get appName() {
        return encodeURIComponent(this.menu.getCurrentApp().name);
    }

    // (Removed DOM-forcing update method; OWL template binding controls the Confirm button.)
    
    get isConfirmEnabled() {
        // Require employee and equipment in all cases
        if (!this.state.selectedEmployee || !this.state.selectedEquipment) {
            return false;
        }

        // If options exist, require an option selection
        // if (this.options && this.options.length && (!this.state.selectedOption || !this.state.optionTouched)) {
        //     return false;
        // }

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
            try {
                if (this.state.isManualAuthorized) {
                    if (this.manualInputRef?.el) {
                        this.manualInputRef.el.focus();
                        this.manualInputRef.el.select();
                    }
                } else {
                    if (this.authLoginRef?.el) {
                        this.authLoginRef.el.focus();
                        this.authLoginRef.el.select();
                    }
                }
            } catch (e) { /* ignore */ }
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
                try {
                    if (this.manualInputRef?.el) {
                        this.manualInputRef.el.focus();
                        this.manualInputRef.el.select();
                    }
                } catch (e) { /* ignore */ }
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
            try {
                if (this.authLoginRef?.el) {
                    this.authLoginRef.el.focus();
                    this.authLoginRef.el.select();
                }
            } catch (e) { /* ignore */ }
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
        // // Only require option if options are available for this workorder
        // if (this.options && this.options.length && (!this.state.selectedOption || !this.state.optionTouched)) {
        //     this.notification.add(_t("You must select an option."), { type: "danger" });
        //     return;
        // }
        if (this.state.selectedMode === "manual" && !this.state.manualWeight) {
            this.notification.add(_t("You must enter a manual weight."), { type: "danger" });
            return;
        }
        const payload = {
            scale_id: this.state.selectedMode === "scale" ? this.state.selectedScaleId : false,
            employee_id: this.state.selectedEmployee || false,
            equipment_id: this.state.selectedEquipment || false,
            option_id: this.state.selectedOption || false,
            manual_weight: (this.state.selectedMode === "manual" && this.state.isManualAuthorized)
                ? parseFloat(this.state.manualWeight)
                : false,
        };

        // persistir última selección en localStorage
        try {
            const workorderId = this.props.active && this.props.active.length ? this.props.active[0] : null;
            const LS_KEY = workorderId ? `idtx_mrp.last_selection.${workorderId}` : 'idtx_mrp.last_selection';
            const data = {
                employee_id: this.state.selectedEmployee ? String(this.state.selectedEmployee) : false,
                equipment_id: this.state.selectedEquipment ? String(this.state.selectedEquipment) : false,
                option_id: this.state.selectedOption ? String(this.state.selectedOption) : false,
            };
            window.localStorage.setItem(LS_KEY, JSON.stringify(data));
        } catch (e) {
            // ignore
        }

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

    async _loadOptions() {
        // Cargar opciones relacionadas al workorder (si no vienen por props)
        try {
            const workorderId = this.props.active && this.props.active.length ? this.props.active[0] : null;
            if (workorderId) {
                const raw = await this.ormService.searchRead('mrp.workorder.option', [['workorder_id', '=', workorderId]], ['name', 'id']);
                // Ensure all items have valid id before assigning
                this.options = (raw || []).filter(opt => opt && opt.id);
            } else {
                this.options = [];
            }
        } catch (e) {
            this.options = [];
        }
        
        if (!this.options.length) {
            this.notification.add(
                _t("No options are available for this work order."),
                { type: "warning" }
            );
        }
    }

    onOptionChange(ev) {
        // t-model already updates state.selectedOption; persist it immediately
        this.state.optionTouched = true;
        try {
            console.log("SelectScaleDialog:onOptionChange -> selectedOption:", this.state.selectedOption, "options:", this.options);
        } catch (e) {
            // ignore
        }
        try {
            const workorderId = this.props.active && this.props.active.length ? this.props.active[0] : null;
            const LS_KEY = workorderId ? `idtx_mrp.last_selection.${workorderId}` : 'idtx_mrp.last_selection';
            const raw = window.localStorage.getItem(LS_KEY);
            const parsed = raw ? JSON.parse(raw) : {};
            parsed.option_id = this.state.selectedOption ? String(this.state.selectedOption) : false;
            // always update employee/equipment from current state (may be blank)
            parsed.employee_id = this.state.selectedEmployee ? String(this.state.selectedEmployee) : false;
            parsed.equipment_id = this.state.selectedEquipment ? String(this.state.selectedEquipment) : false;
            window.localStorage.setItem(LS_KEY, JSON.stringify(parsed));
        } catch (e) {
            // ignore
        }
    }
}
