import datetime
import os.path
import tempfile
from os import path

import numpy
from PIL import Image
import boto3
import cv2

from pdf2image import convert_from_bytes

import settings


class ImageManipulationService:
    @staticmethod
    def convert_pdf_to_jpeg(file: bytes):
        images = convert_from_bytes(
            file.getvalue(),
        )
        return images

    @staticmethod
    def save_temp_images(images: list):
        file_names = []
        for image in images:
            file_name = (
                    'services/checks/images/'
                    + str(datetime.datetime.now()).replace(' ', '_') + '.jpg'
            )
            image.save(file_name, 'JPEG')
            file_names.append(file_name)
        return file_names

    @classmethod
    def cut_object(cls, pages: list):
        file_names = cls.save_temp_images(pages)
        for file_name in file_names:
            cropped_file_name = (
                    'services/checks/cropped/'
                    + str(datetime.datetime.now()).replace(' ', '_') + '.jpg'
            )
            # (1) Make image gray
            img = cv2.imread(file_name)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            th, threshed = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

            # (2) Morph-op to remove noise
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
            morphed = cv2.morphologyEx(threshed, cv2.MORPH_CLOSE, kernel)

            # (3) Find the max-area contour
            contours = cv2.findContours(
                morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )[-2]
            contour = sorted(contours, key=cv2.contourArea)[-1]

            # (4) Crop and save it
            x, y, w, h = cv2.boundingRect(contour)
            destination = img[y:y + h, x:x + w]
            cv2.imwrite(cropped_file_name, destination)
            os.remove(file_name)


class AWSService:
    textract_client = boto3.client(
        'textract',
        region_name='us-east-2',
        aws_access_key_id='AKIAWYRV6LCIDIO25JMQ',
        aws_secret_access_key='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'
    )
    s3_client = boto3.client(
        's3',
        region_name='us-east-2',
        aws_access_key_id='AKIAWYRV6LCIDIO25JMQ',
        aws_secret_access_key='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'
    )

    @classmethod
    def get_text_from_images_local(cls, files_path: list):
        for file_path in files_path:
            print(file_path)
            with open(file_path, 'rb') as image:
                img = bytearray(image.read())

            response = cls.textract_client.detect_document_text(
                Document={'Bytes': img}
            )
            page_block = response['Blocks'][0]
            print(page_block)
            bounding_box = page_block['Geometry']['BoundingBox']
            print(bounding_box)
            img = cv2.imread(file_path)
            h = int(bounding_box['Height'])
            w = int(bounding_box['Width'])
            y = int(bounding_box['Top'])
            x = int(bounding_box['Left'])
            crop_img = img[y:y + h, x:x + w]
            cv2.imshow("cropped", crop_img)
            # im.save('services/checks/cropped/ok.jpeg')
            return response

    @classmethod
    def get_text_from_images_s3(cls, file_name):
        response = cls.textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': 'iink-web-prd',
                    'Name': 'endorsement/check/' + str(file_name)
                }
            }
        )
        page_text = ''
        for item in response['Blocks']:
            if 'Text' in item.keys():
                page_text += (item['Text'].lower()) + ' '

    @classmethod
    def detect_page(cls, page_text):
        front_page_words = [
            'claim', 'policy', 'loss', 'insured', 'insurance', 'company'
        ]
        matched_keywords = 0
        for word in front_page_words:
            word = page_text.find(word)
            if word != -1:
                matched_keywords += 1

        if matched_keywords >= 3:
            return print('Front page')
        else:
            return print('Back page')
