from django.db import models
from django.contrib.auth.models import User

# Create your models

class Season(models.Model):
    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=64, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    
    def __str__(self):
        return self.name or str(self.year)

#
# GRAND PRIX
#
class GrandPrix(models.Model):
    # Using AutoField is recommended for PKs.
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    country = models.CharField(max_length=64)
    nround = models.PositiveIntegerField(blank=True, null=True)
    name = models.CharField(max_length=64)
    last_edit_date = models.DateTimeField(blank=True, null=True)
    qualy_date = models.DateTimeField(blank=True, null=True)
    gp_date = models.DateTimeField(blank=True, null=True)
    is_sprint = models.BooleanField(default=False)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    country_link = models.CharField(max_length=300, blank=True, null=True)
    gp_photo = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_grandprixes'
        verbose_name_plural = 'grandPrixes'

    def __str__(self):
        return self.season.name + " - " + self.country or str(self.season.name + " - " + self.name)

#
# TEAM
#
class Team(models.Model):
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    color_rgb = models.CharField(max_length=7, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    selected_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_teams'
        verbose_name_plural = 'teams'
    
    def __str__(self):
        return self.season.name + " - " + self.name

#
# DRIVER
#
class Driver(models.Model):
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    selected_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_drivers'
        verbose_name_plural = 'drivers'
    
    def __str__(self):
        return self.season.name + " - " + self.name
    
    @property
    def number_photo_link(self):
        return self.photo_link.replace("drivers/", "number/")
    
    @property
    def selected_photo_link(self):
        # from: season2026/drivers/name.png
        # to:   season2026/selected/name.png
        return (self.photo_link or "").replace("drivers/", "selected/")

#
# DRIVER POINTS
#
class DriverPoints(models.Model):
    class Meta:
        db_table = 'public_driverpoints'
        verbose_name_plural = 'driverpoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    # Now referencing the new integer PK field 'id'
    driver = models.ForeignKey(Driver, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return str(self.season.year) + " " + self.gp.country + " - " + self.driver.name

#
# TEAM POINTS
#
class TeamPoints(models.Model):
    class Meta:
        db_table = 'public_teampoints'
        verbose_name_plural = 'teampoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    team = models.ForeignKey(Team, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return str(self.season.year) + " " + self.gp.country + " - " + self.team.name


#
# PORRA
#
class Porra(models.Model):
    class Meta:
        db_table = 'public_porra'
        verbose_name_plural = 'porras'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    fill_date = models.DateTimeField(blank=True, null=True)
    poleman = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman')
    first_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos')
    second_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos')
    third_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos')
    fast_lap = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap')
    driver1 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver1')
    driver2 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver2')
    driver3 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver3')
    driver4 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver4')
    driver5 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver5')
    team_winner = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner')
    team1 = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team1')
    team2 = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team2')
    triple_points_chip = models.BooleanField(default=False)
    points = models.IntegerField(blank=True, null=True)


class BlockChip(models.Model):
    class AssetType(models.TextChoices):
        DRIVER = 'driver', 'Driver'
        TEAM = 'team', 'Team'

    class Meta:
        db_table = 'public_blockchip'
        verbose_name_plural = 'blockchips'
        constraints = [
            models.UniqueConstraint(fields=['season', 'blocker', 'gp'], name='unique_block_per_gp'),
        ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE)
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_made')
    target = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_received')
    asset_type = models.CharField(max_length=8, choices=AssetType.choices)
    blocked_driver = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True)
    blocked_team = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.blocker.username} blocked {self.target.username} ({self.asset_type}) @ {self.gp.country}"


#
# DRIVER GP POINTS DETAIL — per-component breakdown for admin review
#
class DriverGPPointsDetail(models.Model):
    class Meta:
        db_table = 'public_drivergppointsdetail'
        verbose_name_plural = 'driver GP points detail'
        constraints = [
            models.UniqueConstraint(
                fields=['season', 'driver', 'gp'],
                name='unique_driver_gp_detail',
            ),
        ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)

    # Qualifying breakdown
    qualy_participation = models.IntegerField(default=0, help_text="1=Q1, 2=Q2, 3=Q3")
    qualy_position = models.IntegerField(default=0, help_text="Reverse-grid points (0-10)")
    qualy_teammate = models.IntegerField(default=0, help_text="Teammate bonus (0 or 1)")
    qualy_dns_penalty = models.IntegerField(default=0, help_text="-10 if no Q1 time set")
    qualy_total = models.IntegerField(default=0, help_text="Sum of qualy components")

    # Race breakdown
    race_f1_points = models.IntegerField(default=0, help_text="F1 position points (25,18,...)")
    race_positions_gained = models.IntegerField(default=0, help_text="Positions gained/lost")
    race_teammate = models.IntegerField(default=0, help_text="Teammate bonus (0 or 2)")
    race_dnf_penalty = models.IntegerField(default=0, help_text="-10 if DNF")
    race_total = models.IntegerField(default=0, help_text="Sum of race components")

    # Sprint breakdown (0 on non-sprint weekends)
    sprint_position_pts = models.IntegerField(default=0, help_text="Sprint position points (8,7,...)")
    sprint_positions_gained = models.IntegerField(default=0, help_text="Sprint positions gained")
    sprint_teammate = models.IntegerField(default=0, help_text="Sprint teammate bonus (0 or 2)")
    sprint_dnf_penalty = models.IntegerField(default=0, help_text="-10 if sprint DNF")
    sprint_total = models.IntegerField(default=0, help_text="Sum of sprint components")

    # Totals
    auto_total = models.IntegerField(default=0, help_text="Automatic total (qualy + race + sprint)")
    admin_adjustment = models.IntegerField(default=0, help_text="Manual adjustment by admin")
    final_total = models.IntegerField(default=0, help_text="auto_total + admin_adjustment")
    admin_note = models.TextField(blank=True, default="", help_text="Explanation for admin adjustment")
    updated_at = models.DateTimeField(auto_now=True)

    def compute_totals(self):
        """Recompute the sub-totals and final total from components."""
        self.qualy_total = (
            self.qualy_participation + self.qualy_position
            + self.qualy_teammate + self.qualy_dns_penalty
        )
        self.race_total = (
            self.race_f1_points + self.race_positions_gained
            + self.race_teammate + self.race_dnf_penalty
        )
        self.sprint_total = (
            self.sprint_position_pts + self.sprint_positions_gained
            + self.sprint_teammate + self.sprint_dnf_penalty
        )
        self.auto_total = self.qualy_total + self.race_total + self.sprint_total
        self.final_total = self.auto_total + self.admin_adjustment

    def __str__(self):
        return f"{self.driver.name} @ {self.gp.country} = {self.final_total}pts"


#
# TEAM GP POINTS DETAIL — per-component breakdown for admin review
#
class TeamGPPointsDetail(models.Model):
    class Meta:
        db_table = 'public_teamgppointsdetail'
        verbose_name_plural = 'team GP points detail'
        constraints = [
            models.UniqueConstraint(
                fields=['season', 'team', 'gp'],
                name='unique_team_gp_detail',
            ),
        ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)

    # Qualifying breakdown
    qualy_driver_pts_sum = models.IntegerField(default=0, help_text="Sum of both drivers' qualy points")
    qualy_team_bonus = models.IntegerField(default=0, help_text="Team qualy bonus (1/3/5)")
    qualy_total = models.IntegerField(default=0, help_text="Sum of team qualy components")

    # Race breakdown
    race_driver_pts_sum = models.IntegerField(default=0, help_text="Sum of both drivers' race points")
    race_total = models.IntegerField(default=0, help_text="Team race total")

    # Sprint breakdown
    sprint_driver_pts_sum = models.IntegerField(default=0, help_text="Sum of sprint points")
    sprint_total = models.IntegerField(default=0, help_text="Team sprint total")

    # Totals
    auto_total = models.IntegerField(default=0, help_text="Automatic total (qualy + race + sprint)")
    admin_adjustment = models.IntegerField(default=0, help_text="Manual adjustment by admin")
    final_total = models.IntegerField(default=0, help_text="auto_total + admin_adjustment")
    admin_note = models.TextField(blank=True, default="", help_text="Explanation for admin adjustment")
    updated_at = models.DateTimeField(auto_now=True)

    def compute_totals(self):
        """Recompute the sub-totals and final total from components."""
        self.qualy_total = self.qualy_driver_pts_sum + self.qualy_team_bonus
        self.race_total = self.race_driver_pts_sum
        self.sprint_total = self.sprint_driver_pts_sum
        self.auto_total = self.qualy_total + self.race_total + self.sprint_total
        self.final_total = self.auto_total + self.admin_adjustment

    def __str__(self):
        return f"{self.team.name} @ {self.gp.country} = {self.final_total}pts"

#
# RACE RESULTS
#
class RaceResults(models.Model):
    class Meta:
        db_table = 'public_raceresults'
        verbose_name_plural = 'raceresults'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    poleman = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_res')
    first_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_res')
    second_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_res')
    third_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_res')
    fast_lap = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_res')
    team_winner = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_res')


class Achievement(models.Model):
    class Category(models.TextChoices):
        GP = 'gp', 'GP'
        SEASON = 'season', 'Season'
        ALL_TIME = 'all_time', 'All Time'

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField()
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.SEASON)
    icon = models.CharField(max_length=16, blank=True, null=True)
    icon_class = models.CharField(max_length=32, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'public_achievements'
        verbose_name_plural = 'achievements'

    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, on_delete=models.SET_NULL, blank=True, null=True)
    gp = models.ForeignKey(GrandPrix, on_delete=models.SET_NULL, blank=True, null=True)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'public_userachievements'
        verbose_name_plural = 'userachievements'
        constraints = [
            models.UniqueConstraint(fields=['user', 'achievement'], name='unique_user_achievement'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.achievement.name}"
