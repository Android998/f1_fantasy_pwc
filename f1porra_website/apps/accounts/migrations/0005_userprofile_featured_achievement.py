from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_usersteam_season_alter_usersteam_color_and_more'),
        ('public', '0005_achievements'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='featured_achievement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='public.achievement'),
        ),
    ]
