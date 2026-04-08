"""Debug and testing script for the Industrial Maintenance Scheduler."""

from app.utils.date_utils import get_next_monday
from app.services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    update_shift,
)
from app.services.optimizer import optimize_schedule
from app.services.excel_io import fetch_backlog
from app.services.cloud_backlog_client import CloudBacklogClient, CloudBacklogError
from app.models.domain import Assignment, Schedule, WorkOrder
from app.models.shift import Shift
from app.config import get_backlog_integration_settings, load_app_env
import csv
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

# Add the project root to the path before importing app.*
sys.path.insert(0, str(Path(__file__).parent))


load_app_env()

_DEBUG_BACKLOG_PREVIEW_CHARS = 4096


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def debug_fetch_cloud_backlog():
    """Fetch backlog JSON from the configured cloud REST endpoint (.env)."""
    print_section("Cloud backlog (REST)")
    settings = get_backlog_integration_settings()
    print(
        f"URL: {settings.rest_url or '(not set)'}\n"
        f"tenant_id={settings.tenant_id!r} "
        f"organization={settings.organization!r} "
        f"grid_id={settings.grid_id!r} "
        f"dataspy_id={settings.dataspy_id!r}"
    )
    try:
        df = CloudBacklogClient(settings=settings).fetch_backlog()
    except CloudBacklogError as e:
        print(f"Error: {e}")
        if e.response is not None:
            r = e.response
            snippet = (r.text or "")[:500]
            print(f"HTTP {r.status_code} — body (truncated): {snippet}")
        return
    print(f"Response: DataFrame {df.shape[0]} rows × {df.shape[1]} columns")
    text = df.to_string(max_rows=50, max_cols=20)
    if len(text) > _DEBUG_BACKLOG_PREVIEW_CHARS:
        text = text[:_DEBUG_BACKLOG_PREVIEW_CHARS] + "\n... [truncated]"
    print(text)


def debug_patch_cloud_work_order():
    """PATCH one work order (wo_id, ``SCHEDULE_ENDPOINT`` in .env)."""
    print_section("Cloud backlog PATCH (work order)")
    settings = get_backlog_integration_settings()
    print(
        f"rest_url: {settings.rest_url or '(not set)'}\n"
        f"SCHEDULE_ENDPOINT: {settings.schedule_endpoint or '(not set)'}\n"
        f"tenant_id={settings.tenant_id!r} "
        f"organization={settings.organization!r} "
        f"grid_id={settings.grid_id!r} "
        f"dataspy_id={settings.dataspy_id!r}"
    )
    wo_id = 1452505

    start = get_next_monday()
    schedule = Schedule(
        assignments=[
            Assignment(
                work_order_id=str(wo_id),
                day_offset=4,
                resource_id="debug",
            ),
        ],
        horizon_days=7,
        start_date=start,
    )
    wo = WorkOrder(
        id=wo_id,
        description="debug patch",
        duration_hours=1.0,
        priority=1,
        schedule_date=start,
        trade="ELEC",
    )
    try:
        result = CloudBacklogClient(settings=settings).patch_eam_schedule_data(
            wo, schedule
        )
    except CloudBacklogError as e:
        print(f"Error: {e}")
        if e.response is not None:
            r = e.response
            snippet = (r.text or "")[:500]
            print(f"HTTP {r.status_code} — body (truncated): {snippet}")
        return
    text = json.dumps(result, indent=2, default=str)
    if len(text) > _DEBUG_BACKLOG_PREVIEW_CHARS:
        text = text[:_DEBUG_BACKLOG_PREVIEW_CHARS] + "\n... [truncated]"
    print(text)


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
    """Test work order fetching from EAM API."""
    print_section("Testing Work Order Parsing")

    try:
        work_orders = fetch_backlog()
        print(f"   ✓ Fetched {len(work_orders)} work orders from API")

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


def test_optimizer_with_excel_backlog():
    """Test optimize_schedule using work orders from EAM API."""
    output_csv = os.environ.get("OUTPUT_SCHEDULE_CSV", "").strip()
    print_section("Testing Optimizer with API Backlog")

    try:
        start_date = get_next_monday()
        work_orders = fetch_backlog(start_date=start_date)
    except Exception as e:
        print(f"   ✗ Error fetching backlog: {e}")
        import traceback

        traceback.print_exc()
        return

    print(f"   Loaded {len(work_orders)} work orders from API")
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

        wo_duration = {wo.id: wo.duration_hours for wo in work_orders}
        wo_description = {wo.id: wo.description for wo in work_orders}
        wo_priority = {wo.id: wo.priority for wo in work_orders}
        if schedule.assignments:
            print("\n   Assignments:")
            for assignment in schedule.assignments:
                assigned_date = schedule.start_date + timedelta(
                    days=assignment.day_offset
                )
                duration_h = wo_duration.get(assignment.work_order_id, 0)
                print(
                    f"   - {assignment.work_order_id} → {assignment.resource_id} "
                    f"on {assigned_date} ({duration_h}h)"
                )
        else:
            print("   ⚠ No assignments generated")

        if output_csv:
            csv_path = Path(output_csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "work_order_id",
                        "resource_id",
                        "scheduled_date",
                        "duration",
                        "description",
                        "priority",
                    ]
                )
                for a in schedule.assignments:
                    scheduled_date = schedule.start_date + timedelta(days=a.day_offset)
                    duration_h = wo_duration.get(a.work_order_id, 0)
                    description = wo_description.get(a.work_order_id, "")
                    priority = wo_priority.get(a.work_order_id, 0)
                    writer.writerow(
                        [
                            a.work_order_id,
                            a.resource_id,
                            scheduled_date,
                            duration_h,
                            description,
                            priority,
                        ]
                    )
            print(f"\n   ✓ Schedule written to {csv_path}")
    except Exception as e:
        print(f"   ✗ Error optimizing schedule: {e}")
        import traceback

        traceback.print_exc()


def interactive_menu():
    """Interactive debug menu."""
    while True:
        print("\n" + "=" * 60)
        print("  DEBUG MENU")
        print("=" * 60)
        print("1. Test Shift CRUD Operations")
        print("2. Test Work Order Parsing (Excel)")
        print("3. Run All Tests")
        print("4. View Current Shifts")
        print("0. Exit")
        print("-" * 60)

        choice = input("Select an option: ").strip()

        if choice == "1":
            test_shift_crud()
        elif choice == "2":
            test_work_order_parsing()
        elif choice == "3":
            test_shift_crud()
            test_work_order_parsing()
        elif choice == "4":
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
        if test_name == "shift":
            test_shift_crud()
        elif test_name == "excel":
            test_work_order_parsing()
        elif test_name == "optimize-excel":
            test_optimizer_with_excel_backlog()
        elif test_name == "all":
            test_shift_crud()
            test_work_order_parsing()
        elif test_name == "cloud-backlog":
            debug_fetch_cloud_backlog()
        elif test_name == "cloud-backlog-patch":
            debug_patch_cloud_work_order()
        else:
            print(f"Unknown test: {test_name}")
            print(
                "Available tests: shift, excel, optimize-excel, cloud-backlog, "
                "cloud-backlog-patch, all"
            )
    else:
        # Run interactive menu
        interactive_menu()


if __name__ == "__main__":
    main()
