from django.core.management.base import BaseCommand
from django.db import transaction

from f1porra_website.apps.public.models import (
    Season, Team, Driver, GrandPrix, DriverPoints, TeamPoints
)

NEW_YEAR = 2026

# -----------------------------
# Helpers
# -----------------------------
def _slug(s: str) -> str:
    # simple slug: lowercase + alnum only
    return "".join(ch for ch in s.lower() if ch.isalnum())

def team_paths(year: int, team_name: str) -> tuple[str, str]:
    s = _slug(team_name)
    return (f"season{year}/teams/{s}.png", f"season{year}/cars/{s}.png")

def driver_paths(year: int, driver_name: str) -> tuple[str, str]:
    # Usamos el último token como "apellido" (como tu convención: verstappen.png, alonso.png, etc.)
    last = driver_name.strip().split()[-1]
    s = _slug(last)
    return (f"season{year}/drivers/{s}.png", f"season{year}/selected/{s}.png")


# -----------------------------
# F1 2026 OFFICIAL DATA (Formula1.com)
# Teams + Drivers: formula1.com/en/teams and /en/drivers
# Calendar: formula1.com/en/racing/2026
# -----------------------------

TEAMS_2026 = [
    # name, color_rgb lo intentamos heredar desde 2025 si existe; si no, None
    {"name": "Alpine",          "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/alpine.png", "selected_link": "season2026/teams/alpine.png"},
    {"name": "Aston Martin",    "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/astonmartin.png", "selected_link": "season2026/teams/astonmartin.png"},
    {"name": "Williams",        "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/williams.png", "selected_link": "season2026/teams/williams.png"},
    {"name": "Audi",            "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/audi.png", "selected_link": "season2026/teams/audi.png"},
    {"name": "Cadillac",        "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/cadillac.png", "selected_link": "season2026/teams/cadillac.png"},
    {"name": "Ferrari",         "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/ferrari.png", "selected_link": "season2026/teams/ferrari.png"},
    {"name": "Haas F1 Team",    "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/haasf1team.png", "selected_link": "season2026/teams/haasf1team.png"},
    {"name": "McLaren",         "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/mclaren.png", "selected_link": "season2026/teams/mclaren.png"},
    {"name": "Mercedes",        "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/mercedes.png", "selected_link": "season2026/teams/mercedes.png"},
    {"name": "Racing Bulls",    "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/racingbulls.png", "selected_link": "season2026/teams/racingbulls.png"},
    {"name": "Red Bull Racing", "color_rgb": None, "season_id": 3, "photo_link": "season2026/teams/redbullracing.png", "selected_link": "season2026/teams/redbullracing.png"},
]

DRIVERS_2026 = [
    # Alpine
    {"name": "Pierre Gasly",      "team_id": "21", "photo_link": "season2026/teams/gasly.png", "season_id": 3, "selected_link": "season2026/teams/gasly.png"},
    {"name": "Franco Colapinto",  "team_id": "21", "photo_link": "season2026/teams/colapinto.png", "season_id": 3, "selected_link": "season2026/teams/colapinto.png"},

    # Aston Martin
    {"name": "Fernando Alonso",   "team_id": "22", "photo_link": "season2026/teams/alonso.png", "season_id": 3, "selected_link": "season2026/teams/alonso.png"},
    {"name": "Lance Stroll",      "team_id": "22", "photo_link": "season2026/teams/stroll.png", "season_id": 3, "selected_link": "season2026/teams/stroll.png"},

    # Williams
    {"name": "Carlos Sainz",      "team_id": "23", "photo_link": "season2026/teams/sainz.png", "season_id": 3, "selected_link": "season2026/teams/sainz.png"},
    {"name": "Alexander Albon",   "team_id": "23", "photo_link": "season2026/teams/albon.png", "season_id": 3, "selected_link": "season2026/teams/albon.png"},

    # Audi
    {"name": "Nico Hulkenberg",   "team_id": "24", "photo_link": "season2026/teams/hulkenberg.png", "season_id": 3, "selected_link": "season2026/teams/hulkenberg.png"},
    {"name": "Gabriel Bortoleto", "team_id": "24", "photo_link": "season2026/teams/bortoleto.png", "season_id": 3, "selected_link": "season2026/teams/bortoleto.png"},

    # Cadillac
    {"name": "Sergio Perez",      "team_id": "25", "photo_link": "season2026/teams/perez.png", "season_id": 3, "selected_link": "season2026/teams/perez.png"},
    {"name": "Valtteri Bottas",   "team_id": "25", "photo_link": "season2026/teams/bottas.png", "season_id": 3, "selected_link": "season2026/teams/bottas.png"},

    # Ferrari
    {"name": "Charles Leclerc",   "team_id": "26", "photo_link": "season2026/teams/leclerc.png", "season_id": 3, "selected_link": "season2026/teams/leclerc.png"},
    {"name": "Lewis Hamilton",    "team_id": "26", "photo_link": "season2026/teams/hamilton.png", "season_id": 3, "selected_link": "season2026/teams/hamilton.png"},

    # Haas F1 Team
    {"name": "Esteban Ocon",      "team_id": "27", "photo_link": "season2026/teams/ocon.png", "season_id": 3, "selected_link": "season2026/teams/ocon.png"},
    {"name": "Oliver Bearman",    "team_id": "27", "photo_link": "season2026/teams/bearman.png", "season_id": 3, "selected_link": "season2026/teams/bearman.png"},

    # McLaren
    {"name": "Lando Norris",      "team_id": "28", "photo_link": "season2026/teams/norris.png", "season_id": 3, "selected_link": "season2026/teams/norris.png"},
    {"name": "Oscar Piastri",     "team_id": "28", "photo_link": "season2026/teams/piastri.png", "season_id": 3, "selected_link": "season2026/teams/piastri.png"},

    # Mercedes
    {"name": "George Russell",    "team_id": "29", "photo_link": "season2026/teams/russell.png", "season_id": 3, "selected_link": "season2026/teams/russell.png"},
    {"name": "Kimi Antonelli",    "team_id": "29", "photo_link": "season2026/teams/antonelli.png", "season_id": 3, "selected_link": "season2026/teams/antonelli.png"},

    # Racing Bulls
    {"name": "Liam Lawson",       "team_id": "30", "photo_link": "season2026/teams/lawson.png", "season_id": 3, "selected_link": "season2026/teams/lawson.png"},
    {"name": "Arvid Lindblad",    "team_id": "30", "photo_link": "season2026/teams/lindblad.png", "season_id": 3, "selected_link": "season2026/teams/lindblad.png"},

    # Red Bull Racing
    {"name": "Max Verstappen",    "team_id": "31", "photo_link": "season2026/teams/verstappen.png", "season_id": 3, "selected_link": "season2026/teams/verstappen.png"},
    {"name": "Isack Hadjar",      "team_id": "31", "photo_link": "season2026/teams/hadjar.png", "season_id": 3, "selected_link": "season2026/teams/hadjar.png"},
]

# Round order based on official F1 2026 calendar (formula1.com/en/racing/2026)
GRAND_PRIXES_2026 = [
    {"nround": 1,  "country": "Australia",             "name": "Australian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/australia.png", "country_link": "season2026/flags/australia.jpg", "gp_photo": "season2026/track/australia.png", "season": 3},
    {"nround": 2,  "country": "China",                 "name": "Chinese Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/china.png", "country_link": "season2026/flags/china.jpg", "gp_photo": "season2026/track/china.png", "season": 3},
    {"nround": 3,  "country": "Japan",                 "name": "Japanese Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/japan.png", "country_link": "season2026/flags/japan.jpg", "gp_photo": "season2026/track/japan.png", "season": 3},
    {"nround": 4,  "country": "Bahrain",               "name": "Bahrain Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/bahrain.png", "country_link": "season2026/flags/bahrain.jpg", "gp_photo": "season2026/track/bahrain.png", "season": 3},
    {"nround": 5,  "country": "Saudi Arabia",          "name": "Saudi Arabian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/arabiasaudi.png", "country_link": "season2026/flags/arabiasaudi.jpg", "gp_photo": "season2026/track/arabiasaudi.png", "season": 3},
    {"nround": 7,  "country": "Canada",                "name": "Canadian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/canada.png", "country_link": "season2026/flags/canada.jpg", "gp_photo": "season2026/track/canada.png", "season": 3},
    {"nround": 8,  "country": "Monaco",                "name": "Monaco Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/monaco.png", "country_link": "season2026/flags/monaco.jpg", "gp_photo": "season2026/track/monaco.png", "season": 3},
    {"nround": 9,  "country": "Barcelona-Catalunya",   "name": "Barcelona-Catalunya Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/barcelona.png", "country_link": "season2026/flags/spain.jpg", "gp_photo": "season2026/track/barcelona.png", "season": 3},
    {"nround": 10, "country": "Austria",               "name": "Austrian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/austria.png", "country_link": "season2026/flags/austria.jpg", "gp_photo": "season2026/track/austria.png", "season": 3},
    {"nround": 11, "country": "Great Britain",         "name": "British Grand Prix",  	"last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/greatbritain.png", "country_link": "season2026/flags/greatbritain.jpg", "gp_photo": "season2026/track/greatbritain.png", "season": 3},
    {"nround": 13, "country": "Hungary",               "name": "Hungarian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/hungary.png", "country_link": "season2026/flags/hungary.jpg", "gp_photo": "season2026/track/hungary.png", "season": 3},
    {"nround": 14, "country": "Netherlands",           "name": "Dutch Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/netherlands.png", "country_link": "season2026/flags/netherlands.jpg", "gp_photo": "season2026/track/netherlands.png", "season": 3},
    {"nround": 15, "country": "Italy",                 "name": "Italian Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/italy.png", "country_link": "season2026/flags/italy.jpg", "gp_photo": "season2026/track/italy.png", "season": 3},
    {"nround": 16, "country": "Spain",                 "name": "Spanish Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/spain.png", "country_link": "season2026/flags/spain.jpg", "gp_photo": "season2026/track/spain.png", "season": 3},
    {"nround": 17, "country": "Azerbaijan",            "name": "Azerbaijan Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/azerbaijan.png", "country_link": "season2026/flags/azerbaijan.jpg", "gp_photo": "season2026/track/azerbaijan.png", "season": 3},
    {"nround": 18, "country": "Singapore",             "name": "Singapore Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/singapore.png", "country_link": "season2026/flags/singapore.jpg", "gp_photo": "season2026/track/singapore.png", "season": 3},
    {"nround": 19, "country": "United States",         "name": "United States Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/unitedstates.png", "country_link": "season2026/flags/unitedstates.jpg", "gp_photo": "season2026/track/unitedstates.png", "season": 3},
    {"nround": 20, "country": "Mexico",                "name": "Mexico City Grand Prix", 	"last_edit_date": None, "gp_end_date": None, "photo_link":"season2026/gps/mexico.png","country_link":"season2026/flags/mexico.jpg","gp_photo":"season2026/track/mexico.png","season":"3"},
    {"nround": 21, "country": "Brazil",                "name": "São Paulo Grand Prix",  	"last_edit_date": None, "gp_end_date": None, "photo_link":"season2026/gps/brazil.png","country_link":"season2026/flags/brazil.jpg","gp_photo":"season2026/track/brazil.png","season":"3"},
    {"nround": 22, "country": "Las Vegas",             "name": "Las Vegas Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/lasvegas.png", "country_link":"season2026/flags/unitedstates.jpg","gp_photo":"season2026/track/lasvegas.png","season":"3"},
    {"nround": 23, "country": "Qatar",                 "name":"Qatar Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/qatar.png","country_link":"season2026/flags/qatar.jpg","gp_photo":"season2026/track/qatar.png","season":"3"},
    {"nround": 24, "country": "Abu Dhabi",             "name": "Abu Dhabi Grand Prix", "last_edit_date": None, "gp_end_date": None, "photo_link": "season2026/gps/abudhabi.png", "country_link":"season2026/flags/abudhabi.jpg","gp_photo":"season2026/track/abudhabi.png","season":"3"},
]


class Command(BaseCommand):
    help = "Seed season 2026: teams, drivers, grands prix; init price=0 and points=NULL for driver/team points."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=NEW_YEAR)
        parser.add_argument("--name", type=str, default=f"{NEW_YEAR} Season")
        parser.add_argument("--init-points", action="store_true", default=True)
        parser.add_argument("--inherit-team-colors-from-year", type=int, default=2025)
        parser.add_argument("--init-round", type=int, default=1)

    @transaction.atomic
    def handle(self, *args, **opts):
        year = opts["year"]
        name = opts["name"]
        inherit_year = opts["inherit_team_colors_from_year"]

        season, created = Season.objects.get_or_create(
            year=year,
            defaults={"name": name}
        )
        if not created and name and season.name != name:
            season.name = name
            season.save(update_fields=["name"])

        # Map colors from previous season if possible (by team name)
        prev_season = Season.objects.filter(year=inherit_year).first()
        prev_color_by_name = {}
        if prev_season:
            for t in Team.objects.filter(season=prev_season):
                prev_color_by_name[t.name] = t.color_rgb

        # Teams
        team_by_name = {}
        for t in TEAMS_2026:
            p, s = team_paths(year, t["name"])
            color = t.get("color_rgb") or prev_color_by_name.get(t["name"])

            team, _ = Team.objects.get_or_create(
                season=season,
                name=t["name"],
                defaults={
                    "color_rgb": color,
                    "photo_link": p,
                    "selected_link": s,
                }
            )
            # si existe y no tiene links, los rellenamos
            changed = False
            if team.photo_link != p:
                team.photo_link = p; changed = True
            if team.selected_link != s:
                team.selected_link = s; changed = True
            if color and team.color_rgb != color:
                team.color_rgb = color; changed = True
            if changed:
                team.save()

            team_by_name[team.name] = team

        # Drivers
        driver_by_name = {}
        for d in DRIVERS_2026:
            team = team_by_name.get(d["team_id"])
            p, s = driver_paths(year, d["name"])

            driver, _ = Driver.objects.get_or_create(
                season=season,
                name=d["name"],
                defaults={
                    "team": team,
                    "photo_link": p,
                    "selected_link": s,
                }
            )
            changed = False
            if team and driver.team_id != team.id:
                driver.team = team; changed = True
            if driver.photo_link != p:
                driver.photo_link = p; changed = True
            if driver.selected_link != s:
                driver.selected_link = s; changed = True
            if changed:
                driver.save()

            driver_by_name[driver.name] = driver

        # Grands Prix
        gps = []
        for g in GRAND_PRIXES_2026:
            gp, _ = GrandPrix.objects.get_or_create(
                season=season,
                country=g["country"],
                name=g["name"],
                defaults={"nround": g["nround"]}
            )
            if gp.nround != g["nround"]:
                gp.nround = g["nround"]
                gp.save(update_fields=["nround"])
            gps.append(gp)

        # Init points (price=0, points=NULL)
        # Init points (price=0, points=NULL) ONLY FOR ONE ROUND (default round 1)
        if opts["init_points"]:
            init_round = opts["init_round"]

            gp = GrandPrix.objects.filter(season=season, nround=init_round).first()
            if not gp:
                raise ValueError(f"No GrandPrix found for season {season.year} with nround={init_round}")

            for driver in driver_by_name.values():
                DriverPoints.objects.get_or_create(
                    season=season,
                    gp=gp,
                    driver=driver,
                    defaults={"price": 0, "points": None}
                )

            for team in team_by_name.values():
                TeamPoints.objects.get_or_create(
                    season=season,
                    gp=gp,
                    team=team,
                    defaults={"price": 0, "points": None}
                )

        self.stdout.write(self.style.SUCCESS(f"✅ Seeded season {season.year} ({season.name})"))
        self.stdout.write(self.style.SUCCESS(
            f"Teams: {len(team_by_name)} | Drivers: {len(driver_by_name)} | GPs: {len(gps)}"
        ))
