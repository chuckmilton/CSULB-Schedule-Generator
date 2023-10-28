from datetime import datetime


def are_time_windows_in_conflict(days1, time1, days2, time2):
    if time1 == "Times: NA" or time2 == "Times: NA":
        return False
    if days1 == "Days: " or days2 == "Days: ":
        return False
    # Split days by spaces and strip extra whitespace
    days1 = days1.replace('Days:', '').strip().split()
    days2 = days2.replace('Days:', '').strip().split()

    # Strip extra whitespace and check for common days
    days1 = [day.strip() for day in days1]
    days2 = [day.strip() for day in days2]
    common_days = set(days1) & set(days2)

    if common_days:
        # Extract start and end times from the time windows
        start1_str, end1_str = time1.replace('Times:', '').strip().split('-')
        start2_str, end2_str = time2.replace('Times:', '').strip().split('-')

        # Parse start and end times into datetime objects
        start1 = datetime.strptime(start1_str, "%I:%M%p")
        end1 = datetime.strptime(end1_str, "%I:%M%p")
        start2 = datetime.strptime(start2_str, "%I:%M%p")
        end2 = datetime.strptime(end2_str, "%I:%M%p")

        # Check for time conflicts
        if start2 <= start1 <= end2 or start2 <= end1 <= end2:
            return True
    else:
        # If there are no common days, no time conflict
        return False

    # If neither time conflict nor day conflict, return False
    return False
