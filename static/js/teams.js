document.addEventListener('DOMContentLoaded', function() {
    // Ejecutar la función para actualizar la visibilidad del botón de añadir al cargar la página
    updateAddButtonVisibility();
    
    const driversTab = document.getElementById('drivers-tab');
    const constructorsTab = document.getElementById('constructors-tab');
    const driversTable = document.getElementById('drivers-table');
    const constructorsTable = document.getElementById('constructors-table');
    const sortSelect = document.getElementById('myteam-sort-select');
    const budgetProgressBar = document.getElementById('budget-progressBar');

    function getBudgetCap() {
        const parsed = parseFloat(budgetProgressBar?.max);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : 150;
    }

    // Mostrar la tabla de pilotos por defecto
    driversTable.style.display = 'block';
    constructorsTable.style.display = 'none';

    driversTab.addEventListener('click', function() {
        // Mostrar la tabla de pilotos y ocultar la de constructores
        driversTable.style.display = 'block';
        constructorsTable.style.display = 'none';

        // Cambiar el estado activo
        driversTab.classList.add('active');
        constructorsTab.classList.remove('active');
    });

    constructorsTab.addEventListener('click', function() {
        // Mostrar la tabla de constructores y ocultar la de pilotos
        constructorsTable.style.display = 'block';
        driversTable.style.display = 'none';

        // Cambiar el estado activo
        constructorsTab.classList.add('active');
        driversTab.classList.remove('active');
    });

    function parsePointsFromRow(row) {
        const pointsText = row.querySelector('.driver-stats ul li:first-child span')?.innerText || '0';
        const match = pointsText.match(/-?\d+(\.\d+)?/);
        return match ? parseFloat(match[0]) : 0;
    }

    function parsePriceFromRow(row) {
        const priceText = row.querySelector('.driver-price span:first-child')?.innerText || '0';
        const numeric = priceText.replace(/[^\d.-]/g, '');
        const value = parseFloat(numeric);
        return Number.isFinite(value) ? value : 0;
    }

    function rowSortValue(row, sortKey) {
        const points = parsePointsFromRow(row);
        const price = parsePriceFromRow(row);

        if (sortKey === 'price') return price;
        if (sortKey === 'ppm') return price > 0 ? points / price : 0;
        return points;
    }

    function sortRowsInTable(tableEl, sortKey) {
        if (!tableEl) return;
        const listContainer = tableEl.querySelector('ul');
        if (!listContainer) return;

        const items = Array.from(listContainer.querySelectorAll(':scope > li'));
        items.sort((a, b) => {
            const rowA = a.querySelector('.fila-piloto, .fila-equipo');
            const rowB = b.querySelector('.fila-piloto, .fila-equipo');
            const valueA = rowA ? rowSortValue(rowA, sortKey) : 0;
            const valueB = rowB ? rowSortValue(rowB, sortKey) : 0;
            if (valueA !== valueB) return valueB - valueA;

            const nameA = rowA?.querySelector('.driver-name span')?.innerText?.toLowerCase() || '';
            const nameB = rowB?.querySelector('.driver-name span')?.innerText?.toLowerCase() || '';
            return nameA.localeCompare(nameB);
        });

        items.forEach(item => listContainer.appendChild(item));
    }

    function applyListSorting() {
        const sortKey = sortSelect ? sortSelect.value : 'points';
        sortRowsInTable(driversTable, sortKey);
        sortRowsInTable(constructorsTable, sortKey);
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', applyListSorting);
    }
    applyListSorting();

    function isRowBlocked(row) {
        return row && row.dataset && row.dataset.blocked === 'true';
    }

    // Función para manejar la selección de pilotos o equipos
    function handleSelection(button, type) {
        const row = button.closest(`.fila-${type}`);
        if (!row) {
            console.error('Row not found for type:', type);
            return;
        }
        if (isRowBlocked(row)) {
            return;
        }
        const name = row.querySelector(`.driver-name span`).innerText;
        const price = row.querySelector(`.driver-price span:first-child`).innerText;
        const priceChange = row.querySelector('.price-up') ? row.querySelector('.price-up').innerText : row.querySelector('.price-down').innerText;
        const priceChangeClass = row.querySelector('.price-up') ? 'price-up' : 'price-down';
        const bgColor = row.querySelector('.foto-piloto').style.backgroundColor;

        let selectedPhotoSrc = '';
        let selectedLogoSrc = '';

        if (type === 'piloto') {
            const photoImg = row.querySelector('.foto-piloto-inside img');
            const photoSrc = photoImg ? photoImg.getAttribute('src') : '';
            selectedPhotoSrc = photoSrc.replace('/drivers/drivers/', '/drivers/selected/');
        } else {
            // Constructors
            selectedPhotoSrc = row.dataset.carSrc || (row.querySelector('img.team-car')?.getAttribute('src') || '');
            selectedLogoSrc = row.dataset.logoSrc || (row.querySelector('img.team-logo')?.getAttribute('src') || '');
        }

        // Obtener presupuesto disponible actual
        const BudgetEle = document.getElementById('available-budget').querySelector('span:last-child')
        let availableBudget = parseFloat(BudgetEle.innerText.replace('M', '').replace('$', ''));

        // Calcular el presupuesto después de añadir el piloto/equipo
        const newBudget = availableBudget - parseFloat(price.replace('M', '').replace('$', ''));

        // Actualizar presupuesto disponible en el HTML
        const budgetCap = getBudgetCap();
        document.getElementById('budget-span').style.width = `${newBudget * 220 / budgetCap}px`
        document.getElementById('budget-progressBar').value = newBudget
        BudgetEle.innerText = `$${newBudget.toFixed(1)} M`;

        // Buscar el siguiente contenedor de selección disponible
        let selectedContainer = null;
        const maxSelections = type === 'equipo' ? 2 : 5;

        for (let i = 1; i <= maxSelections; i++) {
            const noSelection = document.getElementById(`no-selection${type === 'equipo' ? i + 5 : i}`);
            if (noSelection.style.display !== 'none') {
                if (type=="piloto" && i == 1 && parseFloat(price.replace('M', '').replace('$', ''))>=35) continue;
                selectedContainer = i;
                break;
            }
        }

        if (selectedContainer !== null) {
            document.getElementById(`span-${type}${selectedContainer}`).style.backgroundColor = "hsl(240, 18%, 10%)";
            const selectionContainer = document.getElementById(`selection${type === 'equipo' ? selectedContainer + 5 : selectedContainer}`);
            document.getElementById(`${type}-name-${selectedContainer}`).innerText = name;
            document.getElementById(`${type}-price-${selectedContainer}`).innerText = price;
            document.getElementById(`${type}-price-change-${selectedContainer}`).innerText = priceChange;
            document.getElementById(`${type}-price-change-${selectedContainer}`).className = priceChangeClass;
            document.getElementById(`${type}-photo-${selectedContainer}`).setAttribute('src', selectedPhotoSrc);

            if (type === 'equipo' && selectedLogoSrc) {
                const logoEl = document.getElementById(`equipo-logo-${selectedContainer}`);
                if (logoEl) logoEl.setAttribute('src', selectedLogoSrc);
            }

            // Cambiar el color de fondo del contenedor seleccionado
            selectionContainer.querySelector('.driver-selected-photo').style.backgroundColor = bgColor;

            // Mostrar el contenedor de selección y ocultar el botón de añadir
            selectionContainer.style.display = 'flex';
            document.getElementById(`no-selection${type === 'equipo' ? selectedContainer + 5 : selectedContainer}`).style.display = 'none';

            // Ocultar el botón de añadir y mostrar el de eliminar en la fila del piloto/equipo
            row.querySelector('.selectable-piloto').style.display = 'none';
            row.querySelector('.no-selectable-piloto').style.display = 'flex';

            // Guardar una referencia al contenedor de selección en la fila del piloto/equipo
            row.dataset.selectedContainer = selectedContainer;
        } else {
            console.log('No hay contenedores disponibles');
        }

        updateAddButtonVisibility();
    }

    // Manejar la selección de pilotos
    document.querySelectorAll('.add-piloto').forEach(function(button) {
        button.addEventListener('click', function() {
            handleSelection(button, 'piloto');
        });
    });

    // Manejar la selección de equipos
    document.querySelectorAll('.add-equipo').forEach(function(button) {
        button.addEventListener('click', function() {
            handleSelection(button, 'equipo');
        });
    });



    // Función para manejar la eliminación de pilotos o equipos
    function handleRemoval(button, type) {
        const container = button.closest(`.selected-div`);
        const containerId = container.id;
        const selectedContainerIndex = containerId.replace('selection', '');
        const adjustedContainerIndex = type === 'equipo' ? selectedContainerIndex - 5 : selectedContainerIndex;
        document.getElementById(`span-${type}${adjustedContainerIndex}`).style.backgroundColor = "lightgray";

        // Obtener el nombre del piloto/equipo a eliminar
        const name = container.querySelector('.driver-selected-name span').innerText;

        // Buscar la fila del piloto/equipo en ambas tablas (pilotos y equipos)
        const allRows = Array.from(document.querySelectorAll(`.fila-${type}`));
        const row = allRows.find(row => row.querySelector('.driver-name span').innerText.toUpperCase() === name.toUpperCase());

        // Obtener presupuesto disponible actual
        const price = row.querySelector(`.driver-price span:first-child`).innerText;
        const BudgetEle = document.getElementById('available-budget').querySelector('span:last-child')
        let availableBudget = parseFloat(BudgetEle.innerText.replace('M', '').replace('$', ''));

        // Calcular el presupuesto después de añadir el piloto/equipo
        const newBudget = availableBudget + parseFloat(price.replace('M', '').replace('$', ''));

        // Actualizar presupuesto disponible en el HTML
        const budgetCap = getBudgetCap();
        document.getElementById('budget-span').style.width = `${newBudget * 220 / budgetCap}px`
        document.getElementById('budget-progressBar').value = newBudget
        BudgetEle.innerText = `$${newBudget.toFixed(1)} M`;

        // Ocultar el contenedor de selección y mostrar el botón de añadir
        container.style.display = 'none';
        document.getElementById(`no-selection${selectedContainerIndex}`).style.display = 'flex';

        // Limpiar la información del piloto/equipo seleccionado
        document.getElementById(`${type}-name-${adjustedContainerIndex}`).innerText = '';
        document.getElementById(`${type}-price-${adjustedContainerIndex}`).innerText = '';
        document.getElementById(`${type}-price-change-${adjustedContainerIndex}`).innerText = '';
        document.getElementById(`${type}-photo-${adjustedContainerIndex}`).setAttribute('src', '');

        // Mostrar el botón de añadir y ocultar el de eliminar en la fila del piloto/equipo
        if (row) {
            row.querySelector('.selectable-piloto').style.display = 'flex';
            row.querySelector('.no-selectable-piloto').style.display = 'none';

            // Eliminar la referencia al contenedor de selección en la fila del piloto/equipo
            delete row.dataset.selectedContainer;
        }

        updateAddButtonVisibility();
    }


    // Manejar la eliminación de pilotos seleccionados
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`remove-driver-${i}`).addEventListener('click', function() {
            handleRemoval(this, 'piloto');
        });
    }

    // Manejar la eliminación de equipos seleccionados
    for (let i = 6; i <= 7; i++) {
        document.getElementById(`remove-team-${i - 5}`).addEventListener('click', function() {
            handleRemoval(this, 'equipo');
        });
    }



    // Función para manejar la eliminación desde la tabla
    function handleTableRemoval(button, type) {
        const row = button.closest(`.fila-${type}`);
        console.log(row);
        if (isRowBlocked(row)) {
            return;
        }

        // Obtener presupuesto disponible actual
        const price = row.querySelector(`.driver-price span:first-child`).innerText;
        const BudgetEle = document.getElementById('available-budget').querySelector('span:last-child')
        let availableBudget = parseFloat(BudgetEle.innerText.replace('M', '').replace('$', ''));

        // Calcular el presupuesto después de añadir el piloto/equipo
        const newBudget = availableBudget + parseFloat(price.replace('M', '').replace('$', ''));

        // Actualizar presupuesto disponible en el HTML
        const budgetCap = getBudgetCap();
        document.getElementById('budget-span').style.width = `${newBudget * 220 / budgetCap}px`
        document.getElementById('budget-progressBar').value = newBudget
        BudgetEle.innerText = `$${newBudget.toFixed(1)} M`;

        // Encontrar el contenedor de selección asociado
        const selectedContainerIndex = parseInt(row.dataset.selectedContainer, 10);
        document.getElementById(`span-${type}${selectedContainerIndex}`).style.backgroundColor = "lightgray";
        const adjustedContainerIndex = type === 'equipo' ? selectedContainerIndex + 5 : selectedContainerIndex;

        if (selectedContainerIndex) {
            const selectionContainer = document.getElementById(`selection${adjustedContainerIndex}`);

            // Ocultar el contenedor de selección y mostrar el botón de añadir
            selectionContainer.style.display = 'none';
            document.getElementById(`no-selection${adjustedContainerIndex}`).style.display = 'flex';

            // Limpiar la información del piloto/equipo seleccionado
            document.getElementById(`${type}-name-${selectedContainerIndex}`).innerText = '';
            document.getElementById(`${type}-price-${selectedContainerIndex}`).innerText = '';
            document.getElementById(`${type}-price-change-${selectedContainerIndex}`).innerText = '';
            document.getElementById(`${type}-photo-${selectedContainerIndex}`).setAttribute('src', '');

            // Mostrar el botón de añadir y ocultar el de eliminar en la fila del piloto/equipo
            row.querySelector('.selectable-piloto').style.display = 'flex';
            row.querySelector('.no-selectable-piloto').style.display = 'none';

            // Eliminar la referencia al contenedor de selección en la fila del piloto/equipo
            delete row.dataset.selectedContainer;
        } else {
            console.log('No se encontró un contenedor de selección asociado');
        }

        updateAddButtonVisibility();

    }

    // Manejar la eliminación de pilotos desde la tabla de pilotos
    document.querySelectorAll('.no-selectable-piloto .remove-driver-table').forEach(function(button) {
        button.addEventListener('click', function() {
            handleTableRemoval(this, 'piloto');
        });
    });

    // Manejar la eliminación de equipos desde la tabla de equipos
    document.querySelectorAll('.no-selectable-piloto .remove-team-table').forEach(function(button) {
        button.addEventListener('click', function() {
            handleTableRemoval(this, 'equipo');
        });
    });



    // Function to reset all selections and go back to initial state
    function resetTeamSelection() {
        // Reset budget to initial state
        const initialBudget = getBudgetCap(); // Initial budget value
        const BudgetEle = document.getElementById('available-budget').querySelector('span:last-child');
        BudgetEle.innerText = `$${initialBudget.toFixed(1)} M`;

        // Reset progress bar and width
        document.getElementById('budget-span').style.width = `${initialBudget * 220 / getBudgetCap()}px`;
        document.getElementById('budget-progressBar').value = initialBudget;

        // Reset each selected container to initial state
        for (let i = 1; i <= 7; i++) {
            const selectedContainer = document.getElementById(`selection${i}`);
            console.log("Reseting container: ", selectedContainer.id);
            const noSelection = document.getElementById(`no-selection${i}`);

            if (selectedContainer.style.display == "flex"){
                console.log("Reseting container: ", selectedContainer.id);
                // Hide selection container, show no selection placeholder
                selectedContainer.style.display = 'none';
                noSelection.style.display = 'flex';

                // Obtener el nombre del piloto/equipo a eliminar
                const name = selectedContainer.querySelector('.driver-selected-name span').innerText;

                // Buscar la fila del piloto/equipo en ambas tablas (pilotos y equipos)
                const allRows = Array.from(document.querySelectorAll(`.fila-piloto, .fila-equipo`));
                const row = allRows.find(row => row.querySelector('.driver-name span').innerText.toUpperCase() === name.toUpperCase());

                // Mostrar el botón de añadir y ocultar el de eliminar en la fila del piloto/equipo
                row.querySelector('.selectable-piloto').style.display = 'flex';
                row.querySelector('.no-selectable-piloto').style.display = 'none';

                // Clear text and attributes in selected container
                if (i < 6){
                    document.getElementById(`piloto-name-${i}`).innerText = '';
                    document.getElementById(`piloto-price-${i}`).innerText = '';
                    document.getElementById(`piloto-price-change-${i}`).innerText = '';
                    document.getElementById(`piloto-photo-${i}`).setAttribute('src', '');
                }else{
                    i -= 5;
                    document.getElementById(`equipo-name-${i}`).innerText = '';
                    document.getElementById(`equipo-price-${i}`).innerText = '';
                    document.getElementById(`equipo-price-change-${i}`).innerText = '';
                    document.getElementById(`equipo-photo-${i}`).setAttribute('src', '');
                } 
            }
        }

        updateAddButtonVisibility();
    }

    // Event listener for the Reset Team button
    document.querySelector('.button-reset-team').addEventListener('click', resetTeamSelection);


    // Function to toggle dropdown visibility
    function toggleDropdown(event) {
        var dropdownContent = event.target.nextElementSibling;
        dropdownContent.classList.toggle("show");
    }

    // Function to update button text and handle exclusive selection
    function updateSelection(event) {
        var dropbtn = event.target.closest(".dropdown").querySelector(".dropbtn");
        var dropdownContent = event.target.closest(".dropdown-content");
        dropbtn.textContent = event.target.textContent;
        dropdownContent.classList.remove("show");
        updateOptions();
    }

    // Function to update the options in 1st, 2nd, and 3rd dropdowns
    function updateOptions() {
        var selectedOptions = [];
        var dropdowns = document.querySelectorAll(".dropdown-content a");

        // Collect selected options from 1st, 2nd, and 3rd dropdowns
        document.querySelectorAll(".first-place .dropdown-content, .second-place .dropdown-content, .third-place .dropdown-content").forEach(function(dropdownContent) {
            var selected = dropdownContent.previousElementSibling.textContent;
            if (selected !== "Dropdown") {
                selectedOptions.push(selected);
            }
        });

        // Update options in 1st, 2nd, and 3rd dropdowns
        dropdowns.forEach(function(option) {
            var parentClass = option.closest(".dropdown").parentElement.className;
            if (selectedOptions.includes(option.textContent) && (parentClass.includes("first-place") || parentClass.includes("second-place") || parentClass.includes("third-place"))) {
                option.style.opacity = "0.4";
                option.style.pointerEvents = "none";
            } else {
                option.style.opacity = "1";
                option.style.pointerEvents = "auto";
            }
        });
    }

    // Add event listeners to all dropdown buttons and options
    document.querySelectorAll(".dropbtn").forEach(function(button) {
        button.addEventListener("click", toggleDropdown);
    });

    document.querySelectorAll(".dropdown-content a").forEach(function(option) {
        option.addEventListener("click", updateSelection);
    });

    // Close the dropdown if the user clicks outside of it
    window.onclick = function(event) {
        if (!event.target.matches('.dropbtn')) {
            var dropdowns = document.getElementsByClassName("dropdown-content");
            for (var i = 0; i < dropdowns.length; i++) {
                var openDropdown = dropdowns[i];
                if (openDropdown.classList.contains('show')) {
                    openDropdown.classList.remove('show');
                }
            }
        }
    }

    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    }

    function getDropdownData(id){
       // Get specified element
        const element = document.getElementById(id);

        // Check if the element exists
        if (!element) {
            return null;
        }

        // Get text content and trim it
        const dataText = element.textContent.trim();

        // Return text or null
        return (dataText === "Dropdown") ? null : dataText;
    }

    function getDriverData(driverId) {
        const driverContainer = document.getElementById(driverId);
        if (driverContainer.style.display === "flex") {
            const driverName = driverContainer.querySelector('.driver-selected-name span').textContent.trim();
            return driverName;
        }
        return null;
    }
    
    function saveTeamSelection() {
        // Get data from dropdowns
        const poleman = getDropdownData("poleman-dropdown");
        const first_pos = getDropdownData("first-pos-dropdown");
        const second_pos = getDropdownData("second-pos-dropdown");
        const third_pos = getDropdownData("third-pos-dropdown");
        const fast_lap = getDropdownData("fast-lap-dropdown");
        const best_team = getDropdownData("best-team-dropdown");

        // Get team selections
        const driver1 = getDriverData("selection1");
        const driver2 = getDriverData("selection2");
        const driver3 = getDriverData("selection3");
        const driver4 = getDriverData("selection4");
        const driver5 = getDriverData("selection5");
        const team1 = getDriverData("selection6");
        const team2 = getDriverData("selection7");
        console.log(driver1, driver2, driver3, driver4, driver5, team1, team2);

        const requiredFields = [
            { label: 'Poleman', value: poleman },
            { label: '1st Position', value: first_pos },
            { label: '2nd Position', value: second_pos },
            { label: '3rd Position', value: third_pos },
            { label: 'Fast Lap', value: fast_lap },
            { label: 'Best Team', value: best_team },
            { label: 'Driver 1', value: driver1 },
            { label: 'Driver 2', value: driver2 },
            { label: 'Driver 3', value: driver3 },
            { label: 'Driver 4', value: driver4 },
            { label: 'Driver 5', value: driver5 },
            { label: 'Team 1', value: team1 },
            { label: 'Team 2', value: team2 },
        ];

        const missing = requiredFields.filter((field) => !field.value).map((field) => field.label);
        if (missing.length > 0) {
            const podiumStatus = `Poleman: ${poleman || '❌'} | 1st: ${first_pos || '❌'} | 2nd: ${second_pos || '❌'} | 3rd: ${third_pos || '❌'}`;
            alert(`Team incomplete. Please complete all selections before saving. Missing: - ${missing.join('- ')} Podium selections status:${podiumStatus}`);
            return;
        }

        const csrfToken = getCSRFToken();
        const gpId = document.querySelector('meta[name="gp-id"]').getAttribute('content');
        const triplePointsChip = document.getElementById('triple-points-chip')?.checked || false;

        // Disable the button to prevent multiple submissions
        const saveButton = document.getElementById("save-team-button");
        saveButton.disabled = true;
        saveButton.classList.add("button-save-active");

        fetch('/team/', {  // Asegúrate de que esta URL coincida con la que usarás en tu vista
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                gp_id: gpId,
                poleman_name: poleman,
                first_pos_name: first_pos,
                second_pos_name: second_pos,
                third_pos_name: third_pos,
                fast_lap_name: fast_lap,
                best_team_name: best_team,
                driver1: driver1,
                driver2: driver2,
                driver3: driver3,
                driver4: driver4,
                driver5: driver5,
                team1: team1,
                team2: team2,
                triple_points_chip: triplePointsChip
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show notification
                console.log('Team saved succesfully!');
                showModal();
    
                // Re-enable the button or refresh the page
                saveButton.innerHTML = 'Team Saved';
                setTimeout(() => {
                    location.reload();
                }, 500);
            } else {
                console.log('Error saving the team.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }

    function toggleBlockAssetSelect() {
        const assetTypeEl = document.getElementById('block-asset-type');
        const driverSelect = document.getElementById('block-driver-id');
        const teamSelect = document.getElementById('block-team-id');
        if (!assetTypeEl || !driverSelect || !teamSelect) return;

        if (assetTypeEl.value === 'team') {
            driverSelect.style.display = 'none';
            teamSelect.style.display = 'inline-block';
        } else {
            driverSelect.style.display = 'inline-block';
            teamSelect.style.display = 'none';
        }
    }

    let confirmActionResolver = null;

    function closeConfirmActionModal(result = false) {
        const modal = document.getElementById('confirm-action-modal');
        const acceptBtn = document.getElementById('confirm-action-accept');
        const cancelBtn = document.getElementById('confirm-action-cancel');
        const closeBtn = document.getElementById('close-confirm-action-modal');

        if (!modal || !acceptBtn || !cancelBtn || !closeBtn) return;

        modal.style.display = 'none';
        acceptBtn.onclick = null;
        cancelBtn.onclick = null;
        closeBtn.onclick = null;
        modal.onclick = null;

        if (confirmActionResolver) {
            const resolver = confirmActionResolver;
            confirmActionResolver = null;
            resolver(result);
        }
    }

    function showConfirmActionModal(message, title = 'Confirm action') {
        const modal = document.getElementById('confirm-action-modal');
        const titleEl = document.getElementById('confirm-action-title');
        const messageEl = document.getElementById('confirm-action-message');
        const acceptBtn = document.getElementById('confirm-action-accept');
        const cancelBtn = document.getElementById('confirm-action-cancel');
        const closeBtn = document.getElementById('close-confirm-action-modal');

        if (!modal || !titleEl || !messageEl || !acceptBtn || !cancelBtn || !closeBtn) {
            return Promise.resolve(window.confirm(message));
        }

        titleEl.textContent = title;
        messageEl.textContent = message;
        modal.style.display = 'flex';

        return new Promise((resolve) => {
            confirmActionResolver = resolve;

            acceptBtn.onclick = () => closeConfirmActionModal(true);
            cancelBtn.onclick = () => closeConfirmActionModal(false);
            closeBtn.onclick = () => closeConfirmActionModal(false);
            modal.onclick = (event) => {
                if (event.target === modal) {
                    closeConfirmActionModal(false);
                }
            };
        });
    }

    async function toggleDrsChip() {
        const drsButton = document.getElementById('drs-chip-button');
        const tripleInput = document.getElementById('triple-points-chip');
        if (!drsButton || !tripleInput || tripleInput.disabled) return;

        const isActivating = !tripleInput.checked;
        if (isActivating) {
            const confirmationMsg = drsButton.dataset.confirmMessage
                ? `${drsButton.dataset.confirmMessage}

¿Seguro que quieres activar DRS Boost en este GP?`
                : '¿Seguro que quieres activar DRS Boost en este GP? No podrás volver a usarlo hasta la próxima ventana.';
            const confirmed = await showConfirmActionModal(confirmationMsg, 'Activar DRS Boost');
            if (!confirmed) {
                return;
            }
        }

        tripleInput.checked = !tripleInput.checked;
        syncDrsChipVisualState();
    }

    function syncDrsChipVisualState() {
        const drsButton = document.getElementById('drs-chip-button');
        const tripleInput = document.getElementById('triple-points-chip');
        const statusEl = document.getElementById('drs-chip-status');
        const captainCard = document.getElementById('selection1');
        if (!drsButton || !tripleInput) return;

        const isActive = !!tripleInput.checked;
        drsButton.classList.toggle('active', isActive);

        if (captainCard) {
            captainCard.classList.toggle('drs-boost-active', isActive);
        }

        if (statusEl) {
            statusEl.textContent = isActive ? 'Active' : '';
            statusEl.classList.toggle('active', isActive);
        }
    }

    function openBlockChipModal() {
        const modal = document.getElementById('block-chip-modal');
        const trigger = document.getElementById('pitstop-chip-button');
        if (!modal || !trigger || trigger.disabled) return;
        modal.style.display = 'flex';
    }

    function closeBlockChipModal() {
        const modal = document.getElementById('block-chip-modal');
        if (!modal) return;
        modal.style.display = 'none';
    }

    async function useBlockChip() {
        const btn = document.getElementById('use-block-chip-button');
        const targetUserEl = document.getElementById('block-target-user');
        const assetTypeEl = document.getElementById('block-asset-type');
        const driverSelect = document.getElementById('block-driver-id');
        const teamSelect = document.getElementById('block-team-id');
        const disclaimer = document.querySelector('#block-chip-modal .chip-disclaimer');
        const gpId = document.querySelector('meta[name="gp-id"]').getAttribute('content');

        if (!btn || !targetUserEl || !assetTypeEl || !driverSelect || !teamSelect) return;

        const assetType = assetTypeEl.value;
        const blockedAssetId = assetType === 'team' ? teamSelect.value : driverSelect.value;
        const targetUserId = targetUserEl.value;

        if (!targetUserId || !blockedAssetId) {
            alert('Selecciona usuario y activo a bloquear.');
            return;
        }

        const confirmationMsg = disclaimer ? `${disclaimer.textContent.trim()}

¿Confirmas que quieres usar el chip ahora?` : '¿Confirmas que quieres usar el chip de bloqueo ahora?';
        const confirmed = await showConfirmActionModal(confirmationMsg, 'Chip de Bloqueo');
        if (!confirmed) {
            return;
        }

        btn.disabled = true;

        fetch('/team/block-chip/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                gp_id: gpId,
                target_user_id: targetUserId,
                asset_type: assetType,
                blocked_asset_id: blockedAssetId,
            }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    location.reload();
                    return;
                }
                btn.disabled = false;
                alert(data.error || 'No se pudo guardar el bloqueo.');
            })
            .catch(() => {
                btn.disabled = false;
                alert('Error al guardar el bloqueo.');
            });
    }

    const saveBtn = document.querySelector('.button-save-team');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveTeamSelection);
    }

    const drsChipButton = document.getElementById('drs-chip-button');
    if (drsChipButton) {
        drsChipButton.addEventListener('click', toggleDrsChip);
    }
    syncDrsChipVisualState();

    const pitStopButton = document.getElementById('pitstop-chip-button');
    if (pitStopButton) {
        pitStopButton.addEventListener('click', openBlockChipModal);
    }

    const closeBlockModalButton = document.getElementById('close-block-chip-modal');
    if (closeBlockModalButton) {
        closeBlockModalButton.addEventListener('click', closeBlockChipModal);
    }

    const blockChipModal = document.getElementById('block-chip-modal');
    if (blockChipModal) {
        blockChipModal.addEventListener('click', function(event) {
            if (event.target === blockChipModal) {
                closeBlockChipModal();
            }
        });
    }

    const blockAssetTypeEl = document.getElementById('block-asset-type');
    if (blockAssetTypeEl) {
        blockAssetTypeEl.addEventListener('change', toggleBlockAssetSelect);
        toggleBlockAssetSelect();
    }

    const blockBtn = document.getElementById('use-block-chip-button');
    if (blockBtn) {
        blockBtn.addEventListener('click', useBlockChip);
    }

    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Escape') return;

        const confirmModal = document.getElementById('confirm-action-modal');
        const blockModal = document.getElementById('block-chip-modal');
        const saveModal = document.getElementById('save-success-modal');

        if (confirmModal && confirmModal.style.display === 'flex') {
            closeConfirmActionModal(false);
            return;
        }
        if (blockModal && blockModal.style.display === 'flex') {
            closeBlockChipModal();
            return;
        }
        if (saveModal && saveModal.style.display === 'flex') {
            closeModal();
        }
    });

});

function showModal() {
    const modal = document.getElementById("save-success-modal");
    modal.style.display = "flex";  // Show the modal as a flexbox
}

function closeModal() {
    const modal = document.getElementById("save-success-modal");
    modal.style.display = "none";  // Hide the modal
}

window.onclick = function(event) {
    const modal = document.getElementById("save-success-modal");
    if (event.target == modal) {
        modal.style.display = "none";
    }
}



function updateAddButtonVisibility() {
    const rows = document.querySelectorAll('.fila-piloto, .fila-equipo');

    rows.forEach(row => {
        const addButton = row.querySelector('#add-selection');
        if (!addButton) return;

        if (row.dataset.blocked === 'true') {
            addButton.disabled = true;
            return;
        }
        if (row.querySelector('.no-selectable-piloto').style.display === 'none') {
            // Obtener el precio del piloto/equipo
            const price = row.querySelector(`.driver-price span:first-child`).innerText;
            const cost = parseFloat(price.replace('M', '').replace('$', ''));

            // Obtener presupuesto disponible actual
            const BudgetEle = document.getElementById('available-budget').querySelector('span:last-child');
            const availableBudget = parseFloat(BudgetEle.innerText.replace('M', '').replace('$', ''));

            // Si no hay suficiente presupuesto, desactivar el botón de añadir y reducir la opacidad
            if (availableBudget < cost) {
                row.style.opacity = '0.5';
                addButton.disabled = true;
            } else {
                row.style.opacity = '1';
                addButton.disabled = false;
            }
        }
    });

}



