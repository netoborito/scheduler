# Sample Data

This directory contains sample backlog files for testing the scheduler.

## EAMExport.xlsx

Sample work order backlog exported from an EAM (Enterprise Asset Management) system.

**Format:**
- **Work Order**: Work order ID (numeric)
- **Priority**: Text format like "1-Critical", "2-Urgent/Scheduled", "3-First Opportunity", etc.
- **Status**: Current status (e.g., "Open - Ready to Schedule")
- **Type**: Work order type (e.g., "Corrective")
- **Equipment**: Equipment identifier
- **Description**: Work order description
- **Assigned To**: Assigned technician
- **Creation Date**: When the work order was created
- **Sched Start Date**: Scheduled start date (used as due date for optimization)
- **Department**: Department code
- **Safety**: Safety flag (Yes/No)
- **Persons Required**: Number of people needed
- **Estimated Hs**: Estimated hours (used as duration_hours)
- **Trade**: Trade/skill required
- **Class**: Classification

The parser automatically detects this format and maps:
- `Work Order` → `id`
- `Estimated Hs` → `duration_hours`
- `Priority` → `priority` (converted from text to numeric: 1-Critical=10, 2-Urgent=8, 3-First Opportunity=5, etc.)
- `Sched Start Date` → `due_date`
- `Description` → `description`
