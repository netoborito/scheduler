# Debugging Guide

This guide explains how to use the debugging configurations in VS Code/Cursor.

## Prerequisites

1. **Install Python Extension**: Make sure you have the Python extension installed in Cursor/VS Code
   - Open Extensions (Ctrl+Shift+X)
   - Search for "Python" by Microsoft
   - Install it

2. **Install debugpy**: The debugger uses `debugpy` (usually comes with Python extension)
   ```bash
   pip install debugpy
   ```

## Debug Configurations

The `.vscode/launch.json` file contains several debug configurations:

### 1. Python: FastAPI App
   - **Purpose**: Debug the FastAPI application with hot reload
   - **Usage**: 
     - Set breakpoints in your code
     - Press F5 or go to Run → Start Debugging
     - Select "Python: FastAPI App"
   - **Features**:
     - Auto-reload on code changes
     - Breakpoints work in Python code
     - Can debug API requests/responses

### 2. Python: Debugger Script
   - **Purpose**: Debug the interactive debugger script
   - **Usage**: Run `debug.py` with breakpoints
   - **Best for**: Testing individual components

### 3. Python: Current File
   - **Purpose**: Debug whatever Python file you have open
   - **Usage**: Open a file, set breakpoints, press F5
   - **Best for**: Quick debugging of individual scripts

### 4. Python: FastAPI (No Reload)
   - **Purpose**: Debug FastAPI without auto-reload (faster, more stable)
   - **Usage**: Same as FastAPI App but without reload
   - **Best for**: When reload is causing issues

### 5. Python: Debugger Script (All Tests)
   - **Purpose**: Run all debugger tests with debugging
   - **Usage**: Debug the full test suite

### 6. Python: Debugger Script (Shift Tests)
   - **Purpose**: Debug shift CRUD operations specifically

### 7. Python: Debugger Script (Optimizer Tests)
   - **Purpose**: Debug the schedule optimizer specifically

## How to Debug

### Basic Debugging Steps:

1. **Set Breakpoints**:
   - Click in the gutter (left of line numbers) to add a breakpoint
   - Red dot appears when breakpoint is set

2. **Start Debugging**:
   - Press `F5` or click the Run and Debug icon (play button with bug)
   - Select a configuration from the dropdown
   - Click the green play button

3. **Debug Controls**:
   - **Continue (F5)**: Resume execution
   - **Step Over (F10)**: Execute current line, don't enter functions
   - **Step Into (F11)**: Enter function calls
   - **Step Out (Shift+F11)**: Exit current function
   - **Restart (Ctrl+Shift+F5)**: Restart debugging
   - **Stop (Shift+F5)**: Stop debugging

4. **Debug Panels**:
   - **Variables**: See current variable values
   - **Watch**: Monitor specific expressions
   - **Call Stack**: See function call hierarchy
   - **Breakpoints**: Manage all breakpoints

### Debugging FastAPI Endpoints

1. Set breakpoints in your route handlers (e.g., `app/main.py`)
2. Start "Python: FastAPI App" configuration
3. Make a request to your API (via browser or Postman)
4. Execution will pause at your breakpoints
5. Inspect request data, variables, and step through code

### Debugging Tips

- **Conditional Breakpoints**: Right-click a breakpoint → Edit Breakpoint → Add condition
- **Logpoints**: Right-click → Add Logpoint (logs without stopping)
- **Exception Breakpoints**: Break on exceptions (Debug panel → Breakpoints)
- **Just My Code**: Disabled by default to debug into library code if needed

## Common Issues

### "Module not found" errors
- Make sure `PYTHONPATH` includes `${workspaceFolder}`
- Verify virtual environment is activated
- Check that dependencies are installed

### Breakpoints not hitting
- Ensure you're using the correct debug configuration
- Check that the code path is actually being executed
- Verify `justMyCode` is set to `false` if debugging library code

### FastAPI not reloading
- Use "Python: FastAPI App" (with --reload)
- Check that file changes are being saved
- Restart debugger if needed

## Example: Debugging an API Request

1. Open `app/main.py`
2. Set a breakpoint in the `api_optimize` function (line ~40)
3. Start "Python: FastAPI App" debug configuration
4. Open browser to `http://127.0.0.1:8000`
5. Upload a file and click "Optimize & Visualize"
6. Execution pauses at your breakpoint
7. Inspect `backlog`, `work_orders`, and other variables
8. Step through the code to see how it processes the request

## Example: Debugging Shift Operations

1. Open `app/services/shift_service.py`
2. Set a breakpoint in `add_shift` function
3. Start "Python: Debugger Script (Shift Tests)" configuration
4. Execution pauses when shift is being added
5. Inspect the `shift` object and see how it's saved
