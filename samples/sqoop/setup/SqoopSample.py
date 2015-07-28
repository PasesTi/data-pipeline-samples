import boto3
from SetupPipelineDefinition import SetupPipelineDefinitionHelper
import time


class SqoopSample(object):
    def __init__(self):
        self.s3_bucket_path = ""
        self.rds_id = ""
        self.rds_endpoint = ""
        self.rds_security_group = "sqoop_sample_rds_sec_group"
        self.redshift_id = ""
        self.redshift_endpoint = ""
        self.redshift_security_group = 'sqoop_sample_rs_sec_group'
        self.pipeline_definition = SetupPipelineDefinitionHelper()
        self.account_id = ""
        self.pipeline_id = ""

    def check_for_s3_path_argument(self, args):
        if len(args) > 1:
            return args[1]
        else:
            return ""

    def create_s3_bucket(self, s3_bucket_path):
        client = boto3.client('s3')
        if len(s3_bucket_path) > 0:
            if s3_bucket_path.startswith("s3://"):
                s3_bucket_path = s3_bucket_path[5:]
            if not '/' in s3_bucket_path:
                print "S3 bucket path must contain a subpath"
            self.s3_bucket_path = s3_bucket_path
        else:
            self.s3_bucket_path = "sqoop-demo-" + str(int(time.time()))
            print "Creating s3 bucket: s3://" + self.s3_bucket_path + '/test'
            client.create_bucket(Bucket=self.s3_bucket_path)

    def create_rds_instance(self):
        self.rds_id = 'RDS-sqoop-' + str(int(time.time()))
        print "Creating RDS database with id: " + self.rds_id

        # get account id
        iam = boto3.resource('iam')
        current_user = iam.CurrentUser()
        self.account_id = ''.join([i for i in current_user.arn if i.isdigit()])[0:12]

        client = boto3.client('rds')

        # create security group
        client.create_db_security_group(DBSecurityGroupName=self.rds_security_group,
                                        DBSecurityGroupDescription='Security group for RDS for sqoop example')

        client.authorize_db_security_group_ingress(DBSecurityGroupName=self.rds_security_group,
                                                   EC2SecurityGroupName='elasticmapreduce-master',
                                                   EC2SecurityGroupOwnerId=self.account_id)

        client.authorize_db_security_group_ingress(DBSecurityGroupName=self.rds_security_group,
                                                   EC2SecurityGroupName='elasticmapreduce-slave',
                                                   EC2SecurityGroupOwnerId=self.account_id)

        # create db
        client.create_db_instance(DBName='millionsongs',
                                  DBInstanceIdentifier=self.rds_id,
                                  AllocatedStorage=5,
                                  DBInstanceClass='db.m1.small',
                                  Engine='MySQL',
                                  MasterUsername='dplcustomer',
                                  MasterUserPassword='Dplcustomer1',
                                  DBSecurityGroups=[
                                      self.rds_security_group,
                                  ])

        # wait for db to be created
        waiter = client.get_waiter('db_instance_available')

        waiter.wait(DBInstanceIdentifier=self.rds_id)

        response = client.describe_db_instances(DBInstanceIdentifier=self.rds_id)

        self.rds_endpoint = response['DBInstances'][0]['Endpoint']['Address']
        print "RDS Endpoint: " + self.rds_endpoint

    def create_redshift_cluster(self):
        self.redshift_id = 'Redshift-sqoop-' + str(int(time.time()))
        print "Creating Redshift cluster with id: " + self.redshift_id

        client = boto3.client('redshift')

        # create security group
        client.create_cluster_security_group(ClusterSecurityGroupName=self.redshift_security_group,
                                             Description='Security group for redshift for sqoop example')

        client.authorize_cluster_security_group_ingress(ClusterSecurityGroupName=self.redshift_security_group,
                                                        EC2SecurityGroupName='elasticmapreduce-master',
                                                        EC2SecurityGroupOwnerId=self.account_id)

        # create cluster
        client.create_cluster(DBName='redshiftsqoop',
                              ClusterIdentifier=self.redshift_id,
                              ClusterType='single-node',
                              NodeType='dc1.large',
                              MasterUsername='dplcustomer',
                              MasterUserPassword='Dplcustomer1',
                              ClusterSecurityGroups=[
                                  self.redshift_security_group,
                              ])

        # wait for cluster to be created
        waiter = client.get_waiter('cluster_available')

        waiter.wait(ClusterIdentifier=self.redshift_id)

        response = client.describe_clusters(ClusterIdentifier=self.redshift_id)

        self.redshift_endpoint = response['Clusters'][0]['Endpoint']['Address']
        print "Redshift Endpoint: " + self.redshift_endpoint

    def run_setup_datapipeline(self):
        pipeline_name = 'sqoop-setup-' + str(int(time.time()))
        print "creating and running data pipeline to setup data in RDS with name: " + pipeline_name

        client = boto3.client('datapipeline')

        result = client.create_pipeline(name='Setup Data for Sqoop sample',
                                        uniqueId=pipeline_name)

        self.pipeline_id = result['pipelineId']
        print "Pipeline id: " + self.pipeline_id

        parameter_values = self.pipeline_definition.get_setup_pipeline_parameter_values()
        for param in parameter_values:
            if param['id'] == 'myRdsEndpoint':
                param['stringValue'] = self.rds_endpoint

        client.put_pipeline_definition(pipelineId=self.pipeline_id,
                                       pipelineObjects=self.pipeline_definition.get_setup_pipeline_objects(),
                                       parameterValues=parameter_values)

        client.activate_pipeline(pipelineId=self.pipeline_id)

        response = client.describe_pipelines(pipelineIds=[self.pipeline_id])

        # check pipeline status
        self._check_pipeline_state(response)

    def _check_pipeline_state(self, response):
        count = 0
        pipeline_done = False
        while count < 40 and pipeline_done is False:
            for pipeline in response['pipelineDescriptionList'][0]['fields']:
                if pipeline['stringValue'] == 'FINISHED':
                    print "Setup pipeline run finished"
                    pipeline_done = True
                    break
                elif pipeline['stringValue'] == 'FAILED':
                    pipeline_done = True
                    break
                else:
                    print "Setup pipeline run in progress..."
                    count += 1
                    time.sleep(30)

    def print_setup_results(self):
        print ""
        print "Set-up complete! You are now ready to proceed with the Sqoop Sample."
        print "Please refer to the sample README for instructions on how to run this sample."
        print "**************************************************"
        print "*               Resource Summary                 *"
        print "**************************************************"
        print "RDS ID: " + self.rds_id
        print "RDS Hostname: " + self.rds_endpoint
        print "Redshift ID: " + self.redshift_id
        print "Redshift Hostname: " + self.redshift_endpoint
        print "S3 path: s3://" + self.s3_bucket_path
        print ""
        print "You can copy and paste the following line to add the sample definition to your pipeline once it is " \
              "created (Step 2)"
        print "aws datapipeline put-pipeline-definition --pipeline-id <pipeline-id>  " \
              "--pipeline-definition file://sqoop.json --parameter-values myRdsEndpoint=" + self.rds_endpoint + \
              " myRedshiftEndpoint=" + self.redshift_endpoint + ' myS3StagingPath=s3://' + self.s3_bucket_path + '/test'
        print ""
        print "If you wish to delete all the resources created for this sample, " \
              "please run the teardown script as follows"
        print "python Teardown.py " + self.rds_id + " " + self.redshift_id + ' s3://' + self.s3_bucket_path + '/test'

    def destroy_rds(self, rds_id):
        print "Destroying RDS database with id: " + rds_id
        client = boto3.client('rds')
        client.delete_db_instance(DBInstanceIdentifier=rds_id,
                                  SkipFinalSnapshot=True)

        # wait for db to be deleted
        waiter = client.get_waiter('db_instance_deleted')

        waiter.wait(DBInstanceIdentifier=rds_id)

        # delete security group
        client.delete_db_security_group(DBSecurityGroupName=self.rds_security_group)

    def destroy_redshift(self, redshift_id):
        print "Destroying Redshift cluster with id: " + redshift_id

        client = boto3.client('redshift')

        client.delete_cluster(ClusterIdentifier=redshift_id,
                              SkipFinalClusterSnapshot=True)

        # wait for cluster to be deleted
        waiter = client.get_waiter('cluster_deleted')

        waiter.wait(ClusterIdentifier=redshift_id)

        # delete security group
        client.delete_cluster_security_group(ClusterSecurityGroupName=self.redshift_security_group)

    def destroy_s3_bucket(self, s3_bucket_path):
        print "Destroying S3 bucket with path: " + s3_bucket_path

        if s3_bucket_path.startswith("s3://"):
                s3_bucket_path = s3_bucket_path[5:]

        s3 = boto3.resource('s3')
        client = boto3.client('s3')
        bucket = s3.Bucket(s3_bucket_path)

        for s3_object in bucket.objects.all():
            client.delete_object(Bucket=s3_bucket_path, Key=s3_object.key)

        bucket.delete()
