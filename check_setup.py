#!/usr/bin/env python3
"""
LoopForge Setup Check Script
Checks for Python, FFmpeg, GPU, and config file presence.
Prints clear pass/fail results and next steps for any issues found.
"""
import sys
import os
import subprocess
import json

REQUIRED_PYTHON = (3, 8)
CONFIG_PATH = os.path.join('config', 'config.json')

COLORS = {
    'PASS': '\033[92m',  # Green
    'FAIL': '\033[91m',  # Red
    'ENDC': '\033[0m',
    'WARN': '\033[93m',  # Yellow
}

def print_status(label, status, msg=None):
    color = COLORS['PASS'] if status else COLORS['FAIL']
    print(f"{color}{'✔' if status else '✖'} {label}{COLORS['ENDC']}", end='')
    if msg:
        print(f" - {msg}")
    else:
        print()

def check_python():
    version = sys.version_info
    if version >= REQUIRED_PYTHON:
        print_status("Python version", True, f"{version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_status("Python version", False, f"{version.major}.{version.minor}.{version.micro} (need >= 3.8)")
        return False

def check_ffmpeg():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_status("FFmpeg", True, result.stdout.splitlines()[0])
            return True
        else:
            print_status("FFmpeg", False, "ffmpeg not found in PATH")
            return False
    except Exception:
        print_status("FFmpeg", False, "ffmpeg not found in PATH")
        return False

def check_cuda():
    try:
        import torch
        if torch.cuda.is_available():
            print_status("CUDA GPU", True, torch.cuda.get_device_name(0))
            return True
        else:
            print_status("CUDA GPU", False, "No CUDA GPU detected")
            return False
    except ImportError:
        print_status("CUDA GPU", False, "PyTorch not installed (optional)")
        return False
    except Exception as e:
        print_status("CUDA GPU", False, str(e))
        return False

def check_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            print_status("Config file", True, CONFIG_PATH)
            # Check for API keys
            keys = config.get("api_keys", {})
            missing = []
            if not keys.get("openai"): missing.append("OpenAI")
            if not keys.get("anthropic"): missing.append("Anthropic")
            yt = keys.get("youtube", {})
            if not (yt.get("client_id") and yt.get("client_secret") and yt.get("refresh_token")):
                missing.append("YouTube")
            if missing:
                print(f"{COLORS['WARN']}⚠️  Missing API keys: {', '.join(missing)} (some features will be limited){COLORS['ENDC']}")
            return True
        except Exception as e:
            print_status("Config file", False, f"Invalid JSON: {e}")
            return False
    else:
        print_status("Config file", False, f"{CONFIG_PATH} not found")
        return False

def main():
    print("\nLoopForge Setup Check\n====================\n")
    ok = True
    if not check_python():
        ok = False
    if not check_ffmpeg():
        ok = False
    check_cuda()  # Optional, does not block
    if not check_config():
        ok = False
    print("\n---")
    if ok:
        print(f"{COLORS['PASS']}All essential checks passed! You are ready to run LoopForge.{COLORS['ENDC']}")
        print("Next: Run `python src/run_pipeline.py --all --topic 'your topic' --count 1`")
    else:
        print(f"{COLORS['FAIL']}Some checks failed. Please fix the above issues before running LoopForge.{COLORS['ENDC']}")
        print("See docs/setup.md for help.")

if __name__ == "__main__":
    main() 