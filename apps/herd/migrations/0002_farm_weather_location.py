from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("herd", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="weather_location",
            field=models.CharField(
                blank=True,
                help_text="Parroquia o ciudad usada para consultar el pronostico.",
                max_length=160,
            ),
        ),
    ]
