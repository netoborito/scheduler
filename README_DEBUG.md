# Debugger Usage Guide

The `debug.py` script provides a comprehensive testing and debugging interface for the Industrial Maintenance Scheduler.

## Quick Start

Run the interactive debugger:
```bash
python debug.py
```

## Command Line Options

Run specific tests directly:
```bash
# Test date utilities
python debug.py date

# Test shift CRUD operations
python debug.py shift

# Test Excel parsing
python debug.py excel

# Test schedule optimizer
python debug.py optimize

# Test Excel output generation
python debug.py output

# Run all tests
python debug.py all
```

## Interactive Menu

When run without arguments, the debugger provides an interactive menu:

1. **Test Date Utilities** - Tests the `get_next_monday()` function
2. **Test Shift CRUD Operations** - Tests creating, reading, updating, and deleting shifts
3. **Test Work Order Parsing** - Tests parsing work orders from the sample Excel file
4. **Test Schedule Optimizer** - Tests the OR-Tools optimization engine
5. **Test Excel Schedule Output** - Tests generating schedule Excel files
6. **Run All Tests** - Executes all test functions sequentially
7. **View Current Shifts** - Displays all configured shifts from `data/shifts.json`
0. **Exit** - Quit the debugger

## What Each Test Does

### Date Utilities Test
- Shows today's date and day of week
- Calculates and displays the next Monday
- Shows days until next Monday

### Shift CRUD Test
- Creates test shifts
- Reads and displays all shifts
- Retrieves a specific shift by trade
- Updates a shift's properties
- Deletes test shifts (cleanup)

### Work Order Parsing Test
- Loads `samples/EAMExport.xlsx`
- Parses work orders using the Excel parser
- Displays sample work orders with their properties
- Shows priority, duration, trade, and description

### Schedule Optimizer Test
- Creates sample work orders
- Runs the optimization algorithm
- Displays the generated schedule
- Shows assignments with dates and resources

### Excel Output Test
- Creates a sample schedule
- Generates an Excel workbook
- Displays workbook structure and sample rows

## Tips

- The shift CRUD test creates temporary test shifts that are automatically cleaned up
- Make sure `samples/EAMExport.xlsx` exists for Excel parsing tests
- The optimizer test uses sample data - modify it to test with your own work orders
- All tests include error handling and will show detailed error messages if something fails

## Troubleshooting

If you encounter import errors:
- Make sure you're running from the project root directory
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check that the virtual environment is activated

If Excel parsing fails:
- Verify `samples/EAMExport.xlsx` exists
- Check that the file format matches the expected EAM export format

If optimizer tests show no assignments:
- This may be normal if there are capacity constraints
- Try adjusting work order durations or adding more resources
