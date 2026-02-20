from django.contrib.auth.models import User
from django.contrib import messages  # Import messages for notifications
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login 
from .forms import SignupForm, LoginForm, PasswordResetForm, UserProfileForm, UserProfileExtraForm, UsersTeamForm
from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from .models import UserProfile, UsersTeam
from f1porra_website.apps.public.models import Season

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    def get(self, request):
        try:
            current_season = Season.objects.get(is_active=True)
        except Season.DoesNotExist:
            # Handle no active season
            return render(request, 'accounts/profile.html', {'error': 'No active season found.'})
        
        user_profile, created = UserProfile.objects.get_or_create(user=request.user, season=current_season)
        
        user_form = UserProfileForm(instance=request.user)
        profile_form = UserProfileExtraForm(instance=user_profile)
        
        if user_profile.users_team:
            team_form = UsersTeamForm(instance=user_profile.users_team)
        else:
            team_form = UsersTeamForm()
        
        # Get the profile photo URL after saving
        profile_photo_url = user_profile.photo.url if user_profile.photo else None

        return self.render_to_response({
            'user_form': user_form,
            'profile_form': profile_form,
            'user_profile': user_profile,
            'profile_photo_url': profile_photo_url,
        })

    def post(self, request):
        try:
            current_season = Season.objects.get(is_active=True)
        except Season.DoesNotExist:
            return render(request, 'accounts/profile.html', {'error': 'No active season found.'})
        
        user_profile, created = UserProfile.objects.get_or_create(user=request.user, season=current_season)

        # Handle the personal information update
        user_form = UserProfileForm(request.POST, instance=request.user)
        profile_form = UserProfileExtraForm(request.POST, request.FILES, instance=user_profile)

        # Get the team name from the form
        team_name = request.POST.get('team_name')

        if user_form.is_valid() and profile_form.is_valid():
            # Save user and profile information
            user_form.save()
            profile_form.save()  # Save the profile form, including the uploaded photo.

            # Check if the team name is valid
            try:
                team = UsersTeam.objects.get(name=team_name)
                user_profile.users_team = team
                user_profile.save()
                messages.success(request, 'Your information and team have been updated successfully!')
            except UsersTeam.DoesNotExist:
                messages.error(request, 'The specified team does not exist. Please enter a valid team name.')

        else:
            # If forms are invalid, show error messages
            for form in [user_form, profile_form]:
                for field in form:
                    if form[field].errors:
                        messages.error(request, f'Error in {field}: {form[field].errors.as_text()}')

        # Get the profile photo URL after saving
        profile_photo_url = user_profile.photo.url if user_profile.photo else None

        return self.render_to_response({
            'user_form': user_form,
            'profile_form': profile_form,
            'user_profile': user_profile,
            'profile_photo_url': profile_photo_url,
        })


def password_reset(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            # Use Django's built-in PasswordResetView to handle the email sending
            django_form = DjangoPasswordResetForm({'email': form.cleaned_data['email']})
            if django_form.is_valid():
                email = form.cleaned_data['email']
                if User.objects.filter(email=email).exists():
                    django_form = DjangoPasswordResetForm({'email': email})
                    if django_form.is_valid():
                        django_form.save(request=request, use_https=request.is_secure())
                    return redirect('accounts:password_reset_done')
                else:
                    form.add_error('email', 'This email address is not registered.')
    else:
        form = PasswordResetForm()

    return render(request, 'accounts/password_reset_form.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        if 'signup' in request.POST:
            signup_form = SignupForm(request.POST)
            login_form = LoginForm()
            if signup_form.is_valid():
                signup_form.save()
                return redirect('public:home')

        elif 'login' in request.POST:
            login_form = LoginForm(request.POST)
            signup_form = SignupForm()
            if login_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password']
                user = authenticate(request, username=username, password=password)
                if user:
                    login(request, user)
                    return redirect('public:home')
    else:
        signup_form = SignupForm()
        login_form = LoginForm()

    return render(request, 'accounts/login.html', {'signup_form': signup_form, 'login_form': login_form})
