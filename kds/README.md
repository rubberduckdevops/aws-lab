# Kinesis Data Streams

## usuage

```
aws cloudformation create-stack \
  --stack-name KDSLabBasic \
  --template-body file://cloudformation/01-basic.yml \
  --capabilities CAPABILITY_IAM
```

```
aws cloudformation create-stack \
  --stack-name MyKinesisStack \
  --template-body file://cloudformation/02-firehose.yml \
  --parameters \
    ParameterKey=StreamName,ParameterValue=KinesisLabStream \
    ParameterKey=FirehoseName,ParameterValue=KinesisLabFireHose \
    ParameterKey=S3BucketName,ParameterValue=kinesis-lab-s3-$(openssl rand -hex 6) \
    ParameterKey=S3Prefix,ParameterValue="kinesis-data/" \
    ParameterKey=RetentionPeriodHours,ParameterValue=24 \
    ParameterKey=ShardCount,ParameterValue=1 \
    ParameterKey=StreamEncryption,ParameterValue=true \
    ParameterKey=FirehoseBufferingInterval,ParameterValue=60 \
    ParameterKey=FirehoseBufferingSize,ParameterValue=5 \
  --capabilities CAPABILITY_IAM
```