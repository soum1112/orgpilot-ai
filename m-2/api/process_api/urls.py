from django.urls import path
from . import views

urlpatterns = [
    path("overview/", views.Overview.as_view()),
    path("stages/", views.Stages.as_view()),
    path("bottlenecks/", views.Bottlenecks.as_view()),
    path("anomalies/", views.Anomalies.as_view()),
]
