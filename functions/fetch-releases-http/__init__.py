import logging
import azure.functions as func

def main(req: func.HttpRequest, msg: func.Out[str]) -> func.HttpResponse:
    """Main script to run the function"""
    logging.info('Sending queue message to start fetching releases')

    msg.set("fetch-releases-queue")

    return 'OK'
