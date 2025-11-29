#!/usr/bin/env python3
"""
Redis log formatter - converts Redis logs to match application format.
Example input:  "1:M 16 Oct 2025 16:31:02.086 * Ready to accept connections"
Example output: "2025-10-16 16:31:02 | INFO     | redis                | Ready to accept connections tcp"
"""
import sys
import re
from datetime import datetime

# Map Redis log prefixes to log levels
LEVEL_MAP = {
    '*': 'INFO    ',
    '.': 'DEBUG   ',
    '-': 'WARNING ',
    '#': 'WARNING ',
}

# Month name to number
MONTHS = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

# Regex to match Redis log format
# Format: "1:M 16 Oct 2025 16:31:02.086 * Message"
REDIS_LOG_PATTERN = re.compile(
    r'^[0-9]+:[MSCX] '
    r'(?P<day>\d+) (?P<month>\w+) (?P<year>\d+) '
    r'(?P<time>\d+:\d+:\d+)\.\d+ '
    r'(?P<prefix>[*.#-]) '
    r'(?P<message>.+)$'
)

def format_log_line(line):
    """Format a single Redis log line."""
    match = REDIS_LOG_PATTERN.match(line.rstrip())

    if not match:
        # Pass through lines that don't match (startup banner, etc.)
        return line.rstrip()

    day = int(match.group('day'))
    month = MONTHS.get(match.group('month'), '01')
    year = match.group('year')
    time = match.group('time')
    prefix = match.group('prefix')
    message = match.group('message')

    # Get log level
    level = LEVEL_MAP.get(prefix, 'INFO    ')

    # Format date as YYYY-MM-DD
    formatted_date = f"{year}-{month}-{day:02d}"

    # Return formatted log
    return f"{formatted_date} {time} | {level} | {'redis':<20} | {message}"

def main():
    """Read stdin and format each line."""
    try:
        for line in sys.stdin:
            formatted = format_log_line(line)
            print(formatted, flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # In case of error, pass through original line
        print(line.rstrip(), file=sys.stderr, flush=True)

if __name__ == '__main__':
    main()
