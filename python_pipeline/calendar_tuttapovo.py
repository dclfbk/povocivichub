#!/usr/bin/env python3

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


BASE_URL = "https://www.tuttapovo.it/appuntamenti.asp"


@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    def next_month(self):
        if self.month == 12:
            return YearMonth(self.year + 1, 1)

        return YearMonth(self.year, self.month + 1)

    def label(self):
        return f"{self.month:02d}-{self.year}"

    def filename_label(self):
        return f"{self.year}_{self.month:02d}"


def parse_year_month(value):
    """
    Converte valori come:

    1-2024
    01-2024
    1/2024
    2024-01
    """

    value = value.strip()

    match = re.fullmatch(
        r"(?P<month>\d{1,2})[-/](?P<year>\d{4})",
        value,
    )

    if match:
        month = int(match.group("month"))
        year = int(match.group("year"))
    else:
        match = re.fullmatch(
            r"(?P<year>\d{4})[-/](?P<month>\d{1,2})",
            value,
        )

        if not match:
            raise argparse.ArgumentTypeError(
                f"Formato non valido: {value}. "
                "Usa MM-YYYY, per esempio 03-2024."
            )

        month = int(match.group("month"))
        year = int(match.group("year"))

    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError(
            "Il mese deve essere compreso tra 1 e 12."
        )

    if not 2000 <= year <= 2100:
        raise argparse.ArgumentTypeError(
            "L'anno deve essere compreso tra 2000 e 2100."
        )

    return YearMonth(year=year, month=month)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Scarica gli appuntamenti di Tuttapovo "
            "per un intervallo di mesi."
        )
    )

    parser.add_argument(
        "--from",
        dest="start_month",
        type=parse_year_month,
        required=True,
        metavar="MM-YYYY",
        help="Mese iniziale, per esempio 01-2024.",
    )

    parser.add_argument(
        "--to",
        dest="end_month",
        type=parse_year_month,
        required=True,
        metavar="MM-YYYY",
        help="Mese finale, per esempio 12-2024.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="File CSV di output.",
    )

    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Mostra il browser durante l'esecuzione.",
    )

    return parser.parse_args()


def generate_months(start, end):
    current = start

    while current <= end:
        yield current
        current = current.next_month()


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def first_text(element, selector):
    locator = element.locator(selector)

    if locator.count() == 0:
        return ""

    return clean_text(locator.first.inner_text())


def first_attribute(element, selector, attribute):
    locator = element.locator(selector)

    if locator.count() == 0:
        return ""

    return locator.first.get_attribute(attribute) or ""


def extract_event_type(class_value):
    match = re.search(
        r"\btipo-(\d+)\b",
        class_value or "",
    )

    return match.group(1) if match else ""


def extract_events(page, requested_month):
    event_items = page.locator("ul#elenco > li")
    rows = []

    for index in range(event_items.count()):
        item = event_items.nth(index)

        event_id = (
            item.get_attribute("id") or ""
        ).removeprefix("e-")

        class_value = item.get_attribute("class") or ""
        event_type = extract_event_type(class_value)

        title = first_text(item, ".titolo a")
        organisation = first_text(item, ".ente")
        location = first_text(item, ".luogo")

        email = first_attribute(
            item,
            ".info.email a",
            "href",
        ).removeprefix("mailto:")

        external_link = first_attribute(
            item,
            ".info.link a",
            "href",
        )

        attachment_name = ""
        attachment_url = ""

        attachment_locator = item.locator(
            ".info.allegato a"
        )

        if attachment_locator.count() > 0:
            attachment = attachment_locator.first

            attachment_name = clean_text(
                attachment.inner_text()
            )

            attachment_href = (
                attachment.get_attribute("href") or ""
            )

            attachment_url = urljoin(
                BASE_URL,
                attachment_href,
            )

        detail_href = first_attribute(
            item,
            ".titolo a",
            "href",
        )

        detail_url = urljoin(
            BASE_URL,
            detail_href,
        )

        dates = item.locator(".info.data")

        common_values = {
            "requested_year": requested_month.year,
            "requested_month": requested_month.month,
            "event_id": event_id,
            "event_type": event_type,
            "title": title,
            "organisation": organisation,
            "location": location,
            "email": email,
            "external_link": external_link,
            "attachment_name": attachment_name,
            "attachment_url": attachment_url,
            "detail_url": detail_url,
        }

        if dates.count() == 0:
            rows.append(
                {
                    **common_values,
                    "date_text": "",
                }
            )

            continue

        for date_index in range(dates.count()):
            date_text = clean_text(
                dates.nth(date_index).inner_text()
            )

            rows.append(
                {
                    **common_values,
                    "date_text": date_text,
                }
            )

    return rows


def load_month(page: Page, requested_month: YearMonth):
    fragment = (
        f"m-{requested_month.month}:"
        f"a-{requested_month.year}:"
        "e-1"
    )

    url = f"{BASE_URL}#{fragment}"

    print(f"Scaricamento {requested_month.label()}: {url}")

    # Passare prima da about:blank forza l'elaborazione del frammento
    # anche quando si visitano consecutivamente più mesi.
    page.goto(
        "about:blank",
        wait_until="domcontentloaded",
    )

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    page.locator("ul#elenco").wait_for(
        state="attached",
        timeout=30_000,
    )

    # Breve attesa per consentire allo script del sito
    # di completare l'aggiornamento dell'elenco.
    page.wait_for_timeout(500)

    return extract_events(
        page=page,
        requested_month=requested_month,
    )


def deduplicate_rows(rows):
    """
    Rimuove eventuali duplicati identici.

    Un evento ripetuto in date diverse rimane invece
    correttamente rappresentato da più righe.
    """

    unique_rows = []
    seen = set()

    for row in rows:
        key = (
            row["event_id"],
            row["date_text"],
            row["title"],
            row["location"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique_rows.append(row)

    return unique_rows


def write_csv(rows, output_path):
    columns = [
        "requested_year",
        "requested_month",
        "event_id",
        "event_type",
        "title",
        "organisation",
        "location",
        "date_text",
        "email",
        "external_link",
        "attachment_name",
        "attachment_url",
        "detail_url",
    ]

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=columns,
            delimiter=";",
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_arguments()

    if args.start_month > args.end_month:
        print(
            "Errore: il mese iniziale è successivo "
            "al mese finale.",
            file=sys.stderr,
        )
        return 1

    output_path = args.output or Path(
        "tuttapovo_eventi_"
        f"{args.start_month.filename_label()}_"
        f"{args.end_month.filename_label()}.csv"
    )

    all_rows = []
    failed_months = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=not args.show_browser
            )

            context = browser.new_context(
                locale="it-IT",
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
            )

            page = context.new_page()

            for requested_month in generate_months(
                args.start_month,
                args.end_month,
            ):
                try:
                    month_rows = load_month(
                        page=page,
                        requested_month=requested_month,
                    )

                    all_rows.extend(month_rows)

                    event_count = len(
                        {
                            row["event_id"]
                            for row in month_rows
                        }
                    )

                    print(
                        f"  Eventi: {event_count}; "
                        f"occorrenze: {len(month_rows)}"
                    )

                except PlaywrightTimeoutError:
                    failed_months.append(
                        requested_month.label()
                    )

                    print(
                        "  Attenzione: il mese non è stato "
                        "caricato entro il tempo previsto.",
                        file=sys.stderr,
                    )

                except Exception as error:
                    failed_months.append(
                        requested_month.label()
                    )

                    print(
                        f"  Errore durante il mese: {error}",
                        file=sys.stderr,
                    )

            browser.close()

        all_rows = deduplicate_rows(all_rows)

        write_csv(
            rows=all_rows,
            output_path=output_path,
        )

        unique_events = len(
            {
                row["event_id"]
                for row in all_rows
            }
        )

        print()
        print(f"Eventi distinti complessivi: {unique_events}")
        print(f"Occorrenze complessive: {len(all_rows)}")
        print(f"File creato: {output_path.resolve()}")

        if failed_months:
            print(
                "Mesi non scaricati: "
                + ", ".join(failed_months),
                file=sys.stderr,
            )

            return 2

        return 0

    except Exception as error:
        print(
            f"Errore generale: {error}",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
