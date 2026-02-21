from django.db import models
from django.contrib.auth.models import User

class GlobalModel(models.Model):
    version = models.IntegerField(default=0, unique=True)
    weights_path = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    best_rmse = models.FloatField(null=True, blank=True)
    best_mae = models.FloatField(null=True, blank=True)
    accepted_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-version']

    def __str__(self):
        return f"Fedora Global v{self.version}"


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="fedora_client")
    client_id = models.CharField(max_length=64, unique=True)
    trust_score = models.FloatField(default=1.0)
    rejected_count = models.IntegerField(default=0)
    last_update = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.client_id}) (Score: {self.trust_score:.2f})"

class ModelUpdateLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    norm = models.FloatField()
    accepted = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    local_rmse = models.FloatField(null=True, blank=True)
    local_mae = models.FloatField(null=True, blank=True)
    agg_rmse = models.FloatField(null=True, blank=True)
    agg_mae = models.FloatField(null=True, blank=True)
    base_version = models.IntegerField(default=0)
    staleness = models.IntegerField(default=0)

    def __str__(self):
        status = "Accepted" if self.accepted else "Rejected"
        return f"{self.client.client_id} -> {status} (staleness={self.staleness})"
