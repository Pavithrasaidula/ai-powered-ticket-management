
from django.conf import settings
from django.db import models


class SocialAccount(models.Model):
    PROVIDER_CHOICES = [
        ("google", "Google"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "social_accounts"

    def __str__(self):
        return f"{self.provider}: {self.email}"


class Company(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "permissions"
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        Permission,
        through="RolePermission",
        related_name="roles",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"],
                name="unique_role_slug_per_company",
            )
        ]

    def __str__(self):
        return f"{self.company.slug}:{self.slug}"


class RolePermission(models.Model):
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="unique_permission_per_role",
            )
        ]

    def __str__(self):
        return f"{self.role.slug}:{self.permission.code}"


class CompanyMembership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"],
                name="unique_user_membership_per_company",
            )
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role_id and self.company_id:
            if self.role.company_id != self.company_id:
                raise ValidationError(
                    {"role": "The selected role must belong to this company."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role.slug})"


class Customer(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="customers",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customers"
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"],
                name="unique_customer_email_per_company",
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class TicketCategory(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="ticket_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ticket_categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_category_name_per_company",
            )
        ]

    def __str__(self):
        return f"{self.company.name} - {self.name}"


class Complaint(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="complaints",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="complaints",
    )
    category = models.ForeignKey(
        TicketCategory,
        on_delete=models.PROTECT,
        related_name="complaints",
        null=True,
        blank=True,
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "complaints"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} - {self.status}"


class TicketStatusHistory(models.Model):
    ticket = models.ForeignKey(
        "Ticket",
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="ticket_status_history",
    )
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, choices=[("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")])
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_status_changes",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_status_history"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.ticket.ticket_number}: {self.old_status or 'created'} -> {self.new_status}"


class Ticket(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    complaint = models.OneToOneField(
        Complaint,
        on_delete=models.PROTECT,
        related_name="ticket",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tickets",
    )
    ticket_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tickets"
        ordering = ["-created_at"]

    def __str__(self):
        return self.ticket_number



class ConversationMessage(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="conversation_messages"
    )
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="conversation_messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="ticket_messages"
    )
    message = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversation_messages"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["company", "ticket", "created_at"]),
        ]

    def __str__(self):
        return f"Message on {self.ticket.ticket_number} by {self.sender}"


class ConversationAttachment(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="conversation_attachments"
    )
    message = models.ForeignKey(
        ConversationMessage, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="ticket_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_attachments"
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return self.original_name


class FAQCategory(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="faq_categories")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "faq_categories"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_faq_category_company")]


class FAQArticle(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="faq_articles")
    category = models.ForeignKey(FAQCategory, on_delete=models.PROTECT, related_name="articles")
    question = models.CharField(max_length=255)
    answer = models.TextField()
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="faq_articles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faq_articles"
        ordering = ["question"]
        indexes = [models.Index(fields=["company", "is_published"])]


class SLAPolicy(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sla_policies")
    name = models.CharField(max_length=120)
    priority = models.CharField(max_length=20, choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")], default="medium")
    first_response_minutes = models.PositiveIntegerField(default=240)
    resolution_minutes = models.PositiveIntegerField(default=1440)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sla_policies"
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_sla_name_company")]


class TicketSLA(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="sla")
    policy = models.ForeignKey(SLAPolicy, on_delete=models.PROTECT, related_name="ticket_slas")
    response_due_at = models.DateTimeField()
    resolution_due_at = models.DateTimeField()
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_slas"


class Notification(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ticket_notifications")
    title = models.CharField(max_length=180)
    body = models.TextField()
    kind = models.CharField(max_length=40, default="general")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"])]


class LiveChatSession(models.Model):
    STATUS_CHOICES = [("waiting", "Waiting"), ("active", "Active"), ("ended", "Ended")]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="live_chat_sessions")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_chat_sessions")
    assigned_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_live_chats")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    subject = models.CharField(max_length=200, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "live_chat_sessions"
        ordering = ["-started_at"]


class LiveChatMessage(models.Model):
    session = models.ForeignKey(LiveChatSession, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="live_chat_messages")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "live_chat_messages"
        ordering = ["created_at", "id"]


class TicketFeedback(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="feedback")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="ticket_feedback")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="ticket_feedback")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_feedback"


class AuditLog(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=80, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "created_at"])]


class CompanySetting(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="settings")
    key = models.CharField(max_length=100)
    value = models.JSONField(default=dict)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company_settings"
        constraints = [models.UniqueConstraint(fields=["company", "key"], name="uniq_setting_key_company")]
