"""Interfaz de línea de comandos para comprimir imágenes (input → output)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from compressor import AspectMode, CompressOptions, process_folder


def _parse_aspect(value: str) -> AspectMode:
    v = value.strip().lower()
    allowed: dict[str, AspectMode] = {
        "none": "none",
        "1:1": "1:1",
        "4:5": "4:5",
        "9:16": "9:16",
    }
    if v not in allowed:
        raise argparse.ArgumentTypeError(
            f"aspect debe ser one of {', '.join(sorted(allowed))}"
        )
    return allowed[v]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="InstaLight (CLI): comprime .jpg/.jpeg/.png con recorte y opciones para Instagram."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("input"),
        help="Carpeta con imágenes (por defecto: ./input)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output"),
        help="Carpeta de salida (por defecto: ./output)",
    )
    parser.add_argument(
        "--aspect",
        type=_parse_aspect,
        default="none",
        help="Recorte centrado: none, 1:1, 4:5, 9:16",
    )
    parser.add_argument(
        "--force-jpeg",
        action="store_true",
        help="Salida siempre .jpg (recomendado con --max-kb).",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=2000,
        help="Ancho máximo en píxeles (por defecto: 2000)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=80,
        help="Calidad JPEG 1–95 (por defecto: 80)",
    )
    parser.add_argument(
        "--max-kb",
        type=int,
        default=None,
        help="Tamaño máximo aproximado por archivo en KB (solo JPEG de salida).",
    )
    args = parser.parse_args()

    max_bytes = None if args.max_kb is None else max(1, args.max_kb) * 1024

    options = CompressOptions(
        max_width=args.max_width,
        jpeg_quality=min(95, max(1, args.quality)),
        aspect_mode=args.aspect,
        force_jpeg=args.force_jpeg,
        max_output_bytes=max_bytes,
    )

    def on_progress(msg: str) -> None:
        print(msg)

    ok, err = process_folder(
        args.input,
        args.output,
        options=options,
        on_progress=on_progress,
    )
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
