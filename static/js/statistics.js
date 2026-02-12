document.addEventListener("DOMContentLoaded", () => {
    const seasonSelect = document.getElementById("season-select");
    const metricSelect = document.getElementById("metric-select");
    const presetSelect = document.getElementById("preset-select");
    const usersSelect = document.getElementById("users-select");
    const gpFromInput = document.getElementById("gp-from-input");
    const gpToInput = document.getElementById("gp-to-input");
    const applyBtn = document.getElementById("apply-filters-btn");
    const resetBtn = document.getElementById("reset-filters-btn");
    const feedbackEl = document.getElementById("stats-feedback");
    const emptyStateEl = document.getElementById("stats-empty-state");
    const matrixBody = document.getElementById("statistics-matrix-body");
    const sortableHeaders = document.querySelectorAll(".statistics-table th.sortable");

    const state = {
        sortBy: "total_points",
        sortDir: "desc",
        selectedUsers: [],
    };

    const defaultState = {
        season: "2025",
        metric: "cumulative_points",
        preset: "all",
        gpFrom: "",
        gpTo: "",
    };

    function init() {
        seasonSelect.value = defaultState.season;
        metricSelect.value = defaultState.metric;
        presetSelect.value = defaultState.preset;
        gpFromInput.value = defaultState.gpFrom;
        gpToInput.value = defaultState.gpTo;

        applyBtn.addEventListener("click", refreshData);
        resetBtn.addEventListener("click", resetFilters);
        usersSelect.addEventListener("change", () => {
            state.selectedUsers = getSelectedUsers();
        });
        sortableHeaders.forEach((header) => {
            header.addEventListener("click", () => onSortHeaderClick(header));
        });

        refreshData();
    }

    function resetFilters() {
        seasonSelect.value = defaultState.season;
        metricSelect.value = defaultState.metric;
        presetSelect.value = defaultState.preset;
        gpFromInput.value = "";
        gpToInput.value = "";
        state.sortBy = "total_points";
        state.sortDir = "desc";
        state.selectedUsers = [];
        usersSelect.innerHTML = "";
        refreshData();
    }

    async function refreshData() {
        setLoadingState();
        try {
            const matrixPayload = await fetchMatrix();
            renderMatrix(matrixPayload);
            hydrateUsersFilter(matrixPayload.rows || []);

            const trendsPayload = await fetchTrends();
            renderChart(trendsPayload);
            renderFeedback(matrixPayload, trendsPayload);
        } catch (error) {
            feedbackEl.textContent = "Could not load statistics. Check backend logs and try again.";
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "Error loading statistics.";
            matrixBody.innerHTML = "<tr><td colspan='13'>Error loading matrix data.</td></tr>";
            if (window.Highcharts) {
                Highcharts.chart("trends-chart", {
                    title: { text: "Statistics unavailable" },
                    series: [],
                });
            }
            // eslint-disable-next-line no-console
            console.error(error);
        }
    }

    function setLoadingState() {
        feedbackEl.textContent = "Loading statistics...";
        emptyStateEl.hidden = true;
        matrixBody.innerHTML = "<tr><td colspan='13'>Loading matrix data...</td></tr>";
    }

    async function fetchMatrix() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("sort_by", state.sortBy);
        params.set("sort_dir", state.sortDir);
        if (gpFromInput.value) {
            params.set("gp_from", gpFromInput.value);
        }
        if (gpToInput.value) {
            params.set("gp_to", gpToInput.value);
        }

        const response = await fetch(`/statistics/api/matrix/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Matrix endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    async function fetchTrends() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("metric", metricSelect.value);
        params.set("preset", presetSelect.value);
        if (gpFromInput.value) {
            params.set("gp_from", gpFromInput.value);
        }
        if (gpToInput.value) {
            params.set("gp_to", gpToInput.value);
        }
        const users = getSelectedUsers();
        users.forEach((userId) => params.append("users", String(userId)));

        const response = await fetch(`/statistics/api/trends/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Trends endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    function renderMatrix(payload) {
        const rows = payload.rows || [];
        if (payload.empty_state || rows.length === 0) {
            matrixBody.innerHTML = "<tr><td colspan='13'>No statistics available for selected filters.</td></tr>";
            return;
        }

        matrixBody.innerHTML = rows
            .map((row, index) => {
                return `
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
                        <td class="points">${formatNumber(row.consistency)}</td>
                        <td class="points">${formatNumber(row.gps_played)}</td>
                        <td class="points">${formatNumber(row.teammate_h2h_wins)}</td>
                        <td class="points">${formatNumber(row.teammate_h2h_losses)}</td>
                    </tr>
                `;
            })
            .join("");
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

        if (payload.empty_state || !payload.series || payload.series.length === 0) {
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "No trend data available for selected filters.";
            Highcharts.chart("trends-chart", {
                title: { text: "User Trends" },
                xAxis: { categories: [] },
                yAxis: { title: { text: "" } },
                series: [],
                credits: { enabled: false },
            });
            return;
        }

        emptyStateEl.hidden = true;
        Highcharts.chart("trends-chart", {
            chart: { type: "line", backgroundColor: "#ffffff" },
            title: { text: titleByMetric[payload.metric] || "User Trends" },
            xAxis: { categories: payload.labels || [] },
            yAxis: {
                title: { text: titleByMetric[payload.metric] || "" },
                reversed: payload.metric === "rank_per_gp",
            },
            legend: { enabled: true },
            tooltip: { shared: true },
            credits: { enabled: false },
            series: payload.series.map((seriesItem) => ({
                name: seriesItem.username,
                data: seriesItem.data || [],
            })),
        });
    }

    function renderFeedback(matrixPayload, trendsPayload) {
        if (matrixPayload.empty_state || trendsPayload.empty_state) {
            feedbackEl.textContent = "Season has no scored Grand Prix data for current filters.";
            return;
        }
        feedbackEl.textContent = `Loaded ${matrixPayload.meta.total_users} users across ${matrixPayload.meta.scored_gps} scored GPs.`;
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

    function hydrateUsersFilter(rows) {
        const previousSelection = new Set(getSelectedUsers());
        const options = rows
            .map((row) => ({ id: row.user_id, username: row.username }))
            .sort((a, b) => a.username.localeCompare(b.username));

        usersSelect.innerHTML = options
            .map((option) => {
                const selected = previousSelection.has(option.id) ? "selected" : "";
                return `<option value="${option.id}" ${selected}>${escapeHtml(option.username)}</option>`;
            })
            .join("");

        state.selectedUsers = getSelectedUsers();
    }

    function getSelectedUsers() {
        return Array.from(usersSelect.selectedOptions)
            .map((option) => Number(option.value))
            .filter((value) => Number.isFinite(value));
    }

    function formatNumber(value) {
        if (typeof value === "number") {
            return Number.isInteger(value) ? value.toString() : value.toFixed(2);
        }
        return value ?? "-";
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
