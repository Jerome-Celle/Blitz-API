from django.contrib import admin

from ckeditor_api.models import CKEditorPage


@admin.register(CKEditorPage)
class CKEditorPageAdmin(admin.ModelAdmin):
    pass
