#!/usr/bin/env python3
"""Simple script to enable/disable logging for modules."""

import sys

# Add src to path
sys.path.insert(0, 'src')

from is74_integration.simple_logger import LOGGERS, enable_logger, disable_logger, enable_all, disable_all


def show_status():
    """Show current logging status."""
    print("=== Logging Status ===\n")
    for name, logger in sorted(LOGGERS.items()):
        status = "✓ ENABLED" if logger.enabled else "✗ DISABLED"
        print(f"  {name:20s} {status}")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python toggle_logs.py show              - Show current status")
        print("  python toggle_logs.py enable <module>   - Enable logging for module")
        print("  python toggle_logs.py disable <module>  - Disable logging for module")
        print("  python toggle_logs.py enable-all        - Enable all logging")
        print("  python toggle_logs.py disable-all       - Disable all logging")
        print("\nAvailable modules:")
        for name in sorted(LOGGERS.keys()):
            print(f"  - {name}")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'show':
        show_status()
    elif command == 'enable' and len(sys.argv) >= 3:
        module = sys.argv[2]
        if module in LOGGERS:
            enable_logger(module)
            print(f"✓ Enabled logging for: {module}")
            print("\nNote: Restart the API for changes to take effect")
        else:
            print(f"✗ Unknown module: {module}")
            print(f"Available modules: {', '.join(sorted(LOGGERS.keys()))}")
    elif command == 'disable' and len(sys.argv) >= 3:
        module = sys.argv[2]
        if module in LOGGERS:
            disable_logger(module)
            print(f"✓ Disabled logging for: {module}")
            print("\nNote: Restart the API for changes to take effect")
        else:
            print(f"✗ Unknown module: {module}")
    elif command == 'enable-all':
        enable_all()
        print("✓ Enabled logging for all modules")
        print("\nNote: Restart the API for changes to take effect")
    elif command == 'disable-all':
        disable_all()
        print("✓ Disabled logging for all modules")
        print("\nNote: Restart the API for changes to take effect")
    else:
        print("✗ Invalid command")
        print("Run without arguments to see usage")


if __name__ == "__main__":
    main()
