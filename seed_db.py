import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fedguard.settings')
django.setup()

from main.models import GlobalModel
from django.contrib.auth.models import User

def seed():
    # 1. Ensure a Superuser
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@fedora.hub', 'admin123')
        print("Created Superuser: admin / admin123")

    # 2. Create Global Model v1
    if not GlobalModel.objects.exists():
        # Ensure weights_bank exists
        if not os.path.exists('weights_bank'):
            os.makedirs('weights_bank')
            
        gm = GlobalModel.objects.create(
            version=1,
            weights_path="weights_bank/unified_v1.json"
        )
        print(f"Seed: Created Fedora Global Model v{gm.version}")
    else:
        print("Global Model already exists.")

if __name__ == "__main__":
    seed()
