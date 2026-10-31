
from django.urls import path

from .views import (
    CurrencyListView,
    LatestRatesView,
    HistoricalRatesView,
    convert_currency,
    InstitutionListView,
    InstitutionRatesView,
    BoZRatesView,
    BoZLatestRatesView,
    BoZHistoricalRatesView,
)

urlpatterns = [
    # Currencies
    path(
        "currencies/",
        CurrencyListView.as_view(),
        name="currencies",
    ),

    # International reference rates
    path(
        "rates/latest/",
        LatestRatesView.as_view(),
        name="latest-rates",
    ),
    path(
        "rates/historical/",
        HistoricalRatesView.as_view(),
        name="historical-rates",
    ),

    # Currency conversion
    path(
        "convert/",
        convert_currency,
        name="convert",
    ),

    # Financial institutions
    path(
        "institutions/",
        InstitutionListView.as_view(),
        name="institutions",
    ),
    path(
        "institutions/<str:code>/rates/",
        InstitutionRatesView.as_view(),
        name="institution-rates",
    ),

    # Bank of Zambia rates
    path(
        "rates/boz/",
        BoZRatesView.as_view(),
        name="boz-rates",
    ),
    path(
        "rates/boz/latest/",
        BoZLatestRatesView.as_view(),
        name="boz-latest-rates",
    ),
    path(
        "rates/boz/historical/",
        BoZHistoricalRatesView.as_view(),
        name="boz-historical-rates",
    ),
]
