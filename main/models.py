from django.db import models
from django.contrib.auth.models import User

class GlobalModel(models.Model):
    """
    Unified global model state for the platform.
    Tracks the versioned evolution of the single communal model.
    """
    version = models.IntegerField(default=0, unique=True)
    weights_path = models.CharField(max_length=256, help_text="Local storage path for PyTorch state_dict")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']

    def __str__(self):
        return f"Fedora Global v{self.version}"

class Client(models.Model):
    """Tracks unique clients and their trust scores."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="fedora_client")
    client_id = models.CharField(max_length=64, unique=True)
    trust_score = models.FloatField(default=1.0)
    rejected_count = models.IntegerField(default=0)
    last_update = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.client_id}) (Score: {self.trust_score:.2f})"

class ModelUpdateLog(models.Model):
    """History of every submission in the interactive pool."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    norm = models.FloatField()
    accepted = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "Accepted" if self.accepted else "Rejected"
        return f"{self.client.client_id} -> {status}"
