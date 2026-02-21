from django.urls import path
from . import views

urlpatterns = [
    path('',                                        views.welcome,                name='welcome'),
    path('dashboard/',                              views.dashboard,              name='dashboard'),
    path('track-meals/',                            views.track_meals,            name='track_meals'),
    path('track-meals/delete/<int:meal_id>/',       views.delete_tracked_meal,    name='delete_tracked_meal'),
    path('inventory/',                              views.inventory,              name='inventory'),
    path('inventory/delete/<int:item_id>/',         views.delete_inventory_item,  name='delete_inventory_item'),
    path('inventory/update/<int:item_id>/',         views.update_inventory_item,  name='update_inventory_item'),
    path('signup/',                                 views.signup_view,            name='signup'),
    path('login/',                                  views.login_view,             name='login'),
    path('logout/',                                 views.logout_view,            name='logout'),
    path('delete/<int:meal_id>/',                   views.delete_meal,            name='delete_meal'),
]
