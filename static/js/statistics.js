document.addEventListener("DOMContentLoaded", () => {
    const seasonSelect = document.getElementById("season-select");
    const entitySelect = document.getElementById("entity-select");
    const metricSelect = document.getElementById("metric-select");
    const presetSelect = document.getElementById("preset-select");
    const entitiesLabel = document.getElementById("entities-label");
    const usersDropdownBtn = document.getElementById("users-dropdown-btn");
    const usersDropdownContent = document.getElementById("users-dropdown-content");
    const gpRangeBtn = document.getElementById("gp-range-btn");
    const gpRangeContent = document.getElementById("gp-range-content");
    const applyBtn = document.getElementById("apply-filters-btn");
    const resetBtn = document.getElementById("reset-filters-btn");
    const feedbackEl = document.getElementById("stats-feedback");
    const emptyStateEl = document.getElementById("stats-empty-state");
    const matrixBody = document.getElementById("statistics-matrix-body");
    const matrixHeaderRow = document.getElementById("statistics-matrix-header-row");
    const pageTitle = document.getElementById("stats-page-title");
    const trendsTitle = document.getElementById("trends-title");
    const matrixTitle = document.getElementById("matrix-title");

    const state = {
        entityType: "users",
        sortBy: "total_points",
        sortDir: "desc",
        selectedEntityIds: [],
        gpOptions: [],
        selectedGpRounds: [],
    };

    const ENTITY_CONFIG = {
        users: {
            label: "Users",
            allLabel: "All users",
            singleLabel: "user",
            idKey: "user_id",
            nameKey: "username",
            presetOptions: [
                { value: "all", label: "All Users" },
                { value: "top3", label: "Top 3" },
                { value: "bottom3", label: "Bottom 3" },
                { value: "me_teammate", label: "Me + Teammate" },
            ],
            matrixHeaders: `
                <th class="rank sortable" data-sort-key="rank">Rank</th>
                <th class="user-name sortable" data-sort-key="username">Name</th>
                <th class="team-name sortable" data-sort-key="team_name">Team</th>
                <th class="points sortable" data-sort-key="total_points">Points</th>
                <th class="points sortable" data-sort-key="avg_points_gp">Avg/GP</th>
                <th class="wins sortable" data-sort-key="wins_gp">Wins</th>
                <th class="podiums sortable" data-sort-key="podiums_gp">Podiums</th>
                <th class="last-2 sortable" data-sort-key="bottom3_gp">Bottom 3</th>
                <th class="points sortable" data-sort-key="volatility">Volatility</th>
                <th class="points sortable" data-sort-key="gps_played">GPs</th>
                <th class="points sortable" data-sort-key="teammate_h2h_wins">H2H W</th>
                <th class="points sortable" data-sort-key="teammate_h2h_losses">H2H L</th>
            `,
            emptyColspan: 12,
        },
        teams: {
            label: "Teams",
            allLabel: "All teams",
            singleLabel: "team",
            idKey: "team_id",
            nameKey: "team_name",
            presetOptions: [
                { value: "all", label: "All Teams" },
                { value: "top3", label: "Top 3" },
                { value: "bottom3", label: "Bottom 3" },
                { value: "my_team", label: "My Team" },
            ],
            matrixHeaders: `
                <th class="rank sortable" data-sort-key="rank">Rank</th>
                <th class="team-name sortable" data-sort-key="team_name">Team</th>
                <th class="user-name">Members</th>
                <th class="points sortable" data-sort-key="total_points">Points</th>
                <th class="points sortable" data-sort-key="avg_points_gp">Avg/GP</th>
                <th class="wins sortable" data-sort-key="wins_gp">Wins</th>
                <th class="podiums sortable" data-sort-key="podiums_gp">Podiums</th>
                <th class="last-2 sortable" data-sort-key="bottom3_gp">Bottom 3</th>
                <th class="points sortable" data-sort-key="volatility">Volatility</th>
                <th class="points sortable" data-sort-key="gps_played">GPs</th>
            `,
            emptyColspan: 10,
        },
    };

    function init() {
        seasonSelect.value = "2025";
        entitySelect.value = "users";
        state.entityType = entitySelect.value;
        metricSelect.value = "cumulative_points";
        presetSelect.value = "all";

        applyEntityConfig();

        applyBtn.addEventListener("click", refreshData);
        resetBtn.addEventListener("click", resetFilters);
        entitySelect.addEventListener("change", () => {
            state.entityType = entitySelect.value;
            state.sortBy = "total_points";
            state.sortDir = "desc";
            state.selectedEntityIds = [];
            applyEntityConfig();
            refreshData();
        });
        presetSelect.addEventListener("change", () => {
            if (presetSelect.value === "me_teammate" || presetSelect.value === "my_team") {
                state.selectedEntityIds = [];
            }
        });

        usersDropdownBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            usersDropdownContent.classList.toggle("show");
            gpRangeContent.classList.remove("show");
        });
        gpRangeBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            gpRangeContent.classList.toggle("show");
            usersDropdownContent.classList.remove("show");
        });
        document.addEventListener("click", (event) => {
            if (!usersDropdownContent.contains(event.target) && event.target !== usersDropdownBtn) {
                usersDropdownContent.classList.remove("show");
            }
            if (!gpRangeContent.contains(event.target) && event.target !== gpRangeBtn) {
                gpRangeContent.classList.remove("show");
            }
        });

        refreshData();
    }

    function applyEntityConfig() {
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        if (entitiesLabel) {
            entitiesLabel.textContent = config.label;
        }
        if (pageTitle) {
            pageTitle.textContent = `${config.label} Statistics`;
        }
        if (trendsTitle) {
            trendsTitle.textContent = `${config.label} Trends`;
        }
        if (matrixTitle) {
            matrixTitle.textContent = `${config.label} Matrix`;
        }

        presetSelect.innerHTML = config.presetOptions
            .map((option) => `<option value="${option.value}">${option.label}</option>`)
            .join("");
        presetSelect.value = "all";

        matrixHeaderRow.innerHTML = config.matrixHeaders;
        matrixHeaderRow.querySelectorAll("th.sortable").forEach((header) => {
            header.addEventListener("click", () => onSortHeaderClick(header));
        });

        usersDropdownContent.innerHTML = "";
        usersDropdownBtn.textContent = config.allLabel;
    }

    function resetFilters() {
        seasonSelect.value = "2025";
        metricSelect.value = "cumulative_points";
        state.sortBy = "total_points";
        state.sortDir = "desc";
        state.selectedEntityIds = [];
        state.selectedGpRounds = [];
        usersDropdownContent.innerHTML = "";
        gpRangeContent.innerHTML = "";
        applyEntityConfig();
        gpRangeBtn.textContent = "All GPs";
        refreshData();
    }

    async function refreshData() {
        setLoadingState();
        try {
            const selectedBefore = getSelectedEntityIds();
            const matrixPayload = await fetchMatrix();
            const trendsPayload = await fetchTrends(selectedBefore);

            if (
                (presetSelect.value === "me_teammate" || presetSelect.value === "my_team") &&
                selectedBefore.length === 0 &&
                Array.isArray(resolvePresetIds(trendsPayload)) &&
                resolvePresetIds(trendsPayload).length > 0
            ) {
                const resolved = resolvePresetIds(trendsPayload);
                state.selectedEntityIds = resolved.slice(0, presetSelect.value === "me_teammate" ? 2 : 1);
            }

            hydrateEntitiesFilter(matrixPayload.rows || []);
            hydrateGpRange(trendsPayload.gp_options || []);
            renderMatrix(matrixPayload);
            renderChart(trendsPayload);
            renderFeedback(matrixPayload, trendsPayload);
        } catch (error) {
            feedbackEl.textContent = "Could not load statistics. Check backend logs and try again.";
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "Error loading statistics.";
            matrixBody.innerHTML = "<tr><td colspan=\"12\">Error loading matrix data.</td></tr>";
            if (window.Highcharts) {
                Highcharts.chart("trends-chart", { title: { text: "Statistics unavailable" }, series: [] });
            }
            console.error(error);
        }
    }

    function setLoadingState() {
        feedbackEl.textContent = "Loading statistics...";
        emptyStateEl.hidden = true;
        matrixBody.innerHTML = "<tr><td colspan=\"12\">Loading matrix data...</td></tr>";
    }

    async function fetchMatrix() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("entity", state.entityType);
        params.set("sort_by", state.sortBy);
        params.set("sort_dir", state.sortDir);
        const gpRange = getSelectedGpRange();
        if (gpRange) {
            params.set("gp_from", String(gpRange.from));
            params.set("gp_to", String(gpRange.to));
        }

        const response = await fetch(`/statistics/api/matrix/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Matrix endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    async function fetchTrends(selected) {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("entity", state.entityType);
        params.set("metric", metricSelect.value);
        const gpRange = getSelectedGpRange();
        if (gpRange) {
            params.set("gp_from", String(gpRange.from));
            params.set("gp_to", String(gpRange.to));
        }
        params.set("preset", selected.length > 0 ? "all" : presetSelect.value);
        const paramKey = state.entityType === "teams" ? "teams" : "users";
        selected.forEach((id) => params.append(paramKey, String(id)));

        const response = await fetch(`/statistics/api/trends/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Trends endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    function renderMatrix(payload) {
        let rows = payload.rows || [];
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        if (state.selectedEntityIds.length > 0) {
            const selectedSet = new Set(state.selectedEntityIds);
            rows = rows.filter((row) => selectedSet.has(Number(row[config.idKey])));
        }
        if (payload.empty_state || rows.length === 0) {
            matrixBody.innerHTML = `<tr><td colspan="${config.emptyColspan}">No statistics available for selected filters.</td></tr>`;
            return;
        }

        if (state.entityType === "teams") {
            matrixBody.innerHTML = rows.map((row, index) => `
                <tr>
                    <td class="rank">${index + 1}</td>
                    <td class="team-name">${escapeHtml(row.team_name || "-")}</td>
                    <td class="user-name">${escapeHtml(formatMembers(row.members))}</td>
                    <td class="points">${formatNumber(row.total_points)}</td>
                    <td class="points">${formatNumber(row.avg_points_gp)}</td>
                    <td class="wins">${formatNumber(row.wins_gp)}</td>
                    <td class="podiums">${formatNumber(row.podiums_gp)}</td>
                    <td class="last-2">${formatNumber(row.bottom3_gp)}</td>
                    <td class="points">${formatNumber(row.volatility)}</td>
                    <td class="points">${formatNumber(row.gps_played)}</td>
                </tr>
            `).join("");
            return;
        }

        matrixBody.innerHTML = rows.map((row, index) => `
            <tr>
                <td class="rank">${index + 1}</td>
                <td class="user-name">${escapeHtml(row.username || "-")}</td>
                <td class="team-name">${escapeHtml(row.team_name || "No Team")}</td>
                <td class="points">${formatNumber(row.total_points)}</td>
                <td class="points">${formatNumber(row.avg_points_gp)}</td>
                <td class="wins">${formatNumber(row.wins_gp)}</td>
                <td class="podiums">${formatNumber(row.podiums_gp)}</td>
                <td class="last-2">${formatNumber(row.bottom3_gp)}</td>
                <td class="points">${formatNumber(row.volatility)}</td>
                <td class="points">${formatNumber(row.gps_played)}</td>
                <td class="points">${formatNumber(row.teammate_h2h_wins)}</td>
                <td class="points">${formatNumber(row.teammate_h2h_losses)}</td>
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
        };
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        const seriesNameKey = state.entityType === "teams" ? "team_name" : "username";

        if (payload.empty_state || !payload.series || payload.series.length === 0) {
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "No trend data available for selected filters.";
            Highcharts.chart("trends-chart", {
                title: { text: `${config.label} Trends` },
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
        const chart = Highcharts.chart("trends-chart", {
            chart: { type: "line", backgroundColor: "#ffffff" },
            title: { text: titleByMetric[payload.metric] || `${config.label} Trends` },
            subtitle: {
                text: `Click on a line or legend item to highlight a ${config.singleLabel}`,
                align: "center",
                style: { fontSize: "12px" },
            },
            xAxis: { categories: payload.labels || [] },
            yAxis: {
                title: { text: titleByMetric[payload.metric] || "" },
                reversed: payload.metric === "rank_per_gp",
            },
            legend: { enabled: false },
            tooltip: { shared: true },
            credits: { enabled: false },
            plotOptions: {
                series: {
                    stickyTracking: true,
                    events: {
                        click: function () {
                            focusSeries(this.chart, this.name);
                        },
                    },
                },
            },
            series: payload.series.map((s) => ({
                name: s[seriesNameKey] || (state.entityType === "teams" ? "Team" : "User"),
                data: s.data || [],
            })),
        });
        renderExternalLegend(chart);
    }

    function focusSeries(chart, seriesName) {
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
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
                : `Click on a line or legend item to highlight a ${config.singleLabel}`,
        });
        updateExternalLegendSelection(chart);
        chart.redraw();
    }

    function renderExternalLegend(chart) {
        const parent = document.getElementById("trends-chart")?.parentElement;
        if (!parent) {
            return;
        }

        let legendEl = document.getElementById("users-external-legend");
        if (!legendEl) {
            legendEl = document.createElement("div");
            legendEl.id = "users-external-legend";
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
        const legendEl = document.getElementById("users-external-legend");
        if (!legendEl) {
            return;
        }
        const focused = chart?.userOptions?.custom?.focusedSeriesName || null;
        legendEl.querySelectorAll(".stats-external-legend-item").forEach((item) => {
            item.classList.toggle("active", Boolean(focused) && item.dataset.seriesName === focused);
            item.classList.toggle("dimmed", Boolean(focused) && item.dataset.seriesName !== focused);
        });
    }

    function withAlpha(color, alpha) {
        if (!window.Highcharts || !Highcharts.color) {
            return color;
        }
        return Highcharts.color(color).setOpacity(alpha).get();
    }

    function markerClassFromSymbol(symbol) {
        const known = new Set(["circle", "square", "diamond", "triangle", "triangle-down"]);
        return known.has(symbol) ? `stats-marker-${symbol}` : "stats-marker-circle";
    }

    function renderFeedback(matrixPayload, trendsPayload) {
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        if (matrixPayload.empty_state || trendsPayload.empty_state) {
            feedbackEl.textContent = "Season has no scored Grand Prix data for current filters.";
            return;
        }
        const totalCount = matrixPayload.meta.total_users || matrixPayload.meta.total_teams || matrixPayload.rows.length;
        feedbackEl.textContent = `Loaded ${totalCount} ${config.label.toLowerCase()} across ${matrixPayload.meta.scored_gps} scored GPs.`;
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

    function hydrateEntitiesFilter(rows) {
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        const previous = state.selectedEntityIds.slice();
        const options = rows
            .map((row) => ({ id: row[config.idKey], label: row[config.nameKey] }))
            .filter((o) => Number.isFinite(Number(o.id)) && o.label)
            .sort((a, b) => a.label.localeCompare(b.label));

        const validSelected = previous.filter((id) => options.some((opt) => Number(opt.id) === Number(id)));
        state.selectedEntityIds = validSelected;

        usersDropdownContent.innerHTML = [
            `<label class="users-option"><input type="checkbox" data-entity-id="" ${validSelected.length === 0 ? "checked" : ""}>${config.allLabel}</label>`,
            ...options.map((option) => {
                const checked = validSelected.includes(Number(option.id)) ? "checked" : "";
                return `<label class="users-option"><input type="checkbox" data-entity-id="${option.id}" ${checked}>${escapeHtml(option.label)}</label>`;
            }),
        ].join("");

        usersDropdownContent.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
            checkbox.addEventListener("change", onEntitiesCheckboxChange);
        });
        updateEntitiesButtonLabel();
    }

    function onEntitiesCheckboxChange(event) {
        const input = event.target;
        const isAll = input.dataset.entityId === "";
        const allCheckbox = usersDropdownContent.querySelector("input[data-entity-id='']");
        const itemCheckboxes = Array.from(usersDropdownContent.querySelectorAll("input[data-entity-id]"))
            .filter((cb) => cb.dataset.entityId !== "");

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
        state.selectedEntityIds = getSelectedEntityIds();
        updateEntitiesButtonLabel();
    }

    function getSelectedEntityIds() {
        if (!usersDropdownContent || !usersDropdownContent.children.length) {
            return state.selectedEntityIds.slice();
        }
        return Array.from(usersDropdownContent.querySelectorAll("input[data-entity-id]"))
            .filter((input) => input.checked && input.dataset.entityId !== "")
            .map((input) => Number(input.dataset.entityId))
            .filter((n) => Number.isFinite(n));
    }

    function updateEntitiesButtonLabel() {
        const config = ENTITY_CONFIG[state.entityType] || ENTITY_CONFIG.users;
        const selected = state.selectedEntityIds;
        if (!selected.length) {
            usersDropdownBtn.textContent = config.allLabel;
            return;
        }
        if (selected.length === 1) {
            const label = usersDropdownContent.querySelector(`input[data-entity-id='${selected[0]}']`)?.parentElement?.textContent?.trim();
            usersDropdownBtn.textContent = label || "1 selected";
            return;
        }
        usersDropdownBtn.textContent = `${selected.length} selected`;
    }

    function resolvePresetIds(payload) {
        if (state.entityType === "teams") {
            return payload.resolved_team_ids || [];
        }
        return payload.resolved_user_ids || [];
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

    function formatMembers(value) {
        if (Array.isArray(value)) {
            return value.length ? value.join(", ") : "-";
        }
        return value || "-";
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
