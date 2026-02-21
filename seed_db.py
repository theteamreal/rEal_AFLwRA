import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fedguard.settings')
django.setup()

from main.models import DatasetRegistry, FederatedProject

def seed():
    # 1. Create Dataset
    ds, created = DatasetRegistry.objects.get_or_create(
        name="Stock Market Tabular",
        description="Daily stock prices and technical indicators for trend classification."
    )
    if created:
        print("Created Dataset: Stock Market Tabular")
    
    # 2. Create Projects
    p1, created = FederatedProject.objects.get_or_create(
        dataset=ds,
        name="Trend Classification",
        task_type="classification",
        input_shape=[20],
        num_classes=2,
        aggregation_method="trimmed_mean"
    )
    if created:
        print("Created Project: Trend Classification")

    p2, created = FederatedProject.objects.get_or_create(
        dataset=ds,
        name="Price Regression",
        task_type="regression",
        input_shape=[20],
        num_classes=None,
        aggregation_method="trimmed_mean"
    )
    if created:
        print("Created Project: Price Regression")

if __name__ == "__main__":
    seed()
