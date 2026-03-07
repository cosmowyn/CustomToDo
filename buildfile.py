#!/usr/bin/env python3
"""
Cross-platform PyInstaller build helper (Windows + macOS)

Changes in this version:
- macOS icon picker allows selecting common image formats (.png/.jpg/.jpeg/.bmp/.tiff/.gif).
- If the selected icon is NOT .icns, the script converts it to .icns automatically using:
    - sips (resize)
    - iconutil (iconset -> icns)
  and saves it under: <project_root>/build_assets/icons/<APP_NAME>.icns
  Then uses that .icns for the PyInstaller build.

Notes:
- Splash is skipped on macOS (PyInstaller splash not supported there).
- Runs PyInstaller via venv python (no need to "activate" the venv in the shell).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---- CONFIG ----
APP_NAME = "CustomTaskManager"
ENTRY_SCRIPT = "main.py"   # your app entrypoint
VENV_DIR = ".venv"         # change if your venv folder differs
# ---------------


def _is_windows() -> bool:
    return os.name == "nt"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _venv_python(venv_dir: Path) -> Path:
    if _is_windows():
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _ensure_venv_python() -> Path:
    venv = Path(VENV_DIR).resolve()
    py = _venv_python(venv)

    if not py.exists():
        raise FileNotFoundError(
            f"Could not find virtualenv Python at:\n  {py}\n"
            f"Make sure your venv exists at '{VENV_DIR}' (or edit VENV_DIR)."
        )
    return py


def _ensure_pyinstaller(venv_python: Path) -> None:
    # Check import inside the venv; this is the real source of truth.
    try:
        subprocess.run(
            [str(venv_python), "-c", "import PyInstaller, sys; print('PyInstaller OK', PyInstaller.__version__, sys.executable)"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        print("PyInstaller not importable in this venv. Installing pyinstaller...")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-U", "pyinstaller", "pyinstaller-hooks-contrib"],
            check=True,
        )
        subprocess.run(
            [str(venv_python), "-c", "import PyInstaller, sys; print('PyInstaller OK', PyInstaller.__version__, sys.executable)"],
            check=True,
            capture_output=True,
            text=True,
        )

def _pick_file(title: str, filetypes: list[tuple[str, str]]) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        raise RuntimeError("tkinter is required for file picker but could not be imported.") from e

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    root.destroy()

    return path or None


def _validate_icon_path(icon_path: str) -> None:
    ext = Path(icon_path).suffix.lower()
    if _is_windows():
        if ext != ".ico":
            raise ValueError("On Windows, the icon must be a .ico file.")
    elif _is_macos():
        # On macOS we allow images; conversion happens if not .icns
        if ext not in (".icns", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"):
            raise ValueError("On macOS, icon must be .icns or a common image format.")
    else:
        if ext not in (".png", ".ico", ".icns"):
            raise ValueError("On Linux, please use .png (preferred) or .ico/.icns.")


def _require_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        raise RuntimeError(
            f"Required tool '{tool_name}' not found on PATH.\n"
            f"On macOS, '{tool_name}' should normally be available."
        )


def _convert_image_to_icns_mac(image_path: Path, project_root: Path, app_name: str) -> Path:
    """
    Converts any supported image to .icns on macOS using sips + iconutil.
    Output:
      <project_root>/build_assets/icons/<app_name>.icns
    """
    if not _is_macos():
        raise RuntimeError("ICNS conversion is only supported on macOS in this script.")

    _require_tool("sips")
    _require_tool("iconutil")

    out_dir = project_root / "build_assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    iconset_dir = out_dir / f"{app_name}.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir, ignore_errors=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # Apple iconset sizes
    # icon_16x16.png, icon_16x16@2x.png (32), ..., icon_512x512@2x.png (1024)
    sizes = [16, 32, 128, 256, 512]
    for base in sizes:
        # 1x
        out_png_1x = iconset_dir / f"icon_{base}x{base}.png"
        subprocess.run(
            ["sips", "-z", str(base), str(base), str(image_path), "--out", str(out_png_1x)],
            check=True,
            capture_output=True,
            text=True,
        )

        # 2x
        base2 = base * 2
        out_png_2x = iconset_dir / f"icon_{base}x{base}@2x.png"
        subprocess.run(
            ["sips", "-z", str(base2), str(base2), str(image_path), "--out", str(out_png_2x)],
            check=True,
            capture_output=True,
            text=True,
        )

    out_icns = out_dir / f"{app_name}.icns"
    if out_icns.exists():
        out_icns.unlink(missing_ok=True)

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out_icns)],
        check=True,
        capture_output=True,
        text=True,
    )

    # cleanup iconset folder (optional; keep if you want to inspect)
    shutil.rmtree(iconset_dir, ignore_errors=True)

    if not out_icns.exists():
        raise RuntimeError("ICNS conversion failed: output file was not created.")
    return out_icns


def _prepare_icon_for_platform(icon: str | None, project_root: Path) -> str | None:
    if not icon:
        return None

    _validate_icon_path(icon)
    p = Path(icon).resolve()

    if _is_macos():
        if p.suffix.lower() == ".icns":
            return str(p)
        # Convert image -> icns
        print(f"Converting icon to .icns: {p}")
        icns_path = _convert_image_to_icns_mac(p, project_root, APP_NAME)
        print(f"Using generated icns: {icns_path}")
        return str(icns_path)

    # Windows/Linux: return as-is (validated)
    return str(p)


def _pyinstaller_cmd(
    venv_python: Path,
    entry_script: Path,
    app_name: str,
    splash: str | None,
    icon: str | None,
) -> list[str]:
    cmd = [
        str(venv_python),
        "-m",
        "PyInstaller",
        str(entry_script),
        "--name",
        app_name,
        "--noconfirm",
        "--clean",
        "--windowed",  # no console
        "--log-level", "INFO",
    ]

    # Standalone: onefile on Windows, onedir on macOS/Linux
    if _is_windows():
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Splash (optional) - explicitly skip on macOS
    if splash and not _is_macos():
        cmd.extend(["--splash", splash])

    # Icon (optional)
    if icon:
        cmd.extend(["--icon", icon])

    # Bundle resources folder if present
    resources_dir = entry_script.parent / "resources"
    if resources_dir.exists() and resources_dir.is_dir():
        sep = ";" if _is_windows() else ":"
        cmd.extend(["--add-data", f"{resources_dir}{sep}resources"])

    return cmd


def main() -> int:
    project_root = Path(__file__).resolve().parent
    entry_script = (project_root / ENTRY_SCRIPT).resolve()
    if not entry_script.exists():
        print(f"ERROR: entry script not found: {entry_script}")
        return 1

    print(f"OS: {platform.system()}  |  Project: {project_root}")

    venv_python = _ensure_venv_python()
    _ensure_pyinstaller(venv_python)

    # Splash (optional) - skip on macOS entirely
    splash = None
    if not _is_macos():
        splash = _pick_file(
            title="Select splash image (optional)",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp"),
                ("All files", "*.*"),
            ],
        )
    else:
        print("Note: PyInstaller splash is skipped on macOS.")

    # Icon selection
    icon = None
    if _is_windows():
        icon = _pick_file(
            title="Select .ico icon for Windows (optional)",
            filetypes=[("Windows icon (.ico)", "*.ico"), ("All files", "*.*")],
        )
    elif _is_macos():
        icon = _pick_file(
            title="Select icon for macOS (optional: .icns or image)",
            filetypes=[
                ("macOS icon (.icns)", "*.icns"),
                ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif"),
                ("All files", "*.*"),
            ],
        )
    else:
        icon = _pick_file(
            title="Select app icon for Linux (optional; .png preferred)",
            filetypes=[("Images", "*.png *.ico *.icns"), ("All files", "*.*")],
        )

    # Prepare icon (convert on macOS if needed)
    icon = _prepare_icon_for_platform(icon, project_root) if icon else None

    # Clean old build artifacts
    for d in ("build", "dist"):
        p = project_root / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    spec_file = project_root / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink(missing_ok=True)

    cmd = _pyinstaller_cmd(
        venv_python=venv_python,
        entry_script=entry_script,
        app_name=APP_NAME,
        splash=splash,
        icon=icon,
    )

    print("\nRunning:")
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    print()

    try:
        result = subprocess.run(cmd, cwd=str(project_root), text=True, capture_output=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode != 0:
            print("\nBuild failed.")
            return result.returncode
    except Exception as e:
        print("\nBuild failed.")
        print(str(e))
        return 1

    # Validate expected build output exists
    out_path = project_root / "dist"
    if _is_windows():
        expected = out_path / f"{APP_NAME}.exe"
    else:
        expected = out_path / APP_NAME

    if not expected.exists():
        print("\nERROR: PyInstaller returned success, but expected output was not found:")
        print(f"Expected: {expected}")

        if out_path.exists():
            print("\nContents of dist/:")
            for p in out_path.rglob("*"):
                rel = p.relative_to(out_path)
                print(f"  {rel}")
        else:
            print("\nNote: dist/ folder does not exist at all.")

        print("\nPossible causes:")
        print("- Antivirus/EDR quarantined the output immediately.")
        print("- Build actually failed but only logged to stderr.")
        print("- APP_NAME mismatch vs produced artifact name.")
        return 2

    print("\nBuild complete.")
    print(f"Output folder: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())