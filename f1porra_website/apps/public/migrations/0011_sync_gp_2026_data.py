from datetime import datetime

from django.db import migrations


def _dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def sync_gp_2026_data(apps, schema_editor):
    Season = apps.get_model("public", "Season")
    GrandPrix = apps.get_model("public", "GrandPrix")

    season = Season.objects.filter(year=2026).first()
    if not season:
        return

    gps = {
        "Australia": {
            "last_edit_date": "2026-03-06 22:59:59+00:00",
            "qualy_date": "2026-03-07 05:00:00+00:00",
            "gp_date": "2026-03-08 04:00:00+00:00",
            "country_link": "season2026/flags/australia.jpg",
            "gp_photo": "season2026/track/australia.png",
        },
        "China": {
            "last_edit_date": "2026-03-12 22:59:59+00:00",
            "qualy_date": "2026-03-14 07:00:00+00:00",
            "gp_date": "2026-03-15 07:00:00+00:00",
            "country_link": "season2026/flags/china.jpg",
            "gp_photo": "season2026/track/china.png",
        },
        "Japan": {
            "last_edit_date": "2026-03-27 22:59:59+00:00",
            "qualy_date": "2026-03-28 06:00:00+00:00",
            "gp_date": "2026-03-29 06:00:00+00:00",
            "country_link": "season2026/flags/japon.jpg",
            "gp_photo": "season2026/track/japon.png",
        },
        "Bahrain": {
            "last_edit_date": "2026-04-10 22:59:59+00:00",
            "qualy_date": "2026-04-11 17:00:00+00:00",
            "gp_date": "2026-04-12 16:00:00+00:00",
            "country_link": "season2026/flags/bahrain.jpg",
            "gp_photo": "season2026/track/bahrain.png",
        },
        "Saudi Arabia": {
            "last_edit_date": "2026-04-17 22:59:59+00:00",
            "qualy_date": "2026-04-18 18:00:00+00:00",
            "gp_date": "2026-04-19 18:00:00+00:00",
            "country_link": "season2026/flags/arabia_saudi.jpg",
            "gp_photo": "season2026/track/arabia_saudi.png",
        },
        "Miami": {
            "last_edit_date": "2026-04-30 22:59:59+00:00",
            "qualy_date": "2026-05-02 21:00:00+00:00",
            "gp_date": "2026-05-03 21:00:00+00:00",
            "country_link": "season2026/flags/miami.jpg",
            "gp_photo": "season2026/track/miami.png",
        },
        "Canada": {
            "last_edit_date": "2026-05-21 22:59:59+00:00",
            "qualy_date": "2026-05-23 21:00:00+00:00",
            "gp_date": "2026-05-24 21:00:00+00:00",
            "country_link": "season2026/flags/canada.jpg",
            "gp_photo": "season2026/track/canada.png",
        },
        "Monaco": {
            "last_edit_date": "2026-06-05 22:59:59+00:00",
            "qualy_date": "2026-06-06 15:00:00+00:00",
            "gp_date": "2026-06-07 14:00:00+00:00",
            "country_link": "season2026/flags/monaco.jpg",
            "gp_photo": "season2026/track/monaco.png",
        },
        "Barcelona-Catalunya": {
            "last_edit_date": "2026-06-12 22:59:59+00:00",
            "qualy_date": "2026-06-13 15:00:00+00:00",
            "gp_date": "2026-06-14 14:00:00+00:00",
            "country_link": "season2026/flags/barcelona.jpg",
            "gp_photo": "season2026/track/barcelona.png",
        },
        "Austria": {
            "last_edit_date": "2026-06-26 22:59:59+00:00",
            "qualy_date": "2026-06-27 15:00:00+00:00",
            "gp_date": "2026-06-28 14:00:00+00:00",
            "country_link": "season2026/flags/austria.jpg",
            "gp_photo": "season2026/track/austria.png",
        },
        "Great Britain": {
            "last_edit_date": "2026-07-02 22:59:59+00:00",
            "qualy_date": "2026-07-04 16:00:00+00:00",
            "gp_date": "2026-07-05 15:00:00+00:00",
            "country_link": "season2026/flags/gran_bretaña.jpg",
            "gp_photo": "season2026/track/gran_bretaña.png",
        },
        "Belgium": {
            "last_edit_date": "2026-07-17 22:59:59+00:00",
            "qualy_date": "2026-07-18 15:00:00+00:00",
            "gp_date": "2026-07-19 14:00:00+00:00",
            "country_link": "season2026/flags/belgica.jpg",
            "gp_photo": "season2026/track/belgica.png",
        },
        "Hungary": {
            "last_edit_date": "2026-07-24 22:59:59+00:00",
            "qualy_date": "2026-07-25 15:00:00+00:00",
            "gp_date": "2026-07-26 14:00:00+00:00",
            "country_link": "season2026/flags/hungria.jpg",
            "gp_photo": "season2026/track/hungria.png",
        },
        "Netherlands": {
            "last_edit_date": "2026-08-20 22:59:59+00:00",
            "qualy_date": "2026-08-22 15:00:00+00:00",
            "gp_date": "2026-08-23 14:00:00+00:00",
            "country_link": "season2026/flags/holanda.jpg",
            "gp_photo": "season2026/track/holanda.png",
        },
        "Italy": {
            "last_edit_date": "2026-09-04 22:59:59+00:00",
            "qualy_date": "2026-09-05 15:00:00+00:00",
            "gp_date": "2026-09-06 14:00:00+00:00",
            "country_link": "season2026/flags/italia.jpg",
            "gp_photo": "season2026/track/italia.png",
        },
        "Spain": {
            "last_edit_date": "2026-09-11 22:59:59+00:00",
            "qualy_date": "2026-09-12 15:00:00+00:00",
            "gp_date": "2026-09-13 14:00:00+00:00",
            "country_link": "season2026/flags/españa.jpg",
            "gp_photo": None,
        },
        "Azerbaijan": {
            "last_edit_date": "2026-09-24 22:59:59+00:00",
            "qualy_date": "2026-09-25 13:00:00+00:00",
            "gp_date": "2026-09-26 12:00:00+00:00",
            "country_link": "season2026/flags/azerbaiyan.jpg",
            "gp_photo": "season2026/track/azerbaiyan.png",
        },
        "Singapore": {
            "last_edit_date": "2026-10-08 22:59:59+00:00",
            "qualy_date": "2026-10-10 14:00:00+00:00",
            "gp_date": "2026-10-11 13:00:00+00:00",
            "country_link": "season2026/flags/singapur.jpg",
            "gp_photo": "season2026/track/singapur.png",
        },
        "United States": {
            "last_edit_date": "2026-10-23 22:59:59+00:00",
            "qualy_date": "2026-10-24 22:00:00+00:00",
            "gp_date": "2026-10-25 20:00:00+00:00",
            "country_link": "season2026/flags/texas.jpg",
            "gp_photo": "season2026/track/texas.png",
        },
        "Mexico": {
            "last_edit_date": "2026-10-30 22:59:59+00:00",
            "qualy_date": "2026-10-31 21:00:00+00:00",
            "gp_date": "2026-11-01 20:00:00+00:00",
            "country_link": "season2026/flags/mexico.jpg",
            "gp_photo": "season2026/track/mexico.png",
        },
        "Brazil": {
            "last_edit_date": "2026-11-06 22:59:59+00:00",
            "qualy_date": "2026-11-07 18:00:00+00:00",
            "gp_date": "2026-11-08 17:00:00+00:00",
            "country_link": "season2026/flags/brazil.jpg",
            "gp_photo": "season2026/track/brazil.png",
        },
        "Las Vegas": {
            "last_edit_date": "2026-11-20 22:59:59+00:00",
            "qualy_date": "2026-11-21 04:00:00+00:00",
            "gp_date": "2026-11-22 04:00:00+00:00",
            "country_link": "season2026/flags/vegas.jpg",
            "gp_photo": "season2026/track/vegas.png",
        },
        "Qatar": {
            "last_edit_date": "2026-11-27 22:59:59+00:00",
            "qualy_date": "2026-11-28 18:00:00+00:00",
            "gp_date": "2026-11-29 16:00:00+00:00",
            "country_link": "season2026/flags/qatar.jpg",
            "gp_photo": "season2026/track/qatar.png",
        },
        "Abu Dhabi": {
            "last_edit_date": "2026-12-04 22:59:59+00:00",
            "qualy_date": "2026-12-05 14:00:00+00:00",
            "gp_date": "2026-12-06 13:00:00+00:00",
            "country_link": "season2026/flags/abu_dhabi.jpg",
            "gp_photo": "season2026/track/abu_dhabi.png",
        },
    }

    for country, payload in gps.items():
        GrandPrix.objects.filter(season=season, country=country).update(
            last_edit_date=_dt(payload["last_edit_date"]),
            qualy_date=_dt(payload["qualy_date"]),
            gp_date=_dt(payload["gp_date"]),
            country_link=payload["country_link"],
            gp_photo=payload["gp_photo"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("public", "0010_fix_gp_flag_paths"),
    ]

    operations = [
        migrations.RunPython(sync_gp_2026_data, migrations.RunPython.noop),
    ]
