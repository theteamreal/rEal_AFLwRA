"""
Django Views
-------------
/            → Server monitoring dashboard
/train/      → Client training UI
/datasets/   → Dataset hub (browse + search)
/datasets/new/          → Create new dataset
/datasets/<slug>/       → Dataset detail
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt


def dashboard(request):
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
    context = {
        'page': 'train',
        'title': 'FedGuard — Client Training',
    }
    return render(request, 'train.html', context)


def dataset_hub(request):
    from main.models import Dataset
    q = request.GET.get('q', '').strip()
    tag = request.GET.get('tag', '').strip()
    datasets = Dataset.objects.filter(is_public=True)
    if q:
        datasets = datasets.filter(name__icontains=q) | Dataset.objects.filter(
            description__icontains=q, is_public=True
        ) | Dataset.objects.filter(tags__icontains=q, is_public=True)
        datasets = datasets.distinct()
    if tag:
        datasets = datasets.filter(tags__icontains=tag)
    context = {
        'page': 'datasets',
        'title': 'FedGuard — Dataset Hub',
        'datasets': datasets[:50],
        'query': q,
        'tag': tag,
    }
    return render(request, 'datasets.html', context)


def dataset_detail(request, slug):
    from main.models import Dataset
    dataset = get_object_or_404(Dataset, slug=slug, is_public=True)
    context = {
        'page': 'datasets',
        'title': f'FedGuard — {dataset.name}',
        'dataset': dataset,
    }
    return render(request, 'dataset_detail.html', context)


@csrf_exempt
def dataset_create(request):
    from main.models import Dataset
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            if not name:
                return JsonResponse({'error': 'Name is required'}, status=400)
            if Dataset.objects.filter(name=name).exists():
                return JsonResponse({'error': 'A dataset with this name already exists'}, status=400)
            ds = Dataset.objects.create(
                name=name,
                description=data.get('description', ''),
                tags=data.get('tags', ''),
                created_by=data.get('created_by', 'anonymous'),
                row_count=data.get('row_count', 0),
                feature_count=data.get('feature_count', 0),
                num_classes=data.get('num_classes', 10),
                csv_data=data.get('csv_data', ''),
            )
            return JsonResponse({'slug': ds.slug, 'name': ds.name})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    # GET → render form
    context = {
        'page': 'datasets',
        'title': 'FedGuard — New Dataset',
    }
    return render(request, 'dataset_create.html', context)


def dataset_download(request, slug):
    from main.models import Dataset
    ds = get_object_or_404(Dataset, slug=slug, is_public=True)
    Dataset.objects.filter(pk=ds.pk).update(download_count=ds.download_count + 1)
    resp = HttpResponse(ds.csv_data, content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="{ds.slug}.csv"'
    return resp
