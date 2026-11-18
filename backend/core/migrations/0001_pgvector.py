from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = []

    operations: ClassVar[list] = [
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            "DROP EXTENSION IF EXISTS vector;",
        )
    ]