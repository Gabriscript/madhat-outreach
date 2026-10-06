import time
from scraper.communicator import Communicator
from scraper.common import Common
from bs4 import BeautifulSoup
from selenium.common.exceptions import JavascriptException
from scraper.parser import Parser

class Scroller:

    def __init__(self, driver) -> None:
        self.driver = driver
        self.parser = Parser(driver)  # created up front: the routine reads its results even when nothing was found

    @property
    def finished(self):
        """True only when every business in the list was read. No list counts as unfinished too:
        if Google changes the page, searches get retried instead of silently marked done."""
        return self.parser.finished

    def start_parsing(self):
        self.parser.main(self.__allResultsLinks)
        

    
    def scroll(self):
        """In case search results are not available"""

        scrollAbleElement = self.driver.execute_script(
                """return document.querySelector("[role='feed']")"""
            )
        if scrollAbleElement is None:
            Communicator.show_message(message="Nessun risultato su Google Maps per questa ricerca.")

        else:
            Communicator.show_message(message="Scorro l'elenco dei risultati...")

            last_height = 0

            while True:
                if Common.close_thread_is_set():
                    self.driver.quit()
                    return

                """again finding element to avoid StaleElementReferenceException"""
                scrollAbleElement = self.driver.execute_script(
                """return document.querySelector("[role='feed']")"""
            )
                self.driver.execute_script(
                    "arguments[0].scrollTo(0, arguments[0].scrollHeight);",
                    scrollAbleElement,
                )
                time.sleep(2)


                # get new scroll height and compare with last scroll height.
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight", scrollAbleElement
                )
                if new_height == last_height:
                    """checking if we have reached end of the list"""

                    script = f"""
                    const endingElement = document.querySelector(".PbZDve ");
                    return endingElement;
                    """

                    endAlertElement = self.driver.execute_script(
                        script)  # to know that we are at end of list or not

                    if endAlertElement is None:
                        """if it returns empty list its mean we are not at the end of list"""
                        try:  # sometimes google maps load results when a result is clicked
                            self.driver.execute_script(
                                "array=document.getElementsByClassName('hfpxzc');array[array.length-1].click();"
                            )
                        except JavascriptException:
                            pass
                    else:

                        break
                else:
                    last_height = new_height
                    allResultsListSoup = BeautifulSoup(
                    scrollAbleElement.get_attribute('outerHTML'), 'html.parser')

                    allResultsAnchorTags = allResultsListSoup.find_all(
                        'a', class_='hfpxzc')

                    """all the links of results"""
                    self.__allResultsLinks = [anchorTag.get(
                        'href') for anchorTag in allResultsAnchorTags]
                    
                    Communicator.show_message(f"Attività trovate finora: {len(self.__allResultsLinks)}")

            self.start_parsing()


                    