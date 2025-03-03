import os
import json
from datetime import date
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper import scraper

def get_current_semester():
    today = date.today()
    year = today.year
    if today >= date(year, 10, 7):
        return f"Spring_{year + 1}"
    elif today >= date(year, 3, 10):
        return f"Fall_{year}"
    else:
        return f"Spring_{year}"

CURRENT_SEMESTER = get_current_semester()

def save_courses_to_cache(semester, data):
    cache_file = os.path.join("/tmp", f"cache_{semester}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

# Run scraping and save data
def run_scraper():
    all_course_data = []
    try:
        for subject_code in scraper.subject_codes:
            data = scraper.courses(CURRENT_SEMESTER, subject_code)
            all_course_data.extend(data)
        save_courses_to_cache(CURRENT_SEMESTER, all_course_data)
    except Exception:
        pass

if __name__ == "__main__":
    run_scraper()
