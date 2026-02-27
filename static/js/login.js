function showLoginForm() {
    document.getElementById('login-form').style.display = "block";
    document.getElementById('signup-form').style.display = "none";
    document.getElementById('sign-in-button').style.borderBottom = "3px solid red";
    document.getElementById('register-button').style.borderBottom = "3px solid transparent";
}

function showSignupForm() {
    document.getElementById('signup-form').style.display = "block";
    document.getElementById('login-form').style.display = "none";
    document.getElementById('register-button').style.borderBottom = "3px solid red";
    document.getElementById('sign-in-button').style.borderBottom = "3px solid transparent";
}

function checkDefaultForm() {
    const params = new URLSearchParams(window.location.search);
    const queryForm = params.get('form');

    if (queryForm === 'signup' || queryForm === 'login') {
        queryForm === 'signup' ? showSignupForm() : showLoginForm();
        return;
    }

    const activeFormElement = document.getElementById('active-form');
    if (activeFormElement) {
        const activeForm = JSON.parse(activeFormElement.textContent);
        if (activeForm === 'signup') {
            showSignupForm();
            return;
        }
    }
    showLoginForm();
}

window.onload = checkDefaultForm;