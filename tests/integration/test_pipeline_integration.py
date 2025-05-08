"""
Integration tests for the LoopForge pipeline.
"""
import os
import sys
import unittest
import argparse
import tempfile
import shutil
import json
import glob
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

    def _create_mock_subprocess_result(self, returncode=0, stdout="Success", stderr=""):
        mock_res = MagicMock()
        mock_res.returncode = returncode
        mock_res.stdout = stdout
        mock_res.stderr = stderr
        return mock_res

    def _mock_subprocess_side_effect(self, *args, **kwargs):
        cmd_list = args[0] # Command list is the first argument to subprocess.run
        cmd_str = " ".join(cmd_list) # For easier string searching

        if "generate_prompts.py" in cmd_str:
            prompt_content = {
                "prompt": "A test prompt from mock generation",
                "negative_prompt": "", "caption": "Mock caption",
                "hashtags": ["mock", "test"], "aspect_ratio": "1:1",
                "metadata": {"id": "mock_prompt_01"}
            }
            os.makedirs(self.prompts_dir, exist_ok=True)
            with open(os.path.join(self.prompts_dir, "mock_prompt_01.json"), "w") as f:
                json.dump(prompt_content, f)
            return self._create_mock_subprocess_result(stdout="Generated 1 prompt.")
        
        elif "local_renderer.py" in cmd_str:
            os.makedirs(self.rendered_dir, exist_ok=True)
            # Use a different variable name if glob was imported within the method scope previously
            prompt_files_list = glob.glob(os.path.join(self.prompts_dir, "*.json"))
            if not prompt_files_list:
                return self._create_mock_subprocess_result(returncode=1, stderr="No prompt files found by mock renderer.")
            for pf_path in prompt_files_list:
                video_filename = os.path.basename(pf_path).replace(".json", ".mp4")
                with open(os.path.join(self.rendered_dir, video_filename), "w") as f:
                    f.write("dummy video content for " + os.path.basename(pf_path))
            return self._create_mock_subprocess_result(stdout=f"Rendered {len(prompt_files_list)} clips.")

        elif "process_video.py" in cmd_str:
            os.makedirs(self.ready_dir, exist_ok=True)
            rendered_files_list = glob.glob(os.path.join(self.rendered_dir, "*.mp4"))
            if not rendered_files_list:
                return self._create_mock_subprocess_result(returncode=1, stderr="No rendered files found by mock processor.")
            for rf_path in rendered_files_list:
                processed_filename = os.path.basename(rf_path)
                with open(os.path.join(self.ready_dir, processed_filename), "w") as f:
                    f.write("dummy processed video content for " + os.path.basename(rf_path))
            return self._create_mock_subprocess_result(stdout=f"Processed {len(rendered_files_list)} videos.")

        elif "upload_video.py" in cmd_str:
            return self._create_mock_subprocess_result(stdout="Uploaded videos (mocked).")
        
        print(f"Warning: Unhandled mock subprocess call for command: {cmd_str}")
        return self._create_mock_subprocess_result(returncode=1, stderr=f"Unknown command for mock_subprocess_run: {cmd_str}")

    @patch('src.run_pipeline.load_config')
    @patch('src.run_pipeline.subprocess.run')
    @patch('src.run_pipeline.send_alert')
    @patch('sys.exit') # Add patch for sys.exit
    def test_pipeline_all_stages_dry_run(self, mock_sys_exit, mock_send_alert, mock_subprocess_run, mock_load_config):
        """Test that the pipeline runs all stages end-to-end in dry-run mode."""
        mock_load_config.return_value = self.test_config
        mock_subprocess_run.side_effect = self._mock_subprocess_side_effect
        
        cli_args = [
            'run_pipeline.py', '--all', '--dry-run',
            '--topic', self.args.topic,
            '--count', str(self.args.count),
            '--engine', self.args.engine,
            '--stage-timeout', str(self.args.stage_timeout) # Ensure this is used
        ]
        if self.args.workflow:
            cli_args.extend(['--workflow', self.args.workflow])
        if self.args.skip_captions:
            cli_args.append('--skip-captions')
        if self.args.b_roll:
            cli_args.append('--b-roll')
        if self.args.platform:
            cli_args.extend(['--platform'] + self.args.platform)

        mock_sys_exit.side_effect = lambda code: None

        with patch('sys.argv', cli_args):
            run_pipeline.main()
            
        mock_sys_exit.assert_called_once_with(0)
        self.assertEqual(mock_subprocess_run.call_count, 4, "Expected 4 stages to be called (generate, render, process, upload)")
        
        called_scripts = [call[0][0][1] for call in mock_subprocess_run.call_args_list]
        self.assertTrue(any("generate_prompts.py" in script for script in called_scripts))
        self.assertTrue(any("local_renderer.py" in script for script in called_scripts))
        self.assertTrue(any("process_video.py" in script for script in called_scripts))
        self.assertTrue(any("upload_video.py" in script for script in called_scripts))
        
        self.assertTrue(len(os.listdir(self.prompts_dir)) > 0, "Prompt file should be created by mock")
        self.assertTrue(len(os.listdir(self.rendered_dir)) > 0, "Rendered file should be created by mock")
        self.assertTrue(len(os.listdir(self.ready_dir)) > 0, "Processed file should be created by mock")
        mock_send_alert.assert_any_call("LoopForge: Pipeline Success", "All pipeline stages completed successfully.")

    @patch('src.run_pipeline.load_config')
    @patch('src.run_pipeline.subprocess.run')
    @patch('src.run_pipeline.send_alert')
    @patch('sys.exit') # Add patch for sys.exit
    def test_pipeline_happy_path_run_all_stages(self, mock_sys_exit, mock_send_alert, mock_subprocess_run, mock_load_config):
        """Test the pipeline happy path for all stages (non-dry-run)."""
        mock_load_config.return_value = self.test_config
        mock_subprocess_run.side_effect = self._mock_subprocess_side_effect

        cli_args = [
            'run_pipeline.py', '--all',
            '--topic', self.args.topic,
            '--count', str(self.args.count),
            '--engine', self.args.engine,
            '--stage-timeout', str(self.args.stage_timeout)
        ]
        if self.args.workflow:
            cli_args.extend(['--workflow', self.args.workflow])
        if self.args.skip_captions:
            cli_args.append('--skip-captions')
        if self.args.b_roll:
            cli_args.append('--b-roll')
        if self.args.platform:
            cli_args.extend(['--platform'] + self.args.platform)

        mock_sys_exit.side_effect = lambda code: None

        with patch('sys.argv', cli_args):
            run_pipeline.main()

        mock_sys_exit.assert_called_once_with(0)
        self.assertEqual(mock_subprocess_run.call_count, 4)
        self.assertTrue(len(os.listdir(self.prompts_dir)) > 0)
        self.assertTrue(len(os.listdir(self.rendered_dir)) > 0)
        self.assertTrue(len(os.listdir(self.ready_dir)) > 0)
        mock_send_alert.assert_any_call("LoopForge: Pipeline Success", "All pipeline stages completed successfully.")

if __name__ == '__main__':
    unittest.main() 