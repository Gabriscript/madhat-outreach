from bs4 import BeautifulSoup
from scraper.communicator import Communicator
from scraper.datasaver import DataSaver
from scraper.base import Base
from scraper.common import Common
from selenium.webdriver.support.ui import WebDriverWait
from html import unescape
from functools import lru_cache
from urllib.parse import urldefrag, urljoin, urlparse
import dns.exception
import dns.resolver
import random
import requests
import re
import time
from settings import CARD_PAUSE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}
EMAIL_RE = re.compile(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# ponytail: naive blocklist for asset names, placeholders, JS error-tracker DSNs and PEC certified mailboxes
# (no place for marketing), extend when new junk shows up
JUNK_EMAIL_RE = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|ico|css|js|woff2?|ttf|pdf)$|@(example|domain|dominio|email)\.|sentry|wixpress"
    r"|@(.+\.)?(pec|legalmail|postecert|postacert|arubapec|registerpec|sicurezzapostale|pecimprese)\.", re.I)
# Online booking already sends its own reminders: those businesses get the website pitch instead
BOOKING_RE = re.compile(
    r"miodottore|treatwell|fresha|booksy|uala\.|doctolib|appuntamentionline|prenotazionionline|calendly", re.I)


def site_signals(page_html, url):
    """(has online booking, how outdated the site looks 0-3) from the homepage already downloaded:
    plain http, no mobile viewport, newest copyright year 3+ years old."""
    notice = " ".join(re.findall(r"(?:©|&copy;|&#169;|copyright)([^<]{0,30})", page_html, re.I))
    years = [int(year) for year in re.findall(r"(?:19|20)\d\d", notice)]
    old_year = bool(years) and max(years) <= time.localtime().tm_year - 3
    return bool(BOOKING_RE.search(page_html)), (url.startswith("http:")) + ("viewport" not in page_html) + old_year


def extract_emails(page_html):
    """Emails in a page: plain text, mailto links, &#64; entities and Cloudflare-obfuscated ones. Deduped, lowercase."""
    found = EMAIL_RE.findall(unescape(page_html))
    # Cloudflare hides text emails in data-cfemail and mailto links in /cdn-cgi/l/email-protection#<hex>
    for hexstr in re.findall(r'(?:data-cfemail="|email-protection#)([0-9a-fA-F]+)', page_html):
        key = int(hexstr[:2], 16)  # first byte is the XOR key for the rest
        found += EMAIL_RE.findall("".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2)))
    return list(dict.fromkeys(e.lower() for e in found if not JUNK_EMAIL_RE.search(e)))


def contact_links(page_html, base_url):
    """Same-site links that look like a contact page (contatti, contact-us, kontakt...)."""
    host = (urlparse(base_url).hostname or "").removeprefix("www.")
    links = (urldefrag(urljoin(base_url, a["href"].strip()))[0].rstrip("/")
             for a in BeautifulSoup(page_html, "html.parser").find_all("a", href=True))
    return list(dict.fromkeys(
        link for link in links
        if (urlparse(link).hostname or "").removeprefix("www.") == host and re.search(r"contac?t|kontakt", link, re.I)))


@lru_cache(maxsize=None)  # one DNS query per domain, info@ and eventi@ share it
def domain_accepts_mail(domain):
    """False only when DNS says the domain can't receive mail (doesn't exist or has no MX).
    Says nothing about the mailbox itself: that needs a paid verifier."""
    try:
        dns.resolver.resolve(domain, "MX", lifetime=5)
        return True
    # ponytail: no MX counts as dead; RFC 5321 A-record fallback ignored, real businesses publish MX
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return False
    except dns.exception.DNSException:
        return True  # timeout / no network: keep the email rather than lose it


def fetch_html(url):
    """(page text, final URL after redirects). Text is "" for non-HTML: a PDF menu would yield junk emails."""
    # ponytail: timeout is per socket read, a server dripping bytes can still stall one lookup;
    # run it through concurrent.futures with future.result(timeout=...) if that ever shows up
    with requests.get(url, headers=HEADERS, timeout=(5, 10), stream=True) as response:
        is_html = "html" in response.headers.get("Content-Type", "html").lower()
        return (response.text if is_html else ""), response.url


class Parser(Base):

    def __init__(self, driver) -> None:
        self.driver = driver
        self.finalData = []
        self.finished = False

    def init_data_saver(self):
        self.data_saver = DataSaver()

    def parse(self):
        """Our function to parse the html"""

        """This block will get element details sheet of a business. 
        Details sheet means that business details card when you click on a business in 
        serach results in google maps"""

        try:
            # driver.get returns before Maps (a single-page app) has drawn the details panel:
            # wait for its title, a timeout lands in the except below and skips only this business
            infoSheet = WebDriverWait(self.driver, 15).until(lambda d: d.execute_script(
                """return document.querySelector("[role='main'] h1") && document.querySelector("[role='main']")"""
            ))

            # Initialize data points
            (
                rating,
                totalReviews,
                address,
                websiteUrl,
                email,
                phone,
                hours,
                category,
                gmapsUrl,
                bookingLink,
                businessStatus,
            ) = (None, None, None, None, None, None, None, None, None, None, None)

            html = infoSheet.get_attribute("outerHTML")
            soup = BeautifulSoup(html, "html.parser")

            # Extract rating
            try:
                rating = soup.find("span", class_="ceNzKf").get("aria-label")
                rating = rating.replace("stars", "").strip()
            except:
                rating = None

            # Extract total reviews
            try:
                totalReviews = list(soup.find("div", class_="F7nice").children)
                totalReviews = totalReviews[1].get_text(strip=True)
            except:
                totalReviews = None

            # Extract name
            try:
                name = soup.select_one(".tAiQdd h1.DUwDvf").text.strip()
            except:
                name = None

            # Extract address, phone and website. data-item-id doesn't change with the Maps
            # UI language, unlike the tooltips/aria-labels ("Copy address" vs "Copia indirizzo")
            addressTag = soup.select_one('[data-item-id="address"] .rogA2c')
            address = addressTag.get_text(strip=True) if addressTag else None

            phoneTag = soup.select_one('[data-item-id^="phone:tel:"] .rogA2c')
            phone = phoneTag.get_text(strip=True) if phoneTag else None

            websiteTag = soup.select_one('a[data-item-id="authority"]')
            websiteUrl = websiteTag.get("href") if websiteTag else None

            # Extract Email, plus what the homepage says about online booking and how dated the site is
            booking, siteOld = False, None
            if websiteUrl:
                email, booking, siteOld = self.find_mail(websiteUrl)

            # Extract booking link (English or Italian Maps UI)
            try:
                bookingTag = soup.find(
                    "a", {"aria-label": lambda x: x and ("booking link" in x or "prenotazion" in x)}
                )
                if bookingTag:
                    bookingLink = bookingTag.get("href")
            except:
                bookingLink = None

            # Extract hours of operation
            try:
                hours = soup.find("div", class_="t39EBf").get_text(strip=True)
            except:
                hours = None

            # Extract category
            try:
                category = soup.find("button", class_="DkEaL").text.strip()
            except:
                category = None

            # Extract Google Maps URL
            try:
                gmapsUrl = self.driver.current_url
            except:
                gmapsUrl = None

            # Extract business status
            try:
                businessStatus = (
                    soup.find("span", class_="ZDu9vd")
                    .findChildren("span", recursive=False)[0]
                    .get_text(strip=True)
                )
            except:
                businessStatus = None

            data = {
                "Category": category,
                "Name": name,
                "Phone": phone,
                "Google Maps URL": gmapsUrl,
                "Website": websiteUrl,
                "email": email,
                "Business Status": businessStatus,
                "Address": address,
                "Total Reviews": totalReviews,
                "Booking Links": bookingLink,
                "Rating": rating,
                "Hours": hours,
                # Maps' booking link is often just the business's own contact page: only a real platform counts
                "Prenotazione online": booking or bool(bookingLink and BOOKING_RE.search(bookingLink)),
                "Sito datato": siteOld,
            }

            self.finalData.append(data)

        except Exception as e:
            Communicator.show_message(f"Errore leggendo una scheda di Maps: {e}")

    def find_mail(self, url):
        """(emails, has online booking, outdated-site score): emails from the business homepage,
        else from up to 3 of its contact pages."""
        # ponytail: plain HTTP only, sites that render emails with JS are missed; add a headless
        # second driver if the hit rate is too low (never reuse self.driver, it must stay on Maps)
        emails, booking, old = [], False, None
        try:
            page, final_url = fetch_html(url)
            emails = extract_emails(page)
            booking, old = site_signals(page, final_url)
            if not emails:
                for link in contact_links(page, final_url)[:3]:
                    emails = extract_emails(fetch_html(link)[0])
                    if emails:
                        break
        # ValueError: malformed URLs (typo'd Maps website, broken hrefs). Never let it escape:
        # parse() would drop the whole business row, not just the email
        except (requests.RequestException, ValueError) as e:
            Communicator.show_message(f"Email non cercate su {url}: {e}")
        return ", ".join(email for email in emails if domain_accepts_mail(email.rsplit("@", 1)[1])), booking, old

    def main(self, allResultsLinks):
        Communicator.show_message(
            "Elenco completo. Ora apro le schede una per una e cerco le email (ci vuole un po')..."
        )
        try:
            for done, resultLink in enumerate(allResultsLinks, 1):
                if Common.close_thread_is_set():
                    self.driver.quit()
                    return

                Communicator.show_progress(done, len(allResultsLinks))
                self.openingurl(url=resultLink)
                if Common.close_thread_is_set():
                    return  # Ferma pressed while the page loaded: openingurl already quit the driver
                self.parse()
                Common.closeThread.wait(random.uniform(*CARD_PAUSE))  # human pace; Ferma cuts the pause short

            self.finished = True  # every business read: the search can be marked as done

        except Exception as e:
            Communicator.show_message(
                f"Errore durante la lettura delle schede: {e}"
            )

        finally:
            self.init_data_saver()
            self.data_saver.save(datalist=self.finalData)
