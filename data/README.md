# Data Directory

This directory contains JSON configuration files for the scheduler.

## shifts.json

Stores shift configurations with the following structure:

```json
[
  {
    "trade": "NC-E/I",
    "shift_duration_hours": 8,
    "monday": true,
    "tuesday": true,
    "wednesday": true,
    "thursday": true,
    "friday": true,
    "saturday": false,
    "sunday": false,
    "technicians_per_crew": 2
  }
]
```

### Fields:
- **trade**: Trade/resource type identifier (e.g., "NC-E/I")
- **shift_duration_hours**: Duration of the shift in hours (integer)
- **monday** through **sunday**: Boolean flags indicating which days the shift is active
- **technicians_per_crew**: Number of technicians in this crew (integer)

### Usage:

The shift data can be managed using functions in `app/services/shift_service.py`:
- `load_shifts()` - Load all shifts from JSON
- `save_shifts()` - Save shifts to JSON
- `get_shift_by_trade()` - Get a specific shift by trade name
- `add_shift()` - Add a new shift
- `update_shift()` - Update an existing shift
- `delete_shift()` - Delete a shift
- `get_all_shifts()` - Get all shifts
