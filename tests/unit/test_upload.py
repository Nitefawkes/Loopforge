#!/usr/bin/env python3
"""
Unit tests for the upload module
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, Mock, MagicMock
import tempfile
from pathlib import Path
import pytest
import datetime

# Add parent directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

from src.upload.upload_video import (
    validate_video_file, 
    find_metadata,
    validate_metadata,
    validate_upload_credentials,
    upload_to_youtube,
    verify_youtube_upload,
    update_upload_stats,
    YouTubeUploadError,
    ValidationError,
    ConfigError
)

class TestValidation(unittest.TestCase):
    """Test validation functions in the upload module"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create a temporary video file
        self.video_path = os.path.join(self.temp_dir.name, "test_video.mp4")
        with open(self.video_path, 'wb') as f:
            f.write(b'test video content')
            
        # Create a temporary metadata file
        self.metadata_path = os.path.join(self.temp_dir.name, "test_video.json")
        with open(self.metadata_path, 'w') as f:
            json.dump({
                "prompt_data": {
                    "caption": "Test Caption",
                    "hashtags": ["test", "loopforge"]
                },
                "original_video": "source.mp4",
                "processed_at": "2023-06-22T12:00:00"
            }, f)
            
        # Create a sample config
        self.config = {
            "api_keys": {
                "youtube": {
                    "client_id": "test_client_id",
                    "client_secret": "test_client_secret",
                    "refresh_token": "test_refresh_token"
                }
            }
        }
    
    def tearDown(self):
        """Clean up test environment"""
        self.temp_dir.cleanup()
    
    def test_validate_video_file(self):
        """Test video file validation"""
        # Valid file should pass
        self.assertTrue(validate_video_file(self.video_path))
        
        # Invalid file should raise ValidationError
        with self.assertRaises(ValidationError):
            validate_video_file("/nonexistent/path.mp4")
            
        # Invalid extension should raise ValidationError
        invalid_path = os.path.join(self.temp_dir.name, "invalid.txt")
        with open(invalid_path, 'w') as f:
            f.write("not a video")
            
        with self.assertRaises(ValidationError):
            validate_video_file(invalid_path)
    
    def test_find_metadata(self):
        """Test metadata finding"""
        # Metadata should be found for the test video
        metadata = find_metadata(self.video_path)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["prompt_data"]["caption"], "Test Caption")
        
        # No metadata for nonexistent file
        no_metadata_path = os.path.join(self.temp_dir.name, "no_metadata.mp4")
        with open(no_metadata_path, 'wb') as f:
            f.write(b'test content')
            
        self.assertIsNone(find_metadata(no_metadata_path))
    
    def test_validate_metadata(self):
        """Test metadata validation"""
        # Valid metadata should pass
        valid_metadata = {
            "prompt_data": {
                "caption": "Test Caption",
                "hashtags": ["test"]
            },
            "original_video": "source.mp4"
        }
        self.assertTrue(validate_metadata(valid_metadata))
        
        # Invalid metadata should raise ValidationError
        with self.assertRaises(ValidationError):
            validate_metadata("not a dict")
            
        with self.assertRaises(ValidationError):
            validate_metadata({"prompt_data": "not a dict"})
    
    def test_validate_upload_credentials(self):
        """Test credentials validation"""
        # Valid credentials should pass
        self.assertTrue(validate_upload_credentials(self.config, "youtube"))
        
        # Missing credentials should raise ConfigError
        invalid_config = {"api_keys": {"youtube": {}}}
        with self.assertRaises(ConfigError):
            validate_upload_credentials(invalid_config, "youtube")
            
        # Unknown platform should raise ConfigError
        with self.assertRaises(ConfigError):
            validate_upload_credentials(self.config, "unknown_platform")

class TestYouTubeUpload(unittest.TestCase):
    """Test YouTube upload functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create a temporary video file
        self.video_path = os.path.join(self.temp_dir.name, "test_video.mp4")
        with open(self.video_path, 'wb') as f:
            f.write(b'test video content')
            
        # Create a temporary metadata file
        self.metadata = {
            "prompt_data": {
                "caption": "Test YouTube Upload",
                "hashtags": ["test", "loopforge", "youtube"]
            },
            "original_video": "source.mp4",
            "processed_at": "2023-06-22T12:00:00"
        }
        
        # Create a sample config
        self.config = {
            "api_keys": {
                "youtube": {
                    "client_id": "test_client_id",
                    "client_secret": "test_client_secret",
                    "refresh_token": "test_refresh_token"
                }
            },
            "upload": {
                "platforms": ["youtube"],
                "youtube_category": "22",
                "privacy_status": "public",
                "tags_per_video": 10
            },
            "compliance": {
                "affiliate_disclaimer": "This is a test disclaimer"
            }
        }
    
    def tearDown(self):
        """Clean up test environment"""
        self.temp_dir.cleanup()
    
    @patch('subprocess.run')
    def test_upload_to_youtube_success(self, mock_run):
        """Test successful YouTube upload"""
        # Mock the subprocess.run call
        mock_process = Mock()
        mock_process.stdout = "Video ID: test_video_id\nStatus: uploaded"
        mock_process.stderr = ""
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        # Call the function with dry_run=True to test the path
        result = upload_to_youtube(self.video_path, self.metadata, self.config, dry_run=True)
        
        # Verify result structure for dry run
        self.assertTrue(result["success"])
        self.assertIn("dryrun_", result["video_id"])
        self.assertEqual(result["platform"], "youtube")
        self.assertIn("url", result)
        
        # Now test actual upload path with mocked subprocess
        with patch('src.upload.upload_video.verify_youtube_upload', return_value=True):
            result = upload_to_youtube(self.video_path, self.metadata, self.config, dry_run=False)
            
            # Verify the result
            self.assertTrue(result["success"])
            self.assertEqual(result["video_id"], "test_video_id")
            self.assertEqual(result["platform"], "youtube")
            self.assertEqual(result["url"], "https://youtube.com/shorts/test_video_id")
            self.assertEqual(result["title"], "Test YouTube Upload")
            self.assertTrue(result["verified"])
    
    @patch('subprocess.run')
    def test_upload_to_youtube_failure(self, mock_run):
        """Test YouTube upload failure"""
        # Mock a failed subprocess call
        mock_run.side_effect = Exception("Upload failed")
        
        # Test the error handling
        result = upload_to_youtube(self.video_path, self.metadata, self.config, dry_run=False)
        
        # Verify error result
        self.assertFalse(result["success"])
        self.assertEqual(result["platform"], "youtube")
        self.assertIn("error", result)
        self.assertIn("Upload failed", result["error"])
    
    @patch('subprocess.run')
    def test_token_refresh(self, mock_run):
        """Test token refresh handling"""
        # First call raises token error, second succeeds after refresh
        mock_run.side_effect = [
            Exception("Token expired error"),
            Mock(stdout="Refreshed token", stderr=""),
            Mock(stdout="Video ID: after_refresh_id", stderr="")
        ]
        
        # Should trigger a retry after token refresh
        with patch('src.upload.upload_video.verify_youtube_upload', return_value=True):
            result = upload_to_youtube(self.video_path, self.metadata, self.config, dry_run=False)
            
            # Function should have made 3 calls to subprocess.run
            self.assertEqual(mock_run.call_count, 3)
            self.assertTrue(result["success"])
    
    @patch('subprocess.run')
    def test_verify_youtube_upload(self, mock_run):
        """Test YouTube upload verification"""
        # Mock a successful verification
        mock_process = Mock()
        mock_process.stdout = "Video status: available"
        mock_process.stderr = ""
        mock_run.return_value = mock_process
        
        # Test successful verification
        self.assertTrue(verify_youtube_upload("test_video_id", self.config))
        
        # Mock a processing status followed by available
        mock_run.side_effect = [
            Mock(stdout="Video status: processing", stderr=""),
            Mock(stdout="Video status: available", stderr="")
        ]
        
        # Should retry and succeed
        self.assertTrue(verify_youtube_upload("test_video_id", self.config, retry_count=2))
        
        # Mock a rejection status
        mock_run.side_effect = [Mock(stdout="Video status: rejected", stderr="")]
        
        # Should fail
        self.assertFalse(verify_youtube_upload("test_video_id", self.config))
        
        # Try with unknown video_id
        self.assertFalse(verify_youtube_upload("unknown", self.config))
        
        # Try with dry run id
        self.assertTrue(verify_youtube_upload("dryrun_123", self.config))

class TestUploadStats(unittest.TestCase):
    """Test upload statistics tracking"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.uploads_dir = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(self.uploads_dir, exist_ok=True)
        
        # Create a sample video path
        self.video_path = "/path/to/test_video.mp4"
        
        # Create sample results
        self.success_result = {
            "platform": "youtube",
            "success": True,
            "video_id": "test_id",
            "url": "https://youtube.com/shorts/test_id",
            "timestamp": "2023-06-22T12:00:00"
        }
        
        self.fail_result = {
            "platform": "tiktok",
            "success": False,
            "error": "Upload failed",
            "timestamp": "2023-06-22T12:05:00"
        }
    
    def tearDown(self):
        """Clean up test environment"""
        self.temp_dir.cleanup()
    
    def test_update_upload_stats(self):
        """Test update_upload_stats function"""
        # Test with success result
        stats = update_upload_stats(self.video_path, self.success_result, self.uploads_dir)
        
        # Verify stats structure
        self.assertEqual(stats["total_uploads"], 1)
        self.assertEqual(stats["successful_uploads"], 1)
        self.assertEqual(stats["failed_uploads"], 0)
        self.assertEqual(stats["uploads_by_platform"]["youtube"]["total"], 1)
        self.assertEqual(stats["uploads_by_platform"]["youtube"]["successful"], 1)
        self.assertEqual(len(stats["recent_uploads"]), 1)
        
        # Test with failure result
        stats = update_upload_stats(self.video_path, self.fail_result, self.uploads_dir)
        
        # Verify updated stats
        self.assertEqual(stats["total_uploads"], 2)
        self.assertEqual(stats["successful_uploads"], 1)
        self.assertEqual(stats["failed_uploads"], 1)
        self.assertEqual(stats["uploads_by_platform"]["tiktok"]["total"], 1)
        self.assertEqual(stats["uploads_by_platform"]["tiktok"]["failed"], 1)
        self.assertEqual(len(stats["recent_uploads"]), 2)
        
        # Verify recent uploads ordering (newest first)
        self.assertEqual(stats["recent_uploads"][0]["platform"], "tiktok")
        self.assertEqual(stats["recent_uploads"][1]["platform"], "youtube")
        
        # Check if files were created
        stats_file = os.path.join(self.uploads_dir, "stats", "upload_stats.json")
        self.assertTrue(os.path.exists(stats_file))
        
        upload_record = os.path.join(self.uploads_dir, "test_video_uploads.json")
        self.assertTrue(os.path.exists(upload_record))

if __name__ == "__main__":
    unittest.main() 