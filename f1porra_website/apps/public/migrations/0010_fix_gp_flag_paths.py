from django.db import migrations


def fix_gp_flag_paths(apps, schema_editor):
    Season = apps.get_model("public", "Season")
    GrandPrix = apps.get_model("public", "GrandPrix")

    season = Season.objects.filter(year=2026).first()
    if not season:
        return

    fixes = {
        "Hungary": "season2026/flags/hungria.jpg",
        "Azerbaijan": "season2026/flags/azerbaiyan.jpg",
        "United States": "season2026/flags/texas.jpg",
    }

    for country, path in fixes.items():
        GrandPrix.objects.filter(season=season, country=country).update(country_link=path)


class Migration(migrations.Migration):
    dependencies = [
        ("public", "0009_fix_gp_track_paths"),
    ]

    operations = [
        migrations.RunPython(fix_gp_flag_paths, migrations.RunPython.noop),
    ]
