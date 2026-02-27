from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from f1porra_website.apps.public.models import Season
from .models import UserProfile, UsersTeam


class UserSeasonProfileFlowTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2099, name='Season 2099')

    def test_login_creates_profile_for_active_season(self):
        user = User.objects.create_user(username='demo', password='pass1234')
        UserProfile.objects.filter(user=user).delete()

        response = self.client.post(
            reverse('accounts:login'),
            {'login': '1', 'username': 'demo', 'password': 'pass1234'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserProfile.objects.filter(user=user, season=self.season).exists())

    def test_profile_can_assign_existing_or_new_team_for_season(self):
        user = User.objects.create_user(username='pilot', password='pass1234')
        self.client.force_login(user)
        existing_team = UsersTeam.objects.create(name='Legends', season=self.season)

        response = self.client.post(
            reverse('accounts:profile'),
            {
                'username': 'pilot',
                'first_name': 'Pilot',
                'last_name': 'One',
                'email': 'pilot@example.com',
                'team_id': str(existing_team.id),
            },
        )
        self.assertEqual(response.status_code, 200)

        profile = UserProfile.objects.get(user=user, season=self.season)
        self.assertEqual(profile.users_team, existing_team)

        response = self.client.post(
            reverse('accounts:profile'),
            {
                'username': 'pilot',
                'first_name': 'Pilot',
                'last_name': 'One',
                'email': 'pilot@example.com',
                'team_id': '',
                'new_team_name': 'New Legends',
            },
        )
        self.assertEqual(response.status_code, 200)

        profile.refresh_from_db()
        self.assertIsNotNone(profile.users_team)
        self.assertEqual(profile.users_team.name, 'New Legends')
        self.assertEqual(profile.users_team.season, self.season)

    def test_signup_creates_user_profile_and_logs_in_user(self):
        response = self.client.post(
            reverse('accounts:login'),
            {
                'signup': '1',
                'username': 'newbie',
                'first_name': 'New',
                'last_name': 'User',
                'email': 'newbie@example.com',
                'password1': 'Strongpass123',
                'password2': 'Strongpass123',
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='newbie')
        self.assertTrue(UserProfile.objects.filter(user=user, season=self.season).exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_signup_invalid_keeps_signup_form_visible(self):
        response = self.client.post(
            reverse('accounts:login'),
            {
                'signup': '1',
                'username': 'broken',
                'first_name': 'Broken',
                'last_name': 'User',
                'email': 'broken@example.com',
                'password1': 'abc12345',
                'password2': 'different123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'active-form')
        self.assertContains(response, 'signup')