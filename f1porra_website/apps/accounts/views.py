from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from .forms import SignupForm, LoginForm, PasswordResetForm, UserProfileForm, UserProfileExtraForm, TeamAssignmentForm
from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from .models import UserProfile, UsersTeam
from .utils import ensure_user_profile_for_active_season, get_active_season

from django.core.files.images import get_image_dimensions
import os

# Security: File upload validation constants
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGE_DIMENSION = 4096  # Max width/height in pixels


def validate_uploaded_image(file):
    """Validate uploaded image file for security."""
    errors = []
    
    # Check file size
    if file.size > MAX_FILE_SIZE:
        errors.append(f'File size exceeds maximum of {MAX_FILE_SIZE // (1024*1024)}MB.')
    
    # Check file extension
    ext = os.path.splitext(file.name)[1].lower()
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    if ext not in allowed_extensions:
        errors.append(f'Invalid file extension. Allowed: {", ".join(allowed_extensions)}')
    
    # Check file content type reported by the upload handler
    if hasattr(file, 'content_type') and file.content_type not in ALLOWED_IMAGE_TYPES:
        errors.append('Invalid file type. Only JPEG, PNG, GIF, and WebP images are allowed.')
    
    # Validate image dimensions
    try:
        width, height = get_image_dimensions(file)
        if width and height:
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                errors.append(f'Image dimensions exceed maximum of {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} pixels.')
    except Exception:
        pass  # If we can't get dimensions, skip this check
    
    # Check for potentially malicious filenames
    if file.name:
        # Remove path traversal attempts
        safe_name = os.path.basename(file.name)
        if safe_name != file.name or '..' in file.name or '/' in file.name or '\\' in file.name:
            errors.append('Invalid filename.')
    
    return errors


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'
    
    def _build_context(self, user_form, profile_form, user_profile):
        profile_photo_url = user_profile.photo.url if user_profile.photo else None

        # Get teams with member count info
        teams_queryset = UsersTeam.objects.filter(season=user_profile.season).order_by('name')
        available_teams = []
        for team in teams_queryset:
            member_count = team.get_member_count()
            available_teams.append({
                'id': team.id,
                'name': team.name,
                'photo': team.photo,
                'members': member_count,
                'is_full': member_count >= UsersTeam.MAX_TEAM_MEMBERS,
            })
        
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

        # Validate uploaded file if present
        if 'photo' in request.FILES:
            photo_file = request.FILES['photo']
            file_errors = validate_uploaded_image(photo_file)
            if file_errors:
                for error in file_errors:
                    profile_form.add_error('photo', error)
                return self.render_to_response(self._build_context(user_form, profile_form, user_profile))

        if user_form.is_valid() and profile_form.is_valid():
            profile_form.save()
            user_form.save()

            # Handle team assignment based on action
            team_action = request.POST.get('team_action', 'none')
            team_name = (request.POST.get('team_name') or '').strip()
            selected_team_id = request.POST.get('team_id')
            rename_team_name = (request.POST.get('rename_team_name') or '').strip()

            # Sanitize team names
            import re
            if team_name:
                team_name = re.sub(r'[<>"\']', '', team_name)[:100]
            if rename_team_name:
                rename_team_name = re.sub(r'[<>"\']', '', rename_team_name)[:100]

            if team_action == 'none':
                # User wants no team - unassign them
                user_profile.users_team = None
                user_profile.save(update_fields=['users_team'])
                messages.success(request, 'You have been removed from your team.')
                
            elif team_action == 'create' and team_name:
                # Create new team or join existing with same name
                existing_team = UsersTeam.objects.filter(
                    season=current_season,
                    name__iexact=team_name,
                ).first()
                
                if existing_team:
                    # Check if existing team is full
                    if existing_team.get_member_count() >= UsersTeam.MAX_TEAM_MEMBERS:
                        messages.error(request, f'A team named "{team_name}" already exists and is full.')
                    else:
                        user_profile.users_team = existing_team
                        user_profile.save(update_fields=['users_team'])
                        messages.success(request, f'Joined existing team "{team_name}".')
                else:
                    # Create new team
                    new_team = UsersTeam.objects.create(
                        season=current_season,
                        name=team_name,
                    )
                    user_profile.users_team = new_team
                    user_profile.save(update_fields=['users_team'])
                    messages.success(request, f'Team "{team_name}" created successfully!')
                    
            elif team_action == 'select' and selected_team_id:
                try:
                    team_id = int(selected_team_id)
                    selected_team = UsersTeam.objects.filter(
                        id=team_id,
                        season=current_season
                    ).first()
                    
                    if selected_team:
                        # Check if team is full (but allow if user is already a member)
                        current_members = selected_team.get_member_count()
                        is_already_member = user_profile.users_team_id == selected_team.id
                        
                        if current_members >= UsersTeam.MAX_TEAM_MEMBERS and not is_already_member:
                            messages.error(request, 'This team is full (maximum 2 members).')
                        else:
                            user_profile.users_team = selected_team
                            user_profile.save(update_fields=['users_team'])
                            
                            # Handle team rename if provided and user is on this team
                            if rename_team_name and rename_team_name != selected_team.name:
                                # Check if new name already exists
                                name_exists = UsersTeam.objects.filter(
                                    season=current_season,
                                    name__iexact=rename_team_name
                                ).exclude(id=selected_team.id).exists()
                                
                                if name_exists:
                                    messages.warning(request, f'Team name "{rename_team_name}" is already taken.')
                                else:
                                    selected_team.name = rename_team_name
                                    selected_team.save(update_fields=['name'])
                                    messages.success(request, f'Team renamed to "{rename_team_name}".')
                            else:
                                messages.success(request, f'Joined team "{selected_team.name}".')
                    else:
                        messages.error(request, 'Selected team not found.')
                except (ValueError, TypeError):
                    messages.error(request, 'Invalid team selection.')

            # Refresh user_profile to get updated data
            user_profile.refresh_from_db()
            return render(request, 'accounts/profile.html', 
                         self._build_context(user_form, profile_form, user_profile))

        return self.render_to_response(self._build_context(user_form, profile_form, user_profile))

def search_teams(request):
    """API endpoint to search for teams."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    current_season = get_active_season()
    if current_season is None:
        return JsonResponse({'teams': [], 'error': 'No active season'})
    
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'teams': []})
    
    teams = UsersTeam.objects.filter(
        season=current_season,
        name__icontains=query
    ).values('id', 'name', 'photo').order_by('name')[:10]
    
    teams_list = []
    for team in teams:
        member_count = UsersTeam.objects.get(id=team['id']).get_member_count()
        teams_list.append({
            'id': team['id'],
            'name': team['name'],
            'members': member_count,
            'is_full': member_count >= UsersTeam.MAX_TEAM_MEMBERS,
            'photo': team['photo'],
        })
    
    return JsonResponse({'teams': teams_list})


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
