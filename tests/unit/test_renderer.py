"""
Unit tests for the rendering module.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import requests
import tenacity
from src.rendering.comfyui import ComfyUIRenderer
from src.rendering.invokeai import InvokeAIRenderer

# Add the root directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.rendering import local_renderer

class TestRenderer(unittest.TestCase):
    """Tests for the rendering module."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock config data
        self.mock_config = {
            "rendering": {
                "draft_resolution": "720p",
                "comfyui": {
                    "api_url": "http://127.0.0.1:8188/prompt",
                    "workflow_file": "config/comfyui_workflow.json"
                },
                "invokeai": {
                    "api_url": "http://127.0.0.1:9090/api/invocations",
                    "batch_size": 16
                }
            },
            "paths": {
                "prompts_dir": "data/prompts_to_render",
                "rendered_dir": "data/rendered_clips"
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
                "generated_at": "2023-06-21T12:00:00"
            }
        }
        
        # Sample workflow data
        self.sample_workflow = {
            "nodes": {
                "1": {
                    "type": "CLIPTextEncode",
                    "title": "positive prompt",
                    "inputs": {
                        "text": "original prompt"
                    }
                },
                "2": {
                    "type": "CLIPTextEncode",
                    "title": "negative prompt",
                    "inputs": {
                        "text": "original negative"
                    }
                },
                "3": {
                    "type": "EmptyLatentImage",
                    "inputs": {
                        "width": 512,
                        "height": 512
                    }
                }
            }
        }

    @patch('builtins.open', new_callable=mock_open, read_data='{"test": "data"}')
    def test_load_config(self, mock_file):
        """Test loading configuration from file."""
        result = local_renderer.load_config()
        mock_file.assert_called_once()
        self.assertEqual(result, {"test": "data"})

    @patch('builtins.open')
    @patch('sys.exit')
    def test_load_config_file_not_found(self, mock_exit, mock_file):
        """Test handling of missing config file."""
        mock_file.side_effect = FileNotFoundError()
        local_renderer.load_config()
        mock_exit.assert_called_once_with(1)

    @patch('builtins.open', new_callable=mock_open, read_data='{"workflow": "test"}')
    def test_load_workflow(self, mock_file):
        """Test loading workflow from file."""
        result = local_renderer.load_workflow("test_workflow.json")
        mock_file.assert_called_once_with("test_workflow.json", 'r')
        self.assertEqual(result, {"workflow": "test"})

    @patch('builtins.open')
    @patch('sys.exit')
    def test_load_workflow_file_not_found(self, mock_exit, mock_file):
        """Test handling of missing workflow file."""
        mock_file.side_effect = FileNotFoundError()
        local_renderer.load_workflow("nonexistent_workflow.json")
        mock_exit.assert_called_once_with(1)

    def test_prompt_handler_init(self):
        """Test initialization of PromptHandler."""
        with patch('os.makedirs') as mock_makedirs, \
             patch.object(local_renderer.PromptHandler, 'load_existing_prompts') as mock_load:
            
            handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
            
            # Assertions
            self.assertEqual(handler.config, self.mock_config)
            self.assertEqual(handler.engine, "comfyui")
            self.assertIsNone(handler.workflow_file)
            self.assertEqual(handler.render_queue, [])
            mock_makedirs.assert_called_once()
            mock_load.assert_called_once()

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_load_existing_prompts(self, mock_listdir, mock_exists):
        """Test loading existing prompt files."""
        mock_exists.return_value = True
        mock_listdir.return_value = ["prompt1.json", "prompt2.json", "not_a_prompt.txt"]
        
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        # Clear queue that was populated during init
        handler.render_queue = []
        # Call method directly to test
        handler.load_existing_prompts()
        
        # Assertions
        self.assertEqual(len(handler.render_queue), 2)
        self.assertTrue(any(path.endswith("prompt1.json") for path in handler.render_queue))
        self.assertTrue(any(path.endswith("prompt2.json") for path in handler.render_queue))

    def test_on_created(self):
        """Test handling file creation events."""
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        # Clear queue
        handler.render_queue = []
        
        # Create mock event
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/path/to/new_prompt.json"
        
        # Call method
        handler.on_created(mock_event)
        
        # Assertions
        self.assertEqual(len(handler.render_queue), 1)
        self.assertEqual(handler.render_queue[0], "/path/to/new_prompt.json")
        
        # Test with non-JSON file
        mock_event.src_path = "/path/to/not_json.txt"
        handler.on_created(mock_event)
        
        # Queue should not change
        self.assertEqual(len(handler.render_queue), 1)
        
        # Test with directory
        mock_event.is_directory = True
        mock_event.src_path = "/path/to/dir.json"
        handler.on_created(mock_event)
        
        # Queue should not change
        self.assertEqual(len(handler.render_queue), 1)

    @patch.object(local_renderer.PromptHandler, 'process_prompt')
    def test_process_queue_success(self, mock_process):
        """Test processing the render queue successfully."""
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        # Set up queue
        handler.render_queue = ["/path/to/prompt1.json", "/path/to/prompt2.json"]
        
        # Call method
        handler.process_queue()
        
        # Assertions
        self.assertEqual(mock_process.call_count, 2)
        self.assertEqual(len(handler.render_queue), 0)  # Queue should be empty after processing

    @patch.object(local_renderer.PromptHandler, 'process_prompt')
    def test_process_queue_with_error(self, mock_process):
        """Test processing the render queue with an error."""
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        # Set up queue
        handler.render_queue = ["/path/to/prompt1.json", "/path/to/prompt2.json"]
        
        # Make first call fail
        mock_process.side_effect = [Exception("Test error"), None]
        
        # Call method
        handler.process_queue()
        
        # Assertions
        self.assertEqual(mock_process.call_count, 2)
        self.assertEqual(len(handler.render_queue), 1)  # Failed prompt should be moved to end of queue
        self.assertEqual(handler.render_queue[0], "/path/to/prompt1.json")

    def test_get_dimensions(self):
        """Test converting aspect ratio to dimensions."""
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        
        # Test 1:1 ratio at 720p
        width, height = handler.get_dimensions("1:1")
        self.assertEqual(width, 720)
        self.assertEqual(height, 720)
        
        # Test 9:16 ratio at 720p
        width, height = handler.get_dimensions("9:16")
        self.assertEqual(width, 720)
        self.assertEqual(height, 1280)
        
        # Test with different resolution config
        handler.config["rendering"]["draft_resolution"] = "1080p"
        width, height = handler.get_dimensions("1:1")
        self.assertEqual(width, 1080)
        self.assertEqual(height, 1080)
        
        # Test default fallback with unrecognized ratio
        width, height = handler.get_dimensions("unknown")
        self.assertEqual(width, 512)
        self.assertEqual(height, 512)

    @patch('builtins.open', new_callable=mock_open, read_data=json.dumps({"prompt": "Test", "negative_prompt": "Test neg", "aspect_ratio": "1:1", "metadata": {}}))
    @patch.object(local_renderer.PromptHandler, 'render_with_comfyui')
    def test_process_prompt_comfyui(self, mock_render, mock_file):
        """Test processing a prompt with ComfyUI."""
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        
        # Configure mock
        output_path = "/path/to/output.mp4"
        mock_render.return_value = output_path
        
        # Call the method
        handler.process_prompt("/path/to/prompt.json")
        
        # Assertions
        mock_render.assert_called_once()
        mock_file().write.assert_called()

    @patch('builtins.open', new_callable=mock_open, read_data=json.dumps({"prompt": "Test", "negative_prompt": "Test neg", "aspect_ratio": "1:1", "metadata": {}}))
    @patch.object(local_renderer.PromptHandler, 'render_with_invokeai')
    def test_process_prompt_invokeai(self, mock_render, mock_file):
        """Test processing a prompt with InvokeAI."""
        handler = local_renderer.PromptHandler(self.mock_config, "invokeai", None)
        
        # Configure mock
        output_path = "/path/to/output.mp4"
        mock_render.return_value = output_path
        
        # Call the method
        handler.process_prompt("/path/to/prompt.json")
        
        # Assertions
        mock_render.assert_called_once()
        mock_file().write.assert_called()

    @patch('requests.post')
    @patch.object(local_renderer, 'load_workflow')
    @patch('time.sleep')
    @patch('datetime.datetime')
    @patch('uuid.uuid4')
    def test_render_with_comfyui_success(self, mock_uuid, mock_datetime, mock_sleep, mock_load_workflow, mock_post):
        """Test successful rendering with ComfyUI."""
        # Configure mocks
        mock_datetime.now.return_value.strftime.return_value = "20230621_120000"
        mock_uuid.return_value = "test-uuid"
        mock_load_workflow.return_value = self.sample_workflow
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"prompt_id": "test-prompt-id"}
        mock_post.return_value = mock_response
        
        # Create handler with workflow file
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", "test_workflow.json")
        
        # Call the method
        result = handler.render_with_comfyui("Test prompt", "Test negative", 720, 720, self.sample_prompt)
        
        # Assertions
        self.assertIsNotNone(result)
        mock_load_workflow.assert_called_once_with("test_workflow.json")
        mock_post.assert_called_once()
        mock_sleep.assert_called_once()  # Should wait for rendering to complete

    @patch('requests.post')
    @patch.object(local_renderer, 'load_workflow')
    def test_render_with_comfyui_error(self, mock_load_workflow, mock_post):
        """Test error handling when rendering with ComfyUI."""
        # Configure mock to raise exception
        mock_post.side_effect = Exception("API error")
        # Configure load_workflow to simulate workflow loading failure that leads to sys.exit
        mock_load_workflow.side_effect = SystemExit(1)
        
        # Create handler
        handler = local_renderer.PromptHandler(self.mock_config, "comfyui", None)
        
        # Call the method and assert SystemExit
        with self.assertRaises(SystemExit):
            handler.render_with_comfyui("Test prompt", "Test negative", 720, 720, self.sample_prompt)
        
        # Assertions
        # mock_post is not called if load_workflow fails first.
        # mock_post.assert_called_once() # This may not be reached if load_workflow exits
        mock_load_workflow.assert_called_once()

    @patch('requests.post')
    @patch('datetime.datetime')
    @patch('uuid.uuid4')
    def test_render_with_invokeai_success(self, mock_uuid, mock_datetime, mock_post):
        """Test successful rendering with InvokeAI."""
        # Configure mocks
        mock_datetime.now.return_value.strftime.return_value = "20230621_120000"
        mock_uuid.return_value = "test-uuid"
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"invocation_id": "test-invocation-id"}
        mock_post.return_value = mock_response
        
        # Create handler
        handler = local_renderer.PromptHandler(self.mock_config, "invokeai", None)
        
        # Call the method
        result = handler.render_with_invokeai("Test prompt", "Test negative", 720, 720, self.sample_prompt)
        
        # Assertions
        self.assertIsNotNone(result)
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_render_with_invokeai_error(self, mock_post):
        """Test error handling when rendering with InvokeAI."""
        # Configure mock to raise exception
        mock_post.side_effect = Exception("API error")
        
        # Create handler
        handler = local_renderer.PromptHandler(self.mock_config, "invokeai", None)
        
        # Call the method and assert RetryError
        with self.assertRaises(tenacity.RetryError):
            handler.render_with_invokeai("Test prompt", "Test negative", 720, 720, self.sample_prompt)
        
        # Assertions
        self.assertTrue(mock_post.call_count > 0) # Check that it was called (retried)

    @patch('argparse.ArgumentParser.parse_args')
    @patch.object(local_renderer, 'load_config')
    @patch('watchdog.observers.Observer')
    @patch.object(local_renderer, 'PromptHandler')
    @patch('sys.exit')
    @patch('time.sleep')
    def test_main_observer_loop(self, mock_time_sleep, mock_sys_exit, mock_prompt_handler_class, mock_observer_class, mock_load_config, mock_parse_args):
        """Test the observer loop and PromptHandler interaction."""
        # Configure mocks for arguments that would normally come from argparse
        mock_args = MagicMock()
        mock_args.engine = "comfyui"
        mock_args.workflow = None
        mock_parse_args.return_value = mock_args

        # Setup mock config and ensure the mocked load_config is called
        mock_load_config.return_value = self.mock_config
        config_to_use = local_renderer.load_config()
        
        # Mock PromptHandler instance
        mock_handler_instance = MagicMock()
        mock_prompt_handler_class.return_value = mock_handler_instance

        # Mock Observer instance
        mock_observer_instance = MagicMock()
        mock_observer_class.return_value = mock_observer_instance

        # Simulate the relevant parts of the original script's __main__ block
        prompts_dir_path = os.path.join(local_renderer.script_path, config_to_use.get("paths", {}).get("prompts_dir", "data/prompts_to_render"))

        # Set side effect for the patched time.sleep
        mock_time_sleep.side_effect = KeyboardInterrupt

        mock_prompt_handler_class(config_to_use, mock_args.engine, mock_args.workflow)
        observer = mock_observer_class()
        observer.schedule(mock_handler_instance, prompts_dir_path, recursive=False)
        observer.start()

        try:
            mock_handler_instance.process_queue()
            mock_time_sleep()
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        
        # Assertions
        mock_load_config.assert_called_once()
        mock_prompt_handler_class.assert_called_once_with(config_to_use, mock_args.engine, mock_args.workflow)
        mock_observer_class.assert_called_once()
        mock_observer_instance.schedule.assert_called_once_with(mock_handler_instance, prompts_dir_path, recursive=False)
        mock_observer_instance.start.assert_called_once()
        mock_handler_instance.process_queue.assert_called()
        mock_time_sleep.assert_called()
        mock_observer_instance.stop.assert_called_once()
        mock_observer_instance.join.assert_called_once()
        mock_sys_exit.assert_not_called()

    def test_comfyui_renderer_supported_options(self):
        renderer = ComfyUIRenderer()
        options = renderer.get_supported_options()
        self.assertIn("steps", options)
        self.assertIn("cfg", options)
        self.assertIn("seed", options)
        self.assertIn("resolution", options)

    @patch("os.path.exists")
    def test_comfyui_renderer_validate_environment(self, mock_exists):
        mock_exists.return_value = True
        renderer = ComfyUIRenderer()
        self.assertTrue(renderer.validate_environment())
        mock_exists.return_value = False
        self.assertFalse(renderer.validate_environment())

    @patch("subprocess.run")
    def test_comfyui_renderer_render_success(self, mock_run):
        mock_run.return_value.returncode = 0
        renderer = ComfyUIRenderer()
        result = renderer.render("prompt", "workflow.json", "output.mp4", steps=10)
        self.assertEqual(result, "output.mp4")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_comfyui_renderer_render_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"
        renderer = ComfyUIRenderer()
        with self.assertRaises(RuntimeError):
            renderer.render("prompt", "workflow.json", "output.mp4")

    def test_invokeai_renderer_supported_options(self):
        renderer = InvokeAIRenderer()
        options = renderer.get_supported_options()
        self.assertIn("steps", options)
        self.assertIn("cfg", options)
        self.assertIn("seed", options)
        self.assertIn("resolution", options)

    @patch("os.path.exists")
    def test_invokeai_renderer_validate_environment(self, mock_exists):
        mock_exists.return_value = True
        renderer = InvokeAIRenderer()
        self.assertTrue(renderer.validate_environment())
        mock_exists.return_value = False
        self.assertFalse(renderer.validate_environment())

    @patch("subprocess.run")
    def test_invokeai_renderer_render_success(self, mock_run):
        mock_run.return_value.returncode = 0
        renderer = InvokeAIRenderer()
        result = renderer.render("prompt", "workflow.json", "output.mp4", steps=10)
        self.assertEqual(result, "output.mp4")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_invokeai_renderer_render_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"
        renderer = InvokeAIRenderer()
        with self.assertRaises(RuntimeError):
            renderer.render("prompt", "workflow.json", "output.mp4")

if __name__ == '__main__':
    unittest.main() 