from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0010_conversation_message_attachments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FAQCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faq_categories", to="api.company")),
            ],
            options={"db_table": "faq_categories", "ordering": ["name"]},
        ),
        migrations.AddConstraint(model_name="faqcategory", constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_faq_category_company")),
        migrations.CreateModel(
            name="FAQArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.CharField(max_length=255)),
                ("answer", models.TextField()),
                ("is_published", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="articles", to="api.faqcategory")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faq_articles", to="api.company")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="faq_articles", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "faq_articles", "ordering": ["question"]},
        ),
        migrations.AddIndex(model_name="faqarticle", index=models.Index(fields=["company", "is_published"], name="faq_article_company_69d7d8_idx")),
        migrations.CreateModel(
            name="SLAPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")], default="medium", max_length=20)),
                ("first_response_minutes", models.PositiveIntegerField(default=240)),
                ("resolution_minutes", models.PositiveIntegerField(default=1440)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sla_policies", to="api.company")),
            ],
            options={"db_table": "sla_policies"},
        ),
        migrations.AddConstraint(model_name="slapolicy", constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_sla_name_company")),
        migrations.CreateModel(
            name="TicketSLA",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("response_due_at", models.DateTimeField()),
                ("resolution_due_at", models.DateTimeField()),
                ("first_responded_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_slas", to="api.slapolicy")),
                ("ticket", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sla", to="api.ticket")),
            ],
            options={"db_table": "ticket_slas"},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField()),
                ("kind", models.CharField(default="general", max_length=40)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="api.company")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticket_notifications", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="api.ticket")),
            ],
            options={"db_table": "notifications", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["recipient", "is_read", "created_at"], name="notif_recipient_read_idx")),
        migrations.CreateModel(
            name="LiveChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("waiting", "Waiting"), ("active", "Active"), ("ended", "Ended")], default="waiting", max_length=20)),
                ("subject", models.CharField(blank=True, max_length=200)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_agent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_live_chats", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_chat_sessions", to="api.company")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_chat_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "live_chat_sessions", "ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="LiveChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_chat_messages", to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="api.livechatsession")),
            ],
            options={"db_table": "live_chat_messages", "ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="TicketFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField()),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticket_feedback", to="api.company")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticket_feedback", to="api.customer")),
                ("ticket", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="feedback", to="api.ticket")),
            ],
            options={"db_table": "ticket_feedback"},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=100)),
                ("resource_type", models.CharField(max_length=80)),
                ("resource_id", models.CharField(blank=True, max_length=80)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="api.company")),
            ],
            options={"db_table": "audit_logs", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["company", "created_at"], name="audit_company_created_idx")),
        migrations.CreateModel(
            name="CompanySetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=100)),
                ("value", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="settings", to="api.company")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "company_settings"},
        ),
        migrations.AddConstraint(model_name="companysetting", constraint=models.UniqueConstraint(fields=("company", "key"), name="uniq_setting_key_company")),
    ]
