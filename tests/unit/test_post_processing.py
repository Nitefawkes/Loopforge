"""
Unit tests for the post-processing module.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import subprocess

# Add the root directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.post_processing import process_video

class TestPostProcessing(unittest.TestCase):
    """Tests for the post-processing module."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock config data
        self.mock_config = {
            "video": {
                "watermark_file": "logo.png",
                "watermark_opacity": 0.7,
                "watermark_position": "bottom-right"
            },
            "paths": {
                "prompts_dir": "data/prompts_to_render",
                "rendered_dir": "data/rendered_clips",
                "ready_dir": "data/ready_to_post",
                "b_roll_dir": "assets/b_roll",
                "branding_dir": "assets/branding"
            }
        }
        
        # Sample prompt data
        self.sample_prompt = {
            "prompt": "Test prompt",
            "negative_prompt": "Test negative prompt",
            "caption": "Test caption",
            "hashtags": ["test", "ai", "video"],
            "aspect_ratio": "1:1",
            "metadata": {
                "id": "test-uuid",
                "topic": "test topic",
                "generated_at": "2023-06-21T12:00:00",
                "status": "rendered",
                "output_path": "/path/to/test_video.mp4"
            }
        }

    @patch('builtins.open', new_callable=mock_open, read_data='{"test": "data"}')
    def test_load_config(self, mock_file):
        """Test loading configuration from file."""
        result = process_video.load_config()
        mock_file.assert_called_once()
        self.assertEqual(result, {"test": "data"})

    @patch('builtins.open')
    @patch('sys.exit')
    def test_load_config_file_not_found(self, mock_exit, mock_file):
        """Test handling of missing config file."""
        mock_file.side_effect = FileNotFoundError()
        process_video.load_config()
        mock_exit.assert_called_once_with(1)

    @patch('os.listdir')
    @patch('builtins.open', new_callable=mock_open, read_data=json.dumps({
        "metadata": {"output_path": "/path/to/test_video.mp4"}
    }))
    def test_find_prompt_data_success(self, mock_file, mock_listdir):
        """Test finding prompt data for a video file."""
        # Setup mocks
        mock_listdir.return_value = ["prompt1.json", "prompt2.json"]
        
        # Call the function
        prompt_data, file_path = process_video.find_prompt_data("/path/to/test_video.mp4", self.mock_config)
        
        # Assertions
        self.assertIsNotNone(prompt_data)
        self.assertEqual(prompt_data["metadata"]["output_path"], "/path/to/test_video.mp4")

    @patch('os.listdir')
    def test_find_prompt_data_not_found(self, mock_listdir):
        """Test handling when prompt data is not found."""
        # Setup mocks
        mock_listdir.return_value = ["prompt1.json", "prompt2.json"]
        
        # Mock open to return a different output path
        with patch('builtins.open', new_callable=mock_open, read_data=json.dumps({
            "metadata": {"output_path": "/path/to/different.mp4"}
        })):
            # Call the function
            prompt_data, file_path = process_video.find_prompt_data("/path/to/test_video.mp4", self.mock_config)
            
            # Assertions
            self.assertIsNone(prompt_data)
            self.assertIsNone(file_path)

    @patch('os.makedirs')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_generate_captions_success(self, mock_exists, mock_run, mock_makedirs):
        """Test successful caption generation."""
        # Setup mocks
        mock_exists.return_value = True
        
        # Call the function
        result = process_video.generate_captions("/path/to/test_video.mp4")
        
        # Assertions
        mock_makedirs.assert_called_once()
        mock_run.assert_called_once()
        self.assertIsNotNone(result)

    @patch('os.makedirs')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_generate_captions_failure(self, mock_exists, mock_run, mock_makedirs):
        """Test caption generation when output file is not created."""
        # Setup mocks
        mock_exists.return_value = False
        
        # Call the function
        result = process_video.generate_captions("/path/to/test_video.mp4")
        
        # Assertions
        mock_makedirs.assert_called_once()
        mock_run.assert_called_once()
        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_generate_captions_exception(self, mock_run):
        """Test caption generation with exception."""
        # Setup mocks
        mock_run.side_effect = Exception("Command failed")
        
        # Call the function
        result = process_video.generate_captions("/path/to/test_video.mp4")
        
        # Assertions
        mock_run.assert_called_once()
        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_create_seamless_loop_success(self, mock_run):
        """Test successful seamless loop creation."""
        # Call the function
        result = process_video.create_seamless_loop("/path/to/input.mp4", "/path/to/output.mp4")
        
        # Assertions
        mock_run.assert_called_once()
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_create_seamless_loop_failure(self, mock_run):
        """Test seamless loop creation with exception."""
        # Setup mocks
        mock_run.side_effect = Exception("Command failed")
        
        # Call the function
        result = process_video.create_seamless_loop("/path/to/input.mp4", "/path/to/output.mp4")
        
        # Assertions
        mock_run.assert_called_once()
        self.assertFalse(result)

    @patch('os.path.exists')
    def test_add_b_roll_directory_not_found(self, mock_exists):
        """Test handling when b-roll directory doesn't exist."""
        # Setup mocks
        mock_exists.return_value = False
        
        # Call the function
        result = process_video.add_b_roll("/path/to/input.mp4", "/path/to/output.mp4", self.mock_config)
        
        # Assertions
        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_add_b_roll_no_files(self, mock_listdir, mock_exists):
        """Test handling when no b-roll files are found."""
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = []
        
        # Call the function
        result = process_video.add_b_roll("/path/to/input.mp4", "/path/to/output.mp4", self.mock_config)
        
        # Assertions
        self.assertFalse(result)

    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('moviepy.editor.VideoFileClip')
    @patch('moviepy.editor.CompositeVideoClip')
    def test_add_b_roll_success(self, mock_composite, mock_video_clip, mock_listdir, mock_exists):
        """Test successful b-roll addition."""
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = ["clip1.mp4", "clip2.mp4"]
        
        mock_main_clip = MagicMock()
        mock_main_clip.size = (1080, 1080)
        mock_main_clip.duration = 5.0
        
        mock_b_roll_clip = MagicMock()
        
        mock_final_clip = MagicMock()
        
        mock_video_clip.side_effect = [mock_main_clip, mock_b_roll_clip]
        mock_composite.return_value = mock_final_clip
        
        # Call the function
        result = process_video.add_b_roll("/path/to/input.mp4", "/path/to/output.mp4", self.mock_config)
        
        # Assertions
        self.assertTrue(result)
        mock_b_roll_clip.resize.assert_called_once_with(mock_main_clip.size)
        mock_b_roll_clip.set_opacity.assert_called_once_with(0.3)
        mock_final_clip.write_videofile.assert_called_once()

    @patch('os.path.exists')
    def test_add_watermark_no_file_specified(self, mock_exists):
        """Test handling when no watermark file is specified."""
        # Create a config with no watermark file
        config = {"video": {}}
        
        # Call the function
        result = process_video.add_watermark("/path/to/input.mp4", "/path/to/output.mp4", config)
        
        # Assertions
        self.assertFalse(result)
        mock_exists.assert_not_called()

    @patch('os.path.exists')
    def test_add_watermark_file_not_found(self, mock_exists):
        """Test handling when watermark file doesn't exist."""
        # Setup mocks
        mock_exists.return_value = False
        
        # Call the function
        result = process_video.add_watermark("/path/to/input.mp4", "/path/to/output.mp4", self.mock_config)
        
        # Assertions
        self.assertFalse(result)
        mock_exists.assert_called_once()

    @patch('os.path.exists')
    @patch('moviepy.editor.VideoFileClip')
    @patch('moviepy.editor.ImageClip')
    @patch('moviepy.editor.CompositeVideoClip')
    def test_add_watermark_success(self, mock_composite, mock_image_clip, mock_video_clip, mock_exists):
        """Test successful watermark addition."""
        # Setup mocks
        mock_exists.return_value = True
        
        mock_video = MagicMock()
        mock_video.w = 1080
        mock_video.h = 1080
        
        mock_watermark = MagicMock()
        mock_watermark.w = 100
        mock_watermark.h = 50
        
        mock_final_clip = MagicMock()
        
        mock_video_clip.return_value = mock_video
        mock_image_clip.return_value = mock_watermark
        mock_composite.return_value = mock_final_clip
        
        # Call the function
        result = process_video.add_watermark("/path/to/input.mp4", "/path/to/output.mp4", self.mock_config)
        
        # Assertions
        self.assertTrue(result)
        mock_watermark.set_opacity.assert_called_once_with(0.7)
        mock_watermark.resize.assert_called_once()
        mock_watermark.set_position.assert_called_once()
        mock_final_clip.write_videofile.assert_called_once()

    @patch('moviepy.editor.VideoFileClip')
    @patch('moviepy.editor.TextClip')
    @patch('moviepy.editor.CompositeVideoClip')
    def test_add_captions_to_video(self, mock_composite, mock_text_clip, mock_video_clip):
        """Test adding captions to video."""
        # This is a more complex function to test and would depend on the implementation
        # Mock implementation as needed based on actual code
        pass

    @patch('os.makedirs')
    @patch.object(process_video, 'find_prompt_data')
    @patch.object(process_video, 'create_seamless_loop')
    @patch.object(process_video, 'add_watermark')
    def test_video_handler_process_video(self, mock_add_watermark, mock_create_loop, mock_find_prompt, mock_makedirs):
        """Test the VideoHandler process_video method."""
        # This is a more complex method to test and would depend on the implementation
        # Mock implementation as needed based on actual code
        pass

if __name__ == '__main__':
    unittest.main() 