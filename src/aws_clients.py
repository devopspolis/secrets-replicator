"""
AWS client wrappers for Secrets Manager and STS operations.

Provides high-level interfaces for secret management with
cross-account support via STS AssumeRole.
"""

import boto3
from typing import Optional, Dict, Any, Tuple
from botocore.exceptions import ClientError
from dataclasses import dataclass
from src.logger import setup_logger

# Initialize module logger
logger = setup_logger('aws_clients')


class AWSClientError(Exception):
    """Base exception for AWS client errors"""
    pass


class SecretNotFoundError(AWSClientError):
    """Raised when secret does not exist"""
    pass


class AccessDeniedError(AWSClientError):
    """Raised when access is denied to AWS resource"""
    pass


class InvalidRequestError(AWSClientError):
    """Raised when request is invalid"""
    pass


class ThrottlingError(AWSClientError):
    """Raised when AWS throttles the request"""
    pass


class InternalServiceError(AWSClientError):
    """Raised when AWS internal service error occurs"""
    pass


@dataclass
class SecretValue:
    """
    Container for secret value and metadata.

    Attributes:
        secret_string: String secret value (None if binary)
        secret_binary: Binary secret value (None if string)
        arn: Full ARN of the secret
        name: Name of the secret
        version_id: Version ID
        version_stages: List of version stages (e.g., ['AWSCURRENT'])
        created_date: Creation date
    """
    secret_string: Optional[str] = None
    secret_binary: Optional[bytes] = None
    arn: Optional[str] = None
    name: Optional[str] = None
    version_id: Optional[str] = None
    version_stages: Optional[list] = None
    created_date: Optional[str] = None


class SecretsManagerClient:
    """
    High-level client for AWS Secrets Manager operations.

    Supports both same-account and cross-account operations via
    STS AssumeRole.

    Examples:
        # Same account
        client = SecretsManagerClient(region='us-east-1')
        secret = client.get_secret('my-secret')

        # Cross-account
        client = SecretsManagerClient(
            region='us-west-2',
            role_arn='arn:aws:iam::123456789012:role/SecretReplicator'
        )
        secret = client.get_secret('my-secret')
    """

    def __init__(self, region: str, role_arn: Optional[str] = None,
                 external_id: Optional[str] = None, session_name: Optional[str] = None):
        """
        Initialize Secrets Manager client.

        Args:
            region: AWS region for the client
            role_arn: Optional IAM role ARN to assume for cross-account access
            external_id: Optional external ID for role assumption
            session_name: Optional session name for role assumption

        Raises:
            AccessDeniedError: If role assumption fails
        """
        self.region = region
        self.role_arn = role_arn
        self.external_id = external_id
        self.session_name = session_name or 'secrets-replicator'

        # Initialize client (with or without assumed role)
        if role_arn:
            self._client = self._create_client_with_assumed_role()
        else:
            self._client = boto3.client('secretsmanager', region_name=region)

    def _create_client_with_assumed_role(self) -> Any:
        """
        Create Secrets Manager client with assumed role credentials.

        Returns:
            Boto3 Secrets Manager client with assumed role credentials

        Raises:
            AccessDeniedError: If role assumption fails
        """
        try:
            # Create STS client
            sts = boto3.client('sts')

            # Build assume role parameters
            assume_role_params = {
                'RoleArn': self.role_arn,
                'RoleSessionName': self.session_name
            }

            if self.external_id:
                assume_role_params['ExternalId'] = self.external_id

            # Assume role
            logger.info(f'Assuming role: {self.role_arn}')
            response = sts.assume_role(**assume_role_params)

            credentials = response['Credentials']

            # Create client with temporary credentials
            return boto3.client(
                'secretsmanager',
                region_name=self.region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']

            if error_code == 'AccessDenied':
                raise AccessDeniedError(f'Failed to assume role {self.role_arn}: {error_msg}')
            else:
                raise AWSClientError(f'STS error: {error_msg}')

    def get_secret(self, secret_id: str, version_id: Optional[str] = None,
                   version_stage: Optional[str] = None) -> SecretValue:
        """
        Retrieve a secret value from Secrets Manager.

        Args:
            secret_id: Secret name or ARN
            version_id: Optional specific version ID to retrieve
            version_stage: Optional version stage (e.g., 'AWSCURRENT')

        Returns:
            SecretValue object containing the secret and metadata

        Raises:
            SecretNotFoundError: If secret does not exist
            AccessDeniedError: If access is denied
            InvalidRequestError: If request parameters are invalid
            ThrottlingError: If request is throttled
            InternalServiceError: If AWS internal error occurs

        Examples:
            >>> client = SecretsManagerClient('us-east-1')
            >>> secret = client.get_secret('my-secret')
            >>> print(secret.secret_string)
            '{"username":"admin","password":"secret123"}'
        """
        try:
            # Build request parameters
            params = {'SecretId': secret_id}

            if version_id:
                params['VersionId'] = version_id
            elif version_stage:
                params['VersionStage'] = version_stage

            # Get secret value
            response = self._client.get_secret_value(**params)

            # Extract secret value and metadata
            return SecretValue(
                secret_string=response.get('SecretString'),
                secret_binary=response.get('SecretBinary'),
                arn=response.get('ARN'),
                name=response.get('Name'),
                version_id=response.get('VersionId'),
                version_stages=response.get('VersionStages', []),
                created_date=response.get('CreatedDate')
            )

        except ClientError as e:
            self._handle_client_error(e, f'get_secret({secret_id})')

    def put_secret(self, secret_id: str, secret_value: str,
                   kms_key_id: Optional[str] = None,
                   description: Optional[str] = None,
                   tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Create or update a secret in Secrets Manager.

        If secret exists, updates the value. If it doesn't exist, creates it.

        Args:
            secret_id: Secret name (for new secrets) or name/ARN (for updates)
            secret_value: Secret value to store
            kms_key_id: Optional KMS key ID for encryption
            description: Optional description for new secrets
            tags: Optional tags for new secrets (dict of key-value pairs)

        Returns:
            Response dict with ARN, Name, VersionId

        Raises:
            AccessDeniedError: If access is denied
            InvalidRequestError: If request parameters are invalid
            ThrottlingError: If request is throttled
            InternalServiceError: If AWS internal error occurs

        Examples:
            >>> client = SecretsManagerClient('us-east-1')
            >>> response = client.put_secret('my-secret', '{"user":"admin"}')
            >>> print(response['VersionId'])
            'abc123-def456-...'
        """
        try:
            # Check if secret exists
            exists = self.secret_exists(secret_id)

            if exists:
                # Update existing secret
                params = {
                    'SecretId': secret_id,
                    'SecretString': secret_value
                }

                response = self._client.put_secret_value(**params)

            else:
                # Create new secret
                params = {
                    'Name': secret_id,
                    'SecretString': secret_value
                }

                if kms_key_id:
                    params['KmsKeyId'] = kms_key_id

                if description:
                    params['Description'] = description

                if tags:
                    # Convert dict to list of {Key, Value} dicts
                    params['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]

                response = self._client.create_secret(**params)

            return {
                'ARN': response.get('ARN'),
                'Name': response.get('Name'),
                'VersionId': response.get('VersionId')
            }

        except ClientError as e:
            self._handle_client_error(e, f'put_secret({secret_id})')

    def secret_exists(self, secret_id: str) -> bool:
        """
        Check if a secret exists.

        Args:
            secret_id: Secret name or ARN

        Returns:
            True if secret exists, False otherwise

        Examples:
            >>> client = SecretsManagerClient('us-east-1')
            >>> if client.secret_exists('my-secret'):
            ...     print('Secret exists')
        """
        try:
            self._client.describe_secret(SecretId=secret_id)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return False
            # Re-raise other errors
            self._handle_client_error(e, f'secret_exists({secret_id})')

    def _handle_client_error(self, error: ClientError, operation: str) -> None:
        """
        Handle boto3 ClientError and raise appropriate custom exception.

        Args:
            error: The ClientError from boto3
            operation: Description of the operation that failed

        Raises:
            SecretNotFoundError: For ResourceNotFoundException
            AccessDeniedError: For AccessDeniedException
            InvalidRequestError: For InvalidRequestException, InvalidParameterException
            ThrottlingError: For ThrottlingException
            InternalServiceError: For InternalServiceError
            AWSClientError: For other errors
        """
        error_code = error.response['Error']['Code']
        error_msg = error.response['Error']['Message']

        # Map AWS error codes to custom exceptions
        error_mapping = {
            'ResourceNotFoundException': SecretNotFoundError,
            'AccessDeniedException': AccessDeniedError,
            'InvalidRequestException': InvalidRequestError,
            'InvalidParameterException': InvalidRequestError,
            'ThrottlingException': ThrottlingError,
            'InternalServiceError': InternalServiceError,
        }

        exception_class = error_mapping.get(error_code, AWSClientError)
        raise exception_class(f'{operation} failed: {error_msg}')


def create_secrets_manager_client(region: str,
                                  role_arn: Optional[str] = None,
                                  external_id: Optional[str] = None) -> SecretsManagerClient:
    """
    Factory function to create a SecretsManagerClient.

    Args:
        region: AWS region
        role_arn: Optional IAM role ARN to assume
        external_id: Optional external ID for role assumption

    Returns:
        SecretsManagerClient instance

    Examples:
        >>> client = create_secrets_manager_client('us-east-1')
        >>> client = create_secrets_manager_client('us-west-2', role_arn='arn:...')
    """
    return SecretsManagerClient(region=region, role_arn=role_arn, external_id=external_id)
