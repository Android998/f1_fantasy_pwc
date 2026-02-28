from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('public', '0004_alter_blockchip_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Achievement',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('slug', models.SlugField(unique=True)),
                ('name', models.CharField(max_length=128)),
                ('description', models.TextField()),
                ('category', models.CharField(choices=[('gp', 'GP'), ('season', 'Season'), ('all_time', 'All Time')], default='season', max_length=16)),
                ('icon', models.CharField(blank=True, max_length=16, null=True)),
                ('icon_class', models.CharField(blank=True, max_length=32, null=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name_plural': 'achievements',
                'db_table': 'public_achievements',
            },
        ),
        migrations.CreateModel(
            name='UserAchievement',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('unlocked_at', models.DateTimeField(auto_now_add=True)),
                ('achievement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='public.achievement')),
                ('gp', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='public.grandprix')),
                ('season', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='public.season')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'userachievements',
                'db_table': 'public_userachievements',
            },
        ),
        migrations.AddConstraint(
            model_name='userachievement',
            constraint=models.UniqueConstraint(fields=('user', 'achievement'), name='unique_user_achievement'),
        ),
    ]
