#!/usr/bin/env python

import io
import sys

import yaml
import json
import boto3
from botocore.exceptions import ClientError
import click

import organizer
from organizer.utils import jsonfmt, yamlfmt
from organizer.cli.utils import (
    setup_crawler,
    format_responses,
)


def collect_vpc_data(region, account):
    client = boto3.client('ec2', region_name=region, **account.credentials)
    response = client.describe_vpcs()
    #response.pop('ResponseMetadata')
    #response['account_name'] = account.name
    #response['account_id'] = account.id
    #response['region'] = region
    #return response
    vpc_data = []
    for vpc in response['Vpcs']:
        vpc['AccountName'] = account.name
        vpc['Region'] = region
        vpc_data.append(vpc)
    return vpc_data


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--master-role', '-r',
    required=True,
    help='IAM role to assume for accessing AWS Organization Master account.'
)
@click.option('--spec-file', '-f',
    #required=True,
    default='./spec.yaml',
    show_default=True,
    type=click.File('r'),
    help='Path to file containing account/region specifications.'
)
def main(master_role, spec_file):
    """
    Generate a list of AWS CIDR blocks in VPCs. Ignores default VPCs.

    Usage:

      ./cidr_runner.py -r MyIamRole -f spec.yaml | tee output.yaml
    """
    spec = yaml.load(spec_file.read())
    #print(spec)
    crawler = setup_crawler(
        master_role,
        accounts=spec['accounts'],
        regions=spec['regions'],
    )
    #print(yamlfmt([a.dump() for a in crawler.accounts]))

    execution = crawler.execute(
        collect_vpc_data,
    )
    #print(yamlfmt(execution.dump()))

    # flatten responses into list of vpc 
    vpc_data = []
    for r in execution.responses:
        vpc_data += r.payload_output
    #print(yamlfmt(vpc_data))

    # extract cidr block associations
    #cidr_blocks = []
    text_stream = io.StringIO()
    for vpc in vpc_data:
        if not vpc['IsDefault']:
            for cidr in vpc['CidrBlockAssociationSet']:
                if cidr['CidrBlockState']['State'] == 'associated':
                    cidr_block = dict(
                        AccountId = vpc['OwnerId'],
                        AccountName = vpc['AccountName'],
                        Region = vpc['Region'],
                        VpcId = vpc['VpcId'],
                        CidrBlock = cidr['CidrBlock'],
                    )
                    #cidr_blocks.append(cidr_block)
                    text_stream.write(json.dumps(cidr_block) + '\n')
    #click.echo(yamlfmt(cidr_blocks))
    #print(text_stream.getvalue())

    s3 = boto3.resource('s3')
    bucket = spec['bucket_name']
    obj = spec['object_path'] + '/' + 'cidr_blocks.json'
    try:
        s3.Object(bucket, obj).put(Body=text_stream.getvalue())
    except s3.meta.client.exceptions.NoSuchBucket as e:
        boto3.client('s3').create_bucket(
            ACL = 'private',
            Bucket = bucket,
            CreateBucketConfiguration = {'LocationConstraint':'us-west-2'}
        )
        s3.Object(bucket, obj).put(Body=text_stream.getvalue())
    #botocore.errorfactory.NoSuchBucket: An error occurred (NoSuchBucket) when calling the PutObject operation: The specified bucket does not exist


    ## Another way to do it
    #
    #s3_client = boto3.client('s3')
    #try:
    #    s3_client.create_bucket(
    #        ACL = 'private',
    #        Bucket = spec['bucket_name'],
    #        CreateBucketConfiguration = {'LocationConstraint':'us-west-2'}
    #    )
    #except s3_client.exceptions.BucketAlreadyOwnedByYou as e:
    #    pass
    #s3_client.put_object(
    #    Bucket = spec['bucket_name'],
    #    Key = 'cidr_blocks.json',
    #    Body = text_stream.getvalue(),
    #)
    #botocore.errorfactory.BucketAlreadyOwnedByYou: An error occurred (BucketAlreadyOwnedByYou) when calling the CreateBucket operation: Your previous request to create the named bucket succeeded and you already own it.




    """
https://stackoverflow.com/questions/31031463/can-you-upload-to-s3-using-a-stream-rather-than-a-local-file/35269210
    """

if __name__ == '__main__':
    main()