# Generated by Django 2.2.10 on 2020-03-17 12:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ckeditor_api', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ckeditorpage',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Updated at'),
        ),
    ]
