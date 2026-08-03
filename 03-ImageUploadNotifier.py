import boto3, json, logging

sns = boto3.client('sns')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        bucket = event['Records'][0]['s3']['bucket']['name']
        file_key = event['Records'][0]['s3']['object']['key']
        TOPIC = 'arn:aws:sns:eu-north-1:297646182718:MyFileUploadAlerts'

        subject = f'AWS Alert: {file_key} Uploaded'
        message = (f'Bhuvan, a new file has been detected.\n\n'
                   f'File: {file_key}\nBucket: {bucket}\nStatus: Success')

        sns.publish(TopicArn=TOPIC, Message=message, Subject=subject)
        return {'statusCode': 200, 'body': 'Notification Sent'}

    except Exception as e:
        logger.error(f'Failed: {str(e)}')
        raise e
