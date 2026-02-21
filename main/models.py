"""
Django Models
--------------
RoundHistory    — one row per completed aggregation round
ClientRecord    — per-client participation and flagging stats
Dataset         — shared dataset repository (GitHub-style hub)
"""

from django.db import models
from django.utils.text import slugify


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
        if self.total_updates == 0:
            return 1.0
        return max(0.0, 1.0 - self.flagged_count / self.total_updates)


class Dataset(models.Model):
    """A shared CSV dataset in the FedGuard dataset hub."""
    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=256, blank=True, help_text="Comma-separated tags")
    created_by = models.CharField(max_length=64, blank=True, help_text="Client ID or username")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    row_count = models.IntegerField(default=0)
    feature_count = models.IntegerField(default=0)
    num_classes = models.IntegerField(default=10)
    csv_data = models.TextField(blank=True, help_text="Raw CSV content (max ~5 MB)")
    is_public = models.BooleanField(default=True)
    download_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Dataset"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def __str__(self):
        return self.name
