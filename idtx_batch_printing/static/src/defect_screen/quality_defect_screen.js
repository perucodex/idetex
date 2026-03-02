/** @odoo-module */

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

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
            imagePreviewOpen: false,
            previewLensVisible: false,
            previewLensBgPos: "50% 50%",
            previewLensLeft: 0,
            previewLensTop: 0,
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
            const defects = await this.orm.call("control.apariencia.line", "action_tablet_get_defectos_printing", []);
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
        const defect = this.state.defects.find((item) => item.defecto_id === defectoId);
        if (!defect) {
            return;
        }
        defect.count = (defect.count || 0) + 1;
    }

    openImagePreview() {
        if (!this.state.selectedPartidaData?.design_image_url) {
            return;
        }
        this.state.imagePreviewOpen = true;
    }

    onPreviewImageMouseMove(event) {
        const rect = event.currentTarget.getBoundingClientRect();
        if (!rect.width || !rect.height) {
            return;
        }
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        const xPct = Math.max(0, Math.min(100, x));
        const yPct = Math.max(0, Math.min(100, y));

        const lensSize = 440;
        const offset = 24;
        let left = event.clientX + offset;
        let top = event.clientY + offset;
        if (left + lensSize > window.innerWidth - 8) {
            left = event.clientX - lensSize - offset;
        }
        if (top + lensSize > window.innerHeight - 8) {
            top = event.clientY - lensSize - offset;
        }

        this.state.previewLensBgPos = `${xPct}% ${yPct}%`;
        this.state.previewLensLeft = Math.max(8, left);
        this.state.previewLensTop = Math.max(8, top);
        this.state.previewLensVisible = true;
    }

    onPreviewImageMouseLeave() {
        this.state.previewLensVisible = false;
    }

    get previewLensStyle() {
        const imageUrl = this.state.selectedPartidaData?.design_image_url || "";
        return `left: ${this.state.previewLensLeft}px; top: ${this.state.previewLensTop}px; background-image: url('${imageUrl}'); background-size: 350%; background-position: ${this.state.previewLensBgPos};`;
    }

    closeImagePreview() {
        this.state.imagePreviewOpen = false;
        this.state.previewLensVisible = false;
    }

    async onFinalize() {
        if (this.isFinalizeDisabled) {
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        try {
            const selections = this.state.defects
                .filter((defect) => (defect.count || 0) > 0)
                .map((defect) => ({
                    defecto_id: defect.defecto_id,
                    count: defect.count,
                }));

            await this.orm.call("control.apariencia.line", "action_tablet_finalize_printing", [
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
        this.state.imagePreviewOpen = false;
        this.state.previewLensVisible = false;
        this.state.previewLensBgPos = "50% 50%";
        this.state.previewLensLeft = 0;
        this.state.previewLensTop = 0;
    }

    async close() {
        await this.homeMenu.toggle();
    }

    onClickRefresh() {
        window.location.reload();
    }
}

QualityDefectScreen.template = "idtx_batch_printing.QualityDefectScreen";

registry.category("actions").add("idtx_quality.defect_screen_printing", QualityDefectScreen);
