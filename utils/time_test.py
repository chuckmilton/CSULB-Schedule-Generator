from datetime import datetime

def are_time_windows_in_conflict(days1, time1, days2, time2):
    # If either time window is marked as not available or days are empty, return False.
    if "NA" in time1 or "NA" in time2 or not days1.strip() or not days2.strip():
        return False

    # Remove labels and split days.
    days1_list = days1.replace('Days:', '').strip().split()
    days2_list = days2.replace('Days:', '').strip().split()
    if not set(days1_list) & set(days2_list):
        return False

    try:
        start1_str, end1_str = time1.replace('Times:', '').strip().split('-')
        start2_str, end2_str = time2.replace('Times:', '').strip().split('-')
        start1 = datetime.strptime(start1_str, "%I:%M%p")
        end1 = datetime.strptime(end1_str, "%I:%M%p")
        start2 = datetime.strptime(start2_str, "%I:%M%p")
        end2 = datetime.strptime(end2_str, "%I:%M%p")
    except Exception:
        return False

    # Check for overlap: two windows conflict if one starts before the other ends.
    return start1 < end2 and start2 < end1
