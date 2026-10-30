# HW8: print every agent log line for one correlation_id
# usage: python journey.py <correlation_id>
import sys

from common import journey_lines, show_banner

if __name__ == "__main__":
    show_banner(f"journey for {sys.argv[1]}")
    print("\n".join(journey_lines(sys.argv[1])) or "no log lines for that correlation_id")
