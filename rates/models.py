
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator
from decimal import Decimal


class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "Currencies"

    def __str__(self):
        return f"{self.code} - {self.name}"


class RateProvider(models.Model):
    name = models.CharField(max_length=100, unique=True)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# =========================================================
# INTERNATIONAL REFERENCE EXCHANGE RATES
# =========================================================

class ExchangeRate(models.Model):
    base_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="base_rates"
    )

    quote_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="quote_rates"
    )

    rate = models.DecimalField(
        max_digits=20,
        decimal_places=8
    )

    rate_date = models.DateField()

    provider = models.ForeignKey(
        RateProvider,
        on_delete=models.PROTECT,
        related_name="exchange_rates"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rate_date"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "base_currency",
                    "quote_currency",
                    "rate_date",
                    "provider"
                ],
                name="unique_daily_exchange_rate"
            )
        ]

    def __str__(self):
        return (
            f"1 {self.base_currency.code} = "
            f"{self.rate} {self.quote_currency.code}"
        )


# =========================================================
# FINANCIAL INSTITUTIONS
# =========================================================

class FinancialInstitution(models.Model):

    class InstitutionType(models.TextChoices):
        CENTRAL_BANK = "central_bank", "Central Bank"
        COMMERCIAL_BANK = "commercial_bank", "Commercial Bank"
        BUREAU = "bureau", "Bureau de Change"
        OTHER = "other", "Other Financial Institution"

    code = models.CharField(
        max_length=100,
        unique=True
    )

    name = models.CharField(
        max_length=150
    )

    institution_type = models.CharField(
        max_length=30,
        choices=InstitutionType.choices,
        default=InstitutionType.COMMERCIAL_BANK
    )

    website = models.URLField(blank=True)

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Financial Institution"
        verbose_name_plural = "Financial Institutions"

    def __str__(self):
        return self.name


# =========================================================
# INSTITUTION-SPECIFIC EXCHANGE RATES
# =========================================================

class InstitutionExchangeRate(models.Model):

    class RateCategory(models.TextChoices):
        OFFICIAL = "official", "Official Reference"
        INTERBANK = "interbank", "Interbank"
        RETAIL = "retail", "Retail"
        OTHER = "other", "Other"

    institution = models.ForeignKey(
        FinancialInstitution,
        on_delete=models.PROTECT,
        related_name="exchange_rates"
    )

    base_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="institution_base_rates"
    )

    quote_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="institution_quote_rates"
    )

    buying_rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00000001"))]
    )

    selling_rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00000001"))]
    )

    mid_rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00000001"))]
    )

    category = models.CharField(
        max_length=20,
        choices=RateCategory.choices,
        default=RateCategory.RETAIL
    )

    rate_date = models.DateField()

    observation_time = models.CharField(
        max_length=20,
        blank=True,
        help_text="Published observation time, for example 09:30."
    )

    observed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Exact observation timestamp, when available."
    )

    provider = models.ForeignKey(
        RateProvider,
        on_delete=models.PROTECT,
        related_name="institution_exchange_rates"
    )

    source_reference = models.URLField(
        blank=True,
        help_text="Original publication or data source URL."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rate_date", "-observed_at"]

        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(buying_rate__isnull=False)
                    | Q(selling_rate__isnull=False)
                    | Q(mid_rate__isnull=False)
                ),
                name="institution_rate_has_value"
            ),
            models.CheckConstraint(
                condition=(
                    Q(buying_rate__isnull=True)
                    | Q(buying_rate__gt=0)
                ),
                name="institution_buying_rate_positive"
            ),
            models.CheckConstraint(
                condition=(
                    Q(selling_rate__isnull=True)
                    | Q(selling_rate__gt=0)
                ),
                name="institution_selling_rate_positive"
            ),
            models.CheckConstraint(
                condition=(
                    Q(mid_rate__isnull=True)
                    | Q(mid_rate__gt=0)
                ),
                name="institution_mid_rate_positive"
            ),
            models.UniqueConstraint(
                fields=[
                    "institution",
                    "base_currency",
                    "quote_currency",
                    "category",
                    "rate_date",
                    "observation_time",
                    "provider",
                ],
                name="unique_institution_exchange_rate"
            ),
        ]

        verbose_name = "Institution Exchange Rate"
        verbose_name_plural = "Institution Exchange Rates"

    def __str__(self):
        return (
            f"{self.institution.name}: "
            f"{self.base_currency.code}/"
            f"{self.quote_currency.code} "
            f"({self.rate_date})"
        )
