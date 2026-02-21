"""
Django Views — Phase 6
------------------------
Two views:
  /          → Server monitoring dashboard
  /train/    → Client training UI (loaded by client laptops)
"""

import json
from django.shortcuts import render


def dashboard(request):
    """
    Server operator's dashboard.
    Renders the base template with round history; JS polls /api/metrics every 10s.
    """
    from main.models import RoundHistory, ClientRecord
    rounds = list(RoundHistory.objects.order_by('-timestamp')[:20])
    clients = list(ClientRecord.objects.order_by('-last_seen')[:20])

    context = {
        'page': 'dashboard',
        'rounds': rounds,
        'clients': clients,
        'title': 'FedGuard — Server Dashboard',
    }
    return render(request, 'dashboard.html', context)


def train_page(request):
    """
    Client training page.
    Served to every client laptop that opens http://<server-ip>:8000/train
    No authentication required during hackathon demo.
    """
    context = {
        'page': 'train',
        'title': 'FedGuard — Client Training',
    }
    return render(request, 'train.html', context)
