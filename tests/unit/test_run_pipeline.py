"""
Unit tests for the pipeline orchestrator.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add the root directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import the module under test
from src import run_pipeline

class TestRunPipeline(unittest.TestCase):
    """Tests for the run_pipeline.py module."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock arguments
        self.args = MagicMock()
        self.args.topic = "test_topic"
        self.args.count = 3
        self.args.engine = "comfyui"
        self.args.workflow = None
        self.args.skip_captions = False
        self.args.b_roll = False
        self.args.platform = ["youtube"]
        self.args.dry_run = True
        self.args.timeout = None
        self.args.stage_timeout = None

        # Mock config
        self.config = {
            "paths": {
                "prompts_dir": "data/prompts_to_render",
                "rendered_dir": "data/rendered_clips",
                "final_dir": "data/ready_to_post",
            }
        }

    @patch('subprocess.run')
    @patch('glob.glob')
    def test_run_generate_stage(self, mock_glob, mock_subprocess_run):
        """Test the run_generate_stage function."""
        # Configure mocks
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Generated prompts"
        mock_subprocess_result.stderr = ""
        mock_subprocess_run.return_value = mock_subprocess_result
        
        # Mock finding prompt files
        mock_glob.return_value = ["data/prompts_to_render/prompt1.json", "data/prompts_to_render/prompt2.json"]
        
        # Call the function
        result = run_pipeline.run_generate_stage(self.args, self.config)
        
        # Assertions
        self.assertTrue(result)
        mock_subprocess_run.assert_called_once()
        mock_glob.assert_called_once()

    @patch('subprocess.run')
    @patch('glob.glob')
    def test_run_render_stage(self, mock_glob, mock_subprocess_run):
        """Test the run_render_stage function."""
        # Configure mocks
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Rendered videos"
        mock_subprocess_result.stderr = ""
        mock_subprocess_run.return_value = mock_subprocess_result
        
        # Mock finding rendered files
        mock_glob.return_value = ["data/rendered_clips/video1.mp4", "data/rendered_clips/video2.mp4"]
        
        # Call the function
        result = run_pipeline.run_render_stage(self.args, self.config)
        
        # Assertions
        self.assertTrue(result)
        mock_subprocess_run.assert_called_once()
        mock_glob.assert_called_once()

    @patch('subprocess.run')
    @patch('glob.glob')
    def test_run_process_stage(self, mock_glob, mock_subprocess_run):
        """Test the run_process_stage function."""
        # Configure mocks
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Processed videos"
        mock_subprocess_result.stderr = ""
        mock_subprocess_run.return_value = mock_subprocess_result
        
        # Mock finding processed files
        mock_glob.return_value = ["data/ready_to_post/video1.mp4", "data/ready_to_post/video2.mp4"]
        
        # Call the function
        result = run_pipeline.run_process_stage(self.args, self.config)
        
        # Assertions
        self.assertTrue(result)
        mock_subprocess_run.assert_called_once()
        mock_glob.assert_called_once()

    @patch('subprocess.run')
    def test_run_upload_stage(self, mock_subprocess_run):
        """Test the run_upload_stage function."""
        # Configure mocks
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Uploaded videos"
        mock_subprocess_result.stderr = ""
        mock_subprocess_run.return_value = mock_subprocess_result
        
        # Call the function
        result = run_pipeline.run_upload_stage(self.args, self.config)
        
        # Assertions
        self.assertTrue(result)
        mock_subprocess_run.assert_called_once()

    @patch('src.run_pipeline.run_generate_stage')
    @patch('src.run_pipeline.run_render_stage')
    @patch('src.run_pipeline.run_process_stage')
    @patch('src.run_pipeline.run_upload_stage')
    @patch('src.run_pipeline.exit')
    def test_run_all_stages_success(self, mock_exit, mock_upload, mock_process, mock_render, mock_generate):
        """Test the run_all_stages function with all stages succeeding."""
        # Configure mocks for success
        mock_generate.return_value = True
        mock_render.return_value = True
        mock_process.return_value = True
        mock_upload.return_value = True
        
        # Call the function
        run_pipeline.run_all_stages(self.args, self.config)
        
        # Assertions
        mock_generate.assert_called_once()
        mock_render.assert_called_once()
        mock_process.assert_called_once()
        mock_upload.assert_called_once()
        mock_exit.assert_not_called()  # Should not exit on success

    @patch('src.run_pipeline.run_generate_stage')
    @patch('src.run_pipeline.exit')
    def test_run_all_stages_generate_failure(self, mock_exit, mock_generate):
        """Test the run_all_stages function with generate stage failing."""
        # Configure mock to fail
        mock_generate.return_value = False
        
        # Call the function
        run_pipeline.run_all_stages(self.args, self.config)
        
        # Assertions
        mock_generate.assert_called_once()
        # We just check that exit was called at least once with code 1
        mock_exit.assert_called_with(1)

if __name__ == '__main__':
    unittest.main() 