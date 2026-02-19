from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('public', '0002_driver_selected_link_team_selected_link'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='porra',
            name='triple_points_chip',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='BlockChip',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset_type', models.CharField(choices=[('driver', 'Driver'), ('team', 'Team')], max_length=8)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('blocked_driver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='public.driver')),
                ('blocked_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='public.team')),
                ('blocker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks_made', to=settings.AUTH_USER_MODEL)),
                ('gp', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='public.grandprix')),
                ('season', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='public.season')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'blockchips',
                'db_table': 'public_blockchip',
            },
        ),
        migrations.AddConstraint(
            model_name='blockchip',
            constraint=models.UniqueConstraint(fields=('season', 'blocker', 'gp'), name='unique_block_per_gp'),
        ),
    ]
