# Poshmark Sharing Bot v2

A modular, maintainable Poshmark sharing automation tool.

## Project Structure

The codebase has been refactored into logical, maintainable modules:

### Core Files
- **`gui.py`** (463 lines) - Main GUI application with automatic closet persistence
- **`models.py`** (38 lines) - Data models and utility functions
- **`__init__.py`** - Package initialization

### Automation Modules
- **`automation.py`** (108 lines) - Main orchestrator (was 1,241 lines!)
- **`browser_manager.py`** (46 lines) - Browser setup and management
- **`login_handler.py`** (339 lines) - Poshmark login logic
- **`sharing_logic.py`** (752 lines) - Core sharing functionality

### Backup
- **`automation_old.py`** - Original monolithic automation file (1,241 lines)

## Key Features

### 🚀 **Automatic Closet Persistence**
- Closets are automatically saved after each completion
- List persists between app sessions
- No more manual reloading of closet lists!

### 🧹 **Clean, Modular Code**
- **Before**: 1,241 lines in one file
- **After**: 4 focused modules totaling 1,245 lines
- Each module has a single responsibility
- Much easier to maintain and debug

### 📱 **Enhanced User Experience**
- Automatic saving on all changes
- Better logging and progress tracking
- Clear feedback when closets are completed
- Confirmation dialogs for destructive operations

## Module Responsibilities

### `automation.py` - Main Orchestrator
- Coordinates the entire sharing process
- Manages the flow between components
- Handles total shares limits and progress tracking

### `browser_manager.py` - Browser Management
- Clean browser setup and teardown
- Context manager for automatic cleanup
- Browser state management

### `login_handler.py` - Authentication
- Handles Poshmark login process
- Manages consent popups and 2FA
- Robust fallback strategies for different login scenarios

### `sharing_logic.py` - Core Functionality
- Item loading and scrolling
- Share button detection
- Modal handling and sharing dialogs
- Progress tracking and pacing

### `gui.py` - User Interface
- Main application window
- Automatic closet list management
- Real-time progress updates
- Persistent settings

## Benefits of Refactoring

1. **Maintainability**: Each module has a clear, focused purpose
2. **Debugging**: Issues can be isolated to specific modules
3. **Testing**: Individual components can be tested separately
4. **Extensibility**: New features can be added to appropriate modules
5. **Readability**: Much easier to understand and modify code
6. **Collaboration**: Multiple developers can work on different modules

## Usage

The application works exactly the same as before, but now:
- Closets are automatically saved and loaded
- Completed closets are automatically removed
- The code is much more maintainable
- Better error handling and logging

## File Sizes Comparison

| File | Lines | Purpose |
|------|-------|---------|
| `automation.py` | 108 | Main orchestrator |
| `browser_manager.py` | 46 | Browser management |
| `login_handler.py` | 339 | Login handling |
| `sharing_logic.py` | 752 | Core sharing logic |
| **Total New** | **1,245** | **Modular structure** |
| `automation_old.py` | 1,241 | Old monolithic file |

The refactoring maintains the same functionality while dramatically improving code organization and maintainability.
