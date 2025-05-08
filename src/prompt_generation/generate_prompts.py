#!/usr/bin/env python3
"""
Prompt Generator Script for LoopForge

This script generates AnimateDiff prompts for video loops based on a given topic
or niche. It uses OpenAI or Claude API to create detailed prompts, captions, and
hashtags for each video concept.

Usage:
    python generate_prompts.py --topic "minimalist lifestyle" --count 5
    python generate_prompts.py --niche "productivity" --count 10
"""

import os
import json
import time
import argparse
import random
from datetime import datetime
import openai
from anthropic import Anthropic
import sys
import uuid
from pathlib import Path
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Add root to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import notifications if available
try:
    from src.notifications import send_alert
    notifications_available = True
except ImportError:
    notifications_available = False
    logger.warning("Notifications module not available. Alerts will not be sent.")

class ConfigError(Exception):
    """Exception raised for configuration issues."""
    pass

class APIError(Exception):
    """Exception raised for API-related issues."""
    pass

class ValidationError(Exception):
    """Exception raised for validation issues."""
    pass

def load_config():
    """
    Load configuration from config.json file
    
    Returns:
        dict: The configuration dictionary
    
    Raises:
        ConfigError: If the config file is missing or invalid
    """
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info("Configuration loaded successfully")
            return config
    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        logger.error("Please copy config.example.json to config.json and add your API keys")
        if notifications_available:
            send_alert("LoopForge: Configuration Error", error_msg)
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in config file: {e}"
        logger.error(error_msg)
        if notifications_available:
            send_alert("LoopForge: Configuration Error", error_msg)
        sys.exit(1)

def setup_api_clients(config):
    """
    Setup API clients for OpenAI and Anthropic
    
    Args:
        config (dict): Configuration dictionary
    
    Returns:
        tuple: (openai_client, anthropic_client) - API clients
    
    Raises:
        ConfigError: If API keys are missing or invalid
    """
    openai_client = None
    anthropic_client = None
    
    try:
        if "api_keys" in config:
            if "openai" in config["api_keys"] and config["api_keys"]["openai"]:
                openai.api_key = config["api_keys"]["openai"]
                openai_client = openai.OpenAI(api_key=config["api_keys"]["openai"])
                logger.info("OpenAI client initialized")
            else:
                logger.warning("OpenAI API key not found or empty in config")
            
            if "anthropic" in config["api_keys"] and config["api_keys"]["anthropic"]:
                anthropic_client = Anthropic(api_key=config["api_keys"]["anthropic"])
                logger.info("Anthropic client initialized")
            else:
                logger.warning("Anthropic API key not found or empty in config")
        else:
            logger.warning("No API keys section found in config")
        
        if not openai_client and not anthropic_client:
            logger.error("No valid API clients could be initialized")
            raise ConfigError("No valid API keys found in configuration")
    except Exception as e:
        logger.error(f"Error setting up API clients: {e}")
        if notifications_available:
            send_alert("LoopForge: API Setup Error", str(e))
    
    return openai_client, anthropic_client

def validate_prompts(prompts):
    """
    Validate the structure and content of generated prompts
    
    Args:
        prompts (list): List of prompt dictionaries
    
    Returns:
        bool: True if prompts are valid, False otherwise
    
    Raises:
        ValidationError: If prompts are invalid
    """
    if not prompts or not isinstance(prompts, list):
        raise ValidationError("Generated prompts must be a non-empty list")
    
    required_fields = ["prompt", "negative_prompt", "caption", "hashtags", "aspect_ratio"]
    
    for i, prompt in enumerate(prompts):
        # Check prompt is a dictionary
        if not isinstance(prompt, dict):
            raise ValidationError(f"Prompt #{i+1} is not a dictionary")
        
        # Check required fields
        for field in required_fields:
            if field not in prompt:
                raise ValidationError(f"Prompt #{i+1} is missing required field: {field}")
        
        # Check field types
        if not isinstance(prompt["prompt"], str) or not prompt["prompt"].strip():
            raise ValidationError(f"Prompt #{i+1} has an empty or invalid 'prompt' field")
        
        if not isinstance(prompt["caption"], str) or not prompt["caption"].strip():
            raise ValidationError(f"Prompt #{i+1} has an empty or invalid 'caption' field")
        
        if not isinstance(prompt["hashtags"], list) or len(prompt["hashtags"]) == 0:
            raise ValidationError(f"Prompt #{i+1} has an empty or invalid 'hashtags' field")
        
        if prompt["aspect_ratio"] not in ["1:1", "9:16"]:
            raise ValidationError(f"Prompt #{i+1} has an invalid 'aspect_ratio' value: {prompt['aspect_ratio']}")
    
    logger.info(f"Successfully validated {len(prompts)} prompts")
    return True

@retry(
    retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def generate_with_openai(openai_client, topic, count, config):
    """
    Generate prompts using OpenAI API with retry logic
    
    Args:
        openai_client: The OpenAI client instance
        topic (str): Topic to generate prompts for
        count (int): Number of prompts to generate
        config (dict): Configuration dictionary
    
    Returns:
        list: List of prompt dictionaries or None on failure
    
    Raises:
        APIError: If API call fails after retries
    """
    logger.info(f"Generating {count} prompts for topic '{topic}' using OpenAI")
    
    prompt_config = config.get("prompt_generation", {})
    model = prompt_config.get("model", "gpt-4")
    temperature = prompt_config.get("temperature", 0.7)
    max_tokens = prompt_config.get("max_tokens", 500)
    
    system_message = f"""
    You are an expert at creating detailed, descriptive prompts for AI video generation systems.
    Create {count} unique prompts for generating 3-5 second looping videos about {topic}.
    
    Each prompt should be detailed, descriptive, and optimized for Stable Diffusion with AnimateDiff.
    For each prompt, also include:
    1. A short caption (7-10 words max)
    2. 3-5 relevant hashtags
    
    Format each prompt as a JSON object with the following fields:
    - prompt: The detailed generation prompt
    - negative_prompt: What to avoid in the generation
    - caption: A short caption for social media
    - hashtags: Array of hashtags (without the # symbol)
    - aspect_ratio: Either "1:1" or "9:16" (randomly choose one)
    
    Return an array of these JSON objects.
    """
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"Generate {count} AnimateDiff prompts for looping videos about {topic}."}
    ]
    
    try:
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        elapsed_time = time.time() - start_time
        logger.info(f"OpenAI API call completed in {elapsed_time:.2f} seconds")
        
        content = response.choices[0].message.content
        try:
            prompts = json.loads(content)
            if validate_prompts(prompts):
                logger.info(f"Successfully generated {len(prompts)} prompts with OpenAI")
                return prompts
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid response format from OpenAI: {e}")
            if notifications_available:
                send_alert("LoopForge: Prompt Generation Error", 
                          f"Invalid response format from OpenAI: {e}\nResponse: {content[:500]}...")
            return None
            
    except (openai.APIError, openai.APIConnectionError, openai.RateLimitError) as e:
        # These errors will trigger a retry
        logger.warning(f"OpenAI API error (will retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Error generating prompts with OpenAI: {e}")
        if notifications_available:
            send_alert("LoopForge: OpenAI Generation Error", str(e))
        return None

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def generate_with_anthropic(anthropic_client, topic, count, config):
    """
    Generate prompts using Anthropic's Claude API with retry logic
    
    Args:
        anthropic_client: The Anthropic client instance
        topic (str): Topic to generate prompts for
        count (int): Number of prompts to generate
        config (dict): Configuration dictionary
    
    Returns:
        list: List of prompt dictionaries or None on failure
    
    Raises:
        APIError: If API call fails after retries
    """
    logger.info(f"Generating {count} prompts for topic '{topic}' using Claude")
    
    prompt_config = config.get("prompt_generation", {})
    model = prompt_config.get("anthropic_model", "claude-3-opus-20240229")
    temperature = prompt_config.get("temperature", 0.7)
    max_tokens = prompt_config.get("max_tokens", 500)
    
    system_message = f"""
    You are an expert at creating detailed, descriptive prompts for AI video generation systems.
    """
    
    user_message = f"""
    Create {count} unique prompts for generating 3-5 second looping videos about {topic}.
    
    Each prompt should be detailed, descriptive, and optimized for Stable Diffusion with AnimateDiff.
    For each prompt, also include:
    1. A short caption (7-10 words max)
    2. 3-5 relevant hashtags
    
    Format each prompt as a JSON object with the following fields:
    - prompt: The detailed generation prompt
    - negative_prompt: What to avoid in the generation
    - caption: A short caption for social media
    - hashtags: Array of hashtags (without the # symbol)
    - aspect_ratio: Either "1:1" or "9:16" (randomly choose one)
    
    Return an array of these JSON objects.
    """
    
    try:
        start_time = time.time()
        response = anthropic_client.messages.create(
            model=model,
            system=system_message,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user_message}]
        )
        elapsed_time = time.time() - start_time
        logger.info(f"Claude API call completed in {elapsed_time:.2f} seconds")
        
        content = response.content[0].text
        try:
            prompts = json.loads(content)
            if validate_prompts(prompts):
                logger.info(f"Successfully generated {len(prompts)} prompts with Claude")
                return prompts
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid response format from Claude: {e}")
            if notifications_available:
                send_alert("LoopForge: Prompt Generation Error", 
                          f"Invalid response format from Claude: {e}\nResponse: {content[:500]}...")
            return None
            
    except Exception as e:
        logger.error(f"Error generating prompts with Claude: {e}")
        if notifications_available:
            send_alert("LoopForge: Claude Generation Error", str(e))
        return None

def save_prompts(prompts, output_dir, topic):
    """
    Save generated prompts to JSON files in the output directory
    
    Args:
        prompts (list): List of prompt dictionaries
        output_dir (str): Directory to save prompts in
        topic (str): Topic of the prompts
    
    Returns:
        list: List of saved file paths
    """
    saved_files = []
    
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created output directory: {output_dir}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, prompt_data in enumerate(prompts):
            try:
                # Add metadata
                prompt_data["metadata"] = {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "generated_at": datetime.now().isoformat(),
                    "status": "pending"
                }
                
                # Sanitize topic for filename
                safe_topic = ''.join(c if c.isalnum() else '_' for c in topic)
                
                # Create filename
                filename = f"{safe_topic}_{timestamp}_{i+1}.json"
                file_path = os.path.join(output_dir, filename)
                
                with open(file_path, 'w') as f:
                    json.dump(prompt_data, f, indent=2)
                
                saved_files.append(file_path)
                logger.info(f"Saved prompt to {file_path}")
            except Exception as e:
                logger.error(f"Error saving prompt #{i+1}: {e}")
        
        return saved_files
    except Exception as e:
        logger.error(f"Error saving prompts: {e}")
        if notifications_available:
            send_alert("LoopForge: Error Saving Prompts", str(e))
        return saved_files

def main():
    """Main function to handle prompt generation"""
    parser = argparse.ArgumentParser(description="Generate video prompts for LoopForge")
    parser.add_argument("--topic", type=str, help="Topic to generate prompts for")
    parser.add_argument("--niche", type=str, help="Use predefined niche from config")
    parser.add_argument("--count", type=int, default=5, help="Number of prompts to generate")
    args = parser.parse_args()
    
    try:
        # Load config
        logger.info("Starting prompt generation")
        config = load_config()
        
        # Determine the topic
        topic = args.topic
        if not topic and args.niche:
            topic = args.niche
            logger.info(f"Using niche from arguments: {topic}")
        if not topic:
            topic = config.get("prompt_generation", {}).get("default_niche", "productivity")
            logger.info(f"Using default niche from config: {topic}")
        
        count = args.count
        if count <= 0:
            logger.warning(f"Invalid count value ({count}), using default value 5")
            count = 5
        
        # Setup API clients
        openai_client, anthropic_client = setup_api_clients(config)
        
        # Generate prompts
        prompts = None
        generation_method = None
        
        # Try Claude first if available
        if anthropic_client:
            try:
                logger.info("Attempting to generate prompts with Claude")
                prompts = generate_with_anthropic(anthropic_client, topic, count, config)
                if prompts:
                    generation_method = "Claude"
            except Exception as e:
                logger.warning(f"Failed to generate prompts with Claude: {e}")
        
        # Fall back to OpenAI if Claude fails or is unavailable
        if prompts is None and openai_client:
            try:
                logger.info("Attempting to generate prompts with OpenAI")
                prompts = generate_with_openai(openai_client, topic, count, config)
                if prompts:
                    generation_method = "OpenAI"
            except Exception as e:
                logger.warning(f"Failed to generate prompts with OpenAI: {e}")
        
        if prompts is None:
            error_msg = "Failed to generate prompts with available APIs"
            logger.error(error_msg)
            if notifications_available:
                send_alert("LoopForge: Prompt Generation Failed", error_msg)
            sys.exit(1)
        
        # Determine output directory
        output_dir = os.path.join(script_path, config.get("paths", {}).get("prompts_dir", "data/prompts_to_render"))
        
        # Save prompts
        saved_files = save_prompts(prompts, output_dir, topic)
        
        if saved_files:
            success_msg = f"Successfully generated {len(saved_files)} prompts for topic '{topic}' using {generation_method}"
            logger.info(success_msg)
            if notifications_available:
                send_alert("LoopForge: Prompts Generated", 
                          f"{len(saved_files)} prompts for '{topic}' generated successfully using {generation_method}")
        else:
            error_msg = "Failed to save any prompts"
            logger.error(error_msg)
            if notifications_available:
                send_alert("LoopForge: Prompt Saving Failed", error_msg)
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Prompt generation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error in prompt generation: {e}", exc_info=True)
        if notifications_available:
            send_alert("LoopForge: Unexpected Error", f"Error in prompt generation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
