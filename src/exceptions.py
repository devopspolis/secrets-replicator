"""
Custom exception classes for the secrets replicator.

Provides exception hierarchy for AWS errors, transformation errors,
and other operational failures.
"""


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
