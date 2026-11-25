import os
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from resumes.models import MasterResume, ResumeUpload
from resumes.parsers import normalize
from resumes.services import save_master
from resumes.tasks import parse_resume_task

MAX_BYTES = 5 * 1024 * 1024  # matches ResumeIQ's limit
MAX_UPLOADS_PER_HOUR = 5  # protects the Gemini quota


def _valid_file(name: str, head: bytes) -> bool:
    return (name.endswith(".pdf") and head.startswith(b"%PDF")) or (name.endswith(".docx") and head.startswith(b"PK"))


class UploadView(APIView):
    permission_classes = [IsAuthenticated]  # noqa: RUF012
    parser_classes = [MultiPartParser]  # noqa: RUF012

    def post(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "file is required"}, status=400)
        if f.size > MAX_BYTES:
            return Response({"detail": "file too large (max 5 MB)"}, status=413)
        head = f.read(4)
        f.seek(0)
        if not _valid_file(f.name.lower(), head):
            return Response({"detail": "upload a PDF or DOCX file"}, status=400)
        since = timezone.now() - timedelta(hours=1)
        if ResumeUpload.objects.filter(user=request.user, created_at__gte=since).count() >= MAX_UPLOADS_PER_HOUR:
            return Response({"detail": "upload limit reached, try again later"}, status=429)
        upload = ResumeUpload.objects.create(user=request.user, file=f,
                                             original_filename=os.path.basename(f.name)[:300])
        transaction.on_commit(lambda: parse_resume_task.delay(upload.id))
        return Response({"id": upload.id, "status": upload.status}, status=202)


class UploadDetailView(APIView):
    permission_classes = [IsAuthenticated]  # noqa: RUF012

    def get(self, request, pk):
        upload = ResumeUpload.objects.filter(pk=pk, user=request.user).first()  # owner check
        if not upload:
            return Response({"detail": "not found"}, status=404)
        body = {"id": upload.id, "status": upload.status, "error": upload.error}
        if upload.status == ResumeUpload.Status.PARSED:
            body["parsed_json"] = upload.parsed_json
        return Response(body)


class MasterView(APIView):
    permission_classes = [IsAuthenticated]  # noqa: RUF012
    parser_classes = [JSONParser]  # noqa: RUF012

    def get(self, request):
        m = MasterResume.objects.filter(user=request.user).order_by("-version").first()
        if not m:
            return Response({"detail": "no master resume yet"}, status=404)
        return Response({"version": m.version, "json_resume": m.json_resume, "updated_at": m.updated_at})

    def put(self, request):
        jr = request.data.get("json_resume")
        if not isinstance(jr, dict) or not isinstance(jr.get("basics"), dict):
            return Response({"detail": "json_resume with a basics object is required"}, status=400)
        source = ""
        upload_id = request.data.get("upload_id")
        if upload_id is not None:
            up = ResumeUpload.objects.filter(pk=upload_id, user=request.user).first()
            if not up:
                return Response({"detail": "upload not found"}, status=404)
            source = up.original_filename
        m = save_master(request.user, normalize(jr), source_file=source)
        return Response({"version": m.version}, status=201)
