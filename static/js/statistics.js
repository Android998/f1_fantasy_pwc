document.addEventListener("DOMContentLoaded", () => {
    const seasonSelect = document.getElementById("season-select");
    const metricSelect = document.getElementById("metric-select");
    const presetSelect = document.getElementById("preset-select");
    const usersDropdownBtn = document.getElementById("users-dropdown-btn");
    const usersDropdownContent = document.getElementById("users-dropdown-content");
    const gpRangeBtn = document.getElementById("gp-range-btn");
    const gpRangeContent = document.getElementById("gp-range-content");
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
        gpOptions: [],
        selectedGpRounds: [],
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

        applyBtn.addEventListener("click", refreshData);
        resetBtn.addEventListener("click", resetFilters);
        presetSelect.addEventListener("change", () => {
            if (presetSelect.value === "me_teammate") {
                state.selectedUsers = [];
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
        sortableHeaders.forEach((header) => {
            header.addEventListener("click", () => onSortHeaderClick(header));
        });

        refreshData();
    }

    function resetFilters() {
        seasonSelect.value = defaultState.season;
        metricSelect.value = defaultState.metric;
        presetSelect.value = defaultState.preset;
        state.sortBy = "total_points";
        state.sortDir = "desc";
        state.selectedUsers = [];
        state.selectedGpRounds = [];
        usersDropdownContent.innerHTML = "";
        usersDropdownBtn.textContent = "All users";
        gpRangeContent.innerHTML = "";
        gpRangeBtn.textContent = "All GPs";
        refreshData();
    }

    async function refreshData() {
        setLoadingState();
        try {
            const selectedUsersBeforeRequest = getSelectedUsers();
            const matrixPayload = await fetchMatrix();
            const trendsPayload = await fetchTrends();

            if (
                presetSelect.value === "me_teammate" &&
                selectedUsersBeforeRequest.length === 0 &&
                Array.isArray(trendsPayload.resolved_user_ids) &&
                trendsPayload.resolved_user_ids.length > 0
            ) {
                state.selectedUsers = trendsPayload.resolved_user_ids.slice(0, 2);
            }

            hydrateUsersFilter(matrixPayload.rows || []);
            hydrateGpRange(trendsPayload.gp_options || []);
            renderMatrix(matrixPayload);
            renderChart(trendsPayload);
            renderFeedback(matrixPayload, trendsPayload);
        } catch (error) {
            feedbackEl.textContent = "Could not load statistics. Check backend logs and try again.";
            emptyStateEl.hidden = false;
            emptyStateEl.textContent = "Error loading statistics.";
            matrixBody.innerHTML = "<tr><td colspan='12'>Error loading matrix data.</td></tr>";
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
        matrixBody.innerHTML = "<tr><td colspan='12'>Loading matrix data...</td></tr>";
    }

    async function fetchMatrix() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
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

    async function fetchTrends() {
        const params = new URLSearchParams();
        params.set("season", seasonSelect.value);
        params.set("metric", metricSelect.value);
        const users = getSelectedUsers();
        params.set("preset", users.length > 0 ? "all" : presetSelect.value);
        const gpRange = getSelectedGpRange();
        if (gpRange) {
            params.set("gp_from", String(gpRange.from));
            params.set("gp_to", String(gpRange.to));
        }
        users.forEach((userId) => params.append("users", String(userId)));

        const response = await fetch(`/statistics/api/trends/?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Trends endpoint failed: ${response.status}`);
        }
        return response.json();
    }

    function renderMatrix(payload) {
        let rows = payload.rows || [];
        const selectedUsers = state.selectedUsers;
        if (selectedUsers.length > 0) {
            const selectedSet = new Set(selectedUsers);
            rows = rows.filter((row) => selectedSet.has(row.user_id));
        }
        if (payload.empty_state || rows.length === 0) {
            matrixBody.innerHTML = "<tr><td colspan='12'>No statistics available for selected filters.</td></tr>";
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
        const previousUsers = state.selectedUsers.slice();
        const previousSelection = new Set(previousUsers);
        const options = rows
            .map((row) => ({ id: row.user_id, username: row.username }))
            .sort((a, b) => a.username.localeCompare(b.username));

        const validSelected = previousUsers.filter((id) => options.some((opt) => opt.id === id));
        state.selectedUsers = validSelected;

        const lines = [
            `<label class="users-option"><input type="checkbox" data-user-id="" ${validSelected.length === 0 ? "checked" : ""}>All users</label>`,
            ...options.map((option) => {
                const checked = validSelected.includes(option.id) ? "checked" : "";
                return `<label class="users-option"><input type="checkbox" data-user-id="${option.id}" ${checked}>${escapeHtml(option.username)}</label>`;
            }),
        ];

        usersDropdownContent.innerHTML = lines.join("");
        usersDropdownContent.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
            checkbox.addEventListener("change", onUserCheckboxChange);
        });

        updateUsersButtonLabel();
    }

    function getSelectedUsers() {
        if (!usersDropdownContent || !usersDropdownContent.children.length) {
            return state.selectedUsers.slice();
        }
        return Array.from(usersDropdownContent.querySelectorAll("input[data-user-id]"))
            .filter((input) => input.checked && input.dataset.userId !== "")
            .map((input) => input.dataset.userId)
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value));
    }

    function onUserCheckboxChange(event) {
        const input = event.target;
        const isAll = input.dataset.userId === "";
        const allCheckbox = usersDropdownContent.querySelector("input[data-user-id='']");
        const userCheckboxes = Array.from(usersDropdownContent.querySelectorAll("input[data-user-id]"))
            .filter((cb) => cb.dataset.userId !== "");

        if (isAll) {
            if (input.checked) {
                userCheckboxes.forEach((cb) => {
                    cb.checked = false;
                });
            } else if (!userCheckboxes.some((cb) => cb.checked)) {
                input.checked = true;
            }
        } else {
            if (input.checked) {
                allCheckbox.checked = false;
            }
            if (!userCheckboxes.some((cb) => cb.checked)) {
                allCheckbox.checked = true;
            }
        }

        state.selectedUsers = getSelectedUsers();
        updateUsersButtonLabel();
    }

    function updateUsersButtonLabel() {
        const selected = state.selectedUsers;
        if (!selected.length) {
            usersDropdownBtn.textContent = "All users";
            return;
        }
        if (selected.length === 1) {
            const label = usersDropdownContent.querySelector(`input[data-user-id='${selected[0]}']`)?.parentElement?.textContent?.trim();
            usersDropdownBtn.textContent = label || "1 user";
            return;
        }
        usersDropdownBtn.textContent = `${selected.length} users selected`;
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
            if (idx === -1) {
                selected.push(clickedRound);
            }
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
