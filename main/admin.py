from django.contrib import admin
from .models import GlobalModel, Client, ModelUpdateLog

@admin.register(GlobalModel)
class GlobalModelAdmin(admin.ModelAdmin):
    list_display = ('version', 'created_at')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'trust_score', 'rejected_count')

@admin.register(ModelUpdateLog)
class ModelUpdateLogAdmin(admin.ModelAdmin):
    list_display = ('client', 'norm', 'accepted', 'timestamp')
