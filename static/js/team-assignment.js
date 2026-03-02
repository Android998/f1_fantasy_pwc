/**
 * Team Assignment Management
 * Handles team selection, creation, and UI interactions with button-style interface
 */

document.addEventListener('DOMContentLoaded', function() {
    const teamActionButtons = document.querySelectorAll('.team-action-button');
    const teamActionInput = document.getElementById('teamActionInput');
    const teamSelectContent = document.getElementById('teamSelectContent');
    const teamCreateContent = document.getElementById('teamCreateContent');
    const teamRenameContent = document.getElementById('teamRenameContent');
    const teamSelect = document.getElementById('team_id');
    const teamNameInput = document.getElementById('team_name');
    const renameTeamNameInput = document.getElementById('rename_team_name');
    const profileForm = document.getElementById('profileForm');

    // Initialize first button as active
    const firstButton = document.querySelector('.team-action-button[data-action="none"]');
    if (firstButton) {
        firstButton.classList.add('active');
    }

    // Handle team action button clicks
    teamActionButtons.forEach(button => {
        button.addEventListener('click', function() {
            const action = this.dataset.action;
            selectTeamAction(action);
        });
    });

    // Select team action
    function selectTeamAction(action) {
        // Update active button
        teamActionButtons.forEach(btn => btn.classList.remove('active'));
        const selectedButton = document.querySelector(`.team-action-button[data-action="${action}"]`);
        if (selectedButton) {
            selectedButton.classList.add('active');
        }

        // Update hidden input
        teamActionInput.value = action;

        // Show/hide content based on action
        teamSelectContent.style.display = 'none';
        teamCreateContent.style.display = 'none';
        teamRenameContent.style.display = 'none';

        if (action === 'select') {
            teamSelectContent.style.display = 'block';
            teamSelect.focus();
        } else if (action === 'create') {
            teamCreateContent.style.display = 'block';
            teamNameInput.focus();
        }

        // Clear inputs when switching actions
        if (action !== 'create') {
            teamNameInput.value = '';
            hideTeamCreateConfirmation();
        }
        if (action !== 'select') {
            teamSelect.value = '';
        }
    }

    // Handle team name input for confirmation
    if (teamNameInput) {
        teamNameInput.addEventListener('input', function() {
            const trimmedValue = this.value.trim();
            
            if (trimmedValue && teamNameInput.parentElement.parentElement === teamCreateContent) {
                showTeamCreateConfirmation(trimmedValue);
            } else {
                hideTeamCreateConfirmation();
            }
        });

        teamNameInput.addEventListener('change', function() {
            this.value = this.value.trim();
        });

        // Enforce max length
        teamNameInput.addEventListener('blur', function() {
            if (this.value.length > 255) {
                this.value = this.value.substring(0, 255);
            }
        });
    }

    // Show team creation confirmation
    function showTeamCreateConfirmation(teamName) {
        const confirmationDiv = document.getElementById('teamCreateConfirmation');
        const teamNameConfirm = document.getElementById('teamNameConfirm');
        if (confirmationDiv && teamNameConfirm) {
            teamNameConfirm.textContent = teamName;
            confirmationDiv.style.display = 'block';
        }
    }

    // Hide team creation confirmation
    function hideTeamCreateConfirmation() {
        const confirmationDiv = document.getElementById('teamCreateConfirmation');
        if (confirmationDiv) {
            confirmationDiv.style.display = 'none';
        }
    }

    // Handle team dropdown
    if (teamSelect) {
        teamSelect.addEventListener('change', function() {
            const selectedValue = this.value;
            
            if (selectedValue) {
                // Show rename option for selected team
                const selectedOption = this.querySelector(`option[value="${selectedValue}"]`);
                if (selectedOption && selectedOption.dataset.full === 'false') {
                    teamRenameContent.style.display = 'block';
                    renameTeamNameInput.value = selectedOption.textContent.split('(')[0].trim();
                } else {
                    teamRenameContent.style.display = 'none';
                }
            } else {
                teamRenameContent.style.display = 'none';
                renameTeamNameInput.value = '';
            }
        });

        // Dropdown styling
        teamSelect.addEventListener('focus', function() {
            this.classList.add('focused');
        });

        teamSelect.addEventListener('blur', function() {
            this.classList.remove('focused');
        });
    }

    // Form submission validation
    if (profileForm) {
        profileForm.addEventListener('submit', function(e) {
            const action = teamActionInput.value;

            if (action === 'select') {
                if (!teamSelect.value) {
                    e.preventDefault();
                    showError('Please select a team');
                    return false;
                }
                // Check if selected team is full
                const selectedOption = teamSelect.querySelector(`option[value="${teamSelect.value}"]`);
                if (selectedOption && selectedOption.dataset.full === 'true') {
                    e.preventDefault();
                    showError('This team is full (maximum 2 members)');
                    return false;
                }
            } else if (action === 'create') {
                const teamName = teamNameInput.value.trim();
                if (!teamName) {
                    e.preventDefault();
                    showError('Please enter a team name');
                    return false;
                }
                if (teamName.length > 255) {
                    e.preventDefault();
                    showError('Team name is too long (max 255 characters)');
                    return false;
                }
            }

            return true;
        });
    }

    // Show error message
    function showError(message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger';
        alertDiv.innerHTML = `<p>${message}</p>`;
        
        const container = profileForm.parentElement;
        const existingAlert = container.querySelector('.alert');
        
        if (existingAlert) {
            existingAlert.replaceWith(alertDiv);
        } else {
            container.insertBefore(alertDiv, profileForm);
        }

        // Scroll to alert
        alertDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});
