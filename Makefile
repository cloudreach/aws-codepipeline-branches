APP_NAME := pipeline-branches
TEMPLATE := template.yaml
TEMPLATE_OUT := template-out.yaml

# Define variables around layer creation
BUNDLE := layer_bundle_3.zip
DEPS_DIR := python/lib/python3.6/site-packages/
CWD := $(shell pwd)
ACCOUNT_ID := $(shell aws sts get-caller-identity --query "Account" --output text)
S3_BUCKET = pipeline-branches-template-$(ACCOUNT_ID)
STACK_NAME = $(APP_NAME)

bucket:
	@echo $(S3_BUCKET)
	aws s3api get-bucket-acl --bucket $(S3_BUCKET) ||\
	( echo "Creating bucket $(S3_BUCKET)" && aws s3api create-bucket --acl private --bucket $(S3_BUCKET))

$(BUNDLE): bucket
	mkdir -p $(DEPS_DIR)
	pip install boto3 --target $(DEPS_DIR)
	zip -r $(BUNDLE) $(DEPS_DIR)
	rm -rf $(echo "$(DEPS_DIR)" | cut -d "/" -f2)

.upload_bundle: $(BUNDLE)
	aws s3 cp $(BUNDLE) s3://$(S3_BUCKET)/$(BUNDLE)
	touch .upload_bundle

bundle: .upload_bundle

validate:
	aws cloudformation validate-template \
		--template-body file://$(TEMPLATE)

$(TEMPLATE_OUT):
	aws cloudformation package \
		--template-file $(TEMPLATE) \
		--s3-bucket $(S3_BUCKET) \
		--output-template-file $(TEMPLATE_OUT)

deploy: validate $(TEMPLATE_OUT)
	aws cloudformation deploy \
		--template-file $(TEMPLATE_OUT) \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides \
			ApplicationName=$(APP_NAME) \
			LayerBundleS3Bucket=$(S3_BUCKET) \
			LayerBundleS3Key=$(BUNDLE) \
			PipelineTemplatePath=examples/serverless/pipeline.yaml

clean:
	rm -f $(TEMPLATE_OUT) $(BUNDLE) .upload_bundle

.PHONY: bucket clean bundle validate deploy