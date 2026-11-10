from datetime import date
from unittest.mock import patch

# Create your tests here.
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase

from f1porra_website.apps.accounts.models import UserProfile, UsersTeam
from f1porra_website.apps.public import views
from f1porra_website.apps.public.models import (
    Driver,
    DriverPoints,
    GrandPrix,
    Porra,
    Season,
    Team,
    TeamPoints,
)
from f1porra_website.apps.public.src.api_client import (
    GPSessionData,
    QualifyingResult,
    fetch_qualy_data,
)


class TeamViewBudgetAndPricesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.season = Season.objects.create(year=date.today().year, name="Season Test")
        self._old_current_season = views.current_season
        views.current_season = self.season

        self.users_team = UsersTeam.objects.create(name="Alpha", color="#111111")
        self.user = User.objects.create_user(username="tester", password="secret")
        UserProfile.objects.create(user=self.user, users_team=self.users_team, season=self.season)

        self.gp = GrandPrix.objects.create(
            season=self.season,
            country="Spain",
            nround=1,
            name="Spanish GP",
        )

        self.team1 = Team.objects.create(season=self.season, name="McLaren", color_rgb="#ff8000")
        self.team2 = Team.objects.create(season=self.season, name="Ferrari", color_rgb="#dc0000")

        self.drivers = [
            Driver.objects.create(season=self.season, name=f"Driver {i}", team=self.team1)
            for i in range(1, 6)
        ]

        for index, driver in enumerate(self.drivers, start=1):
            DriverPoints.objects.create(
                season=self.season,
                driver=driver,
                gp=self.gp,
                price=10 + index,
                points=5 * index,
            )

        TeamPoints.objects.create(season=self.season, team=self.team1, gp=self.gp, price=20, points=100)
        TeamPoints.objects.create(season=self.season, team=self.team2, gp=self.gp, price=25, points=90)

        Porra.objects.create(
            season=self.season,
            user=self.user,
            gp=self.gp,
            driver1=self.drivers[0],
            driver2=self.drivers[1],
            driver3=self.drivers[2],
            driver4=self.drivers[3],
            driver5=self.drivers[4],
            team1=self.team1,
            team2=self.team2,
        )

    def tearDown(self):
        views.current_season = self._old_current_season

    def _build_request(self):
        request = self.factory.get('/team/')
        request.user = self.user
        return request

    def test_team_view_loads_current_prices_when_only_one_gp_exists(self):
        request = self._build_request()

        with patch('f1porra_website.apps.public.views.render') as mocked_render:
            views.team(request)

        context = mocked_render.call_args.args[2]
        pilot_prices = {pilot.name: pilot.current_price for pilot in context['pilotos']}
        constructor_prices = {team.name: team.current_price for team in context['equipos']}

        self.assertEqual(pilot_prices['Driver 1'], 11)
        self.assertEqual(pilot_prices['Driver 5'], 15)
        self.assertEqual(constructor_prices['McLaren'], 20)
        self.assertEqual(constructor_prices['Ferrari'], 25)

    def test_team_view_recalculates_budget_from_database_on_page_load(self):
        request = self._build_request()

        with patch('f1porra_website.apps.public.views.render') as mocked_render:
            views.team(request)

        context = mocked_render.call_args.args[2]
        expected_total_spent = sum(10 + i for i in range(1, 6)) + 20 + 25
        self.assertEqual(context['budget_cap'], 160.0)
        self.assertEqual(context['remain_price'], 160.0 - expected_total_spent)


class QualifyingDataAvailabilityTests(SimpleTestCase):
    @staticmethod
    def _qualy_data(q1_time):
        return GPSessionData(
            season=2026,
            round_number=20,
            gp_name="Brazilian Grand Prix",
            qualifying=[
                QualifyingResult(
                    position=1,
                    driver_name="Lando Norris",
                    constructor_name="McLaren",
                    q1_time=q1_time,
                    q2_time=None,
                    q3_time=None,
                ),
            ],
            pole_sitter="Lando Norris",
        )

    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_jolpica")
    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_openf1")
    def test_positions_without_any_q1_times_are_not_scored_as_dns(self, openf1, jolpica):
        jolpica.return_value = None
        openf1.return_value = self._qualy_data(None)

        self.assertIsNone(fetch_qualy_data(2026, 20))

    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_jolpica")
    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_openf1")
    def test_openf1_qualy_is_accepted_when_q1_timings_are_available(self, openf1, jolpica):
        jolpica.return_value = None
        expected = self._qualy_data("90.123")
        openf1.return_value = expected

        self.assertIs(fetch_qualy_data(2026, 20), expected)

    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_jolpica")
    @patch("f1porra_website.apps.public.src.api_client.fetch_qualy_data_openf1")
    def test_incomplete_jolpica_data_falls_back_to_timed_openf1_data(self, openf1, jolpica):
        jolpica.return_value = self._qualy_data(None)
        expected = self._qualy_data("90.123")
        openf1.return_value = expected

        self.assertIs(fetch_qualy_data(2026, 20), expected)


class StandingsSeasonScopedProfileTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.season_2025 = Season.objects.create(year=2025, name="2025")
        self.season_2026 = Season.objects.create(year=2026, name="2026")
        self._old_current_season = views.current_season
        views.current_season = self.season_2026

        self.user = User.objects.create_user(username="multi", first_name="Multi User", password="secret")

        old_team = UsersTeam.objects.create(name="Old Team", color="#123456")
        new_team = UsersTeam.objects.create(name="New Team", color="#654321")

        UserProfile.objects.create(user=self.user, users_team=old_team, season=self.season_2025)
        UserProfile.objects.create(user=self.user, users_team=new_team, season=self.season_2026)

        self.gp_2025 = GrandPrix.objects.create(season=self.season_2025, country="Monaco", nround=1, name="Monaco GP")
        self.gp_2026 = GrandPrix.objects.create(season=self.season_2026, country="Spain", nround=1, name="Spanish GP")

        Porra.objects.create(season=self.season_2025, user=self.user, gp=self.gp_2025, points=90)
        Porra.objects.create(season=self.season_2026, user=self.user, gp=self.gp_2026, points=120)

    def tearDown(self):
        views.current_season = self._old_current_season

    def test_standings_uses_selected_season_profile_and_no_duplicate_rows(self):
        request = self.factory.get('/standings/', {'season': '2026', 'gp': 'overall'})

        with patch('f1porra_website.apps.public.views.render') as mocked_render:
            views.standings(request)

        context = mocked_render.call_args.args[2]
        self.assertEqual(len(context['user_standings']), 1)
        self.assertEqual(context['user_standings'][0]['team_name'], 'New Team')
        self.assertEqual(context['team_standings'][0]['team_name'], 'New Team')