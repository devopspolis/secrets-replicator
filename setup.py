"""
Setup script for secrets-replicator
"""

from setuptools import setup, find_packages

setup(
    name='secrets-replicator',
    version='0.1.0',
    description='AWS Lambda function for cross-region/cross-account AWS Secrets Manager replication with value transformation',
    author='DevOpsPolis',
    license='MIT',
    packages=find_packages(exclude=['tests*']),
    python_requires='>=3.12',
    install_requires=[
        'boto3>=1.34.0',
        'botocore>=1.34.0',
        'tenacity>=8.2.3',
        'jsonpath-ng>=1.6.0',
        'typing-extensions>=4.8.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'pytest-mock>=3.12.0',
            'moto>=4.2.0',
            'black>=23.0.0',
            'pylint>=3.0.0',
            'flake8>=6.1.0',
            'mypy>=1.7.0',
            'boto3-stubs[secretsmanager,s3,sts]>=1.34.0',
            'pre-commit>=3.5.0',
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.12',
    ],
)
