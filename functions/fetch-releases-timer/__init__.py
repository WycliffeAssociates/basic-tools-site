import logging
import datetime
import azure.functions as func

def main(updatetimer: func.TimerRequest, msg: func.Out[str]) -> None:
    utc_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    """Main script to run the function"""
    logging.info('Python timer trigger function ran at %s', utc_timestamp)

    msg.set("fetch-releases-queue")

    logging.info('msg entered in queue')
