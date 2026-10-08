from django.urls import include, path
urlpatterns = [path('api/hr/', include('hr.urls'))]
