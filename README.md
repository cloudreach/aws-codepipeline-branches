# codepipeline-manager

This project enables you to store your CodePipeline definition in CodeCommit with your application
code. In addition, it enables branch based builds. Whenever a new branch is created, the template is used
to create a pipeline for that branch.

## Quick Start

A quick start is available in `examples/serverless` to quickly test out the lambda with
an API application. 

#### Deploy the CodeCommit listener

To deploy the lambda and codecommit repository that will listen to it, run the following command:

`make bundle deploy`

or, to specify your own app name:

`APP_NAME=my-app make bundle deploy -e`

This command will bundle up the latest boto3 (for the CodeCommit get file api), and
install the template with the lambda that listens for to the repository.

#### Deploy sample application

To create a pipeline, and test the feature branch mechanism, you need to push
application code to the newly created CodeCommit repository. 

```
git remote add demo <codecommit url>
git push demo master

# test feature branch
git push demo master:featurebranch

# test branch removal
git push demo -d featurebranch
```

#### Further usage

Once the command has run once, you can skip the bundle step and it will reference
it by account id. The bundle will be deployed to an S3 bucket named `pipeline-branches-template-<ACCOUNT_ID>`.

Then, you can just run:

`APP_NAME=my-api make deploy -e`

## CodeCommit Handler Template

Make deploys a CloudFormation template that creates the repository and the listener. You
can bypass make by installing the template created at template-out.yaml.

#### Handler Template Parameters

* **ApplicationName** - (Required) The name of the application for which the repository will be created
* **LayerBundleS3Bucket** - (Required) The name of the S3 bucket, created during the quickstart
* **LayerBundleS3Key** - (Required) The key of the bundle in the preceding S3 bucket
* **RetentionPolicyInDays** - (Optional, default: `90`) How long to retain build artifacts, logs, etc...
* **PipelineTemplatePath** - (Optional, default: `pipeline.yaml`) The path in the repository to the CloudFormation
template containing the pipeline.

## Required Parameters for Pipeline Template

The following parameters must be included in the pipeline template. These may
or may not be used by the pipeline template.

```yaml
Parameters:
  ApplicationName:
    Type: String
    Description: 'The name of the application for which this pipeline builds'
  ArtifactBucketArn:
    Type: String
    Description: 'The ARN of the bucket used to store artifacts'
  ArtifactBucketName:
    Type: String
    Description: 'The name of the bucket used to store artifacts'
  Branch:
    Type: String
    Description: 'The branch this pipeline is running from'
  CodeCommitRepositoryArn:
    Type: String
    Description: 'The ARN of CodeCommit repository connected to this pipeline'
  CodeCommitRepositoryName:
    Type: String
    Description: 'The name of the CodeCommit repository connected to this pipeline'
  CommitId:
    Type: String
    Description: 'The current commit id'
  PipelineFile:
    Type: String
    Description: 'The path to the pipeline file for this repository'
  PipelineName:
    Type: String
    Description: 'The name to use for the pipeline'
  RetentionPolicyInDays:
    Type: String
    Description: 'How long to retain builds in days'
```