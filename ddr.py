#!/usr/bin/env python3
"""
DDR Simple (Dark-frame Dynamic Range Analysis) - Lightweight CLI version
Auto-installs dependencies, drag & drop RAW files/folders, outputs results in English.
"""

import os
import sys
import subprocess
import importlib
import re

# ------------------------------
# Auto-install missing dependencies
# ------------------------------
def install_package(package):
    print(f"⚠️  Missing dependency: {package}. Attempting auto-install...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package])
        print(f"✅ Successfully installed {package}")
        return True
    except Exception as e:
        print(f"❌ Failed to auto-install {package}: {e}")
        print(f"   Please run manually: pip install {package}")
        return False

def check_and_install_dependencies():
    deps = ["rawpy", "numpy"]
    for dep in deps:
        try:
            importlib.import_module(dep)
        except ImportError:
            if not install_package(dep):
                sys.exit(1)
    print("✅ All dependencies ready")

check_and_install_dependencies()

import rawpy
import numpy as np

# ------------------------------
# Path cleaning (handles escaped spaces and quotes)
# ------------------------------
def clean_path(p):
    """Convert shell-escaped spaces and remove surrounding quotes."""
    # Remove surrounding quotes first
    p = p.strip()
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1]
    # Replace backslash-space with space (common in dragged paths)
    p = re.sub(r'\\ ', ' ', p)
    # Also replace any remaining backslashes (except those part of a valid path on Windows)
    # On macOS/Linux, backslashes are not path separators, so remove them
    p = p.replace('\\', '')
    return p.strip()

# ------------------------------
# Constants
# ------------------------------
DR_JUMP_THRESH = 0.25

# ------------------------------
# Core analysis
# ------------------------------
def analyze_raw(filepath, snr=1.0):
    try:
        with rawpy.imread(filepath) as raw:
            iso = float(raw.other.iso_speed or 0)
            if iso == 0:
                iso = 100

            img = raw.raw_image.astype(np.float32)
            if img.ndim == 3:
                img = np.mean(img, axis=2)
            h, w = img.shape[:2]

            max_dn = getattr(raw, 'white_level', None)
            if max_dn is None or max_dn < 100:
                max_dn = np.percentile(img, 99.99)

            if hasattr(raw, 'black_level_per_channel') and raw.black_level_per_channel:
                blv = [b for b in raw.black_level_per_channel if b is not None]
                bl = np.mean(blv) if blv else np.percentile(img, 1)
            else:
                bl = np.percentile(img, 1)

            mh, mw = h//4, w//4
            roi = img[mh:h-mh, mw:w-mw] - bl
            rn = np.std(roi, ddof=1)

            sat = max_dn - bl
            dr = np.log2(sat / (snr * rn)) if sat>0 and rn>0 else 0.0

            return {
                'iso': iso,
                'bl': round(bl, 2),
                'rn': round(rn, 4),
                'dr': round(dr, 2),
                'file': os.path.basename(filepath),
            }
    except Exception as e:
        print(f"  ⚠️ Failed to analyze {os.path.basename(filepath)}: {e}")
        return None

def get_all_raw_files(path):
    """Return list of RAW files. Works for both file and directory."""
    raw_exts = ('.dng','.cr2','.cr3','.nef','.arw','.orf','.rw2','.pef','.raf','.3fr','.fff')
    if os.path.isfile(path):
        if path.lower().endswith(raw_exts):
            return [path]
        else:
            return []
    elif os.path.isdir(path):
        files = []
        for root, _, filenames in os.walk(path):
            for f in filenames:
                if f.lower().endswith(raw_exts):
                    files.append(os.path.join(root, f))
        return files
    else:
        return []

def classify_gain_type(iso_dr_list):
    if len(iso_dr_list) < 3:
        return "Insufficient data (need >=3 ISO points)"
    isos = [item[0] for item in iso_dr_list]
    drs = [item[1] for item in iso_dr_list]
    switches = []
    for i in range(1, len(drs)):
        if drs[i] - drs[i-1] > DR_JUMP_THRESH:
            switches.append(isos[i])
    if len(switches) >= 2:
        return f"Multi-gain (switches at ISO {', '.join(str(int(s)) for s in switches)})"
    elif len(switches) == 1:
        return f"Dual-gain (switch at ISO {int(switches[0])})"
    else:
        return "Linear / Fusion (no clear switch)"

# ------------------------------
# Main
# ------------------------------
def main():
    print("\n" + "="*60)
    print(" DDR Simple (Dark-frame Dynamic Range Analysis)")
    print(" Lightweight - Drag & drop RAW file/folder to analyze")
    print("="*60 + "\n")

    if len(sys.argv) > 1:
        raw_path = ' '.join(sys.argv[1:])
    else:
        raw_path = input("Please drag & drop a RAW file or folder, then press Enter: ").strip()

    clean_path_str = clean_path(raw_path)

    print(f"🔍 Raw input: {raw_path}")
    print(f"🔍 Cleaned path: {clean_path_str}")

    if not clean_path_str:
        print("❌ No valid path provided")
        input("Press Enter to exit...")
        sys.exit(0)

    if not os.path.exists(clean_path_str):
        print(f"❌ Path does not exist: {clean_path_str}")
        input("Press Enter to exit...")
        sys.exit(0)

    raw_files = get_all_raw_files(clean_path_str)
    print(f"🔍 Found {len(raw_files)} RAW file(s)")

    if not raw_files:
        print(f"❌ No RAW files found at: {clean_path_str}")
        print("   Supported formats: .dng, .cr2, .cr3, .nef, .arw, .orf, .rw2, .pef, .raf, .3fr, .fff")
        input("Press Enter to exit...")
        sys.exit(0)

    print(f"📸 Analyzing {len(raw_files)} file(s)...\n")

    results = []
    for f in raw_files:
        print(f"  Processing: {os.path.basename(f)} ...")
        res = analyze_raw(f)
        if res:
            results.append(res)

    if not results:
        print("❌ No files were successfully analyzed")
        input("Press Enter to exit...")
        sys.exit(0)

    results.sort(key=lambda x: x['iso'])

    print("\n" + "-"*70)
    print(f"{'ISO':>6}  {'BL(DN)':>8}  {'RN(DN)':>8}  {'DR(EV)':>8}  {'File':>30}")
    print("-"*70)
    for r in results:
        print(f"{r['iso']:6.0f}  {r['bl']:8.2f}  {r['rn']:8.4f}  {r['dr']:8.2f}  {r['file']:30}")
    print("-"*70)

    iso_dr_list = [(r['iso'], r['dr']) for r in results]
    gain_type = classify_gain_type(iso_dr_list)
    print(f"\n📊 Gain type: {gain_type}")

    print("\n✅ Analysis completed")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
