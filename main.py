import re
from urllib.parse import urljoin, urlunparse, urlparse
from selenium import webdriver
import json
import html
import time
import logging
import logging.handlers
import uuid
import uvicorn
import boto3
from bs4 import BeautifulSoup
import csv
import datetime
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import FastAPI, BackgroundTasks

app=FastAPI()
class WebsiteParser:
    def __init__(self):
        self.output_filename = None
        self.upload_url = None
        self.count = 0
        self.log_url = None
        self.session = requests.Session()
        self.code = str(uuid.uuid4())
        self.setup_logging()
        self.job_id=''

    def setup_logging(self):
        current_date = datetime.datetime.now().strftime("%d_%m_%Y")
        self.log_file_name = f'{self.brand}_{self.code}_{current_date}.log'
        # Initially get a unique logger using a UUID, brand ID, and job ID
        logger_name = f"Brand ID: {self.brand}, Job ID: {self.job_id}, UUID: {self.code}"
        self.logger = logging.getLogger(logger_name)

        # Set formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Create handler for logs that go to the file on the debug level
        log_file_handler = logging.handlers.RotatingFileHandler(self.log_file_name)
        log_file_handler.setFormatter(formatter)
        log_file_handler.setLevel(logging.DEBUG)

        # Create handler for logs that go to the console on the info level
        log_console_handler = logging.StreamHandler()
        log_console_handler.setFormatter(formatter)
        log_console_handler.setLevel(logging.INFO)

        self.logger.addHandler(log_file_handler)
        self.logger.addHandler(log_console_handler)

        # Initial test that the logger is instantiated and working properly
        self.logger.info("This is what info messages will look like")
        self.logger.error("This is what error messages will look like")
        self.logger.critical("This is what a critical error message looks like")

        self.logger = logging.getLogger(__name__)
        self.logger.info("This is a log message from the Agent script")
    def convert_to_tsv(self, data):
        output = []
        for row in data:
            output.append([str(item) for item in row])

        return output

    def write_to_csv(self, csv_data):
        current_date = datetime.datetime.now().strftime("%d_%m_%Y")

        file_path = f'output_{self.brand}_{self.code}_{current_date}.csv'

        # Write data to CSV
        with open(file_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=',')
            writer.writerows(csv_data)
        self.logger.info(f"Data saved to '{file_path}'")
        return file_path

    def upload_file_to_space(self,file_src, save_as, is_public=True):
        spaces_client = self.get_s3_client()
        space_name = 'iconluxurygroup-s3'  # Your space name

        spaces_client.upload_file(file_src, space_name, save_as, ExtraArgs={'ACL': 'public-read'})
        self.logger.info(f"File uploaded successfully to {space_name}/{save_as}")
        # Generate and return the public URL if the file is public
        if is_public:
            # upload_url = f"{str(os.getenv('SPACES_ENDPOINT'))}/{space_name}/{save_as}"
            upload_url = f"https://iconluxurygroup-s3.s3.us-east-2.amazonaws.com/dev/fiver_user/{save_as}"
            self.logger.info(f"Public URL: {upload_url}")
            return upload_url


    def get_s3_client(self):
        session = boto3.session.Session()
        client = boto3.client(service_name='s3',
                                region_name=os.getenv('REGION'),
                                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))
        # client = boto3.client(service_name='s3',
        #                       region_name=REGION,
        #                       aws_access_key_id=AWS_ACCESS_KEY_ID,
        #                       aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        return client
    def parse_website(self, source):
        category=source
        html_content = self.open_link(source)
        soup = BeautifulSoup(html_content, 'html.parser')
        parsed_data = self.parse_product_blocks(soup,category)
        all_data=parsed_data[0]
        all_data.append('source')
        all_data=[all_data]
        print(all_data)
        for row in parsed_data[1:]:
            row.extend([source])
            all_data.append(row)
        print(all_data)
        all_data=self.convert_to_tsv(all_data)
        file_name=self.write_to_csv(all_data)
        #return to API which updates SQL
        self.output_filename=file_name
        self.upload_url=self.upload_file_to_space(file_name,file_name)
        self.count=len(all_data)-1
        self.log_url=self.upload_file_to_space(self.log_file_name,self.log_file_name)
        self.send_output()
    def send_output(self):
        logging.shutdown()
        headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
        }

        params = {
            'job_id': f"{self.job_id}",
            'resultUrl': f"{self.upload_url}",
            'logUrl': f"{self.log_url}",
            'count': self.count
        }
        os.remove(self.output_filename)
        os.remove(self.log_file_name)
        requests.post(f"{send_out_endpoint}/job_complete", params=params, headers=headers)
    @staticmethod
    def open_link(url):
        try:
            session = requests.Session()
            # Setup retry strategy
            retries = Retry(
                total=5,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]  # Updated to use allowed_methods instead of method_whitelist
            )
            session.mount("https://", HTTPAdapter(max_retries=retries))
            headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.3"}
            print(url)
            response = session.get(url,headers=headers,allow_redirects=True)
            response.raise_for_status()  # Raises an HTTPError for bad responses
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None

class FerragamoProductParser(WebsiteParser):
    def __init__(self):
        self.brand = 'ferragamo'
        super().__init__()
    def parse_product_blocks(self, soup, category):
        parsed_data = []
        column_names = [
            'product_id', 'product_url', 'product_name', 'price','old_price', 'image_urls', 'label'
        ]
        parsed_data.append(column_names)

        product_items = soup.find_all('li', class_='r23-grid--list-plp__item')

        for item in product_items:
            product_id = item.find('button', class_='r23-grid--list-plp__item__product-wishlist')['data-partnumber']
            product_link = item.find('a')
            product_url = product_link['href']
            product_name = item.find('div', class_='r23-grid--list-plp__item__info__product-name').text.strip()
            product_price = item.find('span', class_='r23-grid--list-plp__item__info__product-price-new').text.strip()
            old_product_price = item.find('s',class_='r23-grid--list-plp__item__info__product-price-old').text.strip()
            label = item.find('span', class_='r23-grid--list-plp__item__st').text if item.find('span', class_='r23-grid--list-plp__item__st') else ''

            images = item.find_all('img', class_='r23-grid--list-plp__item__img')
            image_urls = [img.get('data-src', 'src') for img in images]

            product_data = [
                product_id,
                f"https://www.ferragamo.com{product_url}",
                product_name,
                product_price,
                old_product_price,
                ', '.join(image_urls),
                label
            ]
            parsed_data.append(product_data)

        return parsed_data

    def extract_product_id(self, product_url):
        product_id = ''
        if product_url:
            product_id = product_url.split('-')[-1].replace('/','')
        return product_id



def run_parser(job_id,brand_id,source_url):
    print(job_id,brand_id,source_url)
    if brand_id == '481':
        FerragamoParser = FerragamoProductParser()
        FerragamoParser.job_id = job_id
        FerragamoParser.parse_website(source_url)


@app.post("/run_parser")
async def brand_batch_endpoint(job_id:str, brand_id: str, scan_url:str,send_out_endpoint_local:str, background_tasks: BackgroundTasks):
    global send_out_endpoint
    send_out_endpoint=send_out_endpoint_local
    background_tasks.add_task(run_parser,job_id, brand_id, scan_url)

    return {"message": "Notification sent in the background"}
if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, host="0.0.0.0", log_level="info")
