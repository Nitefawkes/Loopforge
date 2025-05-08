#!/usr/bin/env python3
"""
Local Renderer Script for LoopForge

This script monitors the prompts_to_render directory for new prompt JSON files,
processes them by sending them to a local rendering engine (ComfyUI or InvokeAI),
and saves the output to the rendered_clips directory.

Usage:
    python local_renderer.py
    python local_renderer.py --workflow custom_workflow.json
    python local_renderer.py --engine invoke
"""

import os
import sys
import json
import time
import argparse
import requests
import shutil
from pathlib import Path
from datetime import datetime
import uuid
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.json file"""
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        logger.error("Please copy config.example.json to config.json and add your API keys")
        sys.exit(1)

def load_workflow(workflow_file):
    """Load ComfyUI workflow from JSON file"""
    try:
        with open(workflow_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Workflow file not found at {workflow_file}")
        sys.exit(1)

class PromptHandler(FileSystemEventHandler):
    """Handler for file system events in the prompts_to_render directory"""
    
    def __init__(self, config, engine, workflow_file):
        self.config = config
        self.engine = engine
        self.workflow_file = workflow_file
        self.render_queue = []
        
        # Get paths from config
        paths = config.get("paths", {})
        self.prompts_dir = os.path.join(script_path, paths.get("prompts_dir", "data/prompts_to_render"))
        self.rendered_dir = os.path.join(script_path, paths.get("rendered_dir", "data/rendered_clips"))
        
        # Ensure output directory exists
        os.makedirs(self.rendered_dir, exist_ok=True)
        
        # Load existing prompt files
        self.load_existing_prompts()
    
    def load_existing_prompts(self):
        """Load existing prompt files in the prompts_to_render directory"""
        if os.path.exists(self.prompts_dir):
            for filename in os.listdir(self.prompts_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.prompts_dir, filename)
                    self.render_queue.append(file_path)
            
            logger.info(f"Loaded {len(self.render_queue)} existing prompt files")
    
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory and event.src_path.endswith(".json"):
            logger.info(f"New prompt file detected: {event.src_path}")
            self.render_queue.append(event.src_path)
    
    def process_queue(self):
        """Process the render queue"""
        if not self.render_queue:
            return
        
        logger.info(f"Processing render queue: {len(self.render_queue)} files")
        
        for prompt_file in list(self.render_queue):
            try:
                self.process_prompt(prompt_file)
                self.render_queue.remove(prompt_file)
            except Exception as e:
                logger.error(f"Error processing {prompt_file}: {e}")
                # Move to the end of the queue to try again later
                self.render_queue.remove(prompt_file)
                self.render_queue.append(prompt_file)
    
    def process_prompt(self, prompt_file):
        """Process a single prompt file"""
        logger.info(f"Processing prompt file: {prompt_file}")
        
        # Load prompt data
        with open(prompt_file, 'r') as f:
            prompt_data = json.load(f)
        
        # Extract prompt information
        prompt = prompt_data.get("prompt", "")
        negative_prompt = prompt_data.get("negative_prompt", "")
        aspect_ratio = prompt_data.get("aspect_ratio", "1:1")
        metadata = prompt_data.get("metadata", {})
        
        # Determine dimensions based on aspect ratio
        width, height = self.get_dimensions(aspect_ratio)
        
        # Send to renderer
        if self.engine == "comfyui":
            output_path = self.render_with_comfyui(prompt, negative_prompt, width, height, prompt_data)
        else:  # invokeai
            output_path = self.render_with_invokeai(prompt, negative_prompt, width, height, prompt_data)
        
        if output_path:
            # Update prompt status
            prompt_data["metadata"]["status"] = "rendered"
            prompt_data["metadata"]["rendered_at"] = datetime.now().isoformat()
            prompt_data["metadata"]["output_path"] = output_path
            
            # Save updated prompt data
            with open(prompt_file, 'w') as f:
                json.dump(prompt_data, f, indent=2)
            
            logger.info(f"Successfully rendered: {os.path.basename(prompt_file)} -> {os.path.basename(output_path)}")
    
    def get_dimensions(self, aspect_ratio):
        """Convert aspect ratio to dimensions based on configuration"""
        rendering_config = self.config.get("rendering", {})
        draft_resolution = rendering_config.get("draft_resolution", "720p")
        
        if draft_resolution == "720p":
            if aspect_ratio == "1:1":
                return 720, 720
            elif aspect_ratio == "9:16":
                return 720, 1280
        elif draft_resolution == "1080p":
            if aspect_ratio == "1:1":
                return 1080, 1080
            elif aspect_ratio == "9:16":
                return 1080, 1920
        
        # Default fallback
        return 512, 512
    
    def render_with_comfyui(self, prompt, negative_prompt, width, height, prompt_data):
        """Render video using ComfyUI API"""
        logger.info("Rendering with ComfyUI...")
        
        # Get ComfyUI configuration
        comfyui_config = self.config.get("rendering", {}).get("comfyui", {})
        api_url = comfyui_config.get("api_url", "http://127.0.0.1:8188/prompt")
        
        # Load workflow template
        workflow = None
        if self.workflow_file:
            workflow = load_workflow(self.workflow_file)
        else:
            default_workflow = comfyui_config.get("workflow_file")
            if default_workflow:
                workflow = load_workflow(os.path.join(script_path, default_workflow))
        
        if not workflow:
            logger.error("No workflow template available. Please specify a workflow file.")
            return None
        
        # Modify workflow with prompt data
        # This is a simplified example - you'll need to adapt to your actual workflow structure
        for node_id, node in workflow.get("nodes", {}).items():
            if node.get("type") == "CLIPTextEncode":
                if "positive" in node.get("title", "").lower():
                    node["inputs"]["text"] = prompt
                elif "negative" in node.get("title", "").lower():
                    node["inputs"]["text"] = negative_prompt
            
            # Set dimensions for appropriate nodes
            if node.get("type") in ["EmptyLatentImage", "VAEDecode"]:
                if "width" in node.get("inputs", {}):
                    node["inputs"]["width"] = width
                if "height" in node.get("inputs", {}):
                    node["inputs"]["height"] = height
        
        # Send to ComfyUI API
        try:
            response = requests.post(api_url, json={"prompt": workflow})
            response.raise_for_status()
            data = response.json()
            prompt_id = data.get("prompt_id")
            
            # Wait for completion
            # This is a simplified example - you might want to implement a proper polling mechanism
            # or webhook handler depending on your ComfyUI setup
            time.sleep(60)  # Wait for rendering to complete (adjust based on your GPU/model)
            
            # For this example, assume output is saved to a known location
            # In practice, you'd need to query ComfyUI for the output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"render_{timestamp}_{uuid.uuid4()}.mp4"
            output_path = os.path.join(self.rendered_dir, output_filename)
            
            # In a real implementation, you would copy the file from ComfyUI's output location
            # shutil.copy(comfyui_output_path, output_path)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error rendering with ComfyUI: {e}")
            return None
    
    def render_with_invokeai(self, prompt, negative_prompt, width, height, prompt_data):
        """Render video using InvokeAI API"""
        logger.info("Rendering with InvokeAI...")
        
        # Get InvokeAI configuration
        invokeai_config = self.config.get("rendering", {}).get("invokeai", {})
        api_url = invokeai_config.get("api_url", "http://127.0.0.1:9090/api/invocations")
        batch_size = invokeai_config.get("batch_size", 16)
        
        # Prepare InvokeAI request payload
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_frames": batch_size,
            "animation_mode": "AnimateDiff",
            "output_format": "mp4"
        }
        
        # Send to InvokeAI API
        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # In a real implementation, you would monitor the job status
            # and download the output when it's complete
            job_id = data.get("job_id")
            
            # Wait for completion
            time.sleep(60)  # Wait for rendering to complete (adjust based on your GPU/model)
            
            # For this example, assume output is saved to a known location
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"render_{timestamp}_{uuid.uuid4()}.mp4"
            output_path = os.path.join(self.rendered_dir, output_filename)
            
            # In a real implementation, you would download the file from InvokeAI
            # shutil.copy(invokeai_output_path, output_path)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error rendering with InvokeAI: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="LoopForge Local Renderer")
    parser.add_argument("--engine", type=str, choices=["comfyui", "invoke"], default="comfyui",
                        help="Rendering engine to use (default: comfyui)")
    parser.add_argument("--workflow", type=str, help="Custom workflow file for ComfyUI")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Create event handler
    event_handler = PromptHandler(config, args.engine, args.workflow)
    
    # Start watching the prompts directory
    prompts_dir = os.path.join(script_path, config.get("paths", {}).get("prompts_dir", "data/prompts_to_render"))
    observer = Observer()
    observer.schedule(event_handler, prompts_dir, recursive=False)
    observer.start()
    
    logger.info(f"Started watching for prompts in {prompts_dir}")
    
    try:
        while True:
            # Process any queued prompts
            event_handler.process_queue()
            
            # Sleep to prevent CPU overload
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
