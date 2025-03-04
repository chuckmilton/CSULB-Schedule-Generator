import os
import json
from datetime import date
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper import scraper

load_dotenv()

# Load Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Initialize Supabase client with service role key
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

def delete_old_semester_data():
    """
    Deletes course data from the previous semester if it is different from the current semester.
    """
    try:
        # Fetch the most recent semester stored in the database
        response = supabase.table("courses").select("semester").limit(1).execute()
        if response.data:
            latest_stored_semester = response.data[0]["semester"]
            if latest_stored_semester != CURRENT_SEMESTER:
                print(f"Deleting old semester data: {latest_stored_semester}")
                supabase.table("courses").delete().neq("semester", CURRENT_SEMESTER).execute()
                print("Old semester data deleted successfully.")
    except Exception as e:
        print("Error deleting old semester data:", e)

def save_courses_to_supabase(semester, data):
    """
    Inserts or updates courses in Supabase.
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

        # Insert or update data in Supabase
        response = supabase.table("courses").upsert(formatted_data).execute()
        print("Courses successfully stored in Supabase:", response)
    
    except Exception as e:
        print("Error saving to Supabase:", e)

def run_scraper():
    """
    Scrapes the course data and stores it in Supabase.
    """
    all_course_data = []
    try:
        # Delete old semester data if necessary
        delete_old_semester_data()

        for subject_code in scraper.subject_codes:
            data = scraper.courses(CURRENT_SEMESTER, subject_code)
            all_course_data.extend(data)

        # Save the scraped data to Supabase
        save_courses_to_supabase(CURRENT_SEMESTER, all_course_data)
    
    except Exception as e:
        print("Scraper encountered an error:", e)

if __name__ == "__main__":
    run_scraper()
