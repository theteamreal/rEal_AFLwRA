from django.contrib import admin
from django.urls import path
from main import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('train/', views.train_page, name='train'),
    path('datasets/', views.dataset_hub, name='datasets'),
    path('datasets/new/', views.dataset_create, name='dataset_create'),
    path('datasets/<slug:slug>/', views.dataset_detail, name='dataset_detail'),
    path('datasets/<slug:slug>/download/', views.dataset_download, name='dataset_download'),
]
