"""Debug and testing script for the Industrial Maintenance Scheduler."""
import sys
from pathlib import Path
from datetime import date

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.models.shift import Shift
from app.models.domain import WorkOrder
from app.services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    update_shift,
    load_shifts,
    save_shifts,
)
from app.services.excel_io import parse_backlog_from_excel, build_schedule_workbook
from app.services.optimizer import optimize_schedule
from app.utils.date_utils import get_next_monday


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_date_utils():
    """Test date utility functions."""
    print_section("Testing Date Utilities")
    today = date.today()
    next_monday = get_next_monday()
    print(f"Today: {today} ({today.strftime('%A')})")
    print(f"Next Monday: {next_monday} ({next_monday.strftime('%A')})")
    print(f"Days until next Monday: {(next_monday - today).days}")


def test_shift_crud():
    """Test shift CRUD operations."""
    print_section("Testing Shift CRUD Operations")

    # Test creating a shift
    print("\n1. Creating test shifts...")
    test_shift1 = Shift(
        trade="Test-Trade-1",
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

    test_shift2 = Shift(
        trade="Test-Trade-2",
        shift_duration_hours=10,
        monday=True,
        friday=True,
        technicians_per_crew=1,
    )

    try:
        add_shift(test_shift1)
        print(f"   ✓ Created shift: {test_shift1.trade}")
    except ValueError as e:
        print(f"   ✗ Error creating shift: {e}")

    try:
        add_shift(test_shift2)
        print(f"   ✓ Created shift: {test_shift2.trade}")
    except ValueError as e:
        print(f"   ✗ Error creating shift: {e}")

    # Test reading shifts
    print("\n2. Reading all shifts...")
    all_shifts = get_all_shifts()
    print(f"   Found {len(all_shifts)} shifts:")
    for shift in all_shifts:
        active_days = shift.get_active_days()
        print(
            f"   - {shift.trade}: {shift.shift_duration_hours}h, "
            f"Days: {', '.join(active_days)}, "
            f"Crew: {shift.technicians_per_crew}"
        )

    # Test getting specific shift
    print("\n3. Getting specific shift...")
    shift = get_shift_by_trade("Test-Trade-1")
    if shift:
        print(f"   ✓ Found shift: {shift.trade}")
        print(f"   Active days: {shift.get_active_days()}")
    else:
        print("   ✗ Shift not found")

    # Test updating shift
    print("\n4. Updating shift...")
    updated = Shift(
        trade="Test-Trade-1",
        shift_duration_hours=12,  # Changed
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=True,  # Added Saturday
        sunday=False,
        technicians_per_crew=3,  # Increased
    )
    try:
        update_shift("Test-Trade-1", updated)
        print("   ✓ Shift updated successfully")
        updated_shift = get_shift_by_trade("Test-Trade-1")
        if updated_shift:
            print(f"   New duration: {updated_shift.shift_duration_hours}h")
            print(f"   New crew size: {updated_shift.technicians_per_crew}")
            print(f"   Active days: {updated_shift.get_active_days()}")
    except ValueError as e:
        print(f"   ✗ Error updating shift: {e}")

    # Test deleting shift
    print("\n5. Deleting test shifts...")
    try:
        delete_shift("Test-Trade-1")
        print("   ✓ Deleted Test-Trade-1")
    except ValueError as e:
        print(f"   ✗ Error deleting shift: {e}")

    try:
        delete_shift("Test-Trade-2")
        print("   ✓ Deleted Test-Trade-2")
    except ValueError as e:
        print(f"   ✗ Error deleting shift: {e}")


def test_work_order_parsing():
    """Test work order parsing from Excel."""
    print_section("Testing Work Order Parsing")

    sample_file = Path("samples/EAMExport.xlsx")
    if not sample_file.exists():
        print(f"   ⚠ Sample file not found: {sample_file}")
        print("   Skipping Excel parsing test")
        return

    try:
        with open(sample_file, "rb") as f:
            xlsx_bytes = f.read()

        work_orders = parse_backlog_from_excel(xlsx_bytes)
        print(f"   ✓ Parsed {len(work_orders)} work orders from Excel")

        if work_orders:
            print("\n   Sample work orders:")
            for wo in work_orders[:5]:  # Show first 5
                print(
                    f"   - WO {wo.id}: {wo.description[:50]}... "
                    f"(Priority: {wo.priority}, Duration: {wo.duration_hours}h, "
                    f"Trade: {wo.trade})"
                )
            if len(work_orders) > 5:
                print(f"   ... and {len(work_orders) - 5} more")

    except Exception as e:
        print(f"   ✗ Error parsing Excel: {e}")
        import traceback

        traceback.print_exc()


def test_optimizer():
    """Test the schedule optimizer."""
    print_section("Testing Schedule Optimizer")

    # Create sample work orders
    work_orders = [
        WorkOrder(
            id="WO-001",
            description="Test work order 1",
            duration_hours=8,
            priority=1,
            due_date=None,
            trade="NC-E/I",
        ),
        WorkOrder(
            id="WO-002",
            description="Test work order 2",
            duration_hours=4,
            priority=2,
            due_date=None,
            trade="NC-E/I",
        ),
        WorkOrder(
            id="WO-003",
            description="Test work order 3",
            duration_hours=6,
            priority=3,
            due_date=None,
            trade="Mechanical",
        ),
    ]

    print(f"   Testing with {len(work_orders)} work orders")
    for wo in work_orders:
        print(f"   - {wo.id}: {wo.trade}, Priority {wo.priority}, {wo.duration_hours}h")

    try:
        start_date = get_next_monday()
        schedule = optimize_schedule(work_orders=work_orders, start_date=start_date)

        print(f"\n   ✓ Schedule generated")
        print(f"   Start date: {schedule.start_date}")
        print(f"   Horizon: {schedule.horizon_days} days")
        print(f"   Assignments: {len(schedule.assignments)}")

        if schedule.assignments:
            print("\n   Assignments:")
            for assignment in schedule.assignments:
                assigned_date = schedule.start_date
                from datetime import timedelta

                assigned_date += timedelta(days=assignment.day_offset)
                print(
                    f"   - {assignment.work_order_id} → {assignment.resource_id} "
                    f"on {assigned_date} (day {assignment.day_offset})"
                )
        else:
            print("   ⚠ No assignments generated (may be due to capacity constraints)")

    except Exception as e:
        print(f"   ✗ Error optimizing schedule: {e}")
        import traceback

        traceback.print_exc()


def test_optimizer_with_excel_backlog():
    """Test optimize_schedule using work orders from parse_backlog_from_excel(samples/EAMExport.xlsx)."""
    print_section("Testing Optimizer with Excel Backlog (samples/EAMExport.xlsx)")

    sample_file = Path("samples/EAMExport.xlsx")
    if not sample_file.exists():
        print(f"   ✗ Sample file not found: {sample_file}")
        return

    try:
        xlsx_bytes = sample_file.read_bytes()
        start_date = get_next_monday()
        work_orders = parse_backlog_from_excel(xlsx_bytes, start_date=start_date)
    except Exception as e:
        print(f"   ✗ Error loading/parsing Excel: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"   Loaded {len(work_orders)} work orders from Excel")
    if not work_orders:
        print("   ⚠ No work orders to optimize")
        return

    for wo in work_orders[:5]:
        print(f"   - {wo.id}: {wo.trade}, priority {wo.priority}, {wo.duration_hours}h")
    if len(work_orders) > 5:
        print(f"   ... and {len(work_orders) - 5} more")

    try:
        schedule = optimize_schedule(work_orders=work_orders, start_date=start_date)
        print(f"\n   ✓ Schedule generated")
        print(f"   Start date: {schedule.start_date}")
        print(f"   Horizon: {schedule.horizon_days} days")
        print(f"   Assignments: {len(schedule.assignments)}")

        if schedule.assignments:
            print("\n   Assignments:")
            from datetime import timedelta
            for assignment in schedule.assignments:
                assigned_date = schedule.start_date + timedelta(days=assignment.day_offset)
                print(
                    f"   - {assignment.work_order_id} → {assignment.resource_id} "
                    f"on {assigned_date} (day {assignment.day_offset})"
                )
        else:
            print("   ⚠ No assignments generated")
    except Exception as e:
        print(f"   ✗ Error optimizing schedule: {e}")
        import traceback
        traceback.print_exc()


def test_excel_output():
    """Test Excel schedule output."""
    print_section("Testing Excel Schedule Output")

    # Create a sample schedule
    from app.models.domain import Assignment, Schedule

    assignments = [
        Assignment(work_order_id="WO-001", day_offset=0, resource_id="NC-E/I"),
        Assignment(work_order_id="WO-002", day_offset=1, resource_id="NC-E/I"),
    ]
    schedule = Schedule(
        assignments=assignments, horizon_days=7, start_date=get_next_monday()
    )

    try:
        wb = build_schedule_workbook(schedule)
        print("   ✓ Schedule workbook created")
        print(f"   Sheets: {wb.sheetnames}")
        if wb.active:
            print(f"   Rows in schedule sheet: {wb.active.max_row}")
            print("   First few rows:")
            for row in list(wb.active.iter_rows(values_only=True))[:5]:
                print(f"     {row}")
    except Exception as e:
        print(f"   ✗ Error creating workbook: {e}")
        import traceback

        traceback.print_exc()


def interactive_menu():
    """Interactive debug menu."""
    while True:
        print("\n" + "=" * 60)
        print("  DEBUG MENU")
        print("=" * 60)
        print("1. Test Date Utilities")
        print("2. Test Shift CRUD Operations")
        print("3. Test Work Order Parsing (Excel)")
        print("4. Test Schedule Optimizer")
        print("5. Test Excel Schedule Output")
        print("6. Run All Tests")
        print("7. View Current Shifts")
        print("0. Exit")
        print("-" * 60)

        choice = input("Select an option: ").strip()

        if choice == "1":
            test_date_utils()
        elif choice == "2":
            test_shift_crud()
        elif choice == "3":
            test_work_order_parsing()
        elif choice == "4":
            test_optimizer()
        elif choice == "5":
            test_excel_output()
        elif choice == "6":
            test_date_utils()
            test_shift_crud()
            test_work_order_parsing()
            test_optimizer()
            test_excel_output()
        elif choice == "7":
            print_section("Current Shifts")
            shifts = get_all_shifts()
            if shifts:
                for shift in shifts:
                    active_days = shift.get_active_days()
                    print(
                        f"Trade: {shift.trade}\n"
                        f"  Duration: {shift.shift_duration_hours}h\n"
                        f"  Active Days: {', '.join(active_days)}\n"
                        f"  Crew Size: {shift.technicians_per_crew}\n"
                    )
            else:
                print("No shifts configured")
        elif choice == "0":
            print("\nExiting debugger. Goodbye!")
            break
        else:
            print("Invalid option. Please try again.")


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("  INDUSTRIAL MAINTENANCE SCHEDULER - DEBUGGER")
    print("=" * 60)

    if len(sys.argv) > 1:
        # Run specific test if argument provided
        test_name = sys.argv[1].lower()
        if test_name == "date":
            test_date_utils()
        elif test_name == "shift":
            test_shift_crud()
        elif test_name == "excel":
            test_work_order_parsing()
        elif test_name == "optimize":
            test_optimizer()
        elif test_name == "optimize-excel":
            test_optimizer_with_excel_backlog()
        elif test_name == "output":
            test_excel_output()
        elif test_name == "all":
            test_date_utils()
            test_shift_crud()
            test_work_order_parsing()
            test_optimizer()
            test_excel_output()
        else:
            print(f"Unknown test: {test_name}")
            print("Available tests: date, shift, excel, optimize, optimize-excel, output, all")
    else:
        # Run interactive menu
        interactive_menu()


if __name__ == "__main__":
    main()
