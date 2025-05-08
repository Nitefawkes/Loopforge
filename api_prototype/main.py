#!/usr/bin/env python3
"""
LoopForge API Prototype

A simple FastAPI-based web service that serves as an early prototype
for the LoopForge platform. It provides endpoints for generating 
video ideas and prompts.

Usage:
    uvicorn main:app --reload
"""

import os
import sys
import json
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from fastapi import FastAPI, HTTPException, Depends, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import openai
from anthropic import Anthropic

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(script_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    """Load configuration from config.json file"""
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        # Return default config for API prototype
        return {
            "api_prototype": {
                "host": "0.0.0.0",
                "port": 8000,
                "debug": True,
                "allow_origins": ["*"]
            }
        }

config = load_config()

# Set up OpenAI and Anthropic clients
def setup_api_clients():
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

openai_client, anthropic_client = setup_api_clients()

# Initialize FastAPI app
app = FastAPI(
    title="LoopForge API",
    description="A simple API for generating video prompts and ideas",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get("api_prototype", {}).get("allow_origins", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define models
class Prompt(BaseModel):
    prompt: str = Field(..., description="The detailed generation prompt")
    negative_prompt: str = Field("", description="What to avoid in the generation")
    caption: str = Field(..., description="A short caption for social media")
    hashtags: List[str] = Field(default_factory=list, description="Array of hashtags (without the # symbol)")
    aspect_ratio: str = Field("1:1", description="Aspect ratio (1:1 or 9:16)")

class PromptRequest(BaseModel):
    topic: str = Field(..., description="Topic to generate prompts for")
    count: int = Field(5, description="Number of prompts to generate")
    model: Optional[str] = Field(None, description="Model to use (default from config)")

class PromptResponse(BaseModel):
    prompts: List[Prompt] = Field(..., description="Generated prompts")
    topic: str = Field(..., description="Topic used for generation")
    generated_at: str = Field(..., description="Timestamp of generation")
    id: str = Field(..., description="Unique ID for this generation")

# API endpoints
@app.get("/")
async def root():
    """Root endpoint to check if the API is running"""
    return {
        "status": "ok",
        "message": "LoopForge API is running",
        "version": "0.1.0"
    }

@app.post("/generate-prompts", response_model=PromptResponse)
async def generate_prompts(request: PromptRequest):
    """Generate video prompts based on a topic"""
    if not openai_client and not anthropic_client:
        raise HTTPException(status_code=500, detail="No API clients available. Please check your configuration.")
    
    prompts = []
    
    # Determine which client to use
    if anthropic_client and (request.model is None or "claude" in request.model.lower()):
        prompts = await generate_with_anthropic(request.topic, request.count)
    elif openai_client:
        prompts = await generate_with_openai(request.topic, request.count, request.model)
    else:
        raise HTTPException(status_code=400, detail="Requested model not available")
    
    return {
        "prompts": prompts,
        "topic": request.topic,
        "generated_at": datetime.now().isoformat(),
        "id": str(uuid.uuid4())
    }

async def generate_with_openai(topic: str, count: int, model: Optional[str] = None):
    """Generate prompts using OpenAI API"""
    prompt_config = config.get("prompt_generation", {})
    model = model or prompt_config.get("model", "gpt-4")
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
        logger.error(f"Error generating prompts with OpenAI: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating prompts: {str(e)}")

async def generate_with_anthropic(topic: str, count: int):
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
        logger.error(f"Error generating prompts with Claude: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating prompts: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_clients": {
            "openai": openai_client is not None,
            "anthropic": anthropic_client is not None
        }
    }

# API documentation redirect
@app.get("/docs")
async def get_docs():
    """Redirect to API documentation"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")

# Run the app
if __name__ == "__main__":
    import uvicorn
    
    api_config = config.get("api_prototype", {})
    host = api_config.get("host", "0.0.0.0")
    port = api_config.get("port", 8000)
    debug = api_config.get("debug", True)
    
    uvicorn.run("main:app", host=host, port=port, reload=debug)
