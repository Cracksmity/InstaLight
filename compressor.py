"""Lógica de compresión y redimensionado de imágenes para Instagram."""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
DEFAULT_MAX_WIDTH = 2000
DEFAULT_JPEG_QUALITY = 80
DEFAULT_PNG_COMPRESS_LEVEL = 6
MIN_JPEG_QUALITY = 40
MIN_LONG_EDGE_FOR_CAP = 720

AspectMode = Literal["none", "1:1", "4:5", "9:16"]

OnProgress = Callable[[str], None]
OnStep = Callable[[int, int], None]


@dataclass
class CompressOptions:
    max_width: int = DEFAULT_MAX_WIDTH
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    png_compress_level: int = DEFAULT_PNG_COMPRESS_LEVEL
    aspect_mode: AspectMode = "none"
    force_jpeg: bool = False
    max_output_bytes: int | None = None

    def to_json_dict(self) -> dict:
        d = asdict(self)
        d["max_output_bytes"] = self.max_output_bytes
        return d

    @classmethod
    def from_json_dict(cls, d: dict) -> CompressOptions:
        am = d.get("aspect_mode", "none")
        if am not in ("none", "1:1", "4:5", "9:16"):
            am = "none"
        return cls(
            max_width=int(d.get("max_width", DEFAULT_MAX_WIDTH)),
            jpeg_quality=int(d.get("jpeg_quality", DEFAULT_JPEG_QUALITY)),
            png_compress_level=int(
                d.get("png_compress_level", DEFAULT_PNG_COMPRESS_LEVEL)
            ),
            aspect_mode=am,  # type: ignore[arg-type]
            force_jpeg=bool(d.get("force_jpeg", False)),
            max_output_bytes=(
                int(d["max_output_bytes"])
                if d.get("max_output_bytes") is not None
                else None
            ),
        )


def _resample_lanczos() -> int:
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS  # type: ignore[attr-defined]


def aspect_ratio_tuple(mode: AspectMode) -> tuple[int, int] | None:
    if mode == "none":
        return None
    if mode == "1:1":
        return (1, 1)
    if mode == "4:5":
        return (4, 5)
    if mode == "9:16":
        return (9, 16)
    return None


def center_crop_to_aspect(img: Image.Image, rw: int, rh: int) -> Image.Image:
    """Recorte centrado al ratio ancho:alto (ej. 4, 5)."""
    w, h = img.size
    target = rw / rh
    cur = w / h
    if abs(cur - target) < 1e-6:
        return img.copy()
    if cur > target:
        new_w = max(1, int(round(h * rw / rh)))
        new_h = h
        if new_w > w:
            new_w = w
        x0 = (w - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, new_h))
    new_w = w
    new_h = max(1, int(round(w * rh / rw)))
    if new_h > h:
        new_h = h
    y0 = (h - new_h) // 2
    return img.crop((0, y0, new_w, y0 + new_h))


def _prepare_for_jpeg(img: Image.Image) -> Image.Image:
    if img.mode == "CMYK":
        img = img.convert("RGB")
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in getattr(img, "info", {})
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _resize_max_width(img: Image.Image, max_width: int) -> Image.Image:
    w, h = img.size
    if w <= max_width:
        return img
    new_w = max_width
    new_h = max(1, round(h * (max_width / w)))
    return img.resize((new_w, new_h), _resample_lanczos())


def _apply_pipeline_pil(
    img: Image.Image,
    src_suffix: str,
    options: CompressOptions,
) -> tuple[Image.Image, bool]:
    """
    EXIF ya aplicado en el caller. Devuelve (imagen lista para guardar, salida_es_jpeg).
    """
    ar = aspect_ratio_tuple(options.aspect_mode)
    if ar is not None:
        img = center_crop_to_aspect(img, ar[0], ar[1])

    img = _resize_max_width(img, options.max_width)

    out_jpeg = options.force_jpeg or src_suffix in (".jpg", ".jpeg")
    if out_jpeg:
        return _prepare_for_jpeg(img), True
    out = img
    if out.mode == "P" and "transparency" in getattr(out, "info", {}):
        out = out.convert("RGBA")
    return out, False


def _jpeg_bytes(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _shrink_to_long_edge(img: Image.Image, long_edge: int) -> Image.Image:
    w, h = img.size
    m = max(w, h)
    if m <= long_edge:
        return img
    scale = long_edge / m
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return img.resize((nw, nh), _resample_lanczos())


def _fit_jpeg_under_max_bytes(
    img: Image.Image,
    options: CompressOptions,
    on_progress: OnProgress | None,
) -> tuple[bytes, int]:
    """
    Ajusta calidad y, si hace falta, escala para cumplir max_output_bytes (solo JPEG).
    Heurística: bajar quality de 5 en 5 hasta MIN_JPEG_QUALITY; luego reducir long_edge
    ~10% hasta MIN_LONG_EDGE_FOR_CAP o hasta 8 intentos.
    """
    limit = options.max_output_bytes
    q = min(95, max(1, options.jpeg_quality))
    work = img.copy()
    best: tuple[bytes, int] | None = None

    if limit is None:
        data = _jpeg_bytes(work, q)
        return data, q

    for _ in range(24):
        data = _jpeg_bytes(work, q)
        best = (data, q)
        if len(data) <= limit:
            return data, q
        if q > MIN_JPEG_QUALITY + 4:
            q -= 5
            continue
        long_edge = max(work.size)
        if long_edge <= MIN_LONG_EDGE_FOR_CAP:
            if on_progress:
                on_progress(
                    f"Aviso: no se pudo bajar de {len(data)} B con calidad mín. {q}."
                )
            return data, q
        new_long = max(MIN_LONG_EDGE_FOR_CAP, int(long_edge * 0.9))
        work = _shrink_to_long_edge(work, new_long)
        q = min(95, options.jpeg_quality)

    assert best is not None
    return best


def _png_bytes(img: Image.Image, compress_level: int) -> bytes:
    buf = io.BytesIO()
    img.save(
        buf,
        format="PNG",
        optimize=True,
        compress_level=min(9, max(0, compress_level)),
    )
    return buf.getvalue()


def build_processed_image(
    src_path: Path,
    options: CompressOptions,
) -> tuple[Image.Image, bool]:
    """Abre archivo, aplica EXIF y pipeline; devuelve (imagen, salida_es_jpeg)."""
    suffix = src_path.suffix.lower()
    with Image.open(src_path) as raw:
        raw = ImageOps.exif_transpose(raw)
        img = raw.copy()
    return _apply_pipeline_pil(img, suffix, options)


def process_image(
    src_path: Path,
    dst_path: Path,
    options: CompressOptions | None = None,
    on_progress: OnProgress | None = None,
) -> None:
    """Abre, recorta opcional, redimensiona, comprime y guarda."""
    opts = options or CompressOptions()
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = src_path.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(f"Formato no soportado: {suffix}")

    processed, out_jpeg = build_processed_image(src_path, opts)

    if out_jpeg:
        data, used_q = _fit_jpeg_under_max_bytes(processed, opts, on_progress)
        dst_path = dst_path.with_suffix(".jpg")
        dst_path.write_bytes(data)
        if on_progress and opts.max_output_bytes is not None and used_q < opts.jpeg_quality:
            on_progress(
                f"  (ajustado a calidad {used_q} para peso ≤ {opts.max_output_bytes} B)"
            )
        return

    # PNG salida
    processed.save(
        dst_path,
        format="PNG",
        optimize=True,
        compress_level=min(9, max(0, opts.png_compress_level)),
    )


def _iter_jobs(input_dir: Path) -> list[tuple[str, Path]]:
    jobs: list[tuple[str, Path]] = []
    for name in sorted(os.listdir(input_dir)):
        src = input_dir / name
        if not src.is_file():
            continue
        if src.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        jobs.append((name, src))
    return jobs


def _dst_name_for_job(name: str, options: CompressOptions) -> str:
    if options.force_jpeg:
        return f"{Path(name).stem}.jpg"
    return name


def process_folder(
    input_dir: Path,
    output_dir: Path,
    options: CompressOptions | None = None,
    on_progress: OnProgress | None = None,
    on_step: OnStep | None = None,
) -> tuple[int, int]:
    """
    Procesa todas las imágenes .jpg/.jpeg/.png en input_dir.
    Retorna (éxitos, fallos).
    """
    opts = options or CompressOptions()
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    ok = 0
    errors = 0

    if not input_dir.is_dir():
        log(f"Error: la carpeta de origen no existe o no es carpeta: {input_dir}")
        return 0, 1

    jobs = _iter_jobs(input_dir)
    total = len(jobs)

    if (
        opts.max_output_bytes is not None
        and not opts.force_jpeg
        and total > 0
        and on_progress
        and any(Path(n).suffix.lower() == ".png" for n, _ in jobs)
    ):
        on_progress(
            "Aviso: límite de peso (KB) solo se fuerza en salida JPEG; "
            "activa «Solo JPEG» si quieres ese límite en todas las fotos."
        )

    for idx, (name, src) in enumerate(jobs, start=1):
        if on_step:
            on_step(idx, total)
        dst_name = _dst_name_for_job(name, opts)
        dst = output_dir / dst_name
        try:
            process_image(src, dst, opts, on_progress=log)
            ok += 1
            log(f"Listo: {dst_name}")
        except OSError as e:
            errors += 1
            log(f"Error (archivo) {name}: {e}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            log(f"Error {name}: {e}")

    if total == 0:
        log(
            "No se encontraron imágenes .jpg, .jpeg o .png en la carpeta de origen."
        )

    log(f"Resumen: {ok} correctas, {errors} con error.")
    return ok, errors


def preview_compress(
    src_path: Path,
    options: CompressOptions,
    thumb_max: int = 280,
) -> tuple[int, int, Image.Image, Image.Image]:
    """
    Tamaño original en bytes, tamaño de salida en bytes (codificado),
    miniatura antes (RGB), miniatura después (RGB).
    """
    src_path = src_path.resolve()
    bytes_in = src_path.stat().st_size if src_path.is_file() else 0

    with Image.open(src_path) as raw:
        before = ImageOps.exif_transpose(raw).copy()
    before_rgb = before.convert("RGB") if before.mode != "RGB" else before.copy()

    processed, out_jpeg = build_processed_image(src_path, options)
    if out_jpeg:
        data, _ = _fit_jpeg_under_max_bytes(processed, options, None)
        bytes_out = len(data)
        after = Image.open(io.BytesIO(data)).convert("RGB")
    else:
        data = _png_bytes(processed, options.png_compress_level)
        bytes_out = len(data)
        after = Image.open(io.BytesIO(data))
        if after.mode == "RGBA":
            bg = Image.new("RGB", after.size, (255, 255, 255))
            bg.paste(after, mask=after.getchannel("A"))
            after = bg
        else:
            after = after.convert("RGB")

    def thumb(im: Image.Image) -> Image.Image:
        im = im.copy()
        im.thumbnail((thumb_max, thumb_max), _resample_lanczos())
        return im.convert("RGB")

    return bytes_in, bytes_out, thumb(before_rgb), thumb(after)
