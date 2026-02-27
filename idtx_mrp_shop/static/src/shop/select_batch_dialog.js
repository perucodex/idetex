/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState, onMounted, useRef, onWillUnmount } from "@odoo/owl";

export class SelectBatchDialog extends ConfirmationDialog {
    static template = "idtx_mrp_shop.SelectBatchDialog";

    static props = {
        ...ConfirmationDialog.props,
        recordId: { type: Number, optional: true }, // workorder id (para persistencia)
        batchs: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        equipments: { type: Array, optional: true },
        selectedEmployee: { type: [Number, String], optional: true },
        selectedEquipment: { type: [Number, String], optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");

        this.batchs = this.props.batchs || [];
        this.employees = this.props.employees || [];
        this.equipments = this.props.equipments || [];

        this._searchTimer = null;
        this._searchAbort = null;

        this.searchInputRef = useRef("batchSearchInput");

        this.state = useState({
            currentStep: 0,
            maxReachedStep: 0,
            selectedEmployee: this.props.selectedEmployee ? String(this.props.selectedEmployee) : "",
            selectedEquipment: this.props.selectedEquipment ? String(this.props.selectedEquipment) : "",
            selectedBatchId: "",

            batchQuery: "",
            isSearching: false,
            searchError: "",
            results: [],
            recent: [],

            workorderId: this.props.recordId || false,
            partnerName: "",
            colorName: "",
            colorCode: "",

            weight: 0,
            bath_ratio: 0,
            abs_factor: 3.0,
            recipe_salt: 0,
            recipe_carbonate: 0,
            recipe_soda: 0,
            alkalis_volume: 0,
            dyes_volume: 0,

            total_volume: 0,
            start_salt: 0,
            start_brine: 0,
            salt_qty: 0,
            brine_qty: 0,
            actual_volume: 0,
            total_tanq_volume: 0,
            final_volume: 0,
            volume_variation: 0,
            add_salt: 0,
            add_carbonate: 0,
            add_soda: 0,
            message: "",
            ribbon_message: 0,

            hydrophilicity: "",
            peroxide_residual: "",
            antipilling_ph: "",
            dye_ph: "",
            previous_ph: "",
            neutralized_ph: "",
            hardness_dyeing_water: "",

            pump_speed: "",
            reel_speed: "",
            hydrovary: "",
            rope1: "",
            rope2: "",
            rope3: "",
            rope4: "",
            rope5: "",
            rope6: "",

            salt_measurement: "",
            water_batches: "",

            tipo_proceso: "",
            ph_poly: "",
            red_wash: "",
            before_carb: "",
            first_carb: "",
            second_carb: "",
            exhaustion: "",
            neutralization: "",
            soaping: "",
            discharge: "",
            notes: "",
        });

        this.steps = [
            1,
            2,
            3,
            4,
            5,
            6,
        ];

        onMounted(() => {
            // foco directo al buscador para que el operador escanee/teclee rápido
            if (this.searchInputRef.el) {
                this.searchInputRef.el.focus();
            }
        });

        onWillUnmount(() => {
            if (this._searchTimer) clearTimeout(this._searchTimer);
            if (this._searchAbort) this._searchAbort.abort();
        });

        onWillStart(async () => {
            if (!this.employees.length) await this._loadEmployees();
            if (!this.equipments.length) await this._loadEquipments();
            this._restorePersisted();
            await this._loadRecent();
            await this._runSearch("");

            if (this.state.selectedBatchId && this.state.selectedEquipment && this.state.selectedEmployee) {
                await this._loadRegistryDefaults();
            }
        });
    }

    // =========================
    // Persistencia por orden
    // =========================
    _lsKey() {
        const wo = this.props.recordId || null;
        return wo ? `idtx_mrp.last_batch_selection.${wo}` : "idtx_mrp.last_batch_selection";
    }

    _restorePersisted() {
        try {
            const raw = window.localStorage.getItem(this._lsKey());
            if (!raw) return;
            const p = JSON.parse(raw);

            if (!this.state.selectedEmployee && p.employee_id) this.state.selectedEmployee = String(p.employee_id);
            if (!this.state.selectedEquipment && p.equipment_id) this.state.selectedEquipment = String(p.equipment_id);
            if (p.batch_id) this.state.selectedBatchId = String(p.batch_id);

            // opcional: precargar query (no es necesario)
            // if (p.batch_code) this.state.batchQuery = String(p.batch_code);
        } catch (e) {
            // ignore
        }
    }

    _persistPartial() {
        try {
            const raw = window.localStorage.getItem(this._lsKey());
            const p = raw ? JSON.parse(raw) : {};

            // NO borrar con vacío
            if (this.state.selectedEmployee) p.employee_id = String(this.state.selectedEmployee);
            if (this.state.selectedEquipment) p.equipment_id = String(this.state.selectedEquipment);
            if (this.state.selectedBatchId) p.batch_id = String(this.state.selectedBatchId);

            window.localStorage.setItem(this._lsKey(), JSON.stringify(p));
        } catch (e) {
            // ignore
        }
    }

    // =========================
    // Events Employee / Equipment
    // =========================
    onEmployeeChange(ev) {
        this.state.selectedEmployee = ev?.target?.value || "";
        this._persistPartial();
        this._maybeReloadDefaults();
    }

    onEquipmentChange(ev) {
        this.state.selectedEquipment = ev?.target?.value || "";
        this._persistPartial();
        this._refreshEquipmentVolumes();
        this._computeVolumeValues();
        this._maybeReloadDefaults();
    }

    // =========================
    // Search UI
    // =========================
    onBatchQueryInput(ev) {
        this.state.batchQuery = ev?.target?.value || "";
        this._debouncedSearch(this.state.batchQuery);
    }

    onBatchQueryKeyDown(ev) {
        if (ev.key === "Enter") {
            const first = (this.state.results || [])[0];
            if (first) {
                this.selectBatch(first);
            }
        } else if (ev.key === "Escape") {
            this.state.batchQuery = "";
            this._debouncedSearch("");
        }
    }

    _debouncedSearch(q) {
        if (this._searchTimer) clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => {
            this._runSearch(q);
        }, 280);
    }

    async _runSearch(q) {
        if (this._searchAbort) this._searchAbort.abort();
        this._searchAbort = new AbortController();

        this.state.isSearching = true;
        this.state.searchError = "";

        try {
            const query = (q || "").trim();

            const items = await this.ormService.call(
                "mrp.workorder.batch",
                "search_batch_lookup",
                [query],
                {
                    limit: 20,
                    state: "batch",
                },
                { signal: this._searchAbort.signal }
            );

            this.state.results = Array.isArray(items) ? items : [];
        } catch (e) {
            if (String(e)?.includes("AbortError")) {
            } else {
                this.state.searchError = _t("Error searching batches.");
            }
        } finally {
            this.state.isSearching = false;
        }
    }

    async _loadRecent() {
        try {
            const raw = window.localStorage.getItem(this._lsKey());
            if (!raw) {
                this.state.recent = [];
                return;
            }
            const p = JSON.parse(raw);
            const lastId = p?.batch_id ? parseInt(p.batch_id) : null;
            if (!lastId) {
                this.state.recent = [];
                return;
            }

            const rec = await this.ormService.call(
                "mrp.workorder.batch",
                "search_batch_lookup",
                [String(lastId)],
                { limit: 5, state: "batch", prefer_id: lastId }
            );
            this.state.recent = Array.isArray(rec) ? rec.slice(0, 5) : [];
        } catch (e) {
            this.state.recent = [];
        }
    }

    selectBatch(batch) {
        this.state.selectedBatchId = String(batch.id);
        this._persistPartial();
        this._maybeReloadDefaults();
    }

    clearSelectedBatch() {
        this.state.selectedBatchId = "";
        this._persistPartial();
    }

    get selectedBatch() {
        const id = this.state.selectedBatchId;
        if (!id) return null;
        return (this.state.results || []).find(r => String(r.id) === String(id))
            || (this.state.recent || []).find(r => String(r.id) === String(id))
            || null;
    }

    get isLastStep() {
        return this.state.currentStep === this.steps.length - 1;
    }

    get nextButtonLabel() {
        return this.isLastStep ? _t("Confirm") : _t("Next");
    }

    get processImageUrl() {
        if (!this.state.tipo_proceso) {
            return "";
        }
        return `/idtx_mrp_shop/static/src/images/${this.state.tipo_proceso}.jpg`;
    }

    isStepVisible(stepIndex) {
        return this.state.currentStep === stepIndex;
    }

    prevStep() {
        if (this.state.currentStep > 0) {
            this.state.currentStep -= 1;
            this.state.maxReachedStep = this.state.currentStep;
            this._computeVolumeValues();
        }
    }

    goToStep(stepIndex) {
        if (stepIndex < this.state.currentStep) {
            this.state.currentStep = stepIndex;
            this.state.maxReachedStep = stepIndex;
            this._computeVolumeValues();
            return;
        }

        if (stepIndex <= this.state.maxReachedStep) {
            this.state.currentStep = stepIndex;
            this._computeVolumeValues();
            return;
        }

        if (this._validateCurrentStep()) {
            this.state.currentStep = stepIndex;
            this.state.maxReachedStep = stepIndex;
            this._computeVolumeValues();
        }
    }

    async nextStepOrConfirm() {
        if (!this._validateCurrentStep()) {
            return;
        }
        if (this.isLastStep) {
            this.confirm();
            return;
        }
        this.state.currentStep += 1;
        if (this.state.currentStep > this.state.maxReachedStep) {
            this.state.maxReachedStep = this.state.currentStep;
        }
        this._computeVolumeValues();
    }

    _validateCurrentStep() {
        if (this.state.currentStep === 0) {
            if (!this.state.selectedBatchId) {
                this.notification.add(_t("You must select a batch."), { type: "danger" });
                return false;
            }
            if (!this.state.selectedEmployee) {
                this.notification.add(_t("You must select an employee."), { type: "danger" });
                return false;
            }
            if (!this.state.selectedEquipment) {
                this.notification.add(_t("You must select an equipment."), { type: "danger" });
                return false;
            }
        }
        return true;
    }

    confirm() {
        if (!this.state.selectedBatchId || !this.state.selectedEmployee || !this.state.selectedEquipment) {
            this.notification.add(_t("Batch, employee and equipment are required."), { type: "danger" });
            return;
        }

        const payload = {
            batch_id: parseInt(this.state.selectedBatchId),
            employee_id: parseInt(this.state.selectedEmployee),
            equipment_id: parseInt(this.state.selectedEquipment),
            bath_ratio: this._toNumber(this.state.bath_ratio),
            abs_factor: this._toNumber(this.state.abs_factor),
            alkalis_volume: this._toNumber(this.state.alkalis_volume),
            dyes_volume: this._toNumber(this.state.dyes_volume),
            hydrophilicity: this.state.hydrophilicity || false,
            peroxide_residual: this.state.peroxide_residual || false,
            antipilling_ph: this._toNumber(this.state.antipilling_ph),
            dye_ph: this._toNumber(this.state.dye_ph),
            previous_ph: this._toNumber(this.state.previous_ph),
            neutralized_ph: this._toNumber(this.state.neutralized_ph),
            hardness_dyeing_water: this._toNumber(this.state.hardness_dyeing_water),
            pump_speed: this.state.pump_speed || false,
            reel_speed: this._toNumber(this.state.reel_speed),
            hydrovary: this.state.hydrovary || false,
            rope1: this._toNumber(this.state.rope1),
            rope2: this._toNumber(this.state.rope2),
            rope3: this._toNumber(this.state.rope3),
            rope4: this._toNumber(this.state.rope4),
            rope5: this._toNumber(this.state.rope5),
            rope6: this._toNumber(this.state.rope6),
            salt_measurement: this._toNumber(this.state.salt_measurement),
            water_batches: this.state.water_batches || false,
            tipo_proceso: this.state.tipo_proceso || false,
            ph_poly: this._toNumber(this.state.ph_poly),
            red_wash: this._toNumber(this.state.red_wash),
            before_carb: this._toNumber(this.state.before_carb),
            first_carb: this._toNumber(this.state.first_carb),
            second_carb: this._toNumber(this.state.second_carb),
            exhaustion: this._toNumber(this.state.exhaustion),
            neutralization: this._toNumber(this.state.neutralization),
            soaping: this._toNumber(this.state.soaping),
            discharge: this._toNumber(this.state.discharge),
            notes: this.state.notes || false,
        };

        this._persistPartial();
        this.props.confirm(payload);
        this.props.close();
    }

    onInputNumber(ev, fieldName) {
        this.state[fieldName] = ev?.target?.value || "";
        this._computeVolumeValues();
    }

    onInputText(ev, fieldName) {
        this.state[fieldName] = ev?.target?.value || "";
    }

    onSelectionChange(ev, fieldName) {
        this.state[fieldName] = ev?.target?.value || "";
        this._computeVolumeValues();
    }

    _toNumber(value) {
        const num = parseFloat(value || 0);
        return Number.isFinite(num) ? num : 0;
    }

    _refreshEquipmentVolumes() {
        const equipment = (this.equipments || []).find(e => String(e.id) === String(this.state.selectedEquipment || ""));
        if (equipment) {
            this.state.alkalis_volume = this._toNumber(equipment.alkalis_vol);
            this.state.dyes_volume = this._toNumber(equipment.color_vol);
        }
    }

    async _maybeReloadDefaults() {
        if (this.state.selectedBatchId && this.state.selectedEmployee && this.state.selectedEquipment) {
            await this._loadRegistryDefaults();
        }
    }

    async _loadRegistryDefaults() {
        try {
            const defaults = await this.ormService.call(
                "mrp.workorder",
                "action_get_registry_defaults",
                [[this.state.workorderId], parseInt(this.state.selectedBatchId), parseInt(this.state.selectedEmployee), parseInt(this.state.selectedEquipment)]
            );

            this.state.weight = this._toNumber(defaults.weight);
            this.state.bath_ratio = this._toNumber(defaults.bath_ratio);
            this.state.abs_factor = this._toNumber(defaults.abs_factor || 3.0);
            this.state.recipe_salt = this._toNumber(defaults.recipe_salt);
            this.state.recipe_carbonate = this._toNumber(defaults.recipe_carbonate);
            this.state.recipe_soda = this._toNumber(defaults.recipe_soda);
            this.state.alkalis_volume = this._toNumber(defaults.alkalis_volume);
            this.state.dyes_volume = this._toNumber(defaults.dyes_volume);
            this.state.colorName = defaults.color_name || "";
            this.state.colorCode = defaults.color_code || "";
            this.state.partnerName = this.selectedBatch?.partner_id || "";
            this._computeVolumeValues();
        } catch (e) {
            this.notification.add(_t("Error loading registry defaults."), { type: "danger" });
        }
    }

    _computeVolumeValues() {
        const weight = this._toNumber(this.state.weight);
        const bathRatio = this._toNumber(this.state.bath_ratio);
        const absFactor = this._toNumber(this.state.abs_factor);
        const recipeSalt = this._toNumber(this.state.recipe_salt);
        const recipeCarbonate = this._toNumber(this.state.recipe_carbonate);
        const alkalisVolume = this._toNumber(this.state.alkalis_volume);
        const dyesVolume = this._toNumber(this.state.dyes_volume);
        const saltMeasurement = this._toNumber(this.state.salt_measurement);

        this.state.total_volume = weight * bathRatio;
        this.state.start_salt = (this.state.total_volume - (weight * absFactor)) - (dyesVolume + (4 * alkalisVolume));
        this.state.brine_qty = (recipeSalt * this.state.total_volume / 0.33) / 1000;
        this.state.start_brine = (this.state.total_volume - (weight * absFactor)) - (this.state.brine_qty + dyesVolume + (3 * alkalisVolume));
        this.state.salt_qty = recipeSalt * this.state.total_volume / 1000;
        this.state.add_soda = 0;

        if (this.state.water_batches === "wb1") {
            this.state.total_tanq_volume = 3 * alkalisVolume;
        } else if (this.state.water_batches === "wb2") {
            this.state.total_tanq_volume = (3 * alkalisVolume) + dyesVolume;
        } else if (this.state.water_batches === "wb3") {
            this.state.total_tanq_volume = (2 * alkalisVolume) + dyesVolume;
        } else {
            this.state.total_tanq_volume = 0;
        }

        if (saltMeasurement > 0) {
            this.state.actual_volume = this.state.total_volume * recipeSalt / saltMeasurement;
            this.state.final_volume = this.state.actual_volume + this.state.total_tanq_volume;
            this.state.volume_variation = this.state.total_volume - this.state.final_volume;

            if (this.state.volume_variation > 0) {
                this.state.add_salt = 0;
                this.state.add_carbonate = 0;
                this.state.ribbon_message = 1;
                this.state.message = _t("Missing water");
            } else if (this.state.volume_variation < 0) {
                this.state.add_salt = -(recipeSalt * this.state.volume_variation) / 1000;
                this.state.add_carbonate = -(recipeCarbonate * this.state.volume_variation) / 1000;
                this.state.ribbon_message = 2;
                this.state.message = _t("Add Salt and Alkali");
            } else {
                this.state.add_salt = 0;
                this.state.add_carbonate = 0;
                this.state.ribbon_message = 0;
                this.state.message = "";
            }
        } else {
            this.state.actual_volume = 0;
            this.state.final_volume = 0;
            this.state.volume_variation = 0;
            this.state.add_salt = 0;
            this.state.add_carbonate = 0;
            this.state.ribbon_message = 0;
            this.state.message = "";
        }
    }

    // =========================
    // Loaders
    // =========================
    async _loadEmployees() {
        const deptId = await this.ormService.searchRead(
            "ir.model.data",
            [["name", "=", "tintoreria"], ["module", "=", "idtx_mrp_shop"]],
            ["res_id"]
        ).then(data => data[0]?.res_id || false);

        if (!deptId) {
            this.notification.add(
                _t("Department 'Tintorería' not found. Please check the external ID."),
                { type: "danger" }
            );
            return;
        }

        this.employees = await this.ormService.searchRead("hr.employee", [["department_id", "=", deptId]], ["name"]);
        if (!this.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEquipments() {
        const workcenterId = await this.ormService.searchRead(
            "ir.model.data",
            [["name", "=", "mrp_wc_2"], ["module", "=", "idtx_mrp"]],
            ["res_id"]
        ).then(data => data[0]?.res_id || false);

        if (!workcenterId) {
            this.notification.add(
                _t("Workcenter_id 'Tintorería' not found. Please check the external ID."),
                { type: "danger" }
            );
            return;
        }

        // ojo: tu domain tenía [['workcenter_id','in',workcenterId]] pero "in" espera lista
        this.equipments = await this.ormService.searchRead(
            "maintenance.equipment",
            [["workcenter_id", "=", workcenterId]],
            ["name", "alkalis_vol", "color_vol"]
        );

        if (!this.equipments.length) {
            this.notification.add(
                _t("No equipments are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }
}
