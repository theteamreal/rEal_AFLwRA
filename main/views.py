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
    is_host = is_host_request(request)
    latest_model = GlobalModel.objects.first()
    
    # Get current client profile
    client, _ = Client.objects.get_or_create(
        user=request.user, 
        defaults={'client_id': f"node_{request.user.username}_{random.randint(100, 999)}"}
    )

    if is_host:
        clients = Client.objects.all().order_by('-trust_score')
        recent_updates = ModelUpdateLog.objects.all().order_by('-timestamp')[:15]
        
        context = {
            'title': 'Fedora Hub — Administration',
            'latest_model': latest_model,
            'clients': clients,
            'recent_updates': recent_updates,
            'page': 'dashboard',
            'is_host': True,
            'user': request.user
        }
        return render(request, 'dashboard.html', context)
    else:
        # Participant View: restricted and separate experience
        recent_updates = ModelUpdateLog.objects.filter(client=client).order_by('-timestamp')[:10]
        
        context = {
            'title': 'Fedora — Participant Portal',
            'latest_model': latest_model,
            'client': client,
            'recent_updates': recent_updates,
            'page': 'dashboard',
            'is_host': False,
            'user': request.user
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
