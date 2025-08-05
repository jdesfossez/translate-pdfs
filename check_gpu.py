#!/usr/bin/env python3
"""Check GPU availability and CUDA setup."""

import sys

def check_cuda():
    """Check CUDA availability."""
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"CUDA version: {torch.version.cuda}")
            print(f"GPU count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
                print(f"    Memory: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB")
        else:
            print("CUDA not available - will use CPU")
            
        return torch.cuda.is_available()
    except ImportError:
        print("PyTorch not installed")
        return False
    except Exception as e:
        print(f"Error checking CUDA: {e}")
        return False

def check_nvidia_smi():
    """Check nvidia-smi command."""
    try:
        import subprocess
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ nvidia-smi available:")
            print(result.stdout)
            return True
        else:
            print("❌ nvidia-smi failed:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ nvidia-smi not found")
        return False
    except Exception as e:
        print(f"❌ Error running nvidia-smi: {e}")
        return False

def main():
    print("=== GPU/CUDA Check ===")
    
    print("\n1. Checking nvidia-smi...")
    nvidia_available = check_nvidia_smi()
    
    print("\n2. Checking PyTorch CUDA...")
    cuda_available = check_cuda()
    
    print(f"\n=== Summary ===")
    print(f"NVIDIA driver: {'✅' if nvidia_available else '❌'}")
    print(f"CUDA in PyTorch: {'✅' if cuda_available else '❌'}")
    
    if cuda_available:
        print("🚀 GPU acceleration available!")
    else:
        print("💻 Will use CPU-only mode")

if __name__ == "__main__":
    main()
