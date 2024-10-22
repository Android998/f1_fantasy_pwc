document.addEventListener('DOMContentLoaded', function() {
    var dropdownBtn = document.getElementById('gp-dropdown');
    var dropdownContent = document.getElementById('gp-dropdown-content');

    // Add event listener to each dropdown item
    dropdownContent.addEventListener('click', function(event) {
        var selectedGpName = event.target.textContent.trim();
        var selectedGpId = event.target.getAttribute('data-gp-id');

        // Update the dropdown button's text
        dropdownBtn.textContent = selectedGpName;

        // Redirect to the page with the selected GP as a query parameter
        if (selectedGpId) {
            window.location.href = '?gp=' + selectedGpId;
        }

        // Close the dropdown
        dropdownContent.style.display = 'none';
    });

    // Toggle dropdown display on button click
    dropdownBtn.addEventListener('click', function() {
        dropdownContent.style.display = dropdownContent.style.display === 'block' ? 'none' : 'block';
    });

    // Close dropdown if clicked outside
    document.addEventListener('click', function(event) {
        if (!dropdownBtn.contains(event.target) && !dropdownContent.contains(event.target)) {
            dropdownContent.style.display = 'none';
        }
    });
});
