"""Utility helpers for inspecting and logging GPU availability."""

from __future__ import annotations

import logging
from typing import Dict, List

import torch


def _get_logger(logger: logging.Logger | None = None) -> logging.Logger:
    """Return a logger instance, defaulting to module-level logger."""
    return logger if logger is not None else logging.getLogger(__name__)


def collect_gpu_info() -> Dict[str, object]:
    """Return structured information about detected CUDA devices."""
    info: Dict[str, object] = {
        "available": torch.cuda.is_available(),
        "cuda_version": getattr(torch.version, "cuda", None),
        "devices": [],
    }

    if not info["available"]:
        info["device_count"] = 0
        return info

    devices: List[Dict[str, object]] = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        devices.append(
            {
                "index": index,
                "name": props.name,
                "total_memory_gb": round(props.total_memory / 1024**3, 2),
                "multi_processor_count": props.multi_processor_count,
                "compute_capability": f"{props.major}.{props.minor}",
            }
        )

    info["device_count"] = len(devices)
    info["devices"] = devices
    return info


def log_gpu_summary(logger: logging.Logger | None = None) -> Dict[str, object]:
    """Log GPU information and return the gathered metadata."""
    logger = _get_logger(logger)
    summary = collect_gpu_info()

    if not summary["available"]:
        logger.info("CUDA not available; running in CPU mode.")
        return summary

    logger.info(
        "Detected %s CUDA device(s) | CUDA runtime %s",
        summary["device_count"],
        summary.get("cuda_version") or "unknown",
    )

    for device in summary["devices"]:
        logger.info(
            "GPU %(index)s: %(name)s | %(total_memory_gb)s GB | compute %(compute_capability)s | SMs %(multi_processor_count)s",
            device,
        )
        if "GH200" in device["name"]:
            logger.info(
                "NVIDIA GH200 detected; Hopper optimizations (TF32/BF16) enabled."
            )

    return summary
