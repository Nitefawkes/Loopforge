"""
Unit tests for the notifications module.
"""
import os
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src import notifications

class TestNotifications(unittest.TestCase):
    """Tests for the notifications module."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock config data
        self.mock_config = {
            "notifications": {
                "email": {
                    "enabled": True,
                    "smtp_server": "test-smtp.example.com",
                    "smtp_port": 587,
                    "smtp_user": "test-user",
                    "smtp_password": "test-password",
                    "from": "test@example.com",
                    "to": ["recipient@example.com"]
                },
                "slack": {
                    "enabled": True,
                    "webhook_url": "https://hooks.slack.com/services/test/webhook"
                },
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/api/webhooks/test/webhook"
                }
            }
        }

    @patch('src.notifications.load_notification_config')
    @patch('smtplib.SMTP')
    def test_send_email(self, mock_smtp, mock_load_config):
        """Test sending an email notification."""
        # Configure the mock
        mock_load_config.return_value = self.mock_config.get("notifications", {})
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        # Call the function
        notifications.send_email("Test Subject", "Test Message")

        # Assertions
        mock_smtp.assert_called_once_with(
            self.mock_config["notifications"]["email"]["smtp_server"],
            self.mock_config["notifications"]["email"]["smtp_port"]
        )
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(
            self.mock_config["notifications"]["email"]["smtp_user"],
            self.mock_config["notifications"]["email"]["smtp_password"]
        )
        mock_server.sendmail.assert_called_once()

    @patch('src.notifications.load_notification_config')
    @patch('requests.post')
    def test_send_slack(self, mock_post, mock_load_config):
        """Test sending a Slack notification."""
        # Configure the mock
        mock_load_config.return_value = self.mock_config.get("notifications", {})

        # Call the function
        notifications.send_slack("Test Message")

        # Assertions
        mock_post.assert_called_once_with(
            self.mock_config["notifications"]["slack"]["webhook_url"],
            json={"text": "Test Message"},
            timeout=10
        )

    @patch('src.notifications.load_notification_config')
    @patch('requests.post')
    def test_send_discord(self, mock_post, mock_load_config):
        """Test sending a Discord notification."""
        # Configure the mock
        mock_load_config.return_value = self.mock_config.get("notifications", {})

        # Call the function
        notifications.send_discord("Test Message")

        # Assertions
        mock_post.assert_called_once_with(
            self.mock_config["notifications"]["discord"]["webhook_url"],
            json={"content": "Test Message"},
            timeout=10
        )

    @patch('src.notifications.send_email')
    @patch('src.notifications.send_slack')
    @patch('src.notifications.send_discord')
    def test_send_alert(self, mock_discord, mock_slack, mock_email):
        """Test sending an alert to all channels."""
        # Call the function
        notifications.send_alert("Test Subject", "Test Message")

        # Assertions
        mock_email.assert_called_once_with("Test Subject", "Test Message")
        mock_slack.assert_called_once_with("*Test Subject*\nTest Message")
        mock_discord.assert_called_once_with("**Test Subject**\nTest Message")

    @patch('src.notifications.load_notification_config')
    def test_disabled_notifications(self, mock_load_config):
        """Test that notifications aren't sent when disabled."""
        # Configure mock to return disabled notifications
        disabled_config = {
            "email": {"enabled": False},
            "slack": {"enabled": False},
            "discord": {"enabled": False}
        }
        mock_load_config.return_value = disabled_config

        # Test each notification type is properly disabled
        with patch('smtplib.SMTP') as mock_smtp:
            notifications.send_email("Test", "Test")
            mock_smtp.assert_not_called()

        with patch('requests.post') as mock_post:
            notifications.send_slack("Test")
            notifications.send_discord("Test")
            mock_post.assert_not_called()

if __name__ == '__main__':
    unittest.main() 