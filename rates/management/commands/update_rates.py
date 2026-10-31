
from decimal import Decimal, InvalidOperation

import requests

from django.core.management.base import BaseCommand, CommandError

from rates.models import Currency, RateProvider, ExchangeRate


class Command(BaseCommand):
    help = "Import supported exchange rates from Frankfurter API"

    API_URL = "https://api.frankfurter.dev/v2"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.NOTICE("Starting ZamRate exchange-rate import...")
        )

        try:
            # Retrieve currencies supported by Frankfurter
            response = requests.get(
                f"{self.API_URL}/currencies",
                timeout=30,
            )
            response.raise_for_status()
            supported_data = response.json()

            supported_codes = {
                item["iso_code"]
                for item in supported_data
                if item.get("iso_code")
            }

            # Find currencies registered in ZamRate
            currencies = {
                currency.code: currency
                for currency in Currency.objects.filter(is_active=True)
            }

            base_currency = currencies.get("ZMW")

            if not base_currency:
                raise CommandError(
                    "ZMW is not registered in the Currency database."
                )

            # Only request currencies supported by both systems
            quote_codes = sorted(
                (set(currencies.keys()) & supported_codes) - {"ZMW"}
            )

            if not quote_codes:
                raise CommandError(
                    "No supported quote currencies were found."
                )

            self.stdout.write(
                f"Found {len(quote_codes)} supported quote currencies."
            )

            # Retrieve ZMW exchange rates
            response = requests.get(
                f"{self.API_URL}/rates",
                params={
                    "base": "ZMW",
                    "quotes": ",".join(quote_codes),
                },
                timeout=30,
            )
            response.raise_for_status()

            rate_data = response.json()

            if not rate_data:
                self.stdout.write(
                    self.style.WARNING("No exchange rates returned.")
                )
                return

            # Register or retrieve the provider
            provider, _ = RateProvider.objects.update_or_create(
                name="Frankfurter",
                defaults={
                    "website": "https://www.frankfurter.dev/",
                    "description": (
                        "Daily reference exchange rates from Frankfurter API."
                    ),
                    "is_active": True,
                },
            )

            saved = 0
            skipped = 0

            for item in rate_data:
                try:
                    quote_code = item["quote"]
                    rate_value = Decimal(str(item["rate"]))

                    quote_currency = currencies.get(quote_code)

                    if not quote_currency:
                        skipped += 1
                        continue

                    if not rate_value.is_finite() or rate_value <= 0:
                        skipped += 1
                        continue

                    ExchangeRate.objects.update_or_create(
                        base_currency=base_currency,
                        quote_currency=quote_currency,
                        rate_date=item["date"],
                        provider=provider,
                        defaults={
                            "rate": rate_value,
                        },
                    )

                    saved += 1

                    self.stdout.write(
                        f"Saved: 1 ZMW = {rate_value} {quote_code}"
                    )

                except (KeyError, InvalidOperation, ValueError):
                    skipped += 1
                    continue

            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Import completed. {saved} rates saved or updated."
                )
            )

            if skipped:
                self.stdout.write(
                    self.style.WARNING(
                        f"{skipped} records skipped."
                    )
                )

        except requests.RequestException as error:
            raise CommandError(
                f"Could not retrieve exchange rates: {error}"
            )
