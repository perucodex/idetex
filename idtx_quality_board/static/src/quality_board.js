/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef, onPatched } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const RESULTADO_CONFIG = {
    aprobado: {
        label: "APROBADO",
        color: "#198754",
        bgRow: "#d1e7dd",
        textRow: "#0a3622",
        chartColor: "rgba(25, 135, 84, 0.85)",
    },
    concesionado: {
        label: "CONCESIONADO",
        color: "#fd7e14",
        bgRow: "#ffe5d0",
        textRow: "#6d3a00",
        chartColor: "rgba(253, 126, 20, 0.85)",
    },
    rechazado: {
        label: "RECHAZADO",
        color: "#dc3545",
        bgRow: "#f8d7da",
        textRow: "#58151c",
        chartColor: "rgba(220, 53, 69, 0.85)",
    },
};

const RECETA_CONFIG = {
    receta_correcta: {
        label: "RECETA CORRECTA",
        color: "#198754",
        chartColor: "rgba(25, 135, 84, 0.85)",
    },
    cambio_receta: {
        label: "CAMBIO DE RECETA",
        color: "#dc3545",
        chartColor: "rgba(220, 53, 69, 0.85)",
    },
};

const MOTIVO_CONFIG = {
    motivo_tono: {
        label: "MOTIVO TONO",
        color: "#6f42c1",
        chartColor: "rgba(111, 66, 193, 0.85)",
    },
    motivo_tacto: {
        label: "MOTIVO TACTO",
        color: "#fd7e14",
        chartColor: "rgba(253, 126, 20, 0.85)",
    },
    motivo_apariencia: {
        label: "MOTIVO APARIENCIA",
        color: "#0d6efd",
        chartColor: "rgba(13, 110, 253, 0.85)",
    },
};

export class QualityTonoBoard extends Component {
    static template = "idtx_quality.QualityTonoBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.chartRef = useRef("barChart");
        this.chartRecetaRef = useRef("barChartReceta");
        this.chartMotivoRef = useRef("barChartMotivo");

        this.tono = this.props.action?.context?.tono || "tacho";
        this.title = this.tono === "tacho"
            ? "Evaluación de Tono — Tintorería (Tacho)"
            : "Evaluación de Tono — Acabado";
        this.recetaLabelRef = this.tono === "tacho" ? "Receta Laboratorio" : "Receta Acabado";
        this.resultados = ["aprobado", "concesionado", "rechazado"];
        this.config = RESULTADO_CONFIG;
        this.recetaTipos = ["receta_correcta", "cambio_receta"];
        this.recetaConfig = RECETA_CONFIG;
        this.motivoTipos = ["motivo_tono", "motivo_tacto", "motivo_apariencia"];
        this.motivoConfig = MOTIVO_CONFIG;

        this.state = useState({
            months: [],
            matrix: {},
            totals: {},
            grandTotal: 0,
            recetaMatrix: {},
            recetaTotals: {},
            recetaGrandTotal: 0,
            motivoMatrix: {},
            motivoTotals: {},
            motivoGrandTotal: 0,
            loading: true,
            error: null,
        });

        this._chart = null;
        this._chartReceta = null;
        this._chartMotivo = null;

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this._loadData();
        });

        const tryRender = () => {
            if (!this.state.loading && !this.state.error && this.state.months.length) {
                this._renderChart();
                if (this.tono === "tacho" || this.tono === "acabado") {
                    this._renderRecetaChart();
                }
                if (this.tono === "acabado") {
                    this._renderMotivoChart();
                }
            }
        };

        onMounted(tryRender);
        onPatched(tryRender);
    }

    async _loadData() {
        try {
            const fields = ["fecha_eval", "resultado"];
            if (this.tono === "tacho" || this.tono === "acabado") {
                fields.push("receta_tono", "receta");
            }
            if (this.tono === "acabado") {
                fields.push("motivo_tono", "motivo_tacto", "motivo_apariencia");
            }
            const records = await this.orm.searchRead(
                "control.tono.eval.log",
                [["tono", "=", this.tono]],
                fields,
                { order: "fecha_eval ASC" }
            );
            this._processData(records);
        } catch (e) {
            this.state.error = "No se pudieron cargar los datos.";
        } finally {
            this.state.loading = false;
        }
    }

    _processData(records) {
        const raw = {};
        const rawReceta = {};
        const rawMotivo = {};

        for (const r of records) {
            if (!r.fecha_eval) continue;
            const dateStr = typeof r.fecha_eval === "string"
                ? r.fecha_eval.split(" ")[0]
                : new Date(r.fecha_eval).toISOString().split("T")[0];
            const [year, month] = dateStr.split("-");
            const key = `${year}-${month}`;
            const res = r.resultado || "rechazado";

            if (!raw[key]) raw[key] = {};
            raw[key][res] = (raw[key][res] || 0) + 1;

            if (this.tono === "tacho" || this.tono === "acabado") {
                if (!rawReceta[key]) rawReceta[key] = {};
                const tipo = (r.receta_tono && r.receta && r.receta_tono === r.receta)
                    ? "receta_correcta"
                    : "cambio_receta";
                rawReceta[key][tipo] = (rawReceta[key][tipo] || 0) + 1;
            }

            if (this.tono === "acabado") {
                if (!rawMotivo[key]) rawMotivo[key] = {};
                if (r.motivo_tono)      rawMotivo[key].motivo_tono      = (rawMotivo[key].motivo_tono      || 0) + 1;
                if (r.motivo_tacto)     rawMotivo[key].motivo_tacto     = (rawMotivo[key].motivo_tacto     || 0) + 1;
                if (r.motivo_apariencia) rawMotivo[key].motivo_apariencia = (rawMotivo[key].motivo_apariencia || 0) + 1;
            }
        }

        const months = Object.keys(raw).sort();

        // ── Matriz resultado ──
        const matrix = {};
        const totals = {};
        for (const r of this.resultados) {
            matrix[r] = {};
            for (const m of months) matrix[r][m] = (raw[m] || {})[r] || 0;
        }
        for (const m of months) {
            totals[m] = this.resultados.reduce((s, r) => s + (matrix[r][m] || 0), 0);
        }
        const matrixFinal = {};
        for (const r of this.resultados) {
            matrixFinal[r] = {};
            for (const m of months) {
                const count = matrix[r][m] || 0;
                const total = totals[m] || 1;
                matrixFinal[r][m] = { count, pct: Math.round((count / total) * 100) };
            }
        }
        const grandTotal = months.reduce((s, m) => s + (totals[m] || 0), 0);

        this.state.months = months;
        this.state.matrix = matrixFinal;
        this.state.totals = totals;
        this.state.grandTotal = grandTotal;

        // ── Matriz receta (tacho y acabado) ──
        if (this.tono === "tacho" || this.tono === "acabado") {
            const recetaMatrix = {};
            const recetaTotals = {};
            for (const t of this.recetaTipos) {
                recetaMatrix[t] = {};
                for (const m of months) recetaMatrix[t][m] = (rawReceta[m] || {})[t] || 0;
            }
            for (const m of months) {
                recetaTotals[m] = this.recetaTipos.reduce((s, t) => s + (recetaMatrix[t][m] || 0), 0);
            }
            const recetaMatrixFinal = {};
            for (const t of this.recetaTipos) {
                recetaMatrixFinal[t] = {};
                for (const m of months) {
                    const count = recetaMatrix[t][m] || 0;
                    const total = recetaTotals[m] || 1;
                    recetaMatrixFinal[t][m] = { count, pct: Math.round((count / total) * 100) };
                }
            }
            const recetaGrandTotal = months.reduce((s, m) => s + (recetaTotals[m] || 0), 0);

            this.state.recetaMatrix = recetaMatrixFinal;
            this.state.recetaTotals = recetaTotals;
            this.state.recetaGrandTotal = recetaGrandTotal;
        }

        // ── Matriz motivos (solo acabado) ──
        if (this.tono === "acabado") {
            const motivoMatrix = {};
            const motivoTotals = {};
            for (const t of this.motivoTipos) {
                motivoMatrix[t] = {};
                for (const m of months) motivoMatrix[t][m] = (rawMotivo[m] || {})[t] || 0;
            }
            for (const m of months) {
                motivoTotals[m] = this.motivoTipos.reduce((s, t) => s + (motivoMatrix[t][m] || 0), 0);
            }
            const motivoMatrixFinal = {};
            for (const t of this.motivoTipos) {
                motivoMatrixFinal[t] = {};
                for (const m of months) {
                    const count = motivoMatrix[t][m] || 0;
                    const total = motivoTotals[m] || 1;
                    motivoMatrixFinal[t][m] = { count, pct: Math.round((count / total) * 100) };
                }
            }
            const motivoGrandTotal = months.reduce((s, m) => s + (motivoTotals[m] || 0), 0);

            this.state.motivoMatrix = motivoMatrixFinal;
            this.state.motivoTotals = motivoTotals;
            this.state.motivoGrandTotal = motivoGrandTotal;
        }
    }

    formatMonth(key) {
        const [year, month] = key.split("-");
        return `${MONTHS_ES[parseInt(month, 10) - 1]} ${year}`;
    }

    // ── Resultado helpers ──
    getCell(resultado, month) {
        return this.state.matrix[resultado]?.[month] || { count: 0, pct: 0 };
    }

    getRowTotal(resultado) {
        return this.state.months.reduce(
            (s, m) => s + (this.state.matrix[resultado]?.[m]?.count || 0), 0
        );
    }

    getRowPct(resultado) {
        if (!this.state.grandTotal) return 0;
        return Math.round((this.getRowTotal(resultado) / this.state.grandTotal) * 100);
    }

    // ── Receta helpers ──
    getRecetaCell(tipo, month) {
        return this.state.recetaMatrix[tipo]?.[month] || { count: 0, pct: 0 };
    }

    getRecetaRowTotal(tipo) {
        return this.state.months.reduce(
            (s, m) => s + (this.state.recetaMatrix[tipo]?.[m]?.count || 0), 0
        );
    }

    getRecetaRowPct(tipo) {
        if (!this.state.recetaGrandTotal) return 0;
        return Math.round((this.getRecetaRowTotal(tipo) / this.state.recetaGrandTotal) * 100);
    }

    // ── Motivo helpers ──
    getMotivoCell(tipo, month) {
        return this.state.motivoMatrix[tipo]?.[month] || { count: 0, pct: 0 };
    }

    getMotivoRowTotal(tipo) {
        return this.state.months.reduce(
            (s, m) => s + (this.state.motivoMatrix[tipo]?.[m]?.count || 0), 0
        );
    }

    getMotivoRowPct(tipo) {
        if (!this.state.motivoGrandTotal) return 0;
        return Math.round((this.getMotivoRowTotal(tipo) / this.state.motivoGrandTotal) * 100);
    }

    // ── Charts ──
    _renderChart() {
        const canvas = this.chartRef.el;
        if (!canvas) return;
        if (this._chart) { this._chart.destroy(); this._chart = null; }

        const labels = this.state.months.map((m) => this.formatMonth(m));
        const datasets = this.resultados.map((r) => ({
            label: RESULTADO_CONFIG[r].label,
            data: this.state.months.map((m) => this.state.matrix[r]?.[m]?.count || 0),
            backgroundColor: RESULTADO_CONFIG[r].chartColor,
            borderColor: RESULTADO_CONFIG[r].color,
            borderWidth: 1.5,
            borderRadius: 5,
            borderSkipped: false,
        }));

        this._chart = new window.Chart(canvas, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { boxWidth: 14, padding: 20, font: { size: 13, weight: "500" } },
                    },
                    tooltip: {
                        callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}` },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1, font: { size: 12 } },
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                },
            },
        });
    }

    _renderRecetaChart() {
        const canvas = this.chartRecetaRef.el;
        if (!canvas) return;
        if (this._chartReceta) { this._chartReceta.destroy(); this._chartReceta = null; }

        const labels = this.state.months.map((m) => this.formatMonth(m));
        const datasets = this.recetaTipos.map((t) => ({
            label: RECETA_CONFIG[t].label,
            data: this.state.months.map((m) => this.state.recetaMatrix[t]?.[m]?.count || 0),
            backgroundColor: RECETA_CONFIG[t].chartColor,
            borderColor: RECETA_CONFIG[t].color,
            borderWidth: 1.5,
            borderRadius: 5,
            borderSkipped: false,
        }));

        this._chartReceta = new window.Chart(canvas, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { boxWidth: 14, padding: 20, font: { size: 13, weight: "500" } },
                    },
                    tooltip: {
                        callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}` },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1, font: { size: 12 } },
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                },
            },
        });
    }
    _renderMotivoChart() {
        const canvas = this.chartMotivoRef.el;
        if (!canvas) return;
        if (this._chartMotivo) { this._chartMotivo.destroy(); this._chartMotivo = null; }

        const labels = this.state.months.map((m) => this.formatMonth(m));
        const datasets = this.motivoTipos.map((t) => ({
            label: MOTIVO_CONFIG[t].label,
            data: this.state.months.map((m) => this.state.motivoMatrix[t]?.[m]?.count || 0),
            backgroundColor: MOTIVO_CONFIG[t].chartColor,
            borderColor: MOTIVO_CONFIG[t].color,
            borderWidth: 1.5,
            borderRadius: 5,
            borderSkipped: false,
        }));

        this._chartMotivo = new window.Chart(canvas, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { boxWidth: 14, padding: 20, font: { size: 13, weight: "500" } },
                    },
                    tooltip: {
                        callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}` },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1, font: { size: 12 } },
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                },
            },
        });
    }
}

registry.category("actions").add("idtx_quality.tono_board", QualityTonoBoard);
