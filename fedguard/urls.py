from django.contrib import admin
from django.urls import path
from main import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('train/', views.train_page, name='train'),
    path('datasets/', views.dataset_hub, name='datasets'),
]

