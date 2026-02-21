from django.contrib import admin
from main.models import RoundHistory, ClientRecord


@admin.register(RoundHistory)
class RoundHistoryAdmin(admin.ModelAdmin):
    list_display = ['round_id', 'timestamp', 'n_updates', 'n_flagged', 'global_loss']
    list_filter = ['timestamp']
    ordering = ['-timestamp']


@admin.register(ClientRecord)
class ClientRecordAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'last_seen', 'total_updates', 'flagged_count', 'flag_reason']
    list_filter = ['last_seen']
    ordering = ['-last_seen']
