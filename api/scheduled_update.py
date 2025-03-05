import os
import json
from datetime import date
import sys
from supabase import create_client, Client

# Ensure the parent directory is in the path so we can import the scraper module.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper import scraper

# Load Supabase credentials from environment variables (set in Lambda configuration)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Initialize Supabase client with the service role key
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def get_current_semester():
    """
    Determines the current semester based on today's date.
    """
    today = date.today()
    year = today.year
    if today >= date(year, 10, 7):
        return f"Spring_{year + 1}"
    elif today >= date(year, 3, 10):
        return f"Fall_{year}"
    else:
        return f"Spring_{year}"

CURRENT_SEMESTER = get_current_semester()

def clear_table():
    """
    Unconditionally deletes all records from the courses table.
    Uses a filter on the id column (assumed to be > 0 for all valid rows)
    to satisfy Supabase's requirement for a WHERE clause.
    """
    try:
        supabase.table("courses").delete().filter("id", "gt", 0).execute()
        print("Courses table cleared.")
    except Exception as e:
        print("Error clearing courses table:", e)

def save_courses_to_supabase(semester, data):
    """
    Inserts or updates courses in Supabase via upsert.
    (Ensure your courses table has a unique constraint on the columns that uniquely identify a course.)
    """
    try:
        formatted_data = [
            {
                "semester": semester,
                "subject_code": course[0],
                "course_name": course[1],
                "units": course[2],
                "section": course[3],
                "section_type": course[4],
                "days": course[5],
                "time": course[6],
                "location": course[7],
                "professor": course[8],
                "availability": course[9],
                "notes": course[10],
            }
            for course in data
        ]
        supabase.table("courses").upsert(formatted_data).execute()
    except Exception as e:
        print("Error saving courses to supabase:", e)

def run_scraper():
    """
    Scrapes the course data and stores it in Supabase.
    Always clears the courses table before adding new data.
    """
    all_course_data = []
    try:
        for subject_code in scraper.subject_codes:
            data = scraper.courses(CURRENT_SEMESTER, subject_code)
            all_course_data.extend(data)
        clear_table()
        save_courses_to_supabase(CURRENT_SEMESTER, all_course_data)
    except Exception as e:
        print("Error running scraper:", e)

if __name__ == "__main__":
    run_scraper()
