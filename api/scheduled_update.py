# api/scheduled_update.py
from flask import Flask
import os
import json
import time
import sys
from datetime import date
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper import scraper

app = Flask(__name__)

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

@app.route("/", methods=["GET"])
def scheduled_update():
    # Loop through all subject codes and scrape course data.
    all_course_data = []
    for subject_code in scraper.subject_codes:
        data = scraper.courses(CURRENT_SEMESTER, subject_code)
        all_course_data.extend(data)
    save_courses_to_cache(CURRENT_SEMESTER, all_course_data)
    return "Course data updated.", 200

if __name__ == "__main__":
    app.run()
