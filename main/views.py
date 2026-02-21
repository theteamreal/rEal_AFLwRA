from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import GlobalModel, Client, ModelUpdateLog
import random

@login_required
def dashboard_view(request):
    # Fetch the latest global model version
    latest_model = GlobalModel.objects.first()
    clients = Client.objects.all().order_by('-trust_score')
    recent_updates = ModelUpdateLog.objects.all().order_by('-timestamp')[:15]
    
    context = {
        'title': 'Fedora Unified Dashboard',
        'latest_model': latest_model,
        'clients': clients,
        'recent_updates': recent_updates,
        'page': 'dashboard',
    }
    return render(request, 'dashboard.html', context)

@login_required
def train_page(request):
    # Ensure the user has a client profile
    client, created = Client.objects.get_or_create(
        user=request.user,
        defaults={'client_id': f"node_{request.user.username}_{random.randint(100, 999)}"}
    )
    
    context = {
        'title': 'Fedora Training Notebook',
        'page': 'train',
        'client_id': client.client_id
    }
    return render(request, 'train.html', context)

@login_required
def dataset_hub(request):
    # Retaining for navigation, but focuses on the unified model's target
    context = {
        'title': 'Fedora Registry',
        'page': 'datasets',
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
