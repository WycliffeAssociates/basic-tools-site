import json
import logging
from os import environ
from os.path import basename, splitext
import re
from sys import flags
from typing import List
from urllib import request
from urllib.parse import urlparse
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import ContentSettings

repos = [
    {
        "user_name": "Bible-Translation-Tools",
        "repo_name": "Orature"
    },
    {
        "user_name": "Bible-Translation-Tools",
        "repo_name": "BTT-Writer-Android"
    },
    {
        "user_name": "Bible-Translation-Tools",
        "repo_name": "BTT-Writer-Desktop"
    },
    {
        "user_name": "Bible-Translation-Tools",
        "repo_name": "BTT-Exchanger"
    },
    {
        "user_name": "Bible-Translation-Tools",
        "repo_name": "USFM-Converter"
    }
]

CONTAINER_NAME = "releases"
CONNECTION_STRING = environ['AZURE_STORAGE_CONNECTION_STRING']
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

def main(msg: func.QueueMessage) -> None:
    """Main script to run the function"""
    logging.info('Python queue trigger function processed a queue item: %s',
                 msg.get_body().decode('utf-8'))

    app_data = get_local_app_data()

    for repo in repos:
        url = "https://api.github.com/repos/" + repo["user_name"] + "/" + repo["repo_name"] + "/releases/latest"
        
        try:
            with request.urlopen(url) as response:
                data = response.read()
                release = json.loads(data)

                app_name = get_common_app_name(repo["repo_name"])
                repo_name = repo["repo_name"]
                app_version = release["tag_name"]

                if not app_exists(app_data, repo_name, app_version):
                    app_data = remove_old_app(app_data, repo_name)
                    for asset in release["assets"]:
                        download_url = asset["browser_download_url"]
                        if not re.search(".(dmg|exe|deb|zip|AppImage|apk|jar)$", download_url, flags=re.I):
                            continue

                        logging.info(f'Downloading: {download_url}')

                        path = urlparse(download_url).path
                        file_name = basename(path)

                        blob_url = upload_file(download_url, file_name)

                        asset_data = {
                            "name": app_name,
                            "repo_name": repo_name,
                            "version": app_version,
                            "size": asset["size"],
                            "date": asset["updated_at"],
                            "os": get_os_from_path(path),
                            "url": blob_url
                        }

                        app_data.append(asset_data)
        except Exception as e:
            print(e)

    upload_app_data(app_data)

def get_os_from_path(path: str) -> str:
    """Return the os name based on file path"""
    os = "Unknown"
    
    file_name = basename(path)
    extension = splitext(path)[1]
    
    os = get_os_from_filename(file_name)

    if os == "Unknown":
        os = get_os_from_extension(extension)

    return os

def get_os_from_filename(file_name: str) -> str:
    """Get OS name from file name"""

    os = "Unknown"

    if re.search("(osx|macos)", file_name, flags=re.I):
        os = "Osx"
    elif re.search("(windows|win)", file_name, re.I):
        os = "Windows"
        if re.search("32", file_name, re.I):
            os = "Windows32"
        if re.search("64", file_name, re.I):
            os = "Windows64"
    elif re.search("linux", file_name, re.I):
        os = "Linux"
    elif re.search("android", file_name, re.I):
        os = "Android"

    return os


def get_os_from_extension(ext: str) -> str:
    """Get OS name from file extension"""
    os = "Unknown"

    if ext == ".exe":
        os = "Windows"
    elif ext == ".dmg":
        os = "Osx"
    elif ext in (".AppImage", ".deb"):
        os = "Linux"
    elif ext == ".apk":
        os = "Android"
    elif ext == ".zip":
        os = "Zip"

    return os

def upload_app_data(app_data: List):
    """Upload app_data.json file to blob storage"""
    try:
        blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob="app_data.json")
        json_data = json.dumps(app_data, indent=4)
        res = blob_client.upload_blob(json_data.encode("ascii"), overwrite=True, content_settings=ContentSettings(content_type='application/json'))
        logging.info(res)
    except Exception as e:
        logging.info(e)

def create_container():
    """Create blob storage container"""
    try:
        blob_service_client.create_container(CONTAINER_NAME)
    except Exception as e:
        logging.info(e)

def upload_file(url: str, file_name: str) -> str:
    """Download file from url and upload to blob storage"""
    try:
        blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=file_name)
        with request.urlopen(url) as req:
            blob_client.upload_blob(req.read(), overwrite=True)
            return blob_client.url
    except Exception as e:
        logging.info(e)
        return None

def get_common_app_name(name: str) -> str:
    """Get common name of the app"""
    app_name = name
    if app_name in ("BTT-Writer-Android", "BTT-Writer-Desktop"):
        app_name = "BTT-Writer"
    
    return app_name

def get_local_app_data() -> list:
    """Read local version of app_data.json from blob storage"""
    blob_client = blob_service_client.get_container_client(container=CONTAINER_NAME)
    app_data = []

    try:
        app_data_str = blob_client.download_blob("app_data.json").readall()
        app_data = json.loads(app_data_str)
    except Exception as e:
        logging.info(e)

    return app_data

def app_exists(app_data: list, repo_name: str, version: str) -> bool:
    """Check if app version is different"""
    exists = False
    for app in app_data:
        if "repo_name" in app and app["repo_name"] == repo_name and app["version"] == version:
            exists = True

    return exists

def remove_old_app(app_data: list, repo_name: str) -> list:
    """Remove old app from the list"""
    return [app for app in app_data if "repo_name" in app and app["repo_name"] != repo_name]
