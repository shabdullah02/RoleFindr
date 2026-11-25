from django.urls import path

from resumes.views import MasterView, UploadDetailView, UploadView

urlpatterns = [
    path("upload", UploadView.as_view()),
    path("upload/<int:pk>", UploadDetailView.as_view()),
    path("master", MasterView.as_view()),
]
