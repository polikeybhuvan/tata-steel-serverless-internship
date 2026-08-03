import json, boto3, logging

s3 = boto3.client('s3')
logs = boto3.client('logs')
sns = boto3.client('sns')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('SPARKMemory')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    intent = event['sessionState']['intent']['name']
    slots = event['sessionState']['intent'].get('slots', {})

    try:
        if intent == 'WelcomeIntent':
            msg = 'Hello Bhuvan! SPARK is online and ready.'

        elif intent == 'CheckS3Status':
            bucket = slots['bucketName']['value']['interpretedValue']
            s3.get_bucket_location(Bucket=bucket)
            msg = f'Bucket {bucket!r} is active.'

        elif intent == 'GetSystemLogs':
            st = logs.describe_log_streams(
                logGroupName='/aws/lambda/SPARKRouterLambda',
                orderBy='LastEventTime', descending=True, limit=1)
            msg = f'Latest stream: {st["logStreams"][0]["logStreamName"]}'

        elif intent == 'RememberThis':
            k, v = (slots['memoryKey']['value']['interpretedValue'],
                     slots['memoryValue']['value']['interpretedValue'])
            table.put_item(Item={'userId': 'Bhuvan', 'infoKey': k, 'infoValue': v})
            msg = f'Stored {v!r} under {k!r}.'

        elif intent == 'RecallMemory':
            k = slots['memoryKey']['value']['interpretedValue']
            res = table.get_item(Key={'userId': 'Bhuvan', 'infoKey': k})
            msg = f'I remember: {res["Item"]["infoValue"]}' if 'Item' in res else 'No memory found.'

        elif intent == 'SendAlert':
            m = slots['alertMessage']['value']['interpretedValue']
            sns.publish(TopicArn='arn:aws:sns:us-east-1:297646182718:SPARKAlerts',
                        Message=f'SPARK Alert: {m}', Subject='SPARK Dispatch')
            msg = 'Alert dispatched to your email.'

        else:
            msg = 'FallbackIntent — intent not yet programmed.'

    except Exception as e:
        msg = f'Error: {str(e)}'

    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {'name': intent, 'state': 'Fulfilled'}
        },
        'messages': [{'contentType': 'PlainText', 'content': msg}]
    }
