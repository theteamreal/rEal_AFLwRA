from django.contrib import admin
from django.urls import path
from main import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard_client/', views.dashboard_client_view, name='dashboard_client'),
    path('train/', views.train_page, name='train'),
    path('datasets/', views.dataset_hub, name='datasets'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.landing_view, name='landing'),
]
