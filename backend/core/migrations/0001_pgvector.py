# backend/core/migrations/0001_pgvector.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = []
    operations = [migrations.RunSQL(
        "CREATE EXTENSION IF NOT EXISTS vector;", "DROP EXTENSION IF EXISTS vector;")]