# AI Model Setup Guide

This guide provides instructions for setting up the required AI models and checkpoints to use with LoopForge. It focuses on locally running Stable Diffusion with AnimateDiff for video generation.

## Required Models

For full functionality, you'll need to acquire the following models:

### Stable Diffusion Base Models

Choose one of these base models:

- **Dreamshaper 8** (Recommended for general purpose)
- **Realistic Vision V5.1**
- **SDXL 1.0**
- **Stable Diffusion 1.5**

### AnimateDiff Motion Modules

- **mm_sd_v15_v2.ckpt** (Base motion module)
- **mm_sd_v15_emotional.ckpt** (Optional: for more expressive animations)

### Optional Models for Enhanced Results

- **ControlNet models** (for more controlled generation)
- **LoRA models** (for specific styles)
- **VAE models** (improved image quality)

## Model Sources

Models can be acquired from the following sources:

1. **Hugging Face**:
   - [Stable Diffusion Models](https://huggingface.co/models?sort=downloads&search=stable+diffusion)
   - [AnimateDiff Models](https://huggingface.co/guoyww/animatediff)

2. **Civitai**:
   - [Dreamshaper](https://civitai.com/models/4384/dreamshaper)
   - [Realistic Vision](https://civitai.com/models/4201/realistic-vision-v51)

## Setup with ComfyUI (Recommended)

### Step 1: Install ComfyUI

1. Clone the ComfyUI repository:
   ```
   git clone https://github.com/comfyanonymous/ComfyUI
   cd ComfyUI
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

### Step 2: Install AnimateDiff Custom Node

1. Navigate to the custom nodes directory:
   ```
   cd custom_nodes
   ```

2. Clone the AnimateDiff repository:
   ```
   git clone https://github.com/continue-revolution/sd-webui-animatediff
   cd sd-webui-animatediff
   pip install -r requirements.txt
   ```

### Step 3: Download and Place Models

1. Create the following directories:
   ```
   mkdir -p models/checkpoints
   mkdir -p models/animatediff
   ```

2. Download the Stable Diffusion base model and place it in `models/checkpoints/`

3. Download the AnimateDiff motion module and place it in `models/animatediff/`

### Step 4: Start ComfyUI

1. Return to the main ComfyUI directory:
   ```
   cd ../..
   ```

2. Start ComfyUI:
   ```
   python main.py
   ```

3. Access the web UI at `http://localhost:8188`

### Step 5: Import the LoopForge Workflow

1. In the ComfyUI web interface, click on "Load" in the upper right corner
2. Select the workflow file from `Loop-forge/config/comfyui_animatediff_workflow.json`
3. Adjust the workflow settings as needed (model paths, dimensions, etc.)

## Setup with InvokeAI (Alternative)

### Step 1: Install InvokeAI

1. Follow the installation guide at [InvokeAI GitHub](https://github.com/invoke-ai/InvokeAI)
2. Complete the initial setup and model downloads via the InvokeAI installer

### Step 2: Install AnimateDiff Extension

1. From the InvokeAI web UI, go to the "Extensions" tab
2. Search for "AnimateDiff" and install it
3. Restart InvokeAI when prompted

### Step 3: Download Additional Motion Modules

1. Download the motion modules from Hugging Face
2. Place them in the appropriate directory as specified in the InvokeAI extension documentation

## Optimizing for Your Hardware

### NVIDIA GPUs

1. **RTX 3060 Ti (Your GPU)**:
   - Optimal batch size: 8-12 frames
   - Resolution: Start with 512x512 or 768x768
   - Use half-precision (fp16) for better performance

2. **RTX 3070/3080**:
   - Batch size: 16-24 frames
   - Resolution: Up to 1024x1024
   - Can use higher quality settings

3. **RTX 4090**:
   - Batch size: 32+ frames
   - Resolution: Up to 1280x1280
   - Can use highest quality settings

### AMD GPUs

For AMD GPUs, ComfyUI with DirectML backend is recommended:

1. Install DirectML version of PyTorch
2. Use the `--directml` flag when starting ComfyUI

### Memory Optimization

If you encounter CUDA out of memory errors:

1. Reduce batch size (number of frames)
2. Lower the resolution
3. Use `--lowvram` mode with ComfyUI
4. Close other applications using GPU memory

## Troubleshooting

### Common Issues

1. **"CUDA out of memory"**:
   - Reduce batch size
   - Lower resolution
   - Use model pruning techniques

2. **"Model not found"**:
   - Check that you've placed models in the correct directories
   - Verify filenames match those in the workflow

3. **"AnimateDiff node not found"**:
   - Ensure the AnimateDiff custom node is properly installed
   - Restart ComfyUI

4. **Poor animation quality**:
   - Try different motion modules
   - Adjust motion strengths in the workflow
   - Consider using ControlNet for more stable animations

## Additional Resources

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [AnimateDiff GitHub](https://github.com/guoyww/AnimateDiff)
- [InvokeAI Documentation](https://github.com/invoke-ai/InvokeAI)
- [Stable Diffusion WebUI AnimateDiff Extension](https://github.com/continue-revolution/sd-webui-animatediff)

Remember to respect the licenses of all models you download and use.
