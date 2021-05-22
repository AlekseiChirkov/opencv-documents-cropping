import datetime
import tempfile
import os
import numpy
from PIL import Image
import boto3
import cv2

from pdf2image import convert_from_bytes

import settings


class ImageManipulationService:
    @staticmethod
    def convert_pdf_to_jpeg(file: bytes):
        """Converting pdf from bytes to images"""

        images = convert_from_bytes(
            file.getvalue(),
        )
        return images

    @staticmethod
    def save_temp_images(images: list):
        """Creating temp files to read with cv2"""

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
    def cut_obj(cls, pages: list):
        import cv2
        import numpy as np
        file_names = cls.save_temp_images(pages)
        for file_name in file_names:
            cropped_file_name = (
                    'services/checks/cropped/'
                    + str(datetime.datetime.now()).replace(' ', '_') + '.jpg'
            )

            # load image
            img = cv2.imread(file_name)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Separate the background from the foreground
            bit = cv2.bitwise_not(gray)
            # Apply adaptive mean thresholding
            amtImage = cv2.adaptiveThreshold(bit, 255,
                                             cv2.ADAPTIVE_THRESH_MEAN_C,
                                             cv2.THRESH_BINARY, 35, 15)
            # Apply erosion to fill the gaps
            kernel = np.ones((15, 15), np.uint8)
            erosion = cv2.erode(amtImage, kernel, iterations=2)
            # Take the height and width of the image
            (height, width) = img.shape[0:2]
            # Ignore the limits/extremities of the document (sometimes are black, so they distract the algorithm)
            image = erosion[50:height - 50, 50: width - 50]
            (nheight, nwidth) = image.shape[0:2]
            # Create a list to save the indexes of lines containing more than 20% of black.
            index = []
            for x in range(0, nheight):
                line = []

                for y in range(0, nwidth):
                    line2 = []
                    if (image[x, y] < 150):
                        line.append(image[x, y])
                if (len(line) / nwidth > 0.2):
                    index.append(x)
            # Create a list to save the indexes of columns containing more than 15% of black.
            index2 = []
            for a in range(0, nwidth):
                line2 = []
                for b in range(0, nheight):
                    if image[b, a] < 150:
                        line2.append(image[b, a])
                if (len(line2) / nheight > 0.15):
                    index2.append(a)

            # Crop the original image according to the max and min of black lines and columns.
            img = img[min(index):max(index) + min(250, (
                    height - max(index)) * 10 // 11),
                  max(0, min(index2)): max(index2) + min(250, (
                          width - max(index2)) * 10 // 11)]
            # Save the image
            cv2.imwrite(cropped_file_name, img)

    # @classmethod
    # def cut_object(cls, pages: list):
    #     """Curopping checks"""
    #
    #     file_names = cls.save_temp_images(pages)
    #     for file_name in file_names:
    #         cropped_file_name = (
    #                 'services/checks/cropped/'
    #                 + str(datetime.datetime.now()).replace(' ', '_') + '.jpg'
    #         )
    #         # (1) Make image gray
    #         img = cv2.imread(file_name)
    #         gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    #         th, threshed = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    #
    #         # (2) Morph-op to remove noise
    #         kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    #         morphed = cv2.morphologyEx(threshed, cv2.MORPH_CLOSE, kernel)
    #
    #         # (3) Find the max-area contour
    #         contours = cv2.findContours(
    #             morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    #         )[-2]
    #         contour = sorted(contours, key=cv2.contourArea)[-1]
    #
    #         # (4) Crop and save it
    #         x, y, w, h = cv2.boundingRect(contour)
    #         destination = img[y:y + h, x:x + w]
    #         cv2.imwrite(cropped_file_name, destination)
    #         os.remove(file_name)


class AWSService:
    textract_client = boto3.client(
        'textract',
        region_name='us-east-2',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )
    s3_client = boto3.client(
        's3',
        region_name='us-east-2',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )

    @classmethod
    def get_text_from_local_images_and_crop(cls, files_path: list):
        """
        Getting text from image (local files)
        and try to crop it with coordinates
        """

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
        """Getting text from files in s3"""

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
        """Detecting fron and back pages"""

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
