import re
from datetime import datetime, date, timedelta

LOG_FILE = "/volume1/scripts/SEF/sef_subscription.log"

def get_sef_subscription_status():
    """
    Reads the last successful subscription line from the log.
    Returns:
        {
            "last_success": datetime or None,
            "active_tomorrow": bool
        }
    """
    try:
        last_success = None
        success_pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - SUCCESS: SEF subscription OK"
        )

        with open(LOG_FILE, "r") as f:
            for line in f:
                match = success_pattern.match(line.strip())
                if match:
                    last_success = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")

        if not last_success:
            return {"last_success": None, "active_tomorrow": False}

        today = date.today()
        tomorrow = today + timedelta(days=1)

        # If last successful subscription was today, it covers tomorrow
        active_tomorrow = last_success.date() >= today

        return {"last_success": last_success, "active_tomorrow": active_tomorrow}

    except FileNotFoundError:
        return {"last_success": None, "active_tomorrow": False}
