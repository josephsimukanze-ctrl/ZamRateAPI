from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
)

from .models import (
    Currency,
    ExchangeRate,
    FinancialInstitution,
    InstitutionExchangeRate,
)

from .serializers import (
    CurrencySerializer,
    ExchangeRateSerializer,
    FinancialInstitutionSerializer,
    InstitutionExchangeRateSerializer,
    LatestRateSerializer,
)


BOZ_PROVIDER = "Bank of Zambia - Commercial Bank Rates"

# =========================================================
# SHARED INSTITUTION RATE FILTERS
# =========================================================

def filter_institution_rates(queryset, request):
    """
    Apply optional filters to institution exchange rates.
    """

    institution = request.query_params.get("institution")
    category = request.query_params.get("category")
    base = request.query_params.get("base")
    quote = request.query_params.get("quote")
    date_value = request.query_params.get("date")
    observation_time = request.query_params.get("time")

    if institution:
        queryset = queryset.filter(
            institution__code__iexact=institution
        )

    if category:
        queryset = queryset.filter(category=category.lower())

    if base:
        queryset = queryset.filter(
            base_currency__code=base.upper()
        )

    if quote:
        queryset = queryset.filter(
            quote_currency__code=quote.upper()
        )

    if date_value:
        parsed_date = parse_date(date_value)

        if not parsed_date:
            return queryset.none()

        queryset = queryset.filter(rate_date=parsed_date)

    if observation_time:
        queryset = queryset.filter(
            observation_time=observation_time
        )

    return queryset.order_by(
        "-rate_date",
        "-observation_time",
        "institution__name",
        "category",
    )


def institution_rate_queryset():
    return InstitutionExchangeRate.objects.select_related(
        "institution",
        "base_currency",
        "quote_currency",
        "provider",
    )


# =========================================================
# CURRENCY LIST
# =========================================================

class CurrencyListView(generics.ListAPIView):
    """
    Return all active currencies supported by ZamRate API.
    """

    queryset = Currency.objects.filter(is_active=True)
    serializer_class = CurrencySerializer


# =========================================================
# LATEST INTERNATIONAL EXCHANGE RATES
# =========================================================

# =========================================================
# LATEST INTERNATIONAL EXCHANGE RATES
# =========================================================

@extend_schema_view(
    get=extend_schema(
        summary="Get latest exchange rates",
        description=(
            "Returns the latest available international reference "
            "exchange rates for a selected base currency. "
            "Supports direct rates and calculated inverse rates."
        ),
        parameters=[
            OpenApiParameter(
                name="base",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Base currency code, defaults to ZMW.",
                required=False,
            ),
            OpenApiParameter(
                name="quote",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Optional target currency code.",
                required=False,
            ),
        ],
        responses={200: LatestRateSerializer(many=True)},
    )
)
class LatestRatesView(generics.ListAPIView):
    serializer_class = LatestRateSerializer

    def list(self, request, *args, **kwargs):

        base = request.query_params.get(
            "base", "ZMW"
        ).strip().upper()

        quote = request.query_params.get("quote")

        if quote:
            quote = quote.strip().upper()

        selected_rates = {}

        # -------------------------------------------------
        # 1. DIRECT EXCHANGE RATES
        # -------------------------------------------------

        direct_queryset = ExchangeRate.objects.select_related(
            "base_currency",
            "quote_currency",
            "provider",
        ).filter(
            base_currency__code=base,
            base_currency__is_active=True,
            quote_currency__is_active=True,
        ).order_by(
            "-rate_date",
            "provider__name",
        )

        if quote:
            direct_queryset = direct_queryset.filter(
                quote_currency__code=quote
            )

        for record in direct_queryset:

            target = record.quote_currency.code

            if record.rate <= 0:
                continue

            # Keep the newest record for each target currency.
            if target not in selected_rates:
                selected_rates[target] = {
                    "base_currency": base,
                    "quote_currency": target,
                    "rate": record.rate,
                    "rate_date": record.rate_date,
                    "provider": record.provider.name,
                    "rate_type": "direct",
                }

        # -------------------------------------------------
        # 2. INVERSE EXCHANGE RATES
        # -------------------------------------------------

        inverse_queryset = ExchangeRate.objects.select_related(
            "base_currency",
            "quote_currency",
            "provider",
        ).filter(
            quote_currency__code=base,
            base_currency__is_active=True,
            quote_currency__is_active=True,
        ).order_by(
            "-rate_date",
            "provider__name",
        )

        if quote:
            inverse_queryset = inverse_queryset.filter(
                base_currency__code=quote
            )

        for record in inverse_queryset:

            target = record.base_currency.code

            if record.rate <= 0:
                continue

            existing = selected_rates.get(target)

            # Use the inverse if it is newer than the direct record.
            # A direct record takes priority when dates are equal.
            if existing and record.rate_date <= existing["rate_date"]:
                continue

            inverse_rate = (
                Decimal("1") / record.rate
            ).quantize(
                Decimal("0.00000001"),
                rounding=ROUND_HALF_UP,
            )

            selected_rates[target] = {
                "base_currency": base,
                "quote_currency": target,
                "rate": inverse_rate,
                "rate_date": record.rate_date,
                "provider": record.provider.name,
                "rate_type": "inverse_reference",
            }

        results = list(selected_rates.values())

        serializer = self.get_serializer(
            results,
            many=True,
        )

        return Response(serializer.data)



# =========================================================
# HISTORICAL INTERNATIONAL EXCHANGE RATES
# =========================================================

@extend_schema_view(
    get=extend_schema(
        summary="Get historical exchange rates",
        description=(
            "Retrieve historical international exchange rates "
            "using a base currency, optional quote currency and date."
        ),
        parameters=[
            OpenApiParameter(
                name="base",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Base currency code. Defaults to ZMW.",
                required=False,
            ),
            OpenApiParameter(
                name="quote",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Target currency code, for example USD.",
                required=False,
            ),
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Date in YYYY-MM-DD format.",
                required=False,
            ),
        ],
        responses={200: ExchangeRateSerializer(many=True)},
    )
)
class HistoricalRatesView(generics.ListAPIView):
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        queryset = ExchangeRate.objects.select_related(
            "base_currency",
            "quote_currency",
            "provider",
        )

        base = self.request.query_params.get(
            "base", "ZMW"
        ).upper()

        quote = self.request.query_params.get("quote")
        date_value = self.request.query_params.get("date")

        queryset = queryset.filter(
            base_currency__code=base,
            base_currency__is_active=True,
            quote_currency__is_active=True,
        )

        if quote:
            queryset = queryset.filter(
                quote_currency__code=quote.upper()
            )

        if date_value:
            parsed_date = parse_date(date_value)

            if not parsed_date:
                return queryset.none()

            queryset = queryset.filter(rate_date=parsed_date)

        return queryset.order_by("-rate_date")


# =========================================================
# FINANCIAL INSTITUTIONS
# =========================================================

@extend_schema(
    summary="List financial institutions",
    description=(
        "Returns active commercial banks registered in ZamRate."
    ),
    responses={200: FinancialInstitutionSerializer(many=True)},
)
class InstitutionListView(generics.ListAPIView):
    serializer_class = FinancialInstitutionSerializer

    queryset = FinancialInstitution.objects.filter(
        is_active=True,
        institution_type=FinancialInstitution.InstitutionType.COMMERCIAL_BANK,
    )


# =========================================================
# RATES FOR A PARTICULAR INSTITUTION
# =========================================================

@extend_schema(
    summary="Get institution exchange rates",
    description=(
        "Returns exchange rates for a selected financial institution. "
        "Supports optional category, currency, date and time filters."
    ),
    parameters=[
        OpenApiParameter(
            "code",
            OpenApiTypes.STR,
            OpenApiParameter.PATH,
            description="Institution code.",
        ),
        OpenApiParameter(
            "category",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Rate category: interbank or retail.",
        ),
        OpenApiParameter(
            "base",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Base currency, for example USD.",
        ),
        OpenApiParameter(
            "quote",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Quote currency, for example ZMW.",
        ),
        OpenApiParameter(
            "date",
            OpenApiTypes.DATE,
            OpenApiParameter.QUERY,
            description="Rate date in YYYY-MM-DD format.",
        ),
        OpenApiParameter(
            "time",
            OpenApiTypes.STR,
            OpenApiParameter.QUERY,
            description="Observation time, for example 09:30.",
        ),
    ],
    responses={200: InstitutionExchangeRateSerializer(many=True)},
)
class InstitutionRatesView(generics.ListAPIView):
    serializer_class = InstitutionExchangeRateSerializer

    # Helps drf-spectacular inspect the view safely.
    queryset = InstitutionExchangeRate.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset

        institution = get_object_or_404(
            FinancialInstitution,
            code__iexact=self.kwargs["code"],
            is_active=True,
        )

        queryset = institution_rate_queryset().filter(
            institution=institution
        )

        return filter_institution_rates(queryset, self.request)

# =========================================================
# ALL BANK OF ZAMBIA COMMERCIAL RATES
# =========================================================

@extend_schema(
    summary="Get Bank of Zambia commercial-bank rates",
    description=(
        "Returns commercial-bank interbank and board rates "
        "published by the Bank of Zambia. "
        "The retail category represents the source's BOARD RATES."
    ),
    parameters=[
        OpenApiParameter("institution", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("base", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("quote", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.QUERY),
        OpenApiParameter("time", OpenApiTypes.STR, OpenApiParameter.QUERY),
    ],
    responses={200: InstitutionExchangeRateSerializer(many=True)},
)
class BoZRatesView(generics.ListAPIView):
    serializer_class = InstitutionExchangeRateSerializer

    def get_queryset(self):
        queryset = institution_rate_queryset().filter(
            provider__name=BOZ_PROVIDER
        )

        return filter_institution_rates(queryset, self.request)


# =========================================================
# LATEST BANK OF ZAMBIA RATES
# =========================================================

@extend_schema(
    summary="Get latest Bank of Zambia rates",
    description=(
        "Returns all available commercial-bank rate observations "
        "for the latest published date."
    ),
    parameters=[
        OpenApiParameter("institution", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("base", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("quote", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("time", OpenApiTypes.STR, OpenApiParameter.QUERY),
    ],
    responses={200: InstitutionExchangeRateSerializer(many=True)},
)
class BoZLatestRatesView(generics.ListAPIView):
    serializer_class = InstitutionExchangeRateSerializer

    def get_queryset(self):
        queryset = institution_rate_queryset().filter(
            provider__name=BOZ_PROVIDER
        )

        latest_date = queryset.order_by(
            "-rate_date"
        ).values_list("rate_date", flat=True).first()

        if not latest_date:
            return queryset.none()

        queryset = queryset.filter(rate_date=latest_date)

        return filter_institution_rates(queryset, self.request)


# =========================================================
# HISTORICAL BANK OF ZAMBIA RATES
# =========================================================

@extend_schema(
    summary="Get historical Bank of Zambia rates",
    description=(
        "Retrieve historical Bank of Zambia commercial-bank rates. "
        "Use date to select a reporting date."
    ),
    parameters=[
        OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.QUERY),
        OpenApiParameter("institution", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("base", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("quote", OpenApiTypes.STR, OpenApiParameter.QUERY),
        OpenApiParameter("time", OpenApiTypes.STR, OpenApiParameter.QUERY),
    ],
    responses={200: InstitutionExchangeRateSerializer(many=True)},
)
class BoZHistoricalRatesView(generics.ListAPIView):
    serializer_class = InstitutionExchangeRateSerializer

    def get_queryset(self):
        queryset = institution_rate_queryset().filter(
            provider__name=BOZ_PROVIDER
        )

        date_value = self.request.query_params.get("date")

        if date_value:
            parsed_date = parse_date(date_value)

            if not parsed_date:
                return queryset.none()

            queryset = queryset.filter(rate_date=parsed_date)

        return filter_institution_rates(queryset, self.request)


# =========================================================
# CURRENCY CONVERSION
# =========================================================

@extend_schema(
    summary="Convert between currencies",
    description=(
        "Convert an amount using the latest available international "
        "reference exchange rate stored in ZamRate."
    ),
    parameters=[
        OpenApiParameter(
            name="from",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Source currency code. Defaults to ZMW.",
            required=False,
        ),
        OpenApiParameter(
            name="to",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Target currency code. Defaults to USD.",
            required=False,
        ),
        OpenApiParameter(
            name="amount",
            type=OpenApiTypes.NUMBER,
            location=OpenApiParameter.QUERY,
            description="Amount to convert. Must be greater than zero.",
            required=False,
        ),
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
def convert_currency(request):
    from_code = request.query_params.get(
        "from", "ZMW"
    ).strip().upper()

    to_code = request.query_params.get(
        "to", "USD"
    ).strip().upper()

    amount_value = request.query_params.get("amount", "1")

    active_codes = set(
        Currency.objects.filter(is_active=True).values_list(
            "code", flat=True
        )
    )

    if from_code not in active_codes:
        return Response(
            {"error": f"Unsupported source currency: {from_code}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if to_code not in active_codes:
        return Response(
            {"error": f"Unsupported target currency: {to_code}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount = Decimal(amount_value)

        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation

    except (InvalidOperation, ValueError, TypeError):
        return Response(
            {"error": "Amount must be a valid positive number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if from_code == to_code:
        return Response({
            "from": from_code,
            "to": to_code,
            "amount": str(amount),
            "rate": "1",
            "result": str(amount),
            "rate_date": None,
            "provider": None,
            "inverse_rate_used": False,
        })

    direct_rate = ExchangeRate.objects.filter(
        base_currency__code=from_code,
        quote_currency__code=to_code,
        base_currency__is_active=True,
        quote_currency__is_active=True,
    ).select_related(
        "base_currency",
        "quote_currency",
        "provider",
    ).order_by("-rate_date").first()

    inverse_rate = False

    if direct_rate:
        rate = direct_rate.rate

    else:
        reverse_rate = ExchangeRate.objects.filter(
            base_currency__code=to_code,
            quote_currency__code=from_code,
            base_currency__is_active=True,
            quote_currency__is_active=True,
        ).select_related(
            "base_currency",
            "quote_currency",
            "provider",
        ).order_by("-rate_date").first()

        if not reverse_rate:
            return Response(
                {
                    "error": (
                        f"No exchange rate found for "
                        f"{from_code}/{to_code}."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        rate = Decimal("1") / reverse_rate.rate
        direct_rate = reverse_rate
        inverse_rate = True

    result = (amount * rate).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_HALF_UP,
    )

    return Response({
        "from": from_code,
        "to": to_code,
        "amount": str(amount),
        "rate": str(rate),
        "result": str(result),
        "rate_date": direct_rate.rate_date,
        "provider": direct_rate.provider.name,
        "inverse_rate_used": inverse_rate,
    })
