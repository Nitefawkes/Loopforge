"""
Integration tests for the LoopForge pipeline.
"""
import os
import sys
import unittest
import argparse
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add the root directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import the module under test
from src import run_pipeline

class TestPipelineIntegration(unittest.TestCase):
    """Integration tests for the pipeline."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        # Create temporary directory structure
        self.test_dir = tempfile.mkdtemp()
        self.prompts_dir = os.path.join(self.test_dir, "prompts_to_render")
        self.rendered_dir = os.path.join(self.test_dir, "rendered_clips")
        self.ready_dir = os.path.join(self.test_dir, "ready_to_post")
        
        os.makedirs(self.prompts_dir, exist_ok=True)
        os.makedirs(self.rendered_dir, exist_ok=True)
        os.makedirs(self.ready_dir, exist_ok=True)
        
        # Test config
        self.test_config = {
            "paths": {
                "prompts_dir": self.prompts_dir,
                "rendered_dir": self.rendered_dir,
                "final_dir": self.ready_dir
            }
        }
        
        # Mock args
        self.args = argparse.Namespace(
            topic="test_integration",
            count=1,
            engine="comfyui",
            workflow=None,
            skip_captions=True,
            b_roll=False,
            platform=["youtube"],
            dry_run=True,
            timeout=None,
            stage_timeout=10  # Short timeout for tests
        )

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.test_dir)

    @patch('src.run_pipeline.load_config')
    @patch('src.run_pipeline.subprocess.run')
    @unittest.skip("Integration test that requires specific environment setup")
    def test_pipeline_dry_run(self, mock_subprocess_run, mock_load_config):
        """Test that the pipeline can run end-to-end in dry-run mode."""
        # Configure mocks
        mock_load_config.return_value = self.test_config
        
        # Mock successful subprocess runs
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result
        
        # Create a test prompt file
        test_prompt = {
            "prompt": "Test prompt",
            "negative_prompt": "",
            "caption": "Test Caption",
            "hashtags": ["test", "loopforge"],
            "aspect_ratio": "1:1"
        }
        
        import json
        with open(os.path.join(self.prompts_dir, "test_prompt.json"), "w") as f:
            json.dump(test_prompt, f)
        
        # Run the pipeline with all stages
        with patch('sys.argv', ['run_pipeline.py', '--all', '--dry-run']):
            # Normally would call main(), but we'll call run_all_stages directly
            # with our prepared test config and args
            result = run_pipeline.run_all_stages(self.args, self.test_config)
            
            # Assert pipeline completed successfully
            self.assertTrue(result)
            
            # Verify subprocess.run was called for each stage
            self.assertEqual(mock_subprocess_run.call_count, 4)  # Once for each stage

if __name__ == '__main__':
    unittest.main() 