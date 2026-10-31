
import re
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from rates.models import (
    Currency,
    RateProvider,
    FinancialInstitution,
    InstitutionExchangeRate,
)


API_URL = (
    "https://www.boz.zm/"
    "jsonapi/node/commercial_bank_daily_rates"
)

SOURCE_URL = API_URL + "?sort=-created&page[limit]=1"

LOCAL_TZ = ZoneInfo("Africa/Lusaka")


class Command(BaseCommand):
    help = "Import commercial-bank exchange rates from Bank of Zambia."

    def handle(self, *args, **options):
        self.stdout.write("Fetching BoZ commercial-bank rates...")

        try:
            response = requests.get(
                SOURCE_URL,
                headers={"User-Agent": "Mozilla/5.0 ZamRate/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()

        except (requests.RequestException, ValueError) as exc:
            raise CommandError(
                f"Could not retrieve BoZ data: {exc}"
            )

        records = payload.get("data", [])

        if not records:
            raise CommandError(
                "BoZ returned no commercial-bank records."
            )

        attributes = records[0].get("attributes", {})

        publication_date = attributes.get(
            "commercial_bank_rates_date"
        )

        if not publication_date:
            raise CommandError(
                "BoZ record has no reporting date."
            )

        try:
            rate_date = datetime.fromisoformat(
                publication_date
            ).date()

        except (ValueError, TypeError):
            raise CommandError(
                f"Invalid BoZ reporting date: {publication_date}"
            )

        table = attributes.get(
            "field_commercial_bank_rates", {}
        ).get("value", {})

        if not isinstance(table, dict):
            raise CommandError(
                "Unexpected BoZ commercial-bank table format."
            )

        rows = [
            row for row in table.values()
            if isinstance(row, dict) and "weight" in row
        ]

        try:
            rows.sort(key=lambda row: int(row["weight"]))
        except (ValueError, TypeError, KeyError):
            raise CommandError(
                "Invalid row ordering in BoZ commercial-bank table."
            )

        if len(rows) < 4:
            raise CommandError(
                "Commercial-bank table is incomplete."
            )

        header = rows[0]

        slots = []

        for column, value in header.items():

            if column in ("0", "weight"):
                continue

            if isinstance(value, str) and re.fullmatch(
                r"\d{1,2}:\d{2}", value.strip()
            ):
                index = int(column)

                slots.append({
                    "time": value.strip(),
                    "interbank_buy": index,
                    "interbank_sell": index + 1,
                    "board_buy": index + 2,
                    "board_sell": index + 3,
                })

        if not slots:
            raise CommandError(
                "No observation times found."
            )

        slots.sort(
            key=lambda slot: time.fromisoformat(
                slot["time"].zfill(5)
            )
        )

        # Validate the BoZ category layout.
        category_header = rows[1]

        if (
            str(category_header.get("1", "")).strip().upper()
            != "INTERBANK"
            or str(category_header.get("3", "")).strip().upper()
            != "BOARD RATES"
        ):
            raise CommandError(
                "Unexpected BoZ table categories. "
                "Importer stopped to avoid incorrect mapping."
            )

        try:
            usd = Currency.objects.get(
                code="USD",
                is_active=True
            )

            zmw = Currency.objects.get(
                code="ZMW",
                is_active=True
            )

        except Currency.DoesNotExist:
            raise CommandError(
                "USD and ZMW must exist and be active in Currency."
            )

        provider, _ = RateProvider.objects.update_or_create(
            name="Bank of Zambia - Commercial Bank Rates",
            defaults={
                "website": "https://www.boz.zm/",
                "description": (
                    "Commercial-bank exchange rates published "
                    "by the Bank of Zambia."
                ),
                "is_active": True,
            },
        )

        saved = 0
        skipped = 0
        restored_codes = 0

        with transaction.atomic():

            for row in rows[3:]:

                bank_name = re.sub(
                    r"\s+",
                    " ",
                    str(row.get("0", ""))
                ).strip()

                if not bank_name:
                    skipped += 1
                    continue

                is_average = (
                    bank_name.upper() == "MARKET AVERAGE"
                )

                if is_average:
                    code = "BOZ_MARKET_AVERAGE"
                    institution_type = "other"

                else:
                    code = (
                        slugify(bank_name)
                        .replace("-", "_")
                        .upper()
                    )

                    institution_type = "commercial_bank"

                # Find an existing institution by its full code,
                # or by its name if its previous code was truncated.
                institution = (
                    FinancialInstitution.objects
                    .filter(code=code)
                    .first()
                )

                if institution is None:
                    institution = (
                        FinancialInstitution.objects
                        .filter(name__iexact=bank_name)
                        .first()
                    )

                if institution is None:
                    institution = FinancialInstitution.objects.create(
                        code=code,
                        name=bank_name,
                        institution_type=institution_type,
                        description=(
                            "Market average published by BoZ."
                            if is_average
                            else "Commercial bank in Zambia."
                        ),
                        is_active=True,
                    )

                else:
                    update_fields = []

                    if institution.code != code:
                        institution.code = code
                        update_fields.append("code")
                        restored_codes += 1

                    if institution.name != bank_name:
                        institution.name = bank_name
                        update_fields.append("name")

                    if institution.institution_type != institution_type:
                        institution.institution_type = institution_type
                        update_fields.append("institution_type")

                    if not institution.is_active:
                        institution.is_active = True
                        update_fields.append("is_active")

                    if update_fields:
                        institution.save(
                            update_fields=update_fields
                        )

                for slot in slots:

                    observation_time = slot["time"]

                    parsed_time = time.fromisoformat(
                        observation_time.zfill(5)
                    )

                    observed_at = datetime.combine(
                        rate_date,
                        parsed_time,
                        tzinfo=LOCAL_TZ,
                    )

                    categories = [
                        (
                            "interbank",
                            slot["interbank_buy"],
                            slot["interbank_sell"],
                        ),
                        (
                            "retail",
                            slot["board_buy"],
                            slot["board_sell"],
                        ),
                    ]

                    for category, buy_column, sell_column in categories:

                        buy_value = str(
                            row.get(str(buy_column), "")
                        ).strip()

                        sell_value = str(
                            row.get(str(sell_column), "")
                        ).strip()

                        try:
                            buying_rate = (
                                Decimal(buy_value)
                                if buy_value else None
                            )

                            selling_rate = (
                                Decimal(sell_value)
                                if sell_value else None
                            )

                        except InvalidOperation:
                            self.stderr.write(
                                f"Invalid rate for {bank_name} "
                                f"at {observation_time}."
                            )
                            skipped += 1
                            continue

                        if (
                            buying_rate is None
                            and selling_rate is None
                        ):
                            skipped += 1
                            continue

                        if (
                            buying_rate is not None
                            and (
                                not buying_rate.is_finite()
                                or buying_rate <= 0
                            )
                        ):
                            skipped += 1
                            continue

                        if (
                            selling_rate is not None
                            and (
                                not selling_rate.is_finite()
                                or selling_rate <= 0
                            )
                        ):
                            skipped += 1
                            continue

                        _, created = (
                            InstitutionExchangeRate.objects.update_or_create(
                                institution=institution,
                                base_currency=usd,
                                quote_currency=zmw,
                                category=category,
                                rate_date=rate_date,
                                observation_time=observation_time,
                                provider=provider,
                                defaults={
                                    "buying_rate": buying_rate,
                                    "selling_rate": selling_rate,
                                    "mid_rate": None,
                                    "observed_at": observed_at,
                                    "source_reference": SOURCE_URL,
                                },
                            )
                        )

                        saved += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"BoZ import completed. "
                f"{saved} records saved or updated."
            )
        )

        self.stdout.write(
            f"Reporting date: {rate_date}"
        )

        self.stdout.write(
            f"Observation times: {len(slots)}"
        )

        self.stdout.write(
            f"Existing institution codes restored: {restored_codes}"
        )

        self.stdout.write(
            f"Skipped entries: {skipped}"
        )
