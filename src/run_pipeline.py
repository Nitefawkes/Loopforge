#!/usr/bin/env python3
"""
LoopForge Pipeline Orchestrator

This script orchestrates the entire LoopForge pipeline, from prompt generation
to uploading. It can be used to run the pipeline end-to-end or specific stages.

Usage:
    python run_pipeline.py --all
    python run_pipeline.py --stage generate --topic "space exploration" --count 5
    python run_pipeline.py --stage render --engine comfyui
    python run_pipeline.py --stage process
    python run_pipeline.py --stage upload --platform youtube
"""

import os
import sys
import subprocess
import argparse
import logging
import time
import json
from datetime import datetime
import glob
from notifications import send_alert

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

def run_generate_stage(args, config):
    """Run the prompt generation stage"""
    logger.info("Running prompt generation stage")
    generate_script = os.path.join(script_path, "src", "prompt_generation", "generate_prompts.py")
    cmd = [sys.executable, generate_script]
    if args.topic:
        cmd.extend(["--topic", args.topic])
    elif args.niche:
        cmd.extend(["--niche", args.niche])
    if args.count:
        cmd.extend(["--count", str(args.count)])
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        logger.info(f"[generate] STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"[generate] STDERR:\n{result.stderr}")
        if result.returncode != 0:
            logger.error(f"Prompt generation failed with exit code {result.returncode}")
            send_alert("LoopForge: Prompt Generation Failed", f"Exit code: {result.returncode}\nSTDERR:\n{result.stderr}")
            return False
        # Validate output
        prompt_files = glob.glob(os.path.join(script_path, "data", "prompts_to_render", "*.json"))
        logger.info(f"Prompts generated: {len(prompt_files)} in data/prompts_to_render/")
        if len(prompt_files) == 0:
            logger.warning("No prompt files found after generation stage.")
            send_alert("LoopForge: No Prompts Generated", "Prompt generation stage completed but no prompt files were found.")
        return True
    except Exception as e:
        logger.error(f"Error running prompt generation: {e}")
        send_alert("LoopForge: Prompt Generation Exception", str(e))
        return False

def run_render_stage(args, config):
    """Run the rendering stage"""
    logger.info("Running rendering stage")
    render_script = os.path.join(script_path, "src", "rendering", "local_renderer.py")
    cmd = [sys.executable, render_script]
    if args.engine:
        cmd.extend(["--engine", args.engine])
    if args.workflow:
        cmd.extend(["--workflow", args.workflow])
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=args.timeout if args.timeout else None)
        logger.info(f"[render] STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"[render] STDERR:\n{result.stderr}")
        if result.returncode != 0:
            logger.error(f"Rendering failed with exit code {result.returncode}")
            send_alert("LoopForge: Rendering Failed", f"Exit code: {result.returncode}\nSTDERR:\n{result.stderr}")
            return False
        # Validate output
        rendered_files = glob.glob(os.path.join(script_path, "data", "rendered_clips", "*.mp4"))
        logger.info(f"Rendered clips: {len(rendered_files)} in data/rendered_clips/")
        if len(rendered_files) == 0:
            logger.warning("No rendered clips found after rendering stage.")
            send_alert("LoopForge: No Clips Rendered", "Rendering stage completed but no clips were found.")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Rendering stage timed out.")
        send_alert("LoopForge: Rendering Timeout", "Rendering stage timed out.")
        return False
    except Exception as e:
        logger.error(f"Error running rendering: {e}")
        send_alert("LoopForge: Rendering Exception", str(e))
        return False

def run_process_stage(args, config):
    """Run the video processing stage"""
    logger.info("Running video processing stage")
    process_script = os.path.join(script_path, "src", "post_processing", "process_video.py")
    cmd = [sys.executable, process_script]
    if args.skip_captions:
        cmd.append("--skip-captions")
    if args.b_roll:
        cmd.append("--b-roll")
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=args.timeout if args.timeout else None)
        logger.info(f"[process] STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"[process] STDERR:\n{result.stderr}")
        if result.returncode != 0:
            logger.error(f"Video processing failed with exit code {result.returncode}")
            send_alert("LoopForge: Video Processing Failed", f"Exit code: {result.returncode}\nSTDERR:\n{result.stderr}")
            return False
        # Validate output
        processed_files = glob.glob(os.path.join(script_path, "data", "ready_to_post", "*.mp4"))
        logger.info(f"Processed videos: {len(processed_files)} in data/ready_to_post/")
        if len(processed_files) == 0:
            logger.warning("No processed videos found after processing stage.")
            send_alert("LoopForge: No Videos Processed", "Processing stage completed but no processed videos were found.")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Processing stage timed out.")
        send_alert("LoopForge: Processing Timeout", "Processing stage timed out.")
        return False
    except Exception as e:
        logger.error(f"Error running processing: {e}")
        send_alert("LoopForge: Processing Exception", str(e))
        return False

def run_upload_stage(args, config):
    """Run the upload stage"""
    logger.info("Running upload stage")
    upload_script = os.path.join(script_path, "src", "upload", "upload_video.py")
    cmd = [sys.executable, upload_script]
    if args.platform:
        cmd.extend(["--platform"] + args.platform)
    if args.dry_run:
        cmd.append("--dry-run")
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=args.timeout if args.timeout else None)
        logger.info(f"[upload] STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"[upload] STDERR:\n{result.stderr}")
        if result.returncode != 0:
            logger.error(f"Upload failed with exit code {result.returncode}")
            send_alert("LoopForge: Upload Failed", f"Exit code: {result.returncode}\nSTDERR:\n{result.stderr}")
            return False
        logger.info("Upload stage completed. Check platform(s) for results.")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Upload stage timed out.")
        send_alert("LoopForge: Upload Timeout", "Upload stage timed out.")
        return False
    except Exception as e:
        logger.error(f"Error running upload: {e}")
        send_alert("LoopForge: Upload Exception", str(e))
        return False

def run_all_stages(args, config):
    """Run all stages of the pipeline"""
    logger.info("Running all stages of the pipeline")
    summary = {"generate": None, "render": None, "process": None, "upload": None}
    # Run generate stage
    summary["generate"] = run_generate_stage(args, config)
    if not summary["generate"]:
        logger.error("Generate stage failed, stopping pipeline")
        send_alert("LoopForge: Pipeline Failed", "Stage: generate\nSee logs for details.")
        print("\nPipeline summary:")
        for k, v in summary.items():
            print(f"  {k}: {'SUCCESS' if v else 'FAILED' if v is False else 'SKIPPED'}")
        exit(1)
    # Run render stage
    render_args = argparse.Namespace(**vars(args))
    render_args.timeout = args.stage_timeout or 300
    summary["render"] = run_render_stage(render_args, config)
    if not summary["render"]:
        logger.error("Render stage failed, stopping pipeline")
        send_alert("LoopForge: Pipeline Failed", "Stage: render\nSee logs for details.")
        print("\nPipeline summary:")
        for k, v in summary.items():
            print(f"  {k}: {'SUCCESS' if v else 'FAILED' if v is False else 'SKIPPED'}")
        exit(1)
    # Run process stage
    process_args = argparse.Namespace(**vars(args))
    process_args.timeout = args.stage_timeout or 300
    summary["process"] = run_process_stage(process_args, config)
    if not summary["process"]:
        logger.error("Process stage failed, stopping pipeline")
        send_alert("LoopForge: Pipeline Failed", "Stage: process\nSee logs for details.")
        print("\nPipeline summary:")
        for k, v in summary.items():
            print(f"  {k}: {'SUCCESS' if v else 'FAILED' if v is False else 'SKIPPED'}")
        exit(1)
    # Run upload stage
    upload_args = argparse.Namespace(**vars(args))
    upload_args.timeout = args.stage_timeout or 300
    summary["upload"] = run_upload_stage(upload_args, config)
    if not summary["upload"]:
        logger.error("Upload stage failed")
        send_alert("LoopForge: Pipeline Failed", "Stage: upload\nSee logs for details.")
        print("\nPipeline summary:")
        for k, v in summary.items():
            print(f"  {k}: {'SUCCESS' if v else 'FAILED' if v is False else 'SKIPPED'}")
        exit(1)
    logger.info("All pipeline stages completed successfully")
    send_alert("LoopForge: Pipeline Success", "All pipeline stages completed successfully.")
    print("\nPipeline summary:")
    for k, v in summary.items():
        print(f"  {k}: {'SUCCESS' if v else 'FAILED' if v is False else 'SKIPPED'}")
    logger.info("Check logs for detailed output and diagnostics.")

def run_api_prototype(args, config):
    """Run the API prototype"""
    logger.info("Starting API prototype")
    
    api_script = os.path.join(script_path, "api_prototype", "main.py")
    
    cmd = [sys.executable, api_script]
    
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        process = subprocess.Popen(cmd)
        
        logger.info("API prototype is running (press Ctrl+C to stop)")
        process.wait()
        logger.info("API prototype stopped")
        
        return True
    except KeyboardInterrupt:
        logger.info("API prototype stopped by user")
        process.terminate()
        return True
    except Exception as e:
        logger.error(f"Error running API prototype: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="LoopForge Pipeline Orchestrator")
    
    # Pipeline control
    pipeline_group = parser.add_argument_group("Pipeline Control")
    pipeline_group.add_argument("--all", action="store_true", help="Run all stages of the pipeline")
    pipeline_group.add_argument("--stage", type=str, choices=["generate", "render", "process", "upload", "api"],
                              help="Run a specific stage of the pipeline")
    pipeline_group.add_argument("--stage-timeout", type=int, help="Timeout in seconds for each stage when running all stages")
    
    # Generation stage
    generate_group = parser.add_argument_group("Generate Stage")
    generate_group.add_argument("--topic", type=str, help="Topic to generate prompts for")
    generate_group.add_argument("--niche", type=str, help="Use predefined niche from config")
    generate_group.add_argument("--count", type=int, help="Number of prompts to generate")
    
    # Render stage
    render_group = parser.add_argument_group("Render Stage")
    render_group.add_argument("--engine", type=str, choices=["comfyui", "invoke"], help="Rendering engine to use")
    render_group.add_argument("--workflow", type=str, help="Custom workflow file for ComfyUI")
    render_group.add_argument("--timeout", type=int, help="Timeout in seconds for the render stage")
    
    # Process stage
    process_group = parser.add_argument_group("Process Stage")
    process_group.add_argument("--skip-captions", action="store_true", help="Skip adding captions to videos")
    process_group.add_argument("--b-roll", action="store_true", help="Add random B-roll to videos")
    
    # Upload stage
    upload_group = parser.add_argument_group("Upload Stage")
    upload_group.add_argument("--platform", type=str, nargs="+", choices=["youtube", "tiktok"], 
                           help="Platforms to upload to")
    upload_group.add_argument("--dry-run", action="store_true", help="Simulate uploads without actually uploading")
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Run the requested stage or all stages
    if args.all:
        run_all_stages(args, config)
    elif args.stage:
        if args.stage == "generate":
            run_generate_stage(args, config)
        elif args.stage == "render":
            run_render_stage(args, config)
        elif args.stage == "process":
            run_process_stage(args, config)
        elif args.stage == "upload":
            run_upload_stage(args, config)
        elif args.stage == "api":
            run_api_prototype(args, config)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
