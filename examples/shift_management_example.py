"""Example usage of shift management functions."""
from app.models.shift import Shift
from app.services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    update_shift,
)


def main():
    """Demonstrate shift management operations."""

    # Example 1: Create and add a new shift
    print("=== Adding a new shift ===")
    new_shift = Shift(
        trade="NC-E/I",
        shift_duration_hours=8,
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=False,
        sunday=False,
        technicians_per_crew=2,
    )
    try:
        add_shift(new_shift)
        print(f"✓ Added shift for trade: {new_shift.trade}")
    except ValueError as e:
        print(f"✗ Error: {e}")

    # Example 2: Get all shifts
    print("\n=== Getting all shifts ===")
    all_shifts = get_all_shifts()
    for shift in all_shifts:
        active_days = shift.get_active_days()
        print(
            f"Trade: {shift.trade}, "
            f"Duration: {shift.shift_duration_hours}h, "
            f"Days: {', '.join(active_days)}, "
            f"Crew size: {shift.technicians_per_crew}"
        )

    # Example 3: Get a specific shift by trade
    print("\n=== Getting shift by trade ===")
    shift = get_shift_by_trade("NC-E/I")
    if shift:
        print(f"Found shift: {shift.trade}, Duration: {shift.shift_duration_hours}h")
    else:
        print("Shift not found")

    # Example 4: Update an existing shift
    print("\n=== Updating a shift ===")
    updated_shift = Shift(
        trade="NC-E/I",
        shift_duration_hours=10,  # Changed from 8 to 10
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=True,  # Added Saturday
        sunday=False,
        technicians_per_crew=3,  # Increased crew size
    )
    try:
        update_shift("NC-E/I", updated_shift)
        print("✓ Updated shift successfully")
    except ValueError as e:
        print(f"✗ Error: {e}")

    # Example 5: Check if shift is active on a specific day
    print("\n=== Checking active days ===")
    shift = get_shift_by_trade("NC-E/I")
    if shift:
        print(f"Is active on Monday: {shift.is_active_on_day('monday')}")
        print(f"Is active on Saturday: {shift.is_active_on_day('saturday')}")
        print(f"Active days: {shift.get_active_days()}")

    # Example 6: Delete a shift (commented out to preserve data)
    # print("\n=== Deleting a shift ===")
    # try:
    #     delete_shift("NC-E/I")
    #     print("✓ Deleted shift successfully")
    # except ValueError as e:
    #     print(f"✗ Error: {e}")


if __name__ == "__main__":
    main()
