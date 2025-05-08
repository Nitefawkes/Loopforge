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

# Add root to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

def load_config():
    """Load configuration from config.json file"""
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Config file not found at {config_path}")
        print("Please copy config.example.json to config.json and add your API keys")
        sys.exit(1)

def setup_api_clients(config):
    """Setup API clients for OpenAI and Anthropic"""
    openai_client = None
    anthropic_client = None
    
    if "api_keys" in config:
        if "openai" in config["api_keys"]:
            openai.api_key = config["api_keys"]["openai"]
            openai_client = openai.OpenAI(api_key=config["api_keys"]["openai"])
        
        if "anthropic" in config["api_keys"]:
            anthropic_client = Anthropic(api_key=config["api_keys"]["anthropic"])
    
    return openai_client, anthropic_client

def generate_with_openai(openai_client, topic, count, config):
    """Generate prompts using OpenAI API"""
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
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error generating prompts with OpenAI: {e}")
        return None

def generate_with_anthropic(anthropic_client, topic, count, config):
    """Generate prompts using Anthropic's Claude API"""
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
        response = anthropic_client.messages.create(
            model=model,
            system=system_message,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user_message}]
        )
        return json.loads(response.content[0].text)
    except Exception as e:
        print(f"Error generating prompts with Claude: {e}")
        return None

def save_prompts(prompts, output_dir, topic):
    """Save generated prompts to JSON files in the output directory"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for i, prompt_data in enumerate(prompts):
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
            
        print(f"Saved prompt to {file_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate video prompts for LoopForge")
    parser.add_argument("--topic", type=str, help="Topic to generate prompts for")
    parser.add_argument("--niche", type=str, help="Use predefined niche from config")
    parser.add_argument("--count", type=int, default=5, help="Number of prompts to generate")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Determine the topic
    topic = args.topic
    if not topic and args.niche:
        topic = args.niche
    if not topic:
        topic = config.get("prompt_generation", {}).get("default_niche", "productivity")
    
    # Setup API clients
    openai_client, anthropic_client = setup_api_clients(config)
    
    # Generate prompts
    prompts = None
    if anthropic_client:
        prompts = generate_with_anthropic(anthropic_client, topic, args.count, config)
    
    if prompts is None and openai_client:
        prompts = generate_with_openai(openai_client, topic, args.count, config)
    
    if prompts is None:
        print("Failed to generate prompts with available APIs")
        sys.exit(1)
    
    # Determine output directory
    output_dir = os.path.join(script_path, config.get("paths", {}).get("prompts_dir", "data/prompts_to_render"))
    
    # Save prompts
    save_prompts(prompts, output_dir, topic)
    
    print(f"Successfully generated {len(prompts)} prompts for topic '{topic}'")

if __name__ == "__main__":
    main()
