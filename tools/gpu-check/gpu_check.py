"""Prove that PyTorch can see and use the GPU, on the host or inside a container.

Dependencies live in pyproject.toml and uv.lock.
On the host (from this folder):  uv run gpu_check.py
In a container:                  docker build -t gpu-check:dev . && docker run --rm --gpus all gpu-check:dev
"""

import time

import torch


def main() -> None:
    print(f"torch {torch.__version__} | wheel built for CUDA {torch.version.cuda}")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available. Check that `nvidia-smi` works inside WSL.")

    dev = torch.device("cuda:0")
    props = torch.cuda.get_device_properties(dev)
    free, total = torch.cuda.mem_get_info(dev)
    print(f"GPU {props.name} | compute capability {props.major}.{props.minor} | "
          f"VRAM free {free / 2**30:.1f} of {total / 2**30:.1f} GiB")
    print(f"bf16 supported: {torch.cuda.is_bf16_supported()}")

    # A real workload: fp16 matrix multiply on the tensor cores.
    n, iters = 8192, 20
    a = torch.randn(n, n, device=dev, dtype=torch.float16)
    b = torch.randn(n, n, device=dev, dtype=torch.float16)
    torch.matmul(a, b)
    torch.cuda.synchronize()  # warm-up: first call pays for kernel selection

    start = time.perf_counter()
    for _ in range(iters):
        torch.matmul(a, b)
    torch.cuda.synchronize()  # GPU calls are async; wait before stopping the clock
    seconds = (time.perf_counter() - start) / iters

    tflops = 2 * n**3 / seconds / 1e12
    print(f"fp16 matmul {n}x{n}: {seconds * 1e3:.1f} ms per call, {tflops:.1f} TFLOPS")


if __name__ == "__main__":
    main()
