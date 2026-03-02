from django import forms 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, UsersTeam

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')
    first_name = forms.CharField(required=True, help_text='Required. Enter your first name.')
    last_name = forms.CharField(required=True, help_text='Required. Enter your last name.')


    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def save(self, commit=True):
        user = super(SignupForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class PasswordResetForm(forms.Form):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'}))


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username']

class UserProfileExtraForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['photo']


class TeamAssignmentForm(forms.Form):
    """Form for team assignment with creation, selection, and rename capability."""
    
    team_action = forms.ChoiceField(
        choices=[
            ('none', 'No Team'),
            ('select', 'Select Existing Team'),
            ('create', 'Create New Team'),
        ],
        required=True,
        widget=forms.HiddenInput()
    )
    
    team_id = forms.CharField(required=False, widget=forms.HiddenInput())
    team_name = forms.CharField(
        max_length=255, 
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter team name',
        })
    )
    rename_team_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'New team name',
        })
    )
    
    def __init__(self, *args, season=None, user_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.season = season
        self.user_profile = user_profile
    
    def clean(self):
        cleaned_data = super().clean()
        team_action = cleaned_data.get('team_action')
        team_id = cleaned_data.get('team_id')
        team_name = (cleaned_data.get('team_name') or '').strip()
        
        if team_action == 'select':
            if not team_id:
                raise forms.ValidationError("Please select a team.")
        elif team_action == 'create':
            if not team_name:
                raise forms.ValidationError("Please enter a team name.")
            if len(team_name) > 255:
                raise forms.ValidationError("Team name is too long (max 255 characters).")
        
        return cleaned_data
    
    def save(self, user_profile):
        """Save the team assignment and handle renames."""
        team_action = self.cleaned_data.get('team_action')
        team_id = self.cleaned_data.get('team_id')
        team_name = (self.cleaned_data.get('team_name') or '').strip()
        rename_team_name = (self.cleaned_data.get('rename_team_name') or '').strip()
        
        assigned_team = None
        
        if team_action == 'select':
            try:
                assigned_team = UsersTeam.objects.get(id=int(team_id), season=self.season)
                # Check if team has available space
                if assigned_team.is_full():
                    raise forms.ValidationError("This team is full (maximum 2 members).")
                
                # Handle team rename if provided
                if rename_team_name and rename_team_name != assigned_team.name:
                    # Check if new name is already taken
                    existing = UsersTeam.objects.filter(
                        season=self.season,
                        name__iexact=rename_team_name
                    ).exclude(id=assigned_team.id).exists()
                    
                    if existing:
                        raise forms.ValidationError(f"Team name '{rename_team_name}' already exists.")
                    
                    assigned_team.name = rename_team_name
                    assigned_team.save(update_fields=['name'])
                    
            except (UsersTeam.DoesNotExist, ValueError):
                raise forms.ValidationError("Invalid team selection.")
        
        elif team_action == 'create':
            # Check if team already exists
            existing_team = UsersTeam.objects.filter(
                season=self.season,
                name__iexact=team_name
            ).first()
            
            if existing_team:
                assigned_team = existing_team
                # Check if team has available space
                if assigned_team.is_full():
                    raise forms.ValidationError(f"Team '{team_name}' is full (maximum 2 members).")
            else:
                # Create new team
                assigned_team = UsersTeam.objects.create(
                    season=self.season,
                    name=team_name
                )
        
        # Save the assignment (only if action is not 'none')
        if team_action != 'none':
            user_profile.users_team = assigned_team
        else:
            user_profile.users_team = None
        
        user_profile.save(update_fields=['users_team'])
