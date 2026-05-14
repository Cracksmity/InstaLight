"""Interfaz gráfica para comprimir imágenes antes de subirlas a Instagram."""

from __future__ import annotations

import os
import queue
import threading
import tkinter.simpledialog as simpledialog
import zipfile
from pathlib import Path
from typing import Any

import customtkinter as ctk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

try:
    import windnd
except ImportError:
    windnd = None

from app_config import (
    apply_session_to_vars,
    load_last_session,
    load_presets,
    save_last_session,
    save_presets,
    session_payload_from_gui,
)
from compressor import (
    AspectMode,
    CompressOptions,
    preview_compress,
    process_folder,
)
from PIL import Image

DEFAULT_INPUT = Path("input")
DEFAULT_OUTPUT = Path("output")

ASPECT_LABELS: list[str] = [
    "Sin recorte",
    "1:1",
    "4:5 (Feed)",
    "9:16 (Historia/Reel)",
]
ASPECT_FROM_LABEL: dict[str, AspectMode] = {
    "Sin recorte": "none",
    "1:1": "1:1",
    "4:5 (Feed)": "4:5",
    "9:16 (Historia/Reel)": "9:16",
}
LABEL_FROM_ASPECT: dict[AspectMode, str] = {v: k for k, v in ASPECT_FROM_LABEL.items()}


class CompressorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("InstaLight")
        self.geometry("720x820")
        self.minsize(640, 760)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._ui_queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._preview_worker: threading.Thread | None = None

        self._input_var = ctk.StringVar(value=str(DEFAULT_INPUT.resolve()))
        self._output_var = ctk.StringVar(value=str(DEFAULT_OUTPUT.resolve()))
        self._aspect_var = ctk.StringVar(value="Sin recorte")
        self._force_jpeg = ctk.BooleanVar(value=False)
        self._max_kb_var = ctk.StringVar(value="")
        self._qual_var = ctk.DoubleVar(value=80.0)
        self._maxw_var = ctk.DoubleVar(value=2000.0)
        self._theme_var = ctk.StringVar(value="Oscuro")
        self._preset_var = ctk.StringVar(value="(ninguno)")

        self._ctk_before: ctk.CTkImage | None = None
        self._ctk_after: ctk.CTkImage | None = None

        self._presets: list[dict[str, Any]] = []
        self._load_session_and_presets()

        self._build_ui()
        self._try_icon()
        self._setup_dnd()
        self.after(80, self._drain_ui_queue)
        self.after(500, self._request_preview)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _try_icon(self) -> None:
        ico = Path(__file__).resolve().parent / "assets" / "app.ico"
        if ico.is_file():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

    def _setup_dnd(self) -> None:
        if windnd is None:
            return

        def cb(files: list[str | bytes]) -> None:
            self.after(0, lambda: self._apply_drop_files(files))

        try:
            windnd.hook_dropfiles(self, cb, force_unicode=True)
        except Exception:
            pass

    def _apply_drop_files(self, files: list[str | bytes]) -> None:
        if not files:
            return
        first = files[0]
        if isinstance(first, bytes):
            s = first.decode("utf-8", errors="replace").rstrip("\x00")
        else:
            s = str(first)
        p = Path(s)
        if p.is_dir():
            self._input_var.set(str(p.resolve()))
        elif p.is_file():
            self._input_var.set(str(p.parent.resolve()))
        self._request_preview()

    def _load_session_and_presets(self) -> None:
        self._presets = load_presets()
        s = load_last_session()
        if not s:
            return
        v = apply_session_to_vars(s)
        if v.get("input"):
            self._input_var.set(v["input"])
        if v.get("output"):
            self._output_var.set(v["output"])
        am = v.get("aspect", "none")
        try:
            self._aspect_var.set(LABEL_FROM_ASPECT[am])  # type: ignore[index]
        except KeyError:
            self._aspect_var.set("Sin recorte")
        self._force_jpeg.set(v.get("force_jpeg", False))
        self._max_kb_var.set(v.get("max_kb", ""))
        self._qual_var.set(float(v.get("quality", 80)))
        self._maxw_var.set(float(v.get("max_width", 2000)))
        theme = v.get("theme", "dark")
        if theme == "light":
            self._theme_var.set("Claro")
            ctk.set_appearance_mode("light")
        else:
            self._theme_var.set("Oscuro")
            ctk.set_appearance_mode("dark")
        name = v.get("selected_preset", "")
        names = [p.get("name", "") for p in self._presets if p.get("name")]
        if name and name in names:
            self._preset_var.set(name)
        else:
            self._preset_var.set("(ninguno)")

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        title = ctk.CTkLabel(
            self,
            text="InstaLight",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(pady=(16, 4))

        subtitle = ctk.CTkLabel(
            self,
            text="Comprime y recorta fotos para Instagram, con vista previa y menos peso",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
        )
        subtitle.pack(pady=(0, 8))

        theme_row = ctk.CTkFrame(self, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(theme_row, text="Tema").pack(side="left", padx=(0, 8))
        ctk.CTkSegmentedButton(
            theme_row,
            values=["Oscuro", "Claro"],
            variable=self._theme_var,
            command=self._on_theme_change,
            width=200,
        ).pack(side="left")

        in_frame = ctk.CTkFrame(self, fg_color="transparent")
        in_frame.pack(fill="x", **pad)
        ctk.CTkLabel(in_frame, text="Origen", width=88, anchor="w").pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkEntry(in_frame, textvariable=self._input_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(
            in_frame, text="Elegir…", width=88, command=self._pick_input
        ).pack(side="right")

        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.pack(fill="x", **pad)
        ctk.CTkLabel(out_frame, text="Destino", width=88, anchor="w").pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkEntry(out_frame, textvariable=self._output_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(
            out_frame, text="Elegir…", width=88, command=self._pick_output
        ).pack(side="right")

        opt = ctk.CTkFrame(self)
        opt.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(opt, text="Opciones", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(8, 4)
        )

        ctk.CTkLabel(opt, text="Recorte centrado").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        self._aspect_menu = ctk.CTkOptionMenu(
            opt,
            variable=self._aspect_var,
            values=ASPECT_LABELS,
            width=220,
            command=lambda _v: self._request_preview(),
        )
        self._aspect_menu.grid(row=1, column=1, columnspan=3, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(opt, text="Solo JPEG de salida").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        ctk.CTkSwitch(
            opt,
            text="",
            variable=self._force_jpeg,
            command=lambda: self._request_preview(),
            width=48,
        ).grid(row=2, column=1, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(opt, text="Peso máx. (KB, opcional)").grid(
            row=3, column=0, sticky="w", padx=8, pady=4
        )
        ctk.CTkEntry(opt, textvariable=self._max_kb_var, width=120).grid(
            row=3, column=1, sticky="w", padx=8, pady=4
        )

        ctk.CTkLabel(opt, text="Calidad JPEG").grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )
        self._qual_slider = ctk.CTkSlider(
            opt, from_=40, to=95, number_of_steps=55, variable=self._qual_var, command=lambda _v: self._request_preview()
        )
        self._qual_slider.grid(row=4, column=1, sticky="ew", padx=8, pady=4)
        self._qual_label = ctk.CTkLabel(opt, text="80", width=36)
        self._qual_label.grid(row=4, column=2, sticky="w", padx=4)
        self._qual_var.trace_add("write", lambda *_: self._qual_label.configure(text=str(int(round(self._qual_var.get())))))

        ctk.CTkLabel(opt, text="Ancho máx. (px)").grid(
            row=5, column=0, sticky="w", padx=8, pady=4
        )
        self._maxw_slider = ctk.CTkSlider(
            opt, from_=800, to=4000, number_of_steps=64, variable=self._maxw_var, command=lambda _v: self._request_preview()
        )
        self._maxw_slider.grid(row=5, column=1, sticky="ew", padx=8, pady=4)
        self._maxw_label = ctk.CTkLabel(opt, text="2000", width=44)
        self._maxw_label.grid(row=5, column=2, sticky="w", padx=4)
        self._maxw_var.trace_add("write", lambda *_: self._maxw_label.configure(text=str(int(round(self._maxw_var.get())))))

        opt.grid_columnconfigure(1, weight=1)

        pre_row = ctk.CTkFrame(self, fg_color="transparent")
        pre_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(pre_row, text="Perfil").pack(side="left", padx=(0, 8))
        preset_names = ["(ninguno)"] + [p.get("name", "?") for p in self._presets]
        self._preset_combo = ctk.CTkComboBox(
            pre_row,
            values=preset_names,
            variable=self._preset_var,
            width=200,
            command=self._on_preset_selected,
        )
        self._preset_combo.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            pre_row, text="Guardar perfil…", width=120, command=self._save_preset
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            pre_row, text="Eliminar", width=88, command=self._delete_preset
        ).pack(side="left", padx=4)

        self._run_btn = ctk.CTkButton(
            self,
            text="Comprimir ahora",
            height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_compress,
        )
        self._run_btn.pack(pady=10, padx=16, fill="x")

        ctk.CTkButton(
            self,
            text="Exportar salida como ZIP…",
            height=34,
            command=self._export_zip,
        ).pack(padx=16, fill="x", pady=(0, 8))

        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._prog = ctk.CTkProgressBar(prog_frame, height=10)
        self._prog.pack(fill="x", pady=(0, 4))
        self._prog.set(0)
        self._prog_label = ctk.CTkLabel(prog_frame, text="0 / 0")
        self._prog_label.pack(anchor="w")

        pv = ctk.CTkFrame(self)
        pv.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(pv, text="Vista previa", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )
        self._preview_info = ctk.CTkLabel(
            pv,
            text="Elige carpeta y pulsa «Actualizar vista previa».",
            wraplength=640,
            justify="left",
        )
        self._preview_info.pack(anchor="w", padx=8, pady=4)

        thumbs = ctk.CTkFrame(pv, fg_color="transparent")
        thumbs.pack(fill="x", padx=8, pady=8)
        self._lbl_before = ctk.CTkLabel(thumbs, text="Antes", width=280, height=200)
        self._lbl_before.pack(side="left", padx=(0, 12))
        self._lbl_after = ctk.CTkLabel(thumbs, text="Después", width=280, height=200)
        self._lbl_after.pack(side="left")

        ctk.CTkButton(
            pv,
            text="Actualizar vista previa",
            command=self._request_preview,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        log_label = ctk.CTkLabel(self, text="Registro", anchor="w")
        log_label.pack(fill="x", padx=16, pady=(4, 2))

        self._log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12), height=140)
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode("dark" if value == "Oscuro" else "light")

    def _on_preset_selected(self, choice: str) -> None:
        if choice == "(ninguno)":
            return
        for p in self._presets:
            if p.get("name") == choice:
                od = p.get("options") or {}
                try:
                    o = CompressOptions.from_json_dict(od)
                except Exception:
                    return
                self._aspect_var.set(LABEL_FROM_ASPECT.get(o.aspect_mode, "Sin recorte"))
                self._force_jpeg.set(o.force_jpeg)
                self._max_kb_var.set(
                    str(o.max_output_bytes // 1024) if o.max_output_bytes else ""
                )
                self._qual_var.set(float(o.jpeg_quality))
                self._maxw_var.set(float(o.max_width))
                self._request_preview()
                return

    def _refresh_preset_combo(self) -> None:
        names = ["(ninguno)"] + [p.get("name", "?") for p in self._presets]
        self._preset_combo.configure(values=names)

    def _save_preset(self) -> None:
        name = simpledialog.askstring("Guardar perfil", "Nombre del perfil:")
        if not name or not name.strip():
            return
        name = name.strip()
        for p in self._presets:
            if p.get("name") == name:
                if not messagebox.askyesno(
                    "Existe", f"«{name}» ya existe. ¿Sobrescribir?"
                ):
                    return
                p["options"] = self._gather_options().to_json_dict()
                save_presets(self._presets)
                self._preset_var.set(name)
                self._refresh_preset_combo()
                return
        self._presets.append(
            {"name": name, "options": self._gather_options().to_json_dict()}
        )
        save_presets(self._presets)
        self._preset_var.set(name)
        self._refresh_preset_combo()

    def _delete_preset(self) -> None:
        choice = self._preset_var.get()
        if choice == "(ninguno)":
            return
        if not messagebox.askyesno("Eliminar", f"¿Eliminar el perfil «{choice}»?"):
            return
        self._presets = [p for p in self._presets if p.get("name") != choice]
        save_presets(self._presets)
        self._preset_var.set("(ninguno)")
        self._refresh_preset_combo()

    def _gather_options(self) -> CompressOptions:
        kb_s = self._max_kb_var.get().strip()
        max_b = None
        if kb_s:
            try:
                max_b = max(1, int(kb_s)) * 1024
            except ValueError:
                max_b = None
        aspect = ASPECT_FROM_LABEL.get(self._aspect_var.get(), "none")
        return CompressOptions(
            max_width=int(round(self._maxw_var.get())),
            jpeg_quality=int(round(self._qual_var.get())),
            aspect_mode=aspect,
            force_jpeg=self._force_jpeg.get(),
            max_output_bytes=max_b,
        )

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="Carpeta de imágenes")
        if path:
            self._input_var.set(path)
            self._request_preview()

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Carpeta de salida")
        if path:
            self._output_var.set(path)

    def _append_log(self, line: str) -> None:
        self._log.insert("end", line + "\n")
        self._log.see("end")

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                item = self._ui_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(str(item[1]))
                elif kind == "step":
                    cur, tot = int(item[1]), int(item[2])
                    if tot <= 0:
                        self._prog.set(0)
                        self._prog_label.configure(text="0 / 0")
                    else:
                        self._prog.set(cur / tot)
                        self._prog_label.configure(text=f"{cur} / {tot}")
                elif kind == "preview":
                    bi, bo = int(item[1]), int(item[2])
                    pil_b: Image.Image = item[3]
                    pil_a: Image.Image = item[4]
                    self._ctk_before = ctk.CTkImage(
                        light_image=pil_b,
                        dark_image=pil_b,
                        size=(pil_b.width, pil_b.height),
                    )
                    self._ctk_after = ctk.CTkImage(
                        light_image=pil_a,
                        dark_image=pil_a,
                        size=(pil_a.width, pil_a.height),
                    )
                    self._lbl_before.configure(image=self._ctk_before, text="")
                    self._lbl_after.configure(image=self._ctk_after, text="")
                    pct = 0.0 if bi <= 0 else (1.0 - (bo / bi)) * 100.0
                    self._preview_info.configure(
                        text=(
                            f"Peso: {_fmt_bytes(bi)} → {_fmt_bytes(bo)} "
                            f"(ahorro ~{pct:.0f} %)"
                        )
                    )
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    def _enqueue(self, *item: Any) -> None:
        self._ui_queue.put(item)

    def _request_preview(self, *_args: Any) -> None:
        if self._preview_worker is not None and self._preview_worker.is_alive():
            return
        in_dir = Path(self._input_var.get().strip())
        opts = self._gather_options()

        def work() -> None:
            path = _first_image_in_dir(in_dir)
            if path is None:
                self._enqueue(
                    "log",
                    "Vista previa: no hay .jpg/.jpeg/.png en la carpeta de origen.",
                )
                return
            try:
                bi, bo, tb, ta = preview_compress(path, opts)
                self._enqueue("preview", bi, bo, tb, ta)
            except Exception as e:  # noqa: BLE001
                self._enqueue("log", f"Vista previa error: {e}")

        self._preview_worker = threading.Thread(target=work, daemon=True)
        self._preview_worker.start()

    def _start_compress(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return

        self._run_btn.configure(state="disabled", text="Procesando…")
        in_path = Path(self._input_var.get().strip())
        out_path = Path(self._output_var.get().strip())
        opts = self._gather_options()

        def on_step(cur: int, tot: int) -> None:
            self._enqueue("step", cur, tot)

        def on_progress(msg: str) -> None:
            self._enqueue("log", msg)

        def worker() -> None:
            try:
                process_folder(
                    in_path,
                    out_path,
                    options=opts,
                    on_progress=on_progress,
                    on_step=on_step,
                )
            finally:
                self.after(0, self._compress_finished)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _compress_finished(self) -> None:
        self._run_btn.configure(state="normal", text="Comprimir ahora")
        self._prog.set(0)
        self._save_session()

    def _export_zip(self) -> None:
        out = Path(self._output_var.get().strip())
        if not out.is_dir():
            messagebox.showerror("ZIP", "La carpeta de destino no existe.")
            return
        dest = filedialog.asksaveasfilename(
            title="Guardar ZIP",
            defaultextension=".zip",
            initialfile="instagram_output.zip",
            filetypes=[("Archivo ZIP", "*.zip")],
        )
        if not dest:
            return
        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(out.iterdir()):
                    if f.is_file() and f.suffix.lower() != ".zip":
                        zf.write(f, arcname=f.name)
            messagebox.showinfo("ZIP", f"Guardado:\n{dest}")
        except OSError as e:
            messagebox.showerror("ZIP", str(e))

    def _save_session(self) -> None:
        theme = "dark" if self._theme_var.get() == "Oscuro" else "light"
        aspect = ASPECT_FROM_LABEL.get(self._aspect_var.get(), "none")
        payload = session_payload_from_gui(
            self._input_var.get().strip(),
            self._output_var.get().strip(),
            aspect,
            self._force_jpeg.get(),
            self._max_kb_var.get(),
            int(round(self._qual_var.get())),
            int(round(self._maxw_var.get())),
            theme,
            self._preset_var.get(),
        )
        try:
            save_last_session(payload)
        except OSError:
            pass

    def _on_close(self) -> None:
        self._save_session()
        self.destroy()


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _first_image_in_dir(d: Path) -> Path | None:
    if not d.is_dir():
        return None
    for name in sorted(os.listdir(d)):
        p = d / name
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            return p
    return None


def main() -> None:
    app = CompressorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
