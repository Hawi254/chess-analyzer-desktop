# Chess Analyzer Desktop v1.0

**A high-performance, open-source desktop application for deep, engine-powered analysis of your chess games.**

This application provides a rich graphical user interface built on PySide6 for our powerful, Python-based chess analysis engine. It is designed for serious chess players, coaches, and enthusiasts who want to gain deep, actionable insights into their games to facilitate improvement.

---

## Table of Contents

- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [Architectural Overview](#architectural-overview)
- [Development](#development)
- [Contributing](#contributing)

---

## Key Features

The Chess Analyzer Desktop application offers a comprehensive suite of tools to analyze your chess performance.

### Core Analysis

*   **Deep Engine Analysis:** Utilizes the powerful Stockfish chess engine to analyze every move of your games, identifying blunders, mistakes, inaccuracies, and brilliant moves.
*   **PGN Annotation:** Automatically generates a new, richly annotated PGN file with engine evaluations, move classifications, and a high-level game narrative.
*   **CSV Reporting:** Exports a detailed CSV summary for all analyzed games, perfect for external data analysis.

### The "Player's Mind" Dashboard

A multi-tabbed, interactive dashboard designed to provide a deep, data-driven story of your chess journey.

#### Command Center (Overview)
*   **At-a-Glance KPIs:** View your overall accuracy, win/loss/draw record, and total games analyzed, complete with "delta" indicators showing your recent form.
*   **Performance Funnel:** A unique visualization that shows your ability to convert advantageous positions into wins.
*   **"Opponent Cloud" Trend Chart:** A rich scatter plot that visualizes your accuracy over time, where the color of each point is the game result and its size is the opponent's rating.

#### Arsenal (Opening Repertoire)
*   **Interactive Performance Table:** A sortable, filterable table of every opening you've played, showing your W/L/D record and average accuracy in each.
*   **"Cognitive Dissonance" Panel:** A deep-dive tool that highlights the key positions within an opening where the time you spent thinking did not correlate with the quality of the move you played, revealing critical knowledge gaps.

#### Crucible (Tactical & Psychological Analysis)
*   **Decision-Making Matrix:** A powerful bubble chart plotting time spent vs. positional complexity, with bubble size and color representing the severity of your errors. This provides a deep psychological profile of your decision-making habits.
*   **Tactical Signature Heatmap:** An intuitive heatmap that shows which specific tactical motifs (e.g., Forks, Pins) you most frequently miss, providing a clear path for targeted puzzle practice.
*   **Interactive Blunder Reel:** A scrollable list of your worst blunders, complete with a mini-board showing the position. Clicking any blunder immediately navigates to that exact move in the full "Annotated Game" view.

### Detailed Game Review

*   **Interactive Chessboard:** A clean, SVG-rendered chessboard that updates as you navigate through a game.
*   **Rich Move List:** A fully annotated move list with icons and color-coding for blunders (❌), mistakes (⚠️), great moves (!), and brilliant moves (✨).

---

## Technology Stack

*   **Language:** Python 3.12+
*   **GUI Framework:** PySide6 (Qt 6 for Python)
*   **Charting:** PyQtGraph
*   **UI Theming:** Qt-Material
*   **Concurrency:** QThread, asyncio
*   **Core Chess Logic:** `python-chess`
*   **Database:** SQLite (via `aiosqlite`)
*   **Dependency Management:** Poetry

---

## Installation & Setup

Follow these steps to get the application running locally.

### Prerequisites

1.  **Python 3.12 or higher.**
2.  **Poetry:** The project uses Poetry for dependency management. See the [official documentation](https://python-poetry.org/docs/#installation) for installation instructions.
3.  **Stockfish Chess Engine:** You must have a modern version of the Stockfish engine installed and available in your system's `PATH`. You can download it from the [official Stockfish website](https://stockfishchess.org/download/).

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/chess-analyzer-desktop.git
    cd chess-analyzer-desktop
    ```

2.  **Install dependencies using Poetry:**
    ```bash
    poetry install --with dev
    ```
    This command creates a virtual environment and installs all required production and development dependencies.

3.  **Compile Qt Resources:**
    The UI uses custom icons. Compile them into a Python module by running:
    ```bash
    pyside6-rcc resources.qrc -o resources_rc.py
    ```

---

## Usage

Once installed, you can run the application in two modes:

### 1. Standard Mode

For normal use, run the main application entry point:
```bash
poetry run python main.py

2. Development Mode (with Live Reload)

For development, use the run_dev.py script. It uses watchgod to monitor your source files and will automatically restart the application whenever you save a .py file, providing a rapid development loop.


poetry run python run_dev.py

Architectural Overview

The application is built on a clean, modern architecture designed for maintainability, testability, and responsiveness.

Humble Object (Presenter) Pattern: The GUI (Views) is strictly separated from the application logic (Presenter/Controller). The MainWindow acts as the Presenter, orchestrating the UI and delegating all business logic to the AppController.

Multi-Threaded Concurrency: All long-running tasks (game analysis, database queries) are executed on dedicated background QThreads, ensuring the UI never freezes. Inter-thread communication is handled safely via Qt's signals and slots mechanism.

Centralized Services: Critical services like the DatabaseManager are implemented as persistent, application-lifetime services to manage resources and concurrency effectively.

Modular, Component-Based UI: The UI is composed of reusable, self-contained QWidget components (e.g., CardWidget, KpiCardWidget), making the views clean and easy to extend.

Development

Code Formatting: This project uses black for code formatting and ruff for linting. It is recommended to configure your editor to run these automatically on save.

Dependencies: All dependencies are managed in pyproject.toml. To add a new dependency, use poetry add <package-name>.

Contributing

Contributions are welcome. Please feel free to open an issue to report a bug or suggest a new feature. If you would like to contribute code, please fork the repository and submit a Pull Request.


