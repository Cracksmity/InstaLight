# InstaLight

Herramienta en Python para **comprimir y preparar fotos** (.jpg, .jpeg, .png) antes de subirlas a **Instagram**: menos peso, ancho máximo configurable, recortes centrados típicos del feed y de historias, y opción de forzar salida JPEG.

## Requisitos

- Python 3.10 o superior (recomendado 3.11+)
- Windows (la app gráfica usa `windnd` para arrastrar y soltar carpetas)

## Instalación

```bash
cd ruta/al/proyecto
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Icono de ventana (opcional):

```bash
python scripts\gen_icon.py
```

## Uso

### Interfaz gráfica

```bash
python gui.py
```

En la parte superior verás **InstaLight**. Puedes elegir carpetas de origen y destino, ajustar recorte (1:1, 4:5, 9:16), calidad JPEG, ancho máximo en píxeles, límite aproximado de peso en KB (ideal con «Solo JPEG»), ver **vista previa** antes/después, exportar la salida como **ZIP** y arrastrar una **carpeta** sobre la ventana para fijar el origen (Windows).

### Línea de comandos

```bash
python cli.py --input input --output output
```

Opciones útiles:

| Opción | Descripción |
|--------|-------------|
| `--aspect` | Valores: `none`, `1:1`, `4:5`, `9:16` (recorte centrado) |
| `--force-jpeg` | Salida siempre `.jpg` |
| `--max-width N` | Ancho máximo en px (por defecto 2000) |
| `--quality N` | Calidad JPEG 1–95 (por defecto 80) |
| `--max-kb N` | Tamaño máximo aproximado por archivo en KB (JPEG) |

Ejemplo:

```bash
python cli.py -i .\fotos -o .\salida --aspect 4:5 --force-jpeg --max-kb 500
```

El código de salida de `cli.py` es distinto de cero si hubo errores en algún archivo.

## Empaquetado (ejecutable)

Con [PyInstaller](https://pyinstaller.org/) instalado (`pip install pyinstaller`):

```bash
build.bat
```

Se genera un ejecutable cuyo nombre por defecto es **InstaLight** (ver `build.bat`).

## Datos de usuario

Perfiles y última sesión se guardan en el directorio de datos de la aplicación (por ejemplo `%LOCALAPPDATA%\InstaLight\` en Windows). Versiones anteriores usaban la carpeta `CompresorInstagram` en el mismo tipo de ruta; si no ves tus perfiles, copia manualmente los `.json` a la carpeta nueva.

Repositorio: [github.com/Cracksmity/InstaLight](https://github.com/Cracksmity/InstaLight).

## Licencia

MIT — ver el archivo [LICENSE](LICENSE).
