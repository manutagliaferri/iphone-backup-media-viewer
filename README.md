# iPhone Backup Media Viewer (BackupManager) 📱💾

![macOS Support](https://img.shields.io/badge/macOS-Apple_Silicon_Ready-white?logo=apple)
![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)

**BackupManager** is a native macOS application that allows you to easily browse, view, and extract photos and videos from your local iPhone backups without needing to restore the backup to a device. 

Whether your backup was created through Finder, iTunes, or manually copied, this app intelligently detects the format and provides a lightning-fast gallery interface to recover your media in its original, lossless quality.

---

## ✨ Features

- **Smart Format Detection:** Automatically reads different iPhone backup structures:
  - 🗃️ **Standard iTunes/Finder Backups:** Parses the SQLite `Manifest.db` to reconstruct original filenames, dates, and paths.
  - 📸 **Snapshot Backups (iOS 17+ / macOS Sonoma):** Reads modern snapshot backups where files are heavily hashed without extensions. It uses magic bytes to accurately detect media types.
  - 📁 **Direct Scan:** Falls back to recursively scanning any generic folder for media files.
- **Lightning Fast Gallery:** Optimized lazy-loading grid view capable of handling thousands of media files with a smart LRU thumbnail cache.
- **HEIC & Video Support:** Built-in support for Apple's HEIC/HEIF image formats and various video codecs using hardware-accelerated fallback generation.
- **Lossless Extraction:** Export your selected memories to any folder without losing metadata or compression quality.

## 🚀 Installation (End Users)

You don't need to be a developer to use this app. 

1. Go to the [Releases](../../releases) page of this repository.
2. Download the latest `BackupManager-macOS-v1.0.zip` file.
3. Extract the zip file on your Mac.
4. Drag and drop the `BackupManager.app` into your `Applications` folder or keep it on your Desktop.
5. Double-click to run! *(Note: since the app is not notarized by the App Store, macOS might ask you to right-click -> Open the first time you launch it).*

## 🛠️ Running from Source (Developers)

If you want to modify the code or run it directly via Python, you'll need **Homebrew** and **Python 3.11** installed.

### Prerequisites

```bash
# Install Homebrew Python 3.11 (required for proper tkinter GUI support on macOS)
brew install python-tk@3.11

# Clone the repository
git clone https://github.com/manutagliaferri/iphone-backup-media-viewer.git
cd iphone-backup-media-viewer

# Install dependencies
/opt/homebrew/bin/python3.11 -m pip install -r requirements.txt
```

*(Dependencies include `Pillow`, `pillow-heif`, and `opencv-python`)*

### Launching the app

You can run the application directly from the terminal:

```bash
/opt/homebrew/bin/python3.11 src/main.py
```

Or you can use the provided build script to generate a standalone macOS `.app` bundle:

```bash
bash build_app.sh
```

## 📂 Where are iPhone backups located on macOS?

By default, macOS stores local iPhone backups in a hidden folder. When you open the app and click **"Open Backup"**, press `Cmd + Shift + G` and paste this path to find them:

`~/Library/Application Support/MobileSync/Backup/`

---
*Developed for macOS Apple Silicon (M1/M2/M3) architecture.*
