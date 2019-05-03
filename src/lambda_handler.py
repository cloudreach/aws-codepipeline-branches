import boto3
from botocore.exceptions import ClientError
import logging
import os
import time

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Collect environment variables
APPLICATION_NAME = os.getenv('APPLICATION_NAME')
ARTIFACT_BUCKET_ARN = os.getenv('ARTIFACT_BUCKET_ARN')
ARTIFACT_BUCKET_NAME = os.getenv('ARTIFACT_BUCKET_NAME')
PIPELINE_FILE = os.getenv('PIPELINE_FILE', 'pipeline.yaml')
RETENTION_POLICY_IN_DAYS = os.getenv('RETENTION_POLICY_IN_DAYS')


def handler(evt, _):

    # Gather commit information from the codecommit event
    try:
        logger.info(f"handler received {evt}")
        record = evt['Records'][0]
        repo_arn = record['eventSourceARN']
        repo_name = repo_arn.split(':')[-1]
        reference = record['codecommit']['references'][0]
        branch = reference['ref'].split('/')[2]
        event = record['eventName']
        stack_name = f'{APPLICATION_NAME}-{branch}-pipeline'

        if reference.get('deleted', False):
            logger.info(f"Branch {branch} deleted")
            branch_deleted(repo_name, branch, stack_name)
        elif event in ['ReferenceChanges']:
            logger.info(f"New commit on branch {branch}")
            commit_id = reference['commit']
            new_commit(repo_arn, repo_name, branch, commit_id, stack_name)
    except Exception as e:
        logger.exception(f"Exception handling event {evt}")
        raise e


def new_commit(repo_arn, repo_name, branch, commit_id, stack_name):
    """Handles new commits to a repository"""
    logger.info(f'New commit on {repo_name}@{commit_id}')

    # Get the pipeline template from the repo
    file_contents = get_pipeline_file(repo_name, commit_id, PIPELINE_FILE)

    # Create the CloudFormation stack
    create_or_update_stack(stack_name, file_contents, repo_arn, repo_name, branch, commit_id)

    # If CloudFormation stack update succeeds, trigger the pipeline
    if wait_for_stack(stack_name):
        trigger_pipeline(stack_name)
    else:
        logger.error(f'Stack deployment failed for stack {stack_name}')


def branch_deleted(repo_name, branch, stack_name):
    """Called when a branch has been deleted"""
    stack_name = f'{APPLICATION_NAME}-{branch}-pipeline'
    logger.info(f"Deleting stack {stack_name}")
    boto3.client('cloudformation').delete_stack(StackName=stack_name)


def get_pipeline_file(repo_name, commit_id, file_name):
    """Returns the contents of the pipeline file, otherwise return false"""
    file = boto3.client('codecommit').get_file(
        repositoryName=repo_name,
        commitSpecifier=commit_id,
        filePath=file_name,
    )
    logger.info(f"Pipeline file: {file['fileContent']}")
    return file['fileContent'].decode('utf-8')


def create_or_update_stack(stack_name, template, repo_arn, repo_name, branch, commit_id):
    """Create the stack from the pipeline file"""
    cfn = boto3.client('cloudformation')
    create_stack = False

    # Test to see if stack exists or not
    try:
        cfn.describe_stacks(StackName=stack_name)
    except ClientError as e:
        if 'does not exist' in e.response['Error']['Message']:
            logger.info(f"Stack {stack_name} does not exist. Creating.")
            create_stack = True
        else:
            raise e

    # Map of optional parameters that are allowed in the template
    param_values = {
        'ApplicationName': APPLICATION_NAME,
        'ArtifactBucketArn': ARTIFACT_BUCKET_ARN,
        'ArtifactBucketName': ARTIFACT_BUCKET_NAME,
        'Branch': branch,
        'CodeCommitRepositoryArn': repo_arn,
        'CodeCommitRepositoryName': repo_name,
        'CommitId': commit_id,
        'PipelineFile': PIPELINE_FILE,
        'PipelineName': f'{APPLICATION_NAME}-{branch}',
        'RetentionPolicyInDays': RETENTION_POLICY_IN_DAYS,
    }
    params = [{
        'ParameterKey': k,
        'ParameterValue': v,
    } for k, v in param_values.items()]

    capabilities = [
        'CAPABILITY_IAM',
        'CAPABILITY_NAMED_IAM',
        'CAPABILITY_AUTO_EXPAND'
    ]

    if create_stack:
        logger.info(f'Creating stack {stack_name}')
        cfn.create_stack(
            StackName=stack_name,
            TemplateBody=template,
            Parameters=params,
            Capabilities=capabilities,
        )
    else:
        logger.info(f'Updating stack {stack_name}')
        try:
            cfn.update_stack(
                StackName=stack_name,
                TemplateBody=template,
                Parameters=params,
                Capabilities=capabilities,
            )
        except ClientError as e:
            if 'No updates are to be performed' in e.response['Error']['Message']:
                logger.info(f"No update for stack {stack_name}.")
            else:
                raise e


def wait_for_stack(stack_name):
    cfn = boto3.client('cloudformation')

    status = cfn.describe_stacks(StackName=stack_name)['Stacks'][0]['StackStatus']
    logger.info(f'Stack {stack_name} status is {status}')
    if '_IN_PROGRESS' in status:
        time.sleep(5)
        return wait_for_stack(stack_name)
    elif status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
        return True
    else:

        # Print the events
        events = cfn.describe_stack_events(StackName=stack_name)['StackEvents']
        for evt in events:
            logger.info(f"Stack {stack_name} event: {evt['LogicalResourceId']} {evt['PhysicalResourceId']} {evt['ResourceStatus']} {evt.get('ResourceStatusReason', '')}")

        # Delete the stack if ROLLBACK_COMPLETE (On stack creation only)
        if status == 'ROLLBACK_COMPLETE':
            logger.warning(f"Deleting stack {stack_name}")
            cfn.delete_stack(StackName=stack_name)

        return False


def trigger_pipeline(stack_name):
    logger.info(f'Looking for AWS::CodePipeline::Pipeline resource in stack \'{stack_name}\'')

    cfn = boto3.client('cloudformation')

    # Search for the pipeline resource
    stack_resources = cfn.describe_stack_resources(StackName=stack_name)['StackResources']
    pipeline_name = None
    for resource in stack_resources:
        if resource['ResourceType'] == 'AWS::CodePipeline::Pipeline':
            pipeline_name = resource['PhysicalResourceId']
            break

    # Did not find an output named Pipeline
    if not pipeline_name:
        raise Exception(f'Unable to find AWS::CodePipeline::Pipeline resource in stack {stack_name}')

    # Trigger the pipeline
    logger.info(f'Triggering pipeline \'{pipeline_name}\' from stack \'{stack_name}\'')
    boto3.client('codepipeline').start_pipeline_execution(
        name=pipeline_name
    )
