from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from .forms import SignupForm, LoginForm, PasswordResetForm, UserProfileForm, UserProfileExtraForm
from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from .models import UserProfile, UsersTeam
from .utils import ensure_user_profile_for_active_season, get_active_season

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    def _build_context(self, user_form, profile_form, user_profile):
        profile_photo_url = user_profile.photo.url if user_profile.photo else None

        available_teams = UsersTeam.objects.filter(season=user_profile.season).order_by('name')
        return {
            'user_form': user_form,
            'profile_form': profile_form,
            'user_profile': user_profile,
            'profile_photo_url': profile_photo_url,
            'available_teams': available_teams,
        }

    def get(self, request):
        current_season = get_active_season()
        if current_season is None:
            return render(request, 'accounts/profile.html', {'error': 'No active season found.'})

        user_profile, _ = UserProfile.objects.get_or_create(user=request.user, season=current_season)
        user_form = UserProfileForm(instance=request.user)
        profile_form = UserProfileExtraForm(instance=user_profile)
        return self.render_to_response(self._build_context(user_form, profile_form, user_profile))

    def post(self, request):
        current_season = get_active_season()
        if current_season is None:
            return render(request, 'accounts/profile.html', {'error': 'No active season found.'})

        # Handle the personal information update
        user_profile, _ = UserProfile.objects.get_or_create(user=request.user, season=current_season)
        user_form = UserProfileForm(request.POST, instance=request.user)
        profile_form = UserProfileExtraForm(request.POST, request.FILES, instance=user_profile)

        selected_team_id = request.POST.get('team_id')
        new_team_name = (request.POST.get('new_team_name') or '').strip()

        if user_form.is_valid() and profile_form.is_valid():
            profile_form.save()
            user_form.save()

            assigned_team = None
            if new_team_name:
                existing_team = UsersTeam.objects.filter(
                    season=current_season,
                    name__iexact=new_team_name,
                ).first()
                assigned_team = existing_team
                if assigned_team is None:
                    assigned_team = UsersTeam.objects.create(
                        season=current_season,
                        name=new_team_name,
                    )
            elif selected_team_id:
                assigned_team = UsersTeam.objects.filter(
                    id=selected_team_id,
                    season=current_season,
                ).first()

            user_profile.users_team = assigned_team
            user_profile.save(update_fields=['users_team'])
            messages.success(request, 'Your profile has been updated successfully!')

        else:
            # If forms are invalid, show error messages
            for form in [user_form, profile_form]:
                for field in form:
                    if form[field].errors:
                        messages.error(request, f'Error in {field}: {form[field].errors.as_text()}')

        return self.render_to_response(self._build_context(user_form, profile_form, user_profile))


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
    active_form = request.GET.get('form', 'login')

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'login')

        if form_type == 'signup':
            signup_form = SignupForm(request.POST)
            login_form = LoginForm()
            active_form = 'signup'
            if signup_form.is_valid():
                user = signup_form.save()
                login(request, user)
                return redirect('public:home')

        else:
            login_form = LoginForm(request.POST)
            signup_form = SignupForm()
            active_form = 'login'
            if login_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password']
                user = authenticate(request, username=username, password=password)
                if user:
                    ensure_user_profile_for_active_season(user)
                    login(request, user)
                    return redirect('public:home')
                login_form.add_error(None, 'Invalid username or password.')
    else:
        signup_form = SignupForm()
        login_form = LoginForm()

    return render(
        request,
        'accounts/login.html',
        {'signup_form': signup_form, 'login_form': login_form, 'active_form': active_form},
    )