# Generated by Django 2.0.8 on 2018-12-20 02:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('retirement', '0004_retirement_accessibility_form_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalretirement',
            name='place_name',
            field=models.CharField(blank=True, max_length=200, verbose_name='Place name'),
        ),
        migrations.AddField(
            model_name='retirement',
            name='place_name',
            field=models.CharField(blank=True, max_length=200, verbose_name='Place name'),
        ),
    ]
