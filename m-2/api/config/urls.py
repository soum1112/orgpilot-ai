from django.urls import include, path

urlpatterns = [path("api/process/", include("process_api.urls"))]
