/** @odoo-module */

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DEFECT_SIZE_OPTIONS = [
    { value: "1", label: "Hasta 7.5 cm" },
    { value: "2", label: "> 7.5 cm y hasta 15 cm" },
    { value: "3", label: "> 15 cm y hasta 23 cm" },
    { value: "4", label: "> 23 cm" },
];

const HUECO_SIZE_OPTIONS = [
    { value: "2", label: "<= 3 cm" },
    { value: "4", label: "> 3 cm" },
];

export class QualityDefectScreen extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
        updateActionState: { type: Function, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.homeMenu = useService("home_menu");
        this._searchTimer = null;
        this.state = useState({
            loading: true,
            submitting: false,
            error: "",
            partidas: [],
            partidaQuery: "",
            isSearchingPartida: false,
            selectedPartidaId: "",
            rolloNum: "",
            sessionActive: false,
            selectedPartidaData: null,
            defects: [],
            selectedDefectoId: false,
            sizePopupOpen: false,
            popupDefectId: false,
        });

        onWillStart(async () => {
            await this.loadPartidas();
        });
    }

    get canStart() {
        return Boolean(this.state.selectedPartidaId) && Number(this.state.rolloNum) > 0 && !this.state.submitting;
    }

    get hasSession() {
        return Boolean(this.state.sessionActive);
    }

    get selectedDefect() {
        return this.state.defects.find((defect) => defect.defecto_id === this.state.selectedDefectoId);
    }

    get popupDefect() {
        return this.state.defects.find((defect) => defect.defecto_id === this.state.popupDefectId);
    }

    get sizeOptions() {
        if (!this.popupDefect) {
            return [];
        }
        return this.popupDefect.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS;
    }

    get isFinalizeDisabled() {
        return !this.hasSession || this.state.submitting;
    }

    async loadPartidas() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const partidas = await this.orm.call("control.apariencia.line", "action_tablet_get_partidas", ["", 20]);
            this.state.partidas = partidas;
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de partidas.";
        } finally {
            this.state.loading = false;
        }
    }

    onPartidaQueryInput(event) {
        this.state.partidaQuery = event.target.value || "";
        this._debouncedPartidaSearch(this.state.partidaQuery);
    }

    _debouncedPartidaSearch(query) {
        if (this._searchTimer) {
            clearTimeout(this._searchTimer);
        }
        this._searchTimer = setTimeout(() => {
            this.searchPartidas(query);
        }, 250);
    }

    async searchPartidas(query) {
        this.state.isSearchingPartida = true;
        this.state.error = "";
        try {
            const partidas = await this.orm.call("control.apariencia.line", "action_tablet_get_partidas", [query || "", 20]);
            this.state.partidas = partidas || [];
            if (!this.state.partidas.some((partida) => String(partida.id) === String(this.state.selectedPartidaId))) {
                this.state.selectedPartidaId = "";
            }
        } catch (error) {
            this.state.error = error.message || "No se pudo buscar partidas.";
        } finally {
            this.state.isSearchingPartida = false;
        }
    }

    onChangePartida(event) {
        this.state.selectedPartidaId = event.target.value;
    }

    selectPartida(partidaId) {
        this.state.selectedPartidaId = String(partidaId);
    }

    isPartidaSelected(partidaId) {
        return `${partidaId}` === `${this.state.selectedPartidaId}`;
    }

    onChangeRollo(event) {
        this.state.rolloNum = event.target.value;
    }

    async onStartCapture() {
        if (!this.canStart) {
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        try {
            const defects = await this.orm.call("control.apariencia.line", "action_tablet_get_defectos", []);
            this.state.defects = (defects || []).map((defect) => ({ ...defect, sizes: [], count: 0 }));
            this.state.selectedPartidaData = this.state.partidas.find(
                (partida) => `${partida.id}` === `${this.state.selectedPartidaId}`
            ) || null;
            this.state.sessionActive = true;
            this.notification.add("Captura iniciada.", { type: "success" });
        } catch (error) {
            this.state.error = error.message || "No se pudo iniciar la captura.";
        } finally {
            this.state.submitting = false;
        }
    }

    onSelectDefect(defectoId) {
        this.state.selectedDefectoId = defectoId;
        this.state.popupDefectId = defectoId;
        this.state.sizePopupOpen = true;
    }

    async onSelectSize(sizeCode) {
        if (!this.hasSession || !this.popupDefect) {
            return;
        }
        const selectedDefectoId = this.popupDefect.defecto_id;
        const defect = this.state.defects.find((item) => item.defecto_id === selectedDefectoId);
        if (!defect) {
            return;
        }
        defect.sizes.push(sizeCode);
        defect.count = defect.sizes.length;
        this.closeSizePopup();
    }

    closeSizePopup() {
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
    }

    async onFinalize() {
        if (this.isFinalizeDisabled) {
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        try {
            const selections = this.state.defects
                .filter((defect) => (defect.sizes || []).length)
                .map((defect) => ({
                    defecto_id: defect.defecto_id,
                    sizes: defect.sizes,
                }));

            await this.orm.call("control.apariencia.line", "action_tablet_finalize", [
                Number(this.state.selectedPartidaId),
                Number(this.state.rolloNum),
                selections,
            ]);
            this.notification.add("Registro de apariencia guardado.", { type: "success" });
            this.resetScreen();
            await this.loadPartidas();
        } catch (error) {
            this.state.error = error.message || "No se pudo finalizar el registro.";
        } finally {
            this.state.submitting = false;
        }
    }

    resetScreen() {
        this.state.selectedPartidaId = "";
        this.state.rolloNum = "";
        this.state.sessionActive = false;
        this.state.selectedPartidaData = null;
        this.state.defects = [];
        this.state.selectedDefectoId = false;
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
    }

    async close() {
        await this.homeMenu.toggle();
    }

    onClickRefresh() {
        window.location.reload();
    }
}

QualityDefectScreen.template = "idtx_batch_quality.QualityDefectScreen";

registry.category("actions").add("idtx_quality.defect_screen", QualityDefectScreen);
