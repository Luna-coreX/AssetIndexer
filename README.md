<div align="center">

# AssetIndexer

**Fast • Modern • Local Asset Management**

*A modern desktop application for indexing, organizing and exploring your digital assets.*

<img src="assets/logo.png" width="100%">

<br>

![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge\&logo=python\&logoColor=white)
![Qt](https://img.shields.io/badge/PySide6-Qt-41CD52?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)

</div>

---

## Overview

AssetIndexer is a high-performance desktop application designed to help developers, artists and content creators organize massive local asset libraries.

Instead of manually browsing folders, AssetIndexer builds a searchable index of your assets, providing instant search, previews, dependency visualization and intelligent organization tools.

Whether you're working with Unity projects, Godot assets, Blender models, textures, audio libraries or fonts, AssetIndexer helps you find exactly what you need in seconds.

---

# Features

### Search & Indexing

* ⚡ Instant Full-Text Search (SQLite FTS5)
* 🔎 Smart camelCase tokenization
* 📁 Multi-folder indexing
* 🚀 Fast local database
* 🔄 Automatic re-indexing

---

### Asset Management

* 🏷️ Tags
* 🎨 Color Labels
* ⭐ Favorites
* 📂 Advanced Sorting
* 📄 Detailed File Information

---

### Preview

* 🖼️ Image Preview
* 🔤 Font Preview
* 🎵 Audio Playback
* 📦 Metadata Viewer

---

### Analysis

* 📊 Storage Statistics Dashboard
* 📦 Duplicate Detection
* 🖼️ Similar Image Search (Perceptual Hash)

---

### Dependency Graph

Visualize relationships between assets.

Supported formats:

* Unity
* Godot
* glTF
* OBJ

Features:

* Interactive Graph View
* Dependency Lists
* Referenced Assets
* Referencing Assets

---

### User Experience

* 🖱️ Drag & Drop Support
* 📋 Native Context Menu
* 🎨 4 Built-in Themes
* 💾 Persistent Settings
* ✨ Smooth UI Animations

---

# Screenshots

## Main Window

> <img src="assets/main_window.png" width="100%">

---

## Dependency Graph

> *(Add screenshot or GIF here)*

---

## Statistics Dashboard

> *(Add screenshot here)*

---

## Duplicate Detection

> *(Add screenshot here)*

---

# Technology Stack

| Category            | Technology   |
| ------------------- | ------------ |
| Language            | Python       |
| GUI                 | PySide6      |
| Database            | SQLite       |
| Search Engine       | SQLite FTS5  |
| Image Processing    | Pillow       |
| Image Similarity    | ImageHash    |
| Graph Visualization | NetworkX     |
| Drag & Drop         | Qt Framework |

---

# Performance Highlights

✔ SQLite Full-Text Search (FTS5)

✔ Smart Tokenization

✔ Perceptual Image Hashing

✔ Local Database

✔ Dependency Analysis

✔ Interactive Graph Rendering

✔ Modern Qt Interface

---

# Project Structure

```text
AssetIndexer/

├── assetindexer/
│   ├── ui/
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── imaging.py
│   ├── scanner.py
│   └── theme.py
│
├── main.py
├── requirements.txt
└── README.md
```

---

# Installation

Clone the repository

```bash
git clone https://github.com/Luna-coreX/AssetIndexer.git
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run

```bash
python main.py
```

---

# Roadmap

## Completed

* [x] Full-Text Search
* [x] SQLite Database
* [x] Image Preview
* [x] Font Preview
* [x] Audio Playback
* [x] Duplicate Detection
* [x] Similar Image Search
* [x] Dependency Graph
* [x] Statistics Dashboard
* [x] Drag & Drop
* [x] Tags
* [x] Favorites
* [x] Themes

---

# License

Released under the MIT License.

---

<div align="center">

### Built for developers, artists and creators.

</div>
