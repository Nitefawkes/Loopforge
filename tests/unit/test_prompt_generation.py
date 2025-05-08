"""
Unit tests for the prompt generation module.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Add the root directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.prompt_generation import generate_prompts

class TestPromptGeneration(unittest.TestCase):
    """Tests for the prompt_generation module."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock config data
        self.mock_config = {
            "api_keys": {
                "openai": "test-openai-key",
                "anthropic": "test-anthropic-key"
            },
            "prompt_generation": {
                "model": "gpt-4",
                "anthropic_model": "claude-3-opus-20240229",
                "temperature": 0.7,
                "max_tokens": 500,
                "default_niche": "productivity"
            },
            "paths": {
                "prompts_dir": "data/prompts_to_render"
            }
        }
        
        # Sample generated prompts
        self.sample_prompts = [
            {
                "prompt": "Test prompt 1",
                "negative_prompt": "Test negative prompt 1",
                "caption": "Test caption 1",
                "hashtags": ["test", "ai", "video"],
                "aspect_ratio": "1:1"
            },
            {
                "prompt": "Test prompt 2",
                "negative_prompt": "Test negative prompt 2",
                "caption": "Test caption 2",
                "hashtags": ["looping", "content", "minimal"],
                "aspect_ratio": "9:16"
            }
        ]

    @patch('builtins.open', new_callable=mock_open, read_data='{"test": "data"}')
    def test_load_config(self, mock_file):
        """Test loading configuration from file."""
        result = generate_prompts.load_config()
        mock_file.assert_called_once()
        self.assertEqual(result, {"test": "data"})

    @patch('builtins.open')
    @patch('sys.exit')
    def test_load_config_file_not_found(self, mock_exit, mock_file):
        """Test handling of missing config file."""
        mock_file.side_effect = FileNotFoundError()
        generate_prompts.load_config()
        mock_exit.assert_called_once_with(1)

    def test_setup_api_clients(self):
        """Test setting up API clients with valid configuration."""
        with patch('src.prompt_generation.generate_prompts.openai.OpenAI') as mock_openai, \
             patch('src.prompt_generation.generate_prompts.Anthropic') as mock_anthropic:
            
            # Create mock instances
            mock_openai_instance = MagicMock()
            mock_anthropic_instance = MagicMock()
            mock_openai.return_value = mock_openai_instance
            mock_anthropic.return_value = mock_anthropic_instance
            
            # Call function
            openai_client, anthropic_client = generate_prompts.setup_api_clients(self.mock_config)
            
            # Assertions
            mock_openai.assert_called_once_with(api_key=self.mock_config["api_keys"]["openai"])
            mock_anthropic.assert_called_once_with(api_key=self.mock_config["api_keys"]["anthropic"])
            self.assertEqual(openai_client, mock_openai_instance)
            self.assertEqual(anthropic_client, mock_anthropic_instance)

    def test_setup_api_clients_empty_config(self):
        """Test API client setup with empty configuration."""
        empty_config = {}
        openai_client, anthropic_client = generate_prompts.setup_api_clients(empty_config)
        self.assertIsNone(openai_client)
        self.assertIsNone(anthropic_client)

    def test_validate_prompts_success(self):
        """Test successful validation of properly structured prompts."""
        # Use sample prompts from setUp which should be valid
        try:
            result = generate_prompts.validate_prompts(self.sample_prompts)
            self.assertTrue(result)
        except generate_prompts.ValidationError:
            self.fail("validate_prompts raised ValidationError unexpectedly!")

    def test_validate_prompts_invalid_structure(self):
        """Test validation with invalid prompt structures."""
        # Test with non-list input
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts("not a list")
            
        # Test with empty list
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts([])
            
        # Test with non-dict item
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts(["not a dict"])
            
        # Test with missing required field
        invalid_prompt = {
            "prompt": "Test prompt",
            # missing negative_prompt
            "caption": "Test caption",
            "hashtags": ["test"],
            "aspect_ratio": "1:1"
        }
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts([invalid_prompt])
            
        # Test with invalid aspect ratio
        invalid_aspect_ratio = {
            "prompt": "Test prompt",
            "negative_prompt": "Test negative",
            "caption": "Test caption",
            "hashtags": ["test"],
            "aspect_ratio": "16:9"  # Invalid, not 1:1 or 9:16
        }
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts([invalid_aspect_ratio])
            
        # Test with empty prompt field
        empty_prompt = {
            "prompt": "",  # Empty
            "negative_prompt": "Test negative",
            "caption": "Test caption",
            "hashtags": ["test"],
            "aspect_ratio": "1:1"
        }
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts([empty_prompt])
            
        # Test with invalid hashtags
        invalid_hashtags = {
            "prompt": "Test prompt",
            "negative_prompt": "Test negative",
            "caption": "Test caption",
            "hashtags": [],  # Empty array
            "aspect_ratio": "1:1"
        }
        with self.assertRaises(generate_prompts.ValidationError):
            generate_prompts.validate_prompts([invalid_hashtags])

    @patch('openai.OpenAI')
    def test_generate_with_openai_success(self, mock_openai):
        """Test successful prompt generation with OpenAI."""
        # Mock instance and response
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Configure the mock response
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(self.sample_prompts)
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Call the function
        result = generate_prompts.generate_with_openai(mock_client, "test topic", 2, self.mock_config)
        
        # Assertions
        mock_client.chat.completions.create.assert_called_once()
        self.assertEqual(result, self.sample_prompts)

    @patch('openai.OpenAI')
    def test_generate_with_openai_error(self, mock_openai):
        """Test error handling during OpenAI prompt generation."""
        # Mock instance and exception
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")
        
        # Call the function and check result
        result = generate_prompts.generate_with_openai(mock_client, "test topic", 2, self.mock_config)
        self.assertIsNone(result)

    @patch('anthropic.Anthropic')
    def test_generate_with_anthropic_success(self, mock_anthropic):
        """Test successful prompt generation with Anthropic's Claude."""
        # Mock instance and response
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        # Configure the mock response
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps(self.sample_prompts)
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response
        
        # Call the function
        result = generate_prompts.generate_with_anthropic(mock_client, "test topic", 2, self.mock_config)
        
        # Assertions
        mock_client.messages.create.assert_called_once()
        self.assertEqual(result, self.sample_prompts)

    @patch('anthropic.Anthropic')
    def test_generate_with_anthropic_error(self, mock_anthropic):
        """Test error handling during Anthropic prompt generation."""
        # Mock instance and exception
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")
        
        # Call the function and check result
        result = generate_prompts.generate_with_anthropic(mock_client, "test topic", 2, self.mock_config)
        self.assertIsNone(result)

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('uuid.uuid4')
    @patch('datetime.datetime')
    def test_save_prompts(self, mock_datetime, mock_uuid4, mock_open, mock_makedirs):
        """Test saving prompts to files."""
        # Configure mocks
        mock_datetime.now.return_value.strftime.return_value = "20230621_120000"
        mock_datetime.now.return_value.isoformat.return_value = "2023-06-21T12:00:00"
        mock_uuid4.return_value = "test-uuid"
        
        # Call function
        result = generate_prompts.save_prompts(self.sample_prompts, "test_output_dir", "test topic")
        
        # Assertions
        mock_makedirs.assert_called_once_with("test_output_dir", exist_ok=True)
        self.assertEqual(mock_open.call_count, 2)  # Once for each prompt
        
        # Skip checking the write calls as json.dump makes multiple write calls
        # Instead, just check that we got the expected result
        self.assertEqual(len(result), 2)  # Should return 2 saved file paths

    @patch('src.prompt_generation.generate_prompts.load_config')
    @patch('src.prompt_generation.generate_prompts.setup_api_clients')
    @patch('src.prompt_generation.generate_prompts.generate_with_anthropic')
    @patch('src.prompt_generation.generate_prompts.save_prompts')
    def test_main_with_anthropic(self, mock_save, mock_generate_anthropic, mock_setup, mock_load_config):
        """Test the main function using Anthropic for generation."""
        # Configure mocks
        mock_load_config.return_value = self.mock_config
        mock_anthropic = MagicMock()
        mock_openai = MagicMock()
        mock_setup.return_value = (mock_openai, mock_anthropic)
        mock_generate_anthropic.return_value = self.sample_prompts
        
        # Mock command line arguments
        with patch('sys.argv', ['generate_prompts.py', '--topic', 'test topic', '--count', '2']):
            with patch('argparse.ArgumentParser.parse_args') as mock_args:
                # Configure mock arguments
                mock_args.return_value.topic = "test topic"
                mock_args.return_value.niche = None
                mock_args.return_value.count = 2
                
                # Call main function
                generate_prompts.main()
                
                # Assertions
                mock_load_config.assert_called_once()
                mock_setup.assert_called_once_with(self.mock_config)
                mock_generate_anthropic.assert_called_once_with(mock_anthropic, "test topic", 2, self.mock_config)
                mock_save.assert_called_once()

    @patch('src.prompt_generation.generate_prompts.load_config')
    @patch('src.prompt_generation.generate_prompts.setup_api_clients')
    @patch('src.prompt_generation.generate_prompts.generate_with_anthropic')
    @patch('src.prompt_generation.generate_prompts.generate_with_openai')
    @patch('src.prompt_generation.generate_prompts.save_prompts')
    def test_main_fallback_to_openai(self, mock_save, mock_generate_openai, mock_generate_anthropic, 
                                      mock_setup, mock_load_config):
        """Test fallback to OpenAI when Anthropic fails."""
        # Configure mocks
        mock_load_config.return_value = self.mock_config
        mock_anthropic = MagicMock()
        mock_openai = MagicMock()
        mock_setup.return_value = (mock_openai, mock_anthropic)
        mock_generate_anthropic.return_value = None  # Anthropic fails
        mock_generate_openai.return_value = self.sample_prompts  # OpenAI succeeds
        
        # Mock command line arguments
        with patch('sys.argv', ['generate_prompts.py', '--topic', 'test topic', '--count', '2']):
            with patch('argparse.ArgumentParser.parse_args') as mock_args:
                # Configure mock arguments
                mock_args.return_value.topic = "test topic"
                mock_args.return_value.niche = None
                mock_args.return_value.count = 2
                
                # Call main function
                generate_prompts.main()
                
                # Assertions
                mock_generate_anthropic.assert_called_once()
                mock_generate_openai.assert_called_once()
                mock_save.assert_called_once()

if __name__ == '__main__':
    unittest.main() 