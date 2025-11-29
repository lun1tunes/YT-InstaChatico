#!/bin/sh
# Redis log formatter - converts Redis logs to match application format
# Example: "1:M 16 Oct 2025 16:31:02.086 * Ready to accept connections"
# Becomes: "2025-10-16 16:31:02 | INFO     | redis                | Ready to accept connections tcp"

exec redis-server "$@" 2>&1 | awk '
BEGIN {
    # Map Redis log prefixes to log levels
    level_map["*"] = "INFO    "
    level_map["."] = "DEBUG   "
    level_map["-"] = "WARNING "
    level_map["#"] = "WARNING "
}
{
    # Parse Redis log format: "1:M 16 Oct 2025 16:31:02.086 * Message"
    if (match($0, /^[0-9]+:[MSCX] ([0-9]+ [A-Z][a-z]+ [0-9]+) ([0-9]+:[0-9]+:[0-9]+)\.[0-9]+ ([*.#-]) (.+)$/, arr)) {
        # Extract parts
        date = arr[1]
        time = arr[2]
        prefix = arr[3]
        message = arr[4]

        # Convert date format: "16 Oct 2025" -> "2025-10-16"
        split(date, date_parts, " ")
        day = date_parts[1]
        month = date_parts[2]
        year = date_parts[3]

        # Month name to number
        months["Jan"] = "01"; months["Feb"] = "02"; months["Mar"] = "03"
        months["Apr"] = "04"; months["May"] = "05"; months["Jun"] = "06"
        months["Jul"] = "07"; months["Aug"] = "08"; months["Sep"] = "09"
        months["Oct"] = "10"; months["Nov"] = "11"; months["Dec"] = "12"

        formatted_date = sprintf("%s-%s-%02d", year, months[month], day)

        # Get log level
        level = level_map[prefix]
        if (!level) level = "INFO    "

        # Print formatted log
        printf "%s %s | %s | %-20s | %s\n", formatted_date, time, level, "redis", message
    } else {
        # Pass through lines that don't match (startup banner, etc.)
        print $0
    }
}
'
