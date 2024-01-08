import logging
import datetime
import azure.functions as func

def main(updatetimer: func.TimerRequest, msg: func.Out[str]) -> None:
    utc_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    """Main script to run the function"""
    logging.info('Sending queue message to start fetching releases')

    msg.set("fetch-releases-queue")

    return 'OK'
