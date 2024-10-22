document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('id_photo');
    const imgElement = document.getElementById('profileImagePreview');

    if (fileInput) {
        fileInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imgElement.src = e.target.result; // Preview the new image
                };
                reader.readAsDataURL(file);

                // Automatically submit the form after selecting the image
                const form = fileInput.closest('form');
                form.submit();
            }
        });

        // Click on the hidden file input when the user clicks the image
        imgElement.addEventListener('click', function() {
            fileInput.click();
        });
    }
});
