import os
import json
import logging
import boto3
import requests
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3 = boto3.client('s3')

def send_text_response(event, response_text):
    SLACK_URL = "https://slack.com/api/chat.postMessage"
    channel_id = event["event"]["channel"]
    user = event["event"]["user"]
    bot_token = os.environ["BOT_TOKEN"]

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "channel": channel_id,
        "text": response_text,
        "link_names": True
    }

    response = requests.post(SLACK_URL, json=payload, headers=headers)
    return response.json() 

def isFilePayment(event):
    text = event["event"]["text"];
    text_lower = text.lower()
    if 'process payment' not in text_lower:
        return None
    if 'fuga' in text:
        return 'payments-fuga'
    if 'contentid' in text:
        return 'payments-contentid'
    if 'adrev' in text:
        return 'payments-adrev'
    return None

def is_bot(event):
    return 'bot_profile' in event['event']

def is_FromPaymentChanel(event):
    return event['event']['channel'] == os.environ['SLACK_PAYMENT_CHANNEL_ID']

def is_user_allowed(event):
    user = event["event"]["user"]
    return user in os.environ['ALLOWED_USERS'].split(',')

def lambda_handler(event, context):
    try:
        event = json.loads(event["body"])
        if not is_bot(event) and is_FromPaymentChanel(event) and is_user_allowed(event):
            s3Bucket = isFilePayment(event)
            if s3Bucket:
                downloadFileAndUploadToS3(event, s3Bucket)
                file_name = event['event']['files'][0]['name']
                send_text_response(event, f'the file {file_name} will be processed shortly.')
                return {
                    'statusCode': 200,
                    'body': 'OK'
                }
            else:
                payload = payUser(event)
                if payload:
                    response = processUserPayment(payload)
                    send_text_response(event, f'Your request has been processed successfully.')
                    return {
                        'statusCode': 200,
                        'body': 'OK'
                    }
                else:
                    send_text_response(event, 'i could not understand you. Currently only the following messages can be processed:\n[\n\"process payment adrev\"\n\"process payment fuga\"\n\"process payment contentid\"\n\"pay user:MRXXXXX amount:1.00 operation:CREDIT description:description here\"\n\"pay user:MRXXXXX amount:1.00 operation:DEBIT description:description here\"\n]')
                    return {
                        'statusCode': 200,
                        'body': 'OK'
                    }                
        return {
            'statusCode': 200,
            'body': 'OK'
        }
    except Exception as e:
        send_text_response(event, f'There was an error processing your request: {e}')
        logger.error(e)
        return {
            'statusCode': 200,
            'body': 'OK'
        }

def downloadFileAndUploadToS3(event, s3Bucket):
    if 'files' in event['event'] and event['event']['files']:
        headers = {'Authorization': f'Bearer {os.environ["BOT_TOKEN"]}'}

        url = event['event']['files'][0]['url_private_download']

        file_name = event['event']['files'][0]['name']

        logger.info("trying to download file: %s from %s", file_name, url)

        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        logger.info("trying to upload file: %s to bucket %s", file_name, s3Bucket)
        s3.upload_fileobj(response.raw, s3Bucket, file_name)

    else:
        raise Exception('Please send a file within the message')


def payUser(event):
    text = event["event"]["text"];
    pattern = r"user:(?P<memberId>MR\d+)\s+amount:(?P<amount>\d+\.\d{2})\s+operation:(?P<operation>[A-Z]+)\s+description:(?P<description>.+)"
    match = re.search(pattern, text)
    if match:
        return match.groupdict()
    else:
        return None

def processUserPayment(payload):
    apiPayload = {
        "memberId": payload["memberId"],
        "amount": {
            "amount": payload["amount"],
            "currency": "USD",
            "fxRate": 0
        },
        "type": "REVENUE",
        "description": "CREDIT" if payload["operation"] == "CREDIT" else "REVERT",
        "operation": payload["operation"],
        "target": "WALLET",
        "reference": payload["description"],
        "sendEmail": False
    }
    logger.info("trying to process payment: %s", apiPayload)
    # call wallet api
    return apiPayload
        