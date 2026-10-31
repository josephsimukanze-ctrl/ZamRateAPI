
from django.contrib import admin
from .models import (
    Currency,
    RateProvider,
    ExchangeRate,
    FinancialInstitution,
    InstitutionExchangeRate,
)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(RateProvider)
class RateProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "website", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        "base_currency",
        "quote_currency",
        "rate",
        "rate_date",
        "provider",
    )
    list_filter = ("provider", "rate_date")
    search_fields = (
        "base_currency__code",
        "quote_currency__code",
    )


@admin.register(FinancialInstitution)
class FinancialInstitutionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "institution_type",
        "is_active",
    )
    list_filter = ("institution_type", "is_active")
    search_fields = ("name", "code")


@admin.register(InstitutionExchangeRate)
class InstitutionExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        "institution",
        "base_currency",
        "quote_currency",
        "buying_rate",
        "selling_rate",
        "mid_rate",
        "category",
        "rate_date",
        "observation_time",
    )
    list_filter = (
        "institution",
        "category",
        "rate_date",
        "provider",
    )
    search_fields = (
        "institution__name",
        "base_currency__code",
        "quote_currency__code",
    )
    date_hierarchy = "rate_date"
