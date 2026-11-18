
from rest_framework import serializers
from django.contrib.auth.models import User

from api.models import (
    Customer,
    Complaint,
    TicketCategory,
    Ticket,
    CompanyMembership,
)


# AUTHENTICATION SERIALIZERS

class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(
        required=True,
        trim_whitespace=True
    )


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8
    )
    confirm_password = serializers.CharField(
        write_only=True
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "confirm_password",
            "first_name",
            "last_name"
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Email is already registered."
            )
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


# CUSTOMER SERIALIZER

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_email(self, value):
        company_id = self.context.get("company_id")

        queryset = Customer.objects.filter(
            company_id=company_id,
            email__iexact=value,
        )

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "A customer with this email already exists in this company."
            )

        return value


# TICKET CATEGORY SERIALIZER

class TicketCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketCategory
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        company_id = self.context.get("company_id")

        queryset = TicketCategory.objects.filter(
            company_id=company_id,
            name__iexact=value,
        )

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "A category with this name already exists in this company."
            )

        return value


# COMPLAINT SERIALIZER

class ComplaintSerializer(serializers.ModelSerializer):

    category = serializers.PrimaryKeyRelatedField(
        queryset=TicketCategory.objects.none(),
        required=True
    )

    class Meta:
        model = Complaint
        fields = [
            "id",
            "subject",
            "description",
            "category",
            "status",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
        ]

    def get_fields(self):
        fields = super().get_fields()

        company_id = self.context.get("company_id")

        fields["category"].queryset = TicketCategory.objects.filter(
            company_id=company_id,
            is_active=True
        )

        return fields


# AGENT CREATION SERIALIZER

class AgentCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        min_length=8
    )
    confirm_password = serializers.CharField(write_only=True)

    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "This username is already taken."
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "This email is already registered."
            )
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })
        return data


# AGENT UPDATE SERIALIZER

class AgentUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)

    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    def validate_email(self, value):
        user = self.context["user"]

        if User.objects.filter(
            email__iexact=value
        ).exclude(id=user.id).exists():
            raise serializers.ValidationError(
                "This email is already registered."
            )

        return value


# TICKET ASSIGNMENT SERIALIZER

class TicketAssignmentSerializer(serializers.Serializer):

    assigned_agent = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.none(),
        required=True
    )

    def get_fields(self):
        fields = super().get_fields()

        company_id = self.context.get("company_id")

        fields["assigned_agent"].queryset = User.objects.filter(
            is_active=True,
            company_memberships__company_id=company_id,
            company_memberships__is_active=True,
            company_memberships__role__slug="agent",
            company_memberships__role__company_id=company_id,
        ).distinct()

        return fields


# TICKET STATUS UPDATE SERIALIZER

class TicketStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Ticket.STATUS_CHOICES)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )
