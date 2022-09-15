import logging
from os import environ

import azure.functions as func
from azure.storage.blob import BlobServiceClient

CONTAINER_NAME = "releases"
CONNECTION_STRING = environ['AZURE_STORAGE_CONNECTION_STRING']
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """Main script to run the function"""
    logging.info('Getting app_data.json')

    blob_client = blob_service_client.get_container_client(container=CONTAINER_NAME)

    app_data = "{}"

    try:
        app_data = blob_client.download_blob("app_data.json").readall()
    except Exception as e:
        logging.info(e)

    return func.HttpResponse(app_data, mimetype="application/json")
