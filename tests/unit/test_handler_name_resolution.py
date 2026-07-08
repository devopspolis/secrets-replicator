"""
Regression tests for destination secret name resolution.

EventBridge events carry the full secret ARN as secret_id. The handler must
resolve the ARN to the friendly name before the name-mapping lookup and the
destination write - otherwise the destination secret is created under the
full ARN string and name mappings never match.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from aws_clients import SecretValue
from config import DestinationConfig, ReplicatorConfig
from event_parser import SecretEvent
from handler import process_single_secret

SOURCE_ARN = "arn:aws:secretsmanager:us-east-1:123456789012:secret:app/prod/db-AbCdEf"
FRIENDLY_NAME = "app/prod/db"


def make_secret_event(secret_id=SOURCE_ARN):
    return SecretEvent(
        event_name="PutSecretValue",
        secret_id=secret_id,
        secret_arn=SOURCE_ARN,
        version_id="v1",
        region="us-east-1",
        account_id="123456789012",
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_identity=None,
        source_ip=None,
        request_parameters={},
        response_elements={},
    )


def make_source_client():
    client = MagicMock()
    client.get_secret.return_value = SecretValue(
        secret_string='{"host": "db.us-east-1.example.com"}',
        secret_binary=None,
        arn=SOURCE_ARN,
        name=FRIENDLY_NAME,
        version_id="v1",
        version_stages=["AWSCURRENT"],
    )
    client.get_secret_description.return_value = "test secret"
    return client


def make_config():
    return ReplicatorConfig(destinations=[DestinationConfig(region="us-west-2")])


class TestDestinationNameResolution:
    """The handler must use the friendly name, never the event's full ARN"""

    @patch("handler.get_destination_name", return_value=None)
    @patch("handler.load_destinations")
    @patch("handler.create_secrets_manager_client")
    def test_name_mapping_lookup_receives_friendly_name(
        self, mock_create_client, mock_load_destinations, mock_get_dest_name
    ):
        """Name-mapping lookup gets the extracted name, not the ARN"""
        mock_create_client.return_value = make_source_client()

        process_single_secret(
            make_secret_event(), make_config(), MagicMock(), MagicMock(), time.time()
        )

        assert mock_get_dest_name.call_count == 1
        looked_up_name = mock_get_dest_name.call_args[0][0]
        assert looked_up_name == FRIENDLY_NAME

    @patch("handler.get_destination_transformation", return_value=(True, None))
    @patch("handler.load_destinations")
    @patch("handler.create_secrets_manager_client")
    def test_destination_write_uses_friendly_name(
        self, mock_create_client, mock_load_destinations, mock_get_transform
    ):
        """With no name mapping configured, the destination secret is written
        under the source's friendly name, not the source ARN"""
        source_client = make_source_client()
        dest_client = MagicMock()
        dest_client.put_secret.return_value = {"ARN": "arn:dest", "VersionId": "v1"}
        # The handler creates the source client twice (config load + retrieval),
        # then the destination client
        mock_create_client.side_effect = [source_client, source_client, dest_client]

        response = process_single_secret(
            make_secret_event(), make_config(), MagicMock(), MagicMock(), time.time()
        )

        assert dest_client.put_secret.call_count == 1
        written_name = dest_client.put_secret.call_args.kwargs["secret_id"]
        assert written_name == FRIENDLY_NAME
        assert written_name != SOURCE_ARN
        assert response["statusCode"] == 200

    @patch("handler.get_destination_transformation", return_value=(True, None))
    @patch("handler.load_destinations")
    @patch("handler.create_secrets_manager_client")
    def test_plain_name_secret_id_passes_through(
        self, mock_create_client, mock_get_transform, mock_load_destinations
    ):
        """Manual triggers pass a friendly name as secret_id - used as-is"""
        source_client = make_source_client()
        dest_client = MagicMock()
        dest_client.put_secret.return_value = {"ARN": "arn:dest", "VersionId": "v1"}
        mock_create_client.side_effect = [source_client, source_client, dest_client]

        process_single_secret(
            make_secret_event(secret_id=FRIENDLY_NAME),
            make_config(),
            MagicMock(),
            MagicMock(),
            time.time(),
        )

        assert dest_client.put_secret.call_count == 1
        assert dest_client.put_secret.call_args.kwargs["secret_id"] == FRIENDLY_NAME
