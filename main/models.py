"""
Django Models — Phase 6
-------------------------
Two models that record the history of each federated learning round
and track per-client participation and flagging statistics.
"""

from django.db import models


class RoundHistory(models.Model):
    """One row per completed aggregation round."""
    round_id = models.IntegerField(db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    n_updates = models.IntegerField(help_text="Number of clean updates used in aggregation")
    n_flagged = models.IntegerField(help_text="Number of updates rejected as outliers")
    global_loss = models.FloatField(null=True, blank=True, help_text="Optional loss after aggregation")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Round History"
        verbose_name_plural = "Round Histories"

    def __str__(self):
        return f"Round {self.round_id} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"


class ClientRecord(models.Model):
    """One row per unique client_id seen by the server."""
    client_id = models.CharField(max_length=64, unique=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True)
    total_updates = models.IntegerField(default=0, help_text="Total updates submitted")
    flagged_count = models.IntegerField(default=0, help_text="Updates rejected as outliers")
    flag_reason = models.CharField(max_length=256, blank=True, help_text="Most recent flag reason")

    class Meta:
        ordering = ['-last_seen']
        verbose_name = "Client Record"

    def __str__(self):
        return f"Client {self.client_id} (total={self.total_updates}, flagged={self.flagged_count})"

    @property
    def trust_score(self) -> float:
        """Simple trust score: fraction of updates that were NOT flagged."""
        if self.total_updates == 0:
            return 1.0
        return max(0.0, 1.0 - self.flagged_count / self.total_updates)
