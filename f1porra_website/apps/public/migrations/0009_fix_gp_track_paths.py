from django.db import migrations


def fix_gp_track_paths(apps, schema_editor):
    Season = apps.get_model("public", "Season")
    GrandPrix = apps.get_model("public", "GrandPrix")

    season = Season.objects.filter(year=2026).first()
    if not season:
        return

    fixes = {
        "Azerbaijan": "season2026/track/azerbaiyan.png",
        "United States": "season2026/track/texas.png",
        "Spain": None,
    }

    for country, path in fixes.items():
        GrandPrix.objects.filter(season=season, country=country).update(gp_photo=path)


class Migration(migrations.Migration):
    dependencies = [
        ("public", "0008_add_is_sprint_to_grandprix"),
    ]

    operations = [
        migrations.RunPython(fix_gp_track_paths, migrations.RunPython.noop),
    ]
