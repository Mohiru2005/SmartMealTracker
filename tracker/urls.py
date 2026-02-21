from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.welcome,      name='welcome'),
    path('dashboard/',              views.dashboard,    name='dashboard'),
    path('signup/',                 views.signup_view,  name='signup'),
    path('login/',                  views.login_view,   name='login'),
    path('logout/',                 views.logout_view,  name='logout'),
    path('delete/<int:meal_id>/',   views.delete_meal,  name='delete_meal'),
]
