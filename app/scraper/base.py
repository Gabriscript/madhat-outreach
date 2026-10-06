from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from time import sleep
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from .common import Common
from .communicator import Communicator


class Base:
    timeout = 120

    def openingurl(self, url: str):
        """
        To avoid internet connection error while requesting"""

        while True:
            if Common.close_thread_is_set():
                self.driver.quit()
                return

            try:
                self.driver.get(url)
            except WebDriverException:
                sleep(5)
                continue
            else:
                break

        if "/sorry/" in self.driver.current_url:  # Google's "unusual traffic" captcha: never solve it, stop
            Common.blocked.set()
            raise RuntimeError("Google ha mostrato un captcha, ricerche sospese fino a domani")

    def rejectcookies(self):
        """Clean browser profile => Google redirects to consent.google.com every session. Click "Reject all"."""

        if "consent.google" not in self.driver.current_url:
            return  # no banner (non-EU region), skip without hitting the 120s implicit wait

        # ponytail: set_eom=true marks the "Reject all" form in every language; breaks if Google renames the field
        try:
            button = self.driver.find_element(
                By.XPATH, "//form[.//input[@name='set_eom' and @value='true']]//button")
            self.driver.execute_script("arguments[0].click();", button)  # JS click: works even on the hidden mobile duplicate
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: "consent.google" not in d.current_url)
        except (NoSuchElementException, TimeoutException):
            Communicator.show_message("Non riesco a chiudere il banner dei cookie di Google, proseguo comunque")