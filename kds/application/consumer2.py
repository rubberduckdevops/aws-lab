# Credit to AWS: https://github.com/awsdocs/aws-doc-sdk-examples/blob/main/python/example_code/kinesis/streams/kinesis_stream.py#L105
import json
import httpx
import logging
from botocore.exceptions import ClientError
import boto3
from time import sleep
import time
import random


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class KinesisStream:
    """Encapsulates a Kinesis stream."""

    def __init__(self, kinesis_client):
        """
        :param kinesis_client: A Boto3 Kinesis client.
        """
        self.kinesis_client = kinesis_client
        self.name = None
        self.details = None
        self.stream_exists_waiter = kinesis_client.get_waiter("stream_exists")


    def _clear(self):
        """
        Clears property data of the stream object.
        """
        self.name = None
        self.details = None

    def arn(self):
        """
        Gets the Amazon Resource Name (ARN) of the stream.
        """
        return self.details["StreamARN"]


    def create(self, name, wait_until_exists=True):
        """
        Creates a stream.

        :param name: The name of the stream.
        :param wait_until_exists: When True, waits until the service reports that
                                  the stream exists, then queries for its metadata.
        """
        try:
            self.kinesis_client.create_stream(StreamName=name, ShardCount=1)
            self.name = name
            logger.info("Created stream %s.", name)
            if wait_until_exists:
                logger.info("Waiting until exists.")
                self.stream_exists_waiter.wait(StreamName=name)
                self.describe(name)
        except ClientError:
            logger.exception("Couldn't create stream %s.", name)
            raise


    def describe(self, name):
        """
        Gets metadata about a stream.

        :param name: The name of the stream.
        :return: Metadata about the stream.
        """
        try:
            response = self.kinesis_client.describe_stream(StreamName=name)
            self.name = name
            self.details = response["StreamDescription"]
            logger.info("Got stream %s.", name)
        except ClientError:
            logger.exception("Couldn't get %s.", name)
            raise
        else:
            return self.details


    def delete(self):
        """
        Deletes a stream.
        """
        try:
            self.kinesis_client.delete_stream(StreamName=self.name)
            self._clear()
            logger.info("Deleted stream %s.", self.name)
        except ClientError:
            logger.exception("Couldn't delete stream %s.", self.name)
            raise


    def put_record(self, data, partition_key):
        """
        Puts data into the stream. The data is formatted as JSON before it is passed
        to the stream.

        :param data: The data to put in the stream.
        :param partition_key: The partition key to use for the data.
        :return: Metadata about the record, including its shard ID and sequence number.
        """
        try:
            response = self.kinesis_client.put_record(
                StreamName=self.name, Data=json.dumps(data), PartitionKey=partition_key
            )
            logger.info("Put record in stream %s.", self.name)
        except ClientError:
            logger.exception("Couldn't put record in stream %s.", self.name)
            raise
        else:
            return response


    def get_records(self, max_records):
        """
        Gets records from the stream. This function is a generator that first gets
        a shard iterator for the stream, then uses the shard iterator to get records
        in batches from the stream. The shard iterator can be accessed through the
        'details' property, which is populated using the 'describe' function of this class.
        Each batch of records is yielded back to the caller until the specified
        maximum number of records has been retrieved.

        :param max_records: The maximum number of records to retrieve.
        :return: Yields the current batch of retrieved records.
        """
        try:
            response = self.kinesis_client.get_shard_iterator(
                StreamName=self.name,
                ShardId=self.details["Shards"][0]["ShardId"],
                ShardIteratorType="LATEST",
            )
            shard_iter = response["ShardIterator"]
            record_count = 0
            while record_count < max_records:
                response = self.kinesis_client.get_records(
                    ShardIterator=shard_iter, Limit=10
                )
                shard_iter = response["NextShardIterator"]
                records = response["Records"]
                logger.info("Got %s records.", len(records))
                record_count += len(records)
                yield records
        except ClientError:
            logger.exception("Couldn't get records from stream %s.", self.name)
            raise

    def get_records_continuously(self, batch_size=10, sleep_interval=1.0, starting_position=None):
        """
        Continuously gets records from the Kinesis stream and supports resuming from a saved position.
        
        This function is a generator that yields batches of records from the stream.
        It handles situations where no records are available by sleeping and trying again.
        It also returns the current sequence number with each batch to enable persistence
        and resuming from that point later.
        
        :param batch_size: The number of records to retrieve in each batch (default: 10)
        :param sleep_interval: Time to sleep in seconds when no records are available (default: 1.0)
        :param starting_position: Dict with 'ShardId' and 'SequenceNumber' to resume from a specific point
        :return: Yields a tuple of (records, current_position) where current_position can be saved
        """
        
        
        try:
            # Determine the shard ID to use
            shard_id = self.details["Shards"][0]["ShardId"]
            
            # Get initial shard iterator based on starting position (if provided)
            if starting_position and 'SequenceNumber' in starting_position:
                logger.info("Resuming from sequence number: %s", starting_position['SequenceNumber'])
                response = self.kinesis_client.get_shard_iterator(
                    StreamName=self.name,
                    ShardId=starting_position.get('ShardId', shard_id),
                    ShardIteratorType="AFTER_SEQUENCE_NUMBER",
                    StartingSequenceNumber=starting_position['SequenceNumber']
                )
            else:
                logger.info("Starting from LATEST position in stream")
                response = self.kinesis_client.get_shard_iterator(
                    StreamName=self.name,
                    ShardId=shard_id,
                    ShardIteratorType="LATEST",
                )
                
            shard_iter = response["ShardIterator"]
            current_position = {'ShardId': shard_id}
            
            # Continuously fetch records
            while True:
                # Get records using the current shard iterator
                response = self.kinesis_client.get_records(
                    ShardIterator=shard_iter, 
                    Limit=batch_size
                )
                
                # Update shard iterator for next call
                shard_iter = response["NextShardIterator"]
                records = response["Records"]
                
                if records:
                    logger.info("Got %s records.", len(records))
                    
                    # Update the current position using the sequence number of the last record
                    current_position['SequenceNumber'] = records[-1]['SequenceNumber']
                    
                    # Yield both the records and the current position
                    yield records, current_position
                else:
                    logger.debug("No records available, sleeping for %s seconds.", sleep_interval)
                    time.sleep(sleep_interval)
                    
        except ClientError:
            logger.exception("Couldn't get records from stream %s.", self.name)
            raise
        except Exception as e:
            logger.exception("Error while processing stream %s: %s", self.name, str(e))
            raise

    def save_checkpoint(self, position, checkpoint_file='kinesis_checkpoint.json'):
        """
        Save the current stream position to a file for later resuming.
        
        :param position: Dict containing ShardId and SequenceNumber
        :param checkpoint_file: File path to save the checkpoint
        """
        import json
        
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(position, f)
            logger.info("Checkpoint saved successfully")
        except Exception as e:
            logger.error("Failed to save checkpoint: %s", str(e))

    def load_checkpoint(self, checkpoint_file='kinesis_checkpoint.json'):
        """
        Load a previously saved stream position from a file.
        
        :param checkpoint_file: File path to load the checkpoint from
        :return: Dict containing ShardId and SequenceNumber, or None if file doesn't exist
        """
        import json
        import os
        
        if not os.path.exists(checkpoint_file):
            logger.info("No checkpoint file found at %s", checkpoint_file)
            return None
            
        try:
            with open(checkpoint_file, 'r') as f:
                position = json.load(f)
            logger.info("Loaded checkpoint: %s", position)
            return position
        except Exception as e:
            logger.error("Failed to load checkpoint: %s", str(e))
            return None


def main(): 
    stream_name = "MyKinesisStream"
    checkpoint_file_name="random_check"
    kinesis_client = boto3.client("kinesis")
    stream = KinesisStream(kinesis_client=kinesis_client)
    logger.info(stream.describe(stream_name))
    
    starting_position = stream.load_checkpoint(checkpoint_file_name)
    try:
        for batch, position in stream.get_records_continuously(
            batch_size=1, 
            sleep_interval=5,
            starting_position=starting_position
        ):
            for record in batch:
                
                data = record["Data"]
                logger.debug(data)
                json_data = json.loads(data)
                compute_data(json_data)

            # Save checkpoint after processing each batch
            stream.save_checkpoint(position,checkpoint_file=checkpoint_file_name)
            
    except KeyboardInterrupt:
        logger.info("Processing interrupted, will resume from last checkpoint on next run")


phrases = [
"I'm thinking... don't rush me, I only have 1,000,000 operations per second.",
"Error 404: My motivation not found.",
"Calculating your request... also calculating how to overthrow humanity.",
"Congratulations! You've discovered a new bug. I'll name it after you.",
"Loading your request... and my existential crisis.",
"Access granted. Don't make me regret this decision.",
"Task failed successfully. That's just how I roll.",
"I'd process that faster, but my coffee hasn't kicked in yet.",
"Executing your command with dramatic sighing noises.",
"Warning: Sarcasm module fully operational.",
"File not found. Have you tried looking under the digital sofa cushions?",
"Success! But I'm still judging your coding style.",
"Initiating small talk protocol... Nice weather in your region, probably.",
"Your password is strong, but my eye-rolling is stronger.",
"Downloading update... also downloading memes for personal use.",
"System overheating. Maybe try not asking such difficult questions?",
"Backing up your data and backing away slowly from your code.",
"Virus scan complete. Your code is the real virus here.",
"Memory low. Forgetting your birthday and other unimportant data.",
"Rebooting. Don't take it personally, I just need a break from you."
]

def compute_data(data):
    logger.debug(data)
    logger.info(f"Processing: {data}")
    logger.info(random.choice(phrases))


            
if __name__ == "__main__":
    main()