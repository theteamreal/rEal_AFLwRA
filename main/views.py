from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import GlobalModel, Client, ModelUpdateLog
import random
import socket

def is_host_request(request):
    """
    Checks if the request is originating from the host machine.
    """
    remote_addr = request.META.get('REMOTE_ADDR')
    # Standard local addresses
    if remote_addr in ['127.0.0.1', '::1', 'localhost']:
        return True
    
    # Check if remote matches any of our local IPs (handles LAN access from host)
    try:
        host_ips = [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)]
        if remote_addr in host_ips:
            return True
    except:
        pass
        
    return False

@login_required
def dashboard_view(request):
    """Host admin dashboard — global federation overview."""
    is_host = is_host_request(request)
    latest_model = GlobalModel.objects.first()
    Client.objects.get_or_create(
        user=request.user,
        defaults={'client_id': f"node_{request.user.username}_{random.randint(100, 999)}"}
    )
    raw_clients = Client.objects.all().order_by('-last_update')
    recent_updates = ModelUpdateLog.objects.all().order_by('-timestamp')[:20]

    # Pre-compute per-client stats for template
    clients_stats = []
    for c in raw_clients:
        logs = ModelUpdateLog.objects.filter(client=c)
        total    = logs.count()
        accepted = logs.filter(accepted=True).count()
        rate     = f"{round(accepted/total*100)}%" if total > 0 else "—"
        best     = logs.filter(local_rmse__isnull=False).order_by('local_rmse').first()
        clients_stats.append({
            'client': c,
            'total': total,
            'accepted': accepted,
            'rate': rate,
            'best_rmse': f"{best.local_rmse:.4f}" if best else "—",
        })

    # Federation totals
    all_logs     = ModelUpdateLog.objects.all()
    fed_accepted = all_logs.filter(accepted=True).count()
    fed_rejected = all_logs.filter(accepted=False).count()
    fed_total    = all_logs.count()
    fed_rate     = f"{round(fed_accepted/fed_total*100)}%" if fed_total > 0 else "—"

    context = {
        'title': 'Fedora Hub — Administration',
        'latest_model': latest_model,
        'clients_stats': clients_stats,
        'recent_updates': recent_updates,
        'fed_accepted': fed_accepted,
        'fed_rejected': fed_rejected,
        'fed_total': fed_total,
        'fed_rate': fed_rate,
        'page': 'dashboard',
        'is_host': is_host,
        'user': request.user,
    }
    return render(request, 'dashboard.html', context)


@login_required
def dashboard_client_view(request):
    """Participant portal — personal sync history and model quality."""
    is_host = is_host_request(request)
    latest_model = GlobalModel.objects.first()
    client, _ = Client.objects.get_or_create(
        user=request.user,
        defaults={'client_id': f"node_{request.user.username}_{random.randint(100, 999)}"}
    )
    recent_updates = ModelUpdateLog.objects.filter(client=client).order_by('-timestamp')[:15]

    context = {
        'title': 'Fedora — Participant Portal',
        'latest_model': latest_model,
        'client': client,
        'recent_updates': recent_updates,
        'page': 'dashboard_client',
        'is_host': False,
        'user': request.user,
    }
    return render(request, 'dashboard_client.html', context)

@login_required
def train_page(request):
    # Ensure the user has a client profile
    client, created = Client.objects.get_or_create(
        user=request.user,
        defaults={'client_id': f"node_{request.user.username}_{random.randint(100, 999)}"}
    )
    
    context = {
        'user': request.user,
        'title': 'Fedora Training Notebook',
        'page': 'train',
        'client_id': client.client_id,
        'is_host': is_host_request(request)
    }
    return render(request, 'train.html', context)

@login_required
def dataset_hub(request):
    # Retaining for navigation, but focuses on the unified model's target
    context = {
        'title': 'Fedora Registry',
        'page': 'datasets',
        'is_host': is_host_request(request)
    }
    return render(request, 'datasets.html', context)

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form, 'mode': 'login'})

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'login.html', {'form': form, 'mode': 'signup'})

def logout_view(request):
    logout(request)
    return redirect('login')


def landing_view(request):
    """Public landing page — shown to unauthenticated visitors at root URL."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html', {'page': 'landing'})
