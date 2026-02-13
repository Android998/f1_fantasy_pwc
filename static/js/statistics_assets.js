document.addEventListener("DOMContentLoaded", () => {
    const seasonSelect = document.getElementById("season-select");
    const assetTypeSelect = document.getElementById("asset-type-select");
    const metricSelect = document.getElementById("metric-select");
    const assetsDropdownBtn = document.getElementById("assets-dropdown-btn");
    const assetsDropdownContent = document.getElementById("assets-dropdown-content");
    const gpRangeBtn = document.getElementById("gp-range-btn");
    const gpRangeContent = document.getElementById("gp-range-content");
    const applyBtn = document.getElementById("apply-filters-btn");
    const resetBtn = document.getElementById("reset-filters-btn");
    const feedbackEl = document.getElementById("stats-feedback");
    const emptyStateEl = document.getElementById("stats-empty-state");
    const matrixBody = document.getElementById("statistics-matrix-body");
    const matrixHeaderRow = document.getElementById("statistics-matrix-header-row");
    const assetGroupHeader = document.getElementById("asset-group-header");

    const state = {
        sortBy: "total_points",
        sortDir: "desc",
        selectedAssetIds: [],
        gpOptions: [],
        selectedGpRounds: [],
    };

    function init() {
        seasonSelect.value = "2025";
        assetTypeSelect.value = "drivers";
        metricSelect.value = "cumulative_points";

        matrixHeaderRow.querySelectorAll("th.sortable").forEach((header) => {
            header.addEventListener("click", () => onSortHeaderClick(header));
        });

        applyBtn.addEventListener("click", refreshData);
        resetBtn.addEventListener("click", resetFilters);
        assetTypeSelect.addEventListener("change", () => {
            state.selectedAssetIds = [];
            syncMatrixLayout();
            refreshData();
        });

        assetsDropdownBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            assetsDropdownContent.classList.toggle("show");
            gpRangeContent.classList.remove("show");
        });
        gpRangeBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            gpRangeContent.classList.toggle("show");
            assetsDropdownContent.classList.remove("show");
        });
        document.addEventListener("click", (event) => {
            if (!assetsDropdownContent.contains(event.target) && event.target !== assetsDropdownBtn) {
                assetsDropdownContent.classList.remove("show");
            }
            if (!gpRangeContent.contains(event.target) && event.target !== gpRangeBtn) {
                gpRangeContent.classList.remove("show");
            }
        });

        syncMatrixLayout();
        refreshData();
    }

    function resetFilters() {
        seasonSelect.value = "2025";
        assetTypeSelect.value = "drivers";
        metricSelect.value = "cumulative_points";
        state.sortBy = "total_points";
        state.sortDir = "desc";
        state.selectedAssetIds = [];
        state.selectedGpRounds = [];
        assetsDropdownContent.innerHTML = "";
        gpRangeContent.innerHTML = "";
        assetsDropdownBtn.textContent = "All assets";
        gpRangeBtn.textContent = "All GPs";
        syncMatrixLayout();
        refreshData();
    }

    async function refreshData() {
        setLoadingState();
        try {
            const matrixPayload = await fetchMatrix();
            const trendsPayload = await fetchTrends();

            hydrateAssetsFilter(matrixPayload.rows || []);
            hydrateGpRange(trendsPayload.gp_options || []);
            renderMatrix(matrixPayload);
            renderChart(trendsPayload);
            renderFeedback(matrixPayload, trendsPayload);
        } catch (error) {
            feedbackEl.textContent = "Could not load statistics. Check backend logs and try again.";
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "Error loading statistics.";
            matrixBody.innerHTML = `<tr><td colspan="${matrixColspan()}">Error loading matrix data.</td></tr>`;
            if (window.Highcharts) {
                Highcharts.chart("trends-chart", { title: { text: "Statistics unavailable" }, series: [] });
            }
            console.error(error);
        }
    }

    function setLoadingState() {
        feedbackEl.textContent = "Loading statistics...";
        emptyStateEl.hidden = true;
        matrixBody.innerHTML = `<tr><td colspan="${matrixColspan()}">Loading matrix data...</td></tr>`;
    }

    async function fetchMatrix() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("asset_type", assetTypeSelect.value);
        params.set("sort_by", state.sortBy);
        params.set("sort_dir", state.sortDir);
        const gpRange = getSelectedGpRange();
        if (gpRange) {
            params.set("gp_from", String(gpRange.from));
            params.set("gp_to", String(gpRange.to));
        }

        const response = await fetch(`/statistics/api/assets/matrix/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Matrix endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    async function fetchTrends() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("asset_type", assetTypeSelect.value);
        params.set("metric", metricSelect.value);
        const gpRange = getSelectedGpRange();
        if (gpRange) {
            params.set("gp_from", String(gpRange.from));
            params.set("gp_to", String(gpRange.to));
        }
        state.selectedAssetIds.forEach((id) => params.append("assets", String(id)));

        const response = await fetch(`/statistics/api/assets/trends/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Trends endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    function renderMatrix(payload) {
        let rows = payload.rows || [];
        if (state.selectedAssetIds.length > 0) {
            const selectedSet = new Set(state.selectedAssetIds);
            rows = rows.filter((row) => selectedSet.has(row.asset_id));
        }
        if (payload.empty_state || rows.length === 0) {
            matrixBody.innerHTML = `<tr><td colspan="${matrixColspan()}">No statistics available for selected filters.</td></tr>`;
            return;
        }

        const showTeamColumn = assetTypeSelect.value === "drivers";
        matrixBody.innerHTML = rows.map((row, index) => `
            <tr>
                <td class="rank">${index + 1}</td>
                <td class="user-name">${escapeHtml(row.name || "-")}</td>
                ${showTeamColumn ? `<td class="team-name asset-group-cell">${escapeHtml(row.asset_group || "No Team")}</td>` : ""}
                <td class="points">${formatNumber(row.total_points)}</td>
                <td class="points">${formatNumber(row.avg_points_gp)}</td>
                <td class="points">${formatNumber(row.volatility)}</td>
                <td class="points">${formatNumber(row.form_3gp)}</td>
                <td class="points">${formatNumber(row.gps_played)}</td>
                <td class="points">${formatNumber(row.current_price)}</td>
                <td class="points">${formatSigned(row.price_change)}</td>
                <td class="points">${formatNumber(row.points_per_million)}</td>
                <td class="points">${formatPercent(row.pick_rate)}</td>
                <td class="points">${formatPercent(row.pick_rate_last_gp)}</td>
            </tr>
        `).join("");
    }

    function renderChart(payload) {
        if (!window.Highcharts) {
            return;
        }
        const titleByMetric = {
            cumulative_points: "Cumulative Points",
            points_per_gp: "Points per GP",
            rank_per_gp: "Rank per GP",
            gap_to_leader: "Gap to Leader",
            price: "Price",
            price_change_gp: "Price Change per GP",
            points_per_million_gp: "Points per Million per GP",
            cumulative_points_per_million: "Cumulative Points per Million",
            rolling_avg_points_3gp: "Rolling Avg Points (3 GP)",
            rolling_avg_points_per_million_3gp: "Rolling Avg Pts/M (3 GP)",
            pick_rate_gp: "Pick % per GP",
        };

        if (payload.empty_state || !payload.series || payload.series.length === 0) {
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "No trend data available for selected filters.";
            Highcharts.chart("trends-chart", {
                title: { text: "Assets Trends" },
                xAxis: { categories: [] },
                yAxis: { title: { text: "" } },
                series: [],
                legend: { enabled: false },
                credits: { enabled: false },
            });
            renderExternalLegend(null);
            return;
        }

        emptyStateEl.hidden = true;
        const driverMarkerSymbols = ["circle", "square", "diamond", "triangle", "triangle-down"];
        const chart = Highcharts.chart("trends-chart", {
            chart: {
                type: "line",
                backgroundColor: "#ffffff",
            },
            title: { text: titleByMetric[payload.metric] || "Assets Trends" },
            subtitle: {
                text: "Click on a line or legend item to highlight an asset",
                align: "center",
                style: { fontSize: "12px" },
            },
            xAxis: { categories: payload.labels || [] },
            yAxis: {
                title: { text: titleByMetric[payload.metric] || "" },
                reversed: payload.metric === "rank_per_gp",
            },
            legend: {
                enabled: false,
            },
            tooltip: { shared: true },
            credits: { enabled: false },
            plotOptions: {
                series: {
                    stickyTracking: true,
                    events: {
                        click: function () {
                            focusSeries(this.chart, this.name);
                        },
                        legendItemClick: function (event) {
                            if (event && typeof event.preventDefault === "function") {
                                event.preventDefault();
                            }
                            focusSeries(this.chart, this.name);
                            return false;
                        },
                    },
                },
            },
            series: payload.series.map((s) => ({
                name: s.driver_name || s.team_name || s.name || "Asset",
                data: s.data || [],
                color: payload.asset_type === "drivers"
                    ? normalizeSeriesColor(s.team_color)
                    : normalizeSeriesColor(s.team_color),
                marker: {
                    enabled: true,
                    radius: payload.asset_type === "drivers" ? 3 : 2.5,
                    symbol: payload.asset_type === "drivers"
                        ? driverMarkerSymbols[s.asset_id % driverMarkerSymbols.length]
                        : "circle",
                },
            })),
        });
        renderExternalLegend(chart);
    }

    function focusSeries(chart, seriesName) {
        const current = chart.userOptions.custom?.focusedSeriesName || null;
        const nextFocus = current === seriesName ? null : seriesName;

        chart.userOptions.custom = chart.userOptions.custom || {};
        chart.userOptions.custom.focusedSeriesName = nextFocus;
        chart.userOptions.custom.seriesStyles = chart.userOptions.custom.seriesStyles || {};

        chart.series.forEach((series) => {
            if (!chart.userOptions.custom.seriesStyles[series.name]) {
                chart.userOptions.custom.seriesStyles[series.name] = {
                    color: series.color,
                    lineWidth: series.options.lineWidth ?? 2,
                };
            }
        });

        chart.series.forEach((series) => {
            const original = chart.userOptions.custom.seriesStyles[series.name];
            const isFocused = nextFocus && series.name === nextFocus;
            const hasFocus = Boolean(nextFocus);
            const lineWidth = hasFocus ? (isFocused ? 4 : 1) : original.lineWidth;
            const color = hasFocus
                ? (isFocused ? original.color : withAlpha(original.color, 0.15))
                : original.color;

            if (!series.visible) {
                series.setVisible(true, false);
            }

            series.update(
                {
                    lineWidth,
                    color,
                },
                false
            );
        });

        chart.setSubtitle({
            text: nextFocus
                ? `Selected: ${nextFocus}`
                : "Click on a line or legend item to highlight an asset",
        });
        updateExternalLegendSelection(chart);
        chart.redraw();
    }

    function withAlpha(color, alpha) {
        if (!window.Highcharts || !Highcharts.color) {
            return color;
        }
        return Highcharts.color(color).setOpacity(alpha).get();
    }

    function normalizeSeriesColor(color) {
        if (!color || !window.Highcharts || !Highcharts.color) {
            return color || undefined;
        }
        const parsed = Highcharts.color(color);
        // Team colors in DB are often too dark for this background; keep hue but brighten for readability.
        return parsed.brighten(0.25).get();
    }

    function renderExternalLegend(chart) {
        const parent = document.getElementById("trends-chart")?.parentElement;
        if (!parent) {
            return;
        }

        let legendEl = document.getElementById("assets-external-legend");
        if (!legendEl) {
            legendEl = document.createElement("div");
            legendEl.id = "assets-external-legend";
            legendEl.className = "stats-external-legend";
            parent.appendChild(legendEl);
        }

        legendEl.innerHTML = "";
        if (!chart) {
            return;
        }

        chart.series.forEach((series) => {
            if (!series || !series.name) {
                return;
            }
            const item = document.createElement("button");
            item.type = "button";
            item.className = "stats-external-legend-item";
            item.dataset.seriesName = series.name;
            const markerSymbol =
                (series.options && series.options.marker && series.options.marker.symbol) ||
                series.symbol ||
                "circle";
            const markerClass = markerClassFromSymbol(markerSymbol);
            item.innerHTML = `
                <span class="stats-external-legend-icon">
                    <span class="stats-external-legend-line" style="background:${series.color};"></span>
                    <span class="stats-external-legend-marker ${markerClass}" style="background:${series.color};color:${series.color};"></span>
                </span>
                <span class="stats-external-legend-text">${escapeHtml(series.name)}</span>
            `;
            item.addEventListener("click", () => focusSeries(chart, series.name));
            legendEl.appendChild(item);
        });

        updateExternalLegendSelection(chart);
    }

    function updateExternalLegendSelection(chart) {
        const legendEl = document.getElementById("assets-external-legend");
        if (!legendEl) {
            return;
        }
        const focused = chart?.userOptions?.custom?.focusedSeriesName || null;
        legendEl.querySelectorAll(".stats-external-legend-item").forEach((item) => {
            item.classList.toggle("active", Boolean(focused) && item.dataset.seriesName === focused);
            item.classList.toggle("dimmed", Boolean(focused) && item.dataset.seriesName !== focused);
        });
    }

    function markerClassFromSymbol(symbol) {
        const known = new Set(["circle", "square", "diamond", "triangle", "triangle-down"]);
        return known.has(symbol) ? `stats-marker-${symbol}` : "stats-marker-circle";
    }

    function renderFeedback(matrixPayload, trendsPayload) {
        if (matrixPayload.empty_state || trendsPayload.empty_state) {
            feedbackEl.textContent = "Season has no scored Grand Prix data for current filters.";
            return;
        }
        feedbackEl.textContent = `Loaded ${matrixPayload.meta.total_assets || matrixPayload.rows.length} assets across ${matrixPayload.meta.scored_gps} scored GPs.`;
    }

    function onSortHeaderClick(header) {
        const key = header.dataset.sortKey;
        if (!key || key === "rank") {
            return;
        }
        if (state.sortBy === key) {
            state.sortDir = state.sortDir === "desc" ? "asc" : "desc";
        } else {
            state.sortBy = key;
            state.sortDir = "desc";
        }
        refreshData();
    }

    function syncMatrixLayout() {
        const showTeamColumn = assetTypeSelect.value === "drivers";
        if (!assetGroupHeader) return;
        assetGroupHeader.style.display = showTeamColumn ? "" : "none";
        assetGroupHeader.textContent = "Team";
    }

    function matrixColspan() {
        return assetTypeSelect.value === "drivers" ? 13 : 12;
    }

    function hydrateAssetsFilter(rows) {
        const previous = state.selectedAssetIds.slice();
        const options = rows
            .map((row) => ({ id: row.asset_id, label: row.name }))
            .filter((o) => Number.isFinite(Number(o.id)) && o.label)
            .sort((a, b) => a.label.localeCompare(b.label));

        const validSelected = previous.filter((id) => options.some((opt) => Number(opt.id) === Number(id)));
        state.selectedAssetIds = validSelected;

        assetsDropdownContent.innerHTML = [
            `<label class="users-option"><input type="checkbox" data-asset-id="" ${validSelected.length === 0 ? "checked" : ""}>All assets</label>`,
            ...options.map((option) => {
                const checked = validSelected.includes(Number(option.id)) ? "checked" : "";
                return `<label class="users-option"><input type="checkbox" data-asset-id="${option.id}" ${checked}>${escapeHtml(option.label)}</label>`;
            }),
        ].join("");

        assetsDropdownContent.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
            checkbox.addEventListener("change", onAssetsCheckboxChange);
        });
        updateAssetsButtonLabel();
    }

    function onAssetsCheckboxChange(event) {
        const input = event.target;
        const isAll = input.dataset.assetId === "";
        const allCheckbox = assetsDropdownContent.querySelector("input[data-asset-id='']");
        const itemCheckboxes = Array.from(assetsDropdownContent.querySelectorAll("input[data-asset-id]"))
            .filter((cb) => cb.dataset.assetId !== "");

        if (isAll) {
            if (input.checked) {
                itemCheckboxes.forEach((cb) => (cb.checked = false));
            } else if (!itemCheckboxes.some((cb) => cb.checked)) {
                input.checked = true;
            }
        } else {
            if (input.checked) {
                allCheckbox.checked = false;
            }
            if (!itemCheckboxes.some((cb) => cb.checked)) {
                allCheckbox.checked = true;
            }
        }
        state.selectedAssetIds = getSelectedAssetIds();
        updateAssetsButtonLabel();
    }

    function getSelectedAssetIds() {
        if (!assetsDropdownContent || !assetsDropdownContent.children.length) {
            return state.selectedAssetIds.slice();
        }
        return Array.from(assetsDropdownContent.querySelectorAll("input[data-asset-id]"))
            .filter((input) => input.checked && input.dataset.assetId !== "")
            .map((input) => Number(input.dataset.assetId))
            .filter((n) => Number.isFinite(n));
    }

    function updateAssetsButtonLabel() {
        const selected = state.selectedAssetIds;
        if (!selected.length) {
            assetsDropdownBtn.textContent = "All assets";
            return;
        }
        if (selected.length === 1) {
            const label = assetsDropdownContent.querySelector(`input[data-asset-id='${selected[0]}']`)?.parentElement?.textContent?.trim();
            assetsDropdownBtn.textContent = label || "1 selected";
            return;
        }
        assetsDropdownBtn.textContent = `${selected.length} selected`;
    }

    function hydrateGpRange(gpOptions) {
        if (!Array.isArray(gpOptions) || gpOptions.length === 0) {
            gpRangeContent.innerHTML = "";
            gpRangeBtn.textContent = "All GPs";
            state.gpOptions = [];
            state.selectedGpRounds = [];
            return;
        }
        state.gpOptions = gpOptions;
        const validSelected = state.selectedGpRounds.filter((round) =>
            gpOptions.some((gp) => Number(gp.round) === Number(round))
        );
        state.selectedGpRounds = validSelected.slice(0, 2);

        gpRangeContent.innerHTML = gpOptions
            .map((gp) => {
                const checked = state.selectedGpRounds.includes(Number(gp.round)) ? "checked" : "";
                return `<label class="gp-option"><input type="checkbox" data-gp-round="${gp.round}" ${checked}>${escapeHtml(gp.name)}</label>`;
            })
            .join("");
        gpRangeContent.querySelectorAll("input[data-gp-round]").forEach((checkbox) => {
            checkbox.addEventListener("change", onGpRangeChange);
        });
        updateGpRangeButtonLabel();
    }

    function onGpRangeChange(event) {
        const clickedRound = Number(event.target.dataset.gpRound);
        const selected = state.selectedGpRounds.slice();
        const idx = selected.indexOf(clickedRound);
        if (event.target.checked) {
            if (idx === -1) selected.push(clickedRound);
        } else if (idx !== -1) {
            selected.splice(idx, 1);
        }
        while (selected.length > 2) {
            selected.shift();
        }
        state.selectedGpRounds = selected.sort((a, b) => a - b);
        syncGpCheckboxes();
        updateGpRangeButtonLabel();
    }

    function syncGpCheckboxes() {
        const selected = new Set(state.selectedGpRounds);
        gpRangeContent.querySelectorAll("input[data-gp-round]").forEach((checkbox) => {
            checkbox.checked = selected.has(Number(checkbox.dataset.gpRound));
        });
    }

    function updateGpRangeButtonLabel() {
        if (state.selectedGpRounds.length < 2) {
            gpRangeBtn.textContent = state.selectedGpRounds.length === 1 ? "Select one more GP" : "All GPs";
            return;
        }
        const [fromRound, toRound] = state.selectedGpRounds;
        const fromName = state.gpOptions.find((gp) => Number(gp.round) === fromRound)?.name || fromRound;
        const toName = state.gpOptions.find((gp) => Number(gp.round) === toRound)?.name || toRound;
        gpRangeBtn.textContent = `${fromName} - ${toName}`;
    }

    function getSelectedGpRange() {
        if (state.selectedGpRounds.length !== 2) {
            return null;
        }
        const sorted = state.selectedGpRounds.slice().sort((a, b) => a - b);
        if (sorted[0] === sorted[1]) {
            return null;
        }
        return { from: sorted[0], to: sorted[1] };
    }

    function formatNumber(value) {
        if (typeof value === "number") {
            return Number.isInteger(value) ? value.toString() : value.toFixed(2);
        }
        return value ?? "-";
    }

    function formatSigned(value) {
        if (typeof value !== "number") {
            return value ?? "-";
        }
        if (value > 0) {
            return `+${value.toFixed(2)}`;
        }
        return value.toFixed(2);
    }

    function formatPercent(value) {
        if (typeof value !== "number") {
            return value ?? "-";
        }
        return `${value.toFixed(1)}%`;
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    init();
});
