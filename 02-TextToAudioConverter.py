import boto3, os

s3 = boto3.client('s3')
polly = boto3.client('polly')

def lambda_handler(event, context):
    input_bucket = event['Records'][0]['s3']['bucket']['name']
    text_key = event['Records'][0]['s3']['object']['key']
    output_bucket = 'bhuvan-audio-output-2025'
    audio_key = text_key.replace('.txt', '.mp3')

    text_object = s3.get_object(Bucket=input_bucket, Key=text_key)
    text_content = text_object['Body'].read().decode('utf-8')

    response = polly.synthesize_speech(
        Text=text_content, OutputFormat='mp3', VoiceId='Joanna')

    if 'AudioStream' in response:
        s3.put_object(Bucket=output_bucket, Key=audio_key,
                      Body=response['AudioStream'].read(), ContentType='audio/mpeg')

    return {'statusCode': 200, 'message': f'Converted {text_key} to {audio_key}!'}
