#!/usr/bin/env python3
"""Debug environment variables."""

import os

def main():
    print("=== All Environment Variables ===")
    
    # Show all environment variables
    for key, value in sorted(os.environ.items()):
        if any(keyword in key.upper() for keyword in ['PDF', 'NVIDIA', 'CUDA', 'GPU']):
            print(f"{key}: {value}")
    
    print("\n=== PDF_TRANSLATE Variables ===")
    for key, value in sorted(os.environ.items()):
        if key.startswith('PDF_TRANSLATE_'):
            print(f"{key}: {value}")
    
    print("\n=== NVIDIA Variables ===")
    for key, value in sorted(os.environ.items()):
        if 'NVIDIA' in key.upper():
            print(f"{key}: {value}")

if __name__ == "__main__":
    main()
