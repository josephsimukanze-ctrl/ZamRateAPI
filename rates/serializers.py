
from rest_framework import serializers

from .models import (
    Currency,
    ExchangeRate,
    FinancialInstitution,
    InstitutionExchangeRate,
)


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = [
            "id",
            "code",
            "name",
            "symbol",
            "is_active",
        ]


class ExchangeRateSerializer(serializers.ModelSerializer):
    base_currency = serializers.CharField(
        source="base_currency.code",
        read_only=True,
    )

    quote_currency = serializers.CharField(
        source="quote_currency.code",
        read_only=True,
    )

    provider = serializers.CharField(
        source="provider.name",
        read_only=True,
    )

    class Meta:
        model = ExchangeRate
        fields = [
            "base_currency",
            "quote_currency",
            "rate",
            "rate_date",
            "provider",
        ]


class FinancialInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialInstitution
        fields = [
            "id",
            "code",
            "name",
            "institution_type",
            "website",
            "description",
            "is_active",
        ]


class InstitutionExchangeRateSerializer(serializers.ModelSerializer):
    institution = serializers.CharField(
        source="institution.name",
        read_only=True,
    )

    institution_code = serializers.CharField(
        source="institution.code",
        read_only=True,
    )

    base_currency = serializers.CharField(
        source="base_currency.code",
        read_only=True,
    )

    quote_currency = serializers.CharField(
        source="quote_currency.code",
        read_only=True,
    )

    provider = serializers.CharField(
        source="provider.name",
        read_only=True,
    )

    class Meta:
        model = InstitutionExchangeRate
        fields = [
            "id",
            "institution",
            "institution_code",
            "base_currency",
            "quote_currency",
            "buying_rate",
            "selling_rate",
            "mid_rate",
            "category",
            "rate_date",
            "observation_time",
            "observed_at",
            "provider",
            "source_reference",
        ]

class LatestRateSerializer(serializers.Serializer):
    base_currency = serializers.CharField()
    quote_currency = serializers.CharField()
    rate = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
    )
    rate_date = serializers.DateField()
    provider = serializers.CharField()
    rate_type = serializers.CharField()