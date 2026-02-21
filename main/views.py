from django.shortcuts import render
from .models import GlobalModel, Client, ModelUpdateLog

def dashboard(request):
    # Fetch the latest global model version
    latest_model = GlobalModel.objects.all().first()
    clients = Client.objects.all().order_by('-trust_score')
    recent_updates = ModelUpdateLog.objects.all().order_by('-timestamp')[:15]
    
    context = {
        'title': 'Antigravity Unified dashboard',
        'latest_model': latest_model,
        'clients': clients,
        'recent_updates': recent_updates,
        'page': 'dashboard',
    }
    return render(request, 'dashboard.html', context)

def train_page(request):
    # The training page will be redesigned as an interactive notebook
    context = {
        'title': 'Antigravity Training Notebook',
        'page': 'train',
    }
    return render(request, 'train.html', context)

def dataset_hub(request):
    # Retaining for navigation, but focuses on the unified model's target
    context = {
        'title': 'Antigravity Registry',
        'page': 'datasets',
    }
    return render(request, 'datasets.html', context)
