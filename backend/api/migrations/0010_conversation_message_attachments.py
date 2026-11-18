from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0009_ticket_status_history"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField()),
                ("is_internal", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversation_messages", to="api.company")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_messages", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversation_messages", to="api.ticket")),
            ],
            options={
                "db_table": "conversation_messages",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="conversationmessage",
            index=models.Index(fields=["company", "ticket", "created_at"], name="conv_msg_company_ticket_idx"),
        ),
        migrations.CreateModel(
            name="ConversationAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="ticket_attachments/%Y/%m/")),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size", models.PositiveBigIntegerField(default=0)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversation_attachments", to="api.company")),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="api.conversationmessage")),
            ],
            options={
                "db_table": "conversation_attachments",
                "ordering": ["uploaded_at", "id"],
            },
        ),
    ]
