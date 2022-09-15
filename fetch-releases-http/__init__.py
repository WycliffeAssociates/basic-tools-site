import logging
import azure.functions as func

def main(req: func.HttpRequest, msg: func.Out[str]) -> func.HttpResponse:
    """Main script to run the function"""
    logging.info('Python HTTP trigger function processed a request.')

    msg.set("fetch-relases-queue")

    return 'OK'
