from . import views
from django.urls import path

urlpatterns = [
    path('login/',views.login_sql_view, name='login'),
    path('logout/', views.logout_view, name='logout')

]