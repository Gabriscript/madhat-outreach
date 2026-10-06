"""
This module contain the code for saving the scraped data
"""


import pandas as pd
from scraper.communicator import Communicator
from settings import OUTPUT_PATH
import os

class DataSaver:
    def __init__(self) -> None:
        self.outputFormat = Communicator.get_output_format()

    def save(self, datalist):
        """
        This function will save the data that has been scrapped.
        This can be call if any error occurs while scraping , or if scraping is done successfully.
        In both cases we have to save the scraped data.
        """

        if len(datalist) > 0:
            Communicator.show_message("Salvo i risultati...")

            dataFrame = pd.DataFrame(datalist)
            totalRecords = dataFrame.shape[0]

            searchQuery = Communicator.get_search_query()
            filename = f"{searchQuery} - GMS output"

            if self.outputFormat == "excel":
                extension = ".xlsx"
            elif self.outputFormat == "csv":
                extension = ".csv"
            elif self.outputFormat == "json":
                extension = ".json"
                
             # Create the output directory if it does not exist
            if not os.path.exists(OUTPUT_PATH):
                os.makedirs(OUTPUT_PATH)
            joinedPath = OUTPUT_PATH + filename + extension

            if os.path.exists(joinedPath):
                index = 1
                while True:
                    filename = f"{searchQuery} - GMS output ({index})"

                    joinedPath = OUTPUT_PATH + filename + extension

                    if os.path.exists(joinedPath):
                        index += 1

                    else:
                        break
            if self.outputFormat == "excel":
                dataFrame.to_excel(joinedPath, index=False)
            elif self.outputFormat == "csv":
                dataFrame.to_csv(joinedPath, index=False)

            elif self.outputFormat == "json":
                dataFrame.to_json(joinedPath, indent=4, orient="records")

            Communicator.show_message(f"Fatto! {totalRecords} attività salvate in {os.path.abspath(joinedPath)}")
            
        else:
            Communicator.show_message("Nessuna attività raccolta, non c'è niente da salvare.")


