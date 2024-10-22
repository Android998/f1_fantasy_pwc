function showLoginForm() {
    document.getElementById('login-form').style.display = "block";
    document.getElementById('signup-form').style.display = "none";
    document.getElementById('sign-in-button').style.borderBottom = "3px solid red";
    document.getElementById('register-button').style.borderBottom = "3px solid transparent";
}

function showSignupForm() {
    console.log("Showing Signup Form");
    document.getElementById('signup-form').style.display = "block";
    document.getElementById('login-form').style.display = "none";
    document.getElementById('register-button').style.borderBottom = "3px solid red";
    document.getElementById('sign-in-button').style.borderBottom = "3px solid transparent";
}

function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const form = params.get('form');
    
    if (form === 'signup') {
        showSignupForm();
    } else {
        showLoginForm();
    }
}

window.onload = checkUrlParams;