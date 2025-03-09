from flask import Flask, request, render_template_string, redirect, url_for, session, jsonify
import os
import json
import time
from datetime import date, datetime
import itertools
import sys
import math
import requests
# Instead of importing scraper and scheduled_update, we import our Supabase client from our dedicated module.
from supabase_client import supabase
from utils import time_test

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

import hashlib  # For generating the cache key
import redis    # For Redis cache

# Initialize Redis client
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    redis_client.ping()  # Test the connection
    print("Redis connection successful")
except Exception as e:
    print(f"Redis connection failed: {e}")
    # Fallback to a simple in-memory cache if Redis is unavailable
    class SimpleCache:
        def __init__(self):
            self.cache = {}
        
        def get(self, key):
            return self.cache.get(key)
        
        def set(self, key, value, ex=None):
            self.cache[key] = value
            # ex parameter ignored for simplicity
    
    redis_client = SimpleCache()
    print("Using in-memory cache instead")
  
try:
    with open("nameMappings.json", "r") as f:
        name_mappings = json.load(f)
    print("Loaded nameMappings.json successfully")
except Exception as e:
    print("Error loading nameMappings.json:", e)
    name_mappings = {}

def get_current_semester():
    """
    Determine the current semester based on today's date.
    - If today is on or after October 7, the available semester is Spring of next year.
    - If today is on or after March 10 and before October 7, the available semester is Fall of the current year.
    - Otherwise (before March 10), the available semester is Spring of the current year.
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

def fetch_courses_from_supabase():
    """
    Fetch courses for the CURRENT_SEMESTER from Supabase by paginating through results.
    Converts each row to a list in the order:
    [subject_code, course_name, units, section, section_type, days, time, location, professor, availability, notes].
    """
    batch_size = 1000
    offset = 0
    all_courses = []
    while True:
        result = supabase.table("courses")\
                         .select("*", count="exact")\
                         .eq("semester", CURRENT_SEMESTER)\
                         .range(offset, offset + batch_size - 1)\
                         .execute()
        if result.data:
            all_courses.extend(result.data)
            if len(result.data) < batch_size:
                break
            offset += batch_size
        else:
            break
    courses = []
    for course in all_courses:
        courses.append([
            course.get("subject_code", ""),
            course.get("course_name", ""),
            course.get("units", ""),
            course.get("section", ""),
            course.get("section_type", ""),
            course.get("days", ""),
            course.get("time", ""),
            course.get("location", ""),
            course.get("professor", ""),
            course.get("availability", ""),
            course.get("notes", "")
        ])
    return courses

def clean_professor_name(name):
    """Remove extraneous text and periods from initials."""
    import re
    clean_name = re.sub(r'(To be Announced|TBA)', '', name, flags=re.IGNORECASE)
    clean_name = re.sub(r'\b([A-Z])\.', r'\1', clean_name)
    return " ".join(clean_name.split())

def fetch_professor_details(professor_name):
    """
    Query the RateMyProfessors GraphQL endpoint for details of a given professor.
    Uses CSULB’s legacy school ID.
    Caches the result in Redis for 24 hours.
    Only returns the rating and the profile link.
    Uses nameMappings.json to map short names to full names.
    """
    if not professor_name:
        return None
    # Check if the professor name exists in name_mappings; if so, use the mapped full name.
    mapped_name = name_mappings.get(professor_name, professor_name)
    clean_name = clean_professor_name(mapped_name)
    cache_key = "rmp:" + hashlib.md5(clean_name.lower().encode('utf-8')).hexdigest()
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    CSULB_SCHOOL_ID = "U2Nob29sLTE4ODQ2"  # CSULB legacyId
    query = {
        "query": f"""
        query {{
          newSearch {{
            teachers(query: {{ text: "{clean_name}", schoolID: "{CSULB_SCHOOL_ID}" }}) {{
              edges {{
                node {{
                  firstName
                  lastName
                  avgRating
                  legacyId
                }}
              }}
            }}
          }}
        }}
        """
    }
    proxy_url = "https://www.ratemyprofessors.com/graphql"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Basic dGVzdDp0ZXN0",  # Example token; adjust as needed
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.post(proxy_url, json=query, headers=headers)
        data = response.json()
        edges = data.get("data", {}).get("newSearch", {}).get("teachers", {}).get("edges", [])
        if not edges:
            return None
        # Take the first matching professor
        professor = edges[0]["node"]
        details = {
            "rating": professor.get("avgRating", "N/A"),
            "profileLink": f"https://www.ratemyprofessors.com/professor/{professor.get('legacyId')}"
        }
        redis_client.set(cache_key, json.dumps(details), ex=86400)
        return details
    except Exception as e:
        print(f"Error fetching RMP details for {professor_name}: {e}")
        return None

def format_combination_as_calendar(combination):
    """
    Render a weekly calendar for a schedule combination.
    For each course section, fetch RateMyProfessors details and display the rating as a clickable hyperlink.
    """
    week = {
        "Sunday": [],
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": [],
        "Saturday": []
    }
    color_classes = [
        "bg-red-100", "bg-blue-100", "bg-green-100", "bg-yellow-100",
        "bg-purple-100", "bg-pink-100", "bg-indigo-100", "bg-teal-100", "bg-orange-100"
    ]
    color_map = {}
    for sec in combination:
        days_str = sec[5].strip()
        day_list = days_str.split()
        time_str = sec[6]
        try:
            start_str = time_str.split('-')[0]
            start_time = datetime.strptime(start_str, "%I:%M%p")
        except Exception:
            start_time = None
        if sec[0] not in color_map:
            color_map[sec[0]] = color_classes[len(color_map) % len(color_classes)]
        professor = sec[8].strip()
        event = {
            "course": sec[0],
            "section_type": sec[4],
            "units": sec[2],
            "time": sec[6],
            "location": sec[7],
            "professor": professor,
            "start": start_time,
            "color": color_map[sec[0]]
        }
        rating_info = fetch_professor_details(professor)
        if rating_info:
            # Create a hyperlink for the rating
            event["rmp"] = f'<a href="{rating_info.get("profileLink", "#")}" target="_blank">Rating: {rating_info.get("rating", "N/A")} / 5</a>'
        else:
            event["rmp"] = ""
        for day in day_list:
            if day in week:
                week[day].append(event)
    for day in week:
        week[day].sort(key=lambda e: e["start"] if e["start"] is not None else datetime.min)
    html = '<div class="grid grid-cols-1 md:grid-cols-7 gap-4">'
    for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
        html += f'<div><div class="font-bold text-center border-b pb-2">{day}</div>'
        if week[day]:
            for event in week[day]:
                html += f'<div class="{event["color"]} p-2 rounded mb-2 text-xs">'
                html += f'<div class="font-semibold">{event["course"]} ({event["section_type"]})</div>'
                html += f'<div>{event["time"]}</div>'
                html += f'<div>{event["location"]}</div>'
                html += f'<div>{event["professor"]}</div>'
                if event["rmp"]:
                    html += f'<div class="text-xs text-gray-600">{event["rmp"]}</div>'
                html += '</div>'
        else:
            html += '<div class="text-center text-gray-500 text-xs mt-2">—</div>'
        html += '</div>'
    html += '</div>'
    return html

def event_overlaps_exclude_range(event_time, exclude_range):
    try:
        ev_start, ev_end = event_time.split('-')
        ex_start, ex_end = exclude_range.split('-')
        ev_start_dt = datetime.strptime(ev_start.strip(), "%I:%M%p")
        ev_end_dt = datetime.strptime(ev_end.strip(), "%I:%M%p")
        ex_start_dt = datetime.strptime(ex_start.strip(), "%I:%M%p")
        ex_end_dt = datetime.strptime(ex_end.strip(), "%I:%M%p")
        return ev_start_dt < ex_end_dt and ex_start_dt < ev_end_dt
    except Exception:
        return False

def event_overlaps_custom(event_time, custom_start, custom_end):
    try:
        ev_start, ev_end = event_time.split('-')
        ev_start_dt = datetime.strptime(ev_start.strip(), "%I:%M%p")
        ev_end_dt = datetime.strptime(ev_end.strip(), "%I:%M%p")
        cust_start_dt = datetime.strptime(custom_start.strip(), "%H:%M")
        cust_end_dt = datetime.strptime(custom_end.strip(), "%H:%M")
        return ev_start_dt < cust_end_dt and cust_start_dt < ev_end_dt
    except Exception:
        return False

def schedule_signature(combination):
    """
    Compute a signature (a tuple of (day, time) pairs) for a given schedule combination.
    This signature is used to group schedules that have the same days and times.
    """
    sig = []
    for sec in combination:
        days = sec[5].split()
        time_val = sec[6].strip()
        for day in days:
            if time_val.lower() not in ["", "na"]:
                sig.append((day, time_val))
    sig.sort()
    return tuple(sig)

# ------------------------------
# Frontend Templates
# ------------------------------

form_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CSULB Schedule Generator</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://cdn.jsdelivr.net/npm/tom-select/dist/css/tom-select.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/tom-select/dist/js/tom-select.complete.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    body {
      font-family: 'Inter', sans-serif;
      background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f2 100%);
      min-height: 100vh;
    }
    
    .page-container {
      animation: fadeIn 0.8s ease-in-out;
    }
    
    .form-container {
      box-shadow: 0 10px 25px rgba(0,0,0,0.05);
      transition: transform 0.3s ease, box-shadow 0.3s ease;
      border-radius: 12px;
      background: white;
      overflow: hidden;
    }
    
    .form-container:hover {
      transform: translateY(-5px);
      box-shadow: 0 15px 30px rgba(0,0,0,0.1);
    }
    
    .header-section {
      background: linear-gradient(to right, #3b82f6, #60a5fa);
      padding: 1.5rem;
      color: white;
      border-radius: 12px 12px 0 0;
    }
    
    .form-content {
      padding: 2rem;
    }
    
    .form-label {
      color: #334155;
      font-weight: 500;
      margin-bottom: 0.5rem;
      display: block;
    }
    
    .select-container {
      margin-bottom: 1.5rem;
    }
    
    .form-hint {
      color: #64748b;
      font-size: 0.85rem;
      margin-top: 0.5rem;
    }
    
    .small-hint {
      color: #94a3b8;
      font-size: 0.75rem;
      margin-top: 0.25rem;
    }
    
    .custom-slot {
      margin-bottom: 0.75rem;
      animation: fadeInLeft 0.3s ease-in-out;
    }
    
    .delete-slot {
      background-color: #ef4444;
      color: white;
      border: none;
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      cursor: pointer;
      transition: background-color 0.2s ease;
    }
    
    .delete-slot:hover {
      background-color: #dc2626;
    }
    
    .add-slot-button {
      background-color: #e2e8f0;
      transition: all 0.2s ease;
    }
    
    .add-slot-button:hover {
      background-color: #cbd5e1;
    }
    
    .submit-button {
      background: linear-gradient(to right, #2563eb, #3b82f6);
      transition: all 0.3s ease;
      font-weight: 500;
      letter-spacing: 0.025em;
    }
    
    .submit-button:hover {
      background: linear-gradient(to right, #1d4ed8, #2563eb);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    }
    
    /* Tom Select custom styling */
    .ts-control {
      border-radius: 0.375rem !important;
      border-color: #e2e8f0 !important;
      padding: 0.5rem !important;
      box-shadow: none !important;
    }
    
    .ts-control:focus {
      border-color: #60a5fa !important;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2) !important;
    }
    
    .ts-dropdown {
      border-radius: 0.375rem !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
      overflow: hidden;
      position: static;
    }
    
    .ts-dropdown .active {
      background-color: #dbeafe !important;
      color: #1e40af !important;
    }
    
    .ts-dropdown .option:hover {
      background-color: #f1f5f9 !important;
    }
    
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    @keyframes fadeInLeft {
      from {
        opacity: 0;
        transform: translateX(-20px);
      }
      to {
        opacity: 1;
        transform: translateX(0);
      }
    }
    
    .footer {
      text-align: center;
      font-size: 0.75rem;
      color: #94a3b8;
      margin-top: 2rem;
      padding: 0.5rem;
    }
    
    .loading {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(255, 255, 255, 0.8);
      z-index: 9999;
      justify-content: center;
      align-items: center;
      flex-direction: column;
    }
    
    .loading-spinner {
      border: 5px solid #f3f3f3;
      border-top: 5px solid #3b82f6;
      border-radius: 50%;
      width: 50px;
      height: 50px;
      animation: spin 1s linear infinite;
      margin-bottom: 1rem;
    }
    
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <div class="page-container py-10 px-4">
    <div class="max-w-2xl mx-auto">
      <div class="form-container">
        <div class="header-section">
          <h1 class="text-xl md:text-2xl font-bold text-center">CSULB Course Schedule Generator</h1>
          <p class="text-center text-blue-100 mt-2">Semester: <span class="font-semibold">{{ semester.replace('_', ' ') }}</span></p>
          {% if last_updated %}
            <p class="text-center text-blue-100 text-sm mt-1">
              Last updated: {{ last_updated | datetimeformat }}
            </p>
          {% endif %}
        </div>
        
        <div class="form-content">
          <form id="courseForm" action="{{ url_for('generate') }}" method="post">
            <div class="select-container">
              <label for="courses" class="form-label">Select Courses</label>
              <select id="courses" name="courses" multiple class="w-full border border-gray-200 rounded-md">
                {% for code, title in courses %}
                  <option value="{{ code }}" {% if code in selected_courses %}selected{% endif %}>
                    {{ code }} - {{ title }}
                  </option>
                {% endfor %}
              </select>
              <p class="form-hint">
                Type to search. Use Ctrl (or Command on Mac) to select multiple.
              </p>
              <p class="small-hint">
                Note: If you cannot find your course, it may not be available (i.e. no seats available).
              </p>
            </div>
            
            <div class="select-container">
              <label for="exclude_professors" class="form-label">Exclude Professors</label>
              <select id="exclude_professors" name="exclude_professors" multiple class="w-full border border-gray-200 rounded-md">
                {% for prof in professors %}
                  <option value="{{ prof }}" {% if prof in exclude_professors %}selected{% endif %}>{{ prof }}</option>
                {% endfor %}
              </select>
              <p class="small-hint">
                Note: If you cannot find a professor here, it may be because no available courses are taught by them.
              </p>
            </div>
            
            <div class="select-container">
              <label for="exclude_times" class="form-label">Exclude Time Ranges</label>
              <select id="exclude_times" name="exclude_times" multiple class="w-full border border-gray-200 rounded-md">
                {% for time_range in time_ranges %}
                  <option value="{{ time_range }}" {% if time_range in exclude_times %}selected{% endif %}>{{ time_range }}</option>
                {% endfor %}
              </select>
            </div>
            
            <div class="select-container">
              <label for="exclude_days" class="form-label">Exclude Days</label>
              <select id="exclude_days" name="exclude_days" multiple class="w-full border border-gray-200 rounded-md">
                {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
                  <option value="{{ day }}" {% if day in exclude_days %}selected{% endif %}>{{ day }}</option>
                {% endfor %}
              </select>
            </div>
            
            <div class="select-container">
              <label class="form-label">Exclude Specific Day & Time</label>
              <div id="customSlots">
                {% if exclude_custom %}
                  {% for custom in exclude_custom %}
                  <div class="custom-slot flex space-x-2">
                    <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
                      {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
                        <option value="{{ day }}" {% if day == custom[0] %}selected{% endif %}>{{ day }}</option>
                      {% endfor %}
                    </select>
                    <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-200 rounded-md" value="{{ custom[1] }}">
                    <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-200 rounded-md" value="{{ custom[2] }}">
                    <button type="button" class="delete-slot">Delete</button>
                  </div>
                  {% endfor %}
                {% else %}
                  <div class="custom-slot flex space-x-2">
                    <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
                      {% for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] %}
                        <option value="{{ day }}">{{ day }}</option>
                      {% endfor %}
                    </select>
                    <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
                    <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
                    <button type="button" class="delete-slot">Delete</button>
                  </div>
                {% endif %}
              </div>
              <div class="mt-2">
                <button type="button" id="addSlot" class="add-slot-button w-full font-medium py-2 rounded flex items-center justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M10 3a1 1 0 00-1 1v5H4a1 1 0 100 2h5v5a1 1 0 102 0v-5h5a1 1 0 100-2h-5V4a1 1 0 00-1-1z" clip-rule="evenodd" />
                  </svg>
                  Add Another Time Slot
                </button>
              </div>
            </div>
            
            <button type="submit" id="submitBtn" class="submit-button w-full text-white py-3 px-4 rounded-md mt-6 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13a1 1 0 102 0V9.414l1.293 1.293a1 1 0 001.414-1.414z" clip-rule="evenodd" />
              </svg>
              Generate Schedules
            </button>
          </form>
        </div>
      </div>
      
      <div class="footer">
        <p>Course data updates every 24 hours during registration windows.</p>
      </div>
    </div>
  </div>
  
  <div class="loading" id="loadingOverlay">
    <div class="loading-spinner"></div>
    <p class="text-gray-700">Generating your schedules...</p>
  </div>
  
  <script>
    // Initialize Tom Select with custom styling and animations
    let tomSelects = [
      new TomSelect("#courses", { 
        maxItems: null,
        plugins: ['remove_button'],
        render: {
          option: function(data, escape) {
            return `<div class="py-2 px-3 option">${escape(data.text)}</div>`;
          },
          item: function(data, escape) {
            return `<div class="item py-1 px-2">${escape(data.text)}</div>`;
          }
        }
      }),
      new TomSelect("#exclude_professors", { 
        maxItems: null,
        plugins: ['remove_button']
      }),
      new TomSelect("#exclude_times", { 
        maxItems: null,
        plugins: ['remove_button']
      }),
      new TomSelect("#exclude_days", { 
        maxItems: null,
        plugins: ['remove_button']
      })
    ];
    
    // Add slot functionality
    document.getElementById("addSlot").addEventListener("click", function() {
      let container = document.getElementById("customSlots");
      let newSlot = document.createElement("div");
      newSlot.className = "custom-slot flex space-x-2";
      newSlot.innerHTML = `
        <select name="exclude_custom_day[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
          <option value="Sunday">Sunday</option>
          <option value="Monday">Monday</option>
          <option value="Tuesday">Tuesday</option>
          <option value="Wednesday">Wednesday</option>
          <option value="Thursday">Thursday</option>
          <option value="Friday">Friday</option>
          <option value="Saturday">Saturday</option>
        </select>
        <input type="time" name="exclude_custom_start[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
        <input type="time" name="exclude_custom_end[]" class="w-1/3 p-2 border border-gray-200 rounded-md">
        <button type="button" class="delete-slot">Delete</button>
      `;
      container.appendChild(newSlot);
    });
    
    // Delete slot functionality
    document.getElementById("customSlots").addEventListener("click", function(e) {
      if (e.target && e.target.classList.contains("delete-slot")) {
        const slotToRemove = e.target.parentElement;
        slotToRemove.style.opacity = '0';
        slotToRemove.style.transform = 'translateX(-20px)';
        slotToRemove.style.transition = 'all 0.3s ease';
        
        // Remove after animation completes
        setTimeout(() => {
          slotToRemove.remove();
        }, 300);
      }
    });
    
    // Form submission with loading overlay
    document.getElementById("courseForm").addEventListener("submit", function() {
      document.getElementById("loadingOverlay").style.display = "flex";
    });
    
    // Animate form elements on load
    document.addEventListener("DOMContentLoaded", function() {
      const formElements = document.querySelectorAll(".select-container");
      formElements.forEach((element, index) => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(20px)';
        element.style.transition = 'all 0.3s ease';
        
        setTimeout(() => {
          element.style.opacity = '1';
          element.style.transform = 'translateY(0)';
        }, 100 + (index * 100));
      });
    });
  </script>
</body>
</html>
"""

# Updated result_template with cache_key in pagination URLs
result_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CSULB Schedule Results</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    body {
      font-family: 'Inter', sans-serif;
      background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f2 100%);
      min-height: 100vh;
    }
    
    .page-container {
      animation: fadeIn 0.8s ease-in-out;
      padding: 2rem 1rem;
    }
    
    .results-container {
      background: white;
      border-radius: 12px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.05);
      overflow: hidden;
    }
    
    .header-section {
      background: linear-gradient(to right, #3b82f6, #60a5fa);
      padding: 1.5rem;
      color: white;
      border-radius: 12px 12px 0 0;
    }
    
    .back-button {
      background-color: #475569;
      transition: all 0.2s ease;
    }
    
    .back-button:hover {
      background-color: #334155;
      transform: translateY(-1px);
    }
    
    .stats-container {
      background-color: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
      padding: 1rem;
    }
    
    .online-container {
      border: 2px solid #22c55e;
      border-radius: 8px;
      background-color: #f0fdf4;
      transition: all 0.3s ease;
    }
    
    .online-container:hover {
      box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
      transform: translateY(-2px);
    }
    
    .schedule-pattern {
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      transition: all 0.3s ease;
      margin-bottom: 1.5rem;
      overflow: hidden;
    }
    
    .schedule-pattern:hover {
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
      transform: translateY(-2px);
    }
    
    .pattern-header {
      background-color: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
      padding: 1rem;
    }
    
    .pattern-content {
      padding: 1rem;
    }
    
    .day-time-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.5rem;
      margin: 0.5rem 0;
      padding: 0.5rem;
      background-color: #f8fafc;
      border-radius: 6px;
    }
    
    .day-time-item {
      padding: 0.5rem;
      border-radius: 4px;
      background-color: white;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    
    .calendar-container {
      margin-top: 1rem;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      overflow: hidden;
    }
    
    .calendar-header {
      background-color: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
      padding: 0.75rem;
    }
    
    .calendar-content {
      padding: 0.75rem;
    }
    
    /* Calendar item colors with enhanced styling */
    .bg-red-100 { background-color: #fee2e2; border-left: 3px solid #ef4444; }
    .bg-blue-100 { background-color: #dbeafe; border-left: 3px solid #3b82f6; }
    .bg-green-100 { background-color: #dcfce7; border-left: 3px solid #22c55e; }
    .bg-yellow-100 { background-color: #fef9c3; border-left: 3px solid #eab308; }
    .bg-purple-100 { background-color: #f3e8ff; border-left: 3px solid #a855f7; }
    .bg-pink-100 { background-color: #fce7f3; border-left: 3px solid #ec4899; }
    .bg-indigo-100 { background-color: #e0e7ff; border-left: 3px solid #6366f1; }
    .bg-teal-100 { background-color: #ccfbf1; border-left: 3px solid #14b8a6; }
    .bg-orange-100 { background-color: #ffedd5; border-left: 3px solid #f97316; }
    
    .pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 2rem 0;
      padding: 1rem;
      background-color: white;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .page-button {
      background: linear-gradient(to right, #2563eb, #3b82f6);
      transition: all 0.3s ease;
    }
    
    .page-button:hover {
      background: linear-gradient(to right, #1d4ed8, #2563eb);
      transform: translateY(-2px);
      box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
    }
    
    .no-schedules {
      text-align: center;
      padding: 3rem 1rem;
      color: #ef4444;
      border: 2px dashed #fecaca;
      border-radius: 8px;
      background-color: #fef2f2;
      margin: 2rem 0;
    }
    
    /* Animation keyframes */
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    @keyframes fadeInUp {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    /* Calendar view enhancements */
    .calendar-grid {
      border-radius: 8px;
      overflow: hidden;
    }
    
    .day-column {
      border-radius: 0;
    }
    
    .day-header {
      font-weight: 600;
      text-align: center;
      padding: 0.75rem 0;
      background-color: #f8fafc;
      border-bottom: 2px solid #e2e8f0;
    }
    
    .calendar-event {
      margin-bottom: 0.5rem;
      border-radius: 6px;
      padding: 0.75rem;
      transition: all 0.2s ease;
    }
    
    .calendar-event:hover {
      transform: translateY(-2px);
      box-shadow: 0 3px 6px rgba(0,0,0,0.1);
    }
    
    .event-title {
      font-weight: 600;
      margin-bottom: 0.25rem;
    }
    
    .event-detail {
      font-size: 0.75rem;
      margin-bottom: 0.15rem;
    }
    
    .event-professor {
      font-weight: 500;
    }
    
    .event-rating {
      font-size: 0.7rem;
      padding: 0.2rem 0;
    }
    
    .event-rating a {
      color: #4b5563;
      text-decoration: none;
      padding: 2px 4px;
      border-radius: 4px;
      background-color: rgba(255,255,255,0.6);
      transition: all 0.2s ease;
    }
    
    .event-rating a:hover {
      background-color: white;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      color: #1e40af;
    }
    
    .empty-day {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 60px;
      color: #9ca3af;
      font-size: 0.75rem;
    }
  </style>
</head>
<body>
  <div class="page-container">
    <div class="max-w-6xl mx-auto results-container animate__animated animate__fadeIn">
      <div class="header-section">
        <div class="flex justify-between items-center">
          <a href="{{ url_for('index') }}" class="back-button text-white font-bold py-2 px-4 rounded inline-flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" />
            </svg>
            Back to Form
          </a>
          <h1 class="text-xl md:text-2xl font-bold">CSULB Course Schedules</h1>
          <div class="w-28"></div> <!-- Spacer for flex alignment -->
        </div>
      </div>
      
      <div class="p-6">
        {% if online_sections %}
          <div class="online-container p-4 mb-6 animate__animated animate__fadeInUp">
            <h2 class="text-xl font-semibold text-center text-green-700">Online Classes (No Meeting Times)</h2>
            <ul class="mt-3 space-y-2">
              {% for code, sections in online_sections.items() %}
                <li class="p-2 bg-white rounded-md shadow-sm">
                  <strong class="text-green-700">{{ code }}:</strong>
                  {% for sec in sections %}
                    <span class="ml-2">{{ sec[4] }} - {{ sec[8] }}</span>
                    {% if not loop.last %}<br class="ml-6">{% endif %}
                  {% endfor %}
                </li>
              {% endfor %}
            </ul>
          </div>
        {% endif %}
        
        {% if groups %}
          <div class="stats-container rounded-md mb-6 animate__animated animate__fadeInUp animate__delay-1s">
            <h2 class="text-lg font-semibold text-center text-gray-700">Schedule Statistics</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3 text-center">
              <div class="stat-item p-3 bg-white rounded-md shadow-sm">
                <div class="text-sm text-gray-500">Total Valid Combinations</div>
                <div class="text-xl font-bold text-blue-600">{{ total_valid }}</div>
              </div>
              <div class="stat-item p-3 bg-white rounded-md shadow-sm">
                <div class="text-sm text-gray-500">Unique Schedules</div>
                <div class="text-xl font-bold text-blue-600">{{ total_unique }}</div>
              </div>
              <div class="stat-item p-3 bg-white rounded-md shadow-sm">
                <div class="text-sm text-gray-500">Schedule Patterns</div>
                <div class="text-xl font-bold text-blue-600">{{ groups|length }}</div>
              </div>
            </div>
          </div>
          
          {% if total_count > 100 %}
            <div class="info-message p-3 bg-blue-50 border border-blue-200 rounded-md mb-6 text-center animate__animated animate__fadeIn animate__delay-1s">
              <p class="text-blue-700">
                Showing {{ groups|length }} schedule patterns out of {{ total_count }} valid combinations.
                <br>Use filters to narrow down your options.
              </p>
            </div>
          {% endif %}
          
          {% for sig, calendars in groups.items() %}
            <div class="schedule-pattern animate__animated animate__fadeInUp animate__delay-1s" style="animation-delay: {{ loop.index * 0.1 + 0.5 }}s">
              <div class="pattern-header">
                <h3 class="font-bold text-lg flex items-center">
                  <span class="inline-flex items-center justify-center h-6 w-6 rounded-full bg-blue-100 text-blue-800 mr-2 text-sm">
                    {{ loop.index }}
                  </span>
                  Schedule Pattern: {{ calendars|length }} schedule{% if calendars|length > 1 %}s{% endif %}
                </h3>
                
                <div class="day-time-grid mt-2">
                  {% for day, time in sig %}
                    <div class="day-time-item">
                      <span class="font-medium text-gray-700">{{ day }}:</span>
                      <span class="text-gray-600">{{ time }}</span>
                    </div>
                  {% endfor %}
                </div>
              </div>
              
              {% for calendar in calendars %}
                <div class="calendar-container m-4 shadow-sm animate__animated animate__fadeIn" style="animation-delay: {{ loop.index * 0.1 }}s">
                  <div class="calendar-header flex justify-between items-center">
                    <h4 class="font-medium text-gray-700">Schedule {{ loop.index }}</h4>
                    <span class="text-xs text-gray-500">Click course blocks for details</span>
                  </div>
                  <div class="calendar-content">
                    {{ calendar | safe }}
                  </div>
                </div>
              {% endfor %}
            </div>
          {% endfor %}
          
          {% if total_pages > 1 %}
            <div class="pagination animate__animated animate__fadeInUp animate__delay-2s">
              <div class="flex items-center space-x-2">
                {% if current_page > 1 %}
                  <a href="{{ url_for('generate') }}?page=1&key={{ cache_key }}" class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm">First</a>
                  <a href="{{ url_for('generate') }}?page={{ current_page - 1 }}&key={{ cache_key }}" class="page-button text-white font-medium py-2 px-4 rounded inline-flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                    Previous
                  </a>
                {% else %}
                  <button disabled class="px-3 py-1 bg-gray-100 rounded text-gray-400 cursor-not-allowed text-sm">First</button>
                  <button disabled class="bg-gray-300 text-gray-500 font-medium py-2 px-4 rounded inline-flex items-center cursor-not-allowed">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                    Previous
                  </button>
                {% endif %}
              </div>
              
              <div class="text-center">
                <span class="px-3 py-1 bg-blue-100 rounded-full text-blue-800 font-medium">
                  Page {{ current_page }} of {{ total_pages }}
                </span>
              </div>
              
              <div class="flex items-center space-x-2">
                {% if current_page < total_pages %}
                  <a href="{{ url_for('generate') }}?page={{ current_page + 1 }}&key={{ cache_key }}" class="page-button text-white font-medium py-2 px-4 rounded inline-flex items-center">
                    Next
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 ml-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
                    </svg>
                  </a>
                  <a href="{{ url_for('generate') }}?page={{ total_pages }}&key={{ cache_key }}" class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm">Last</a>
                {% else %}
                  <button disabled class="bg-gray-300 text-gray-500 font-medium py-2 px-4 rounded inline-flex items-center cursor-not-allowed">
                    Next
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 ml-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
                    </svg>
                  </button>
                  <button disabled class="px-3 py-1 bg-gray-100 rounded text-gray-400 cursor-not-allowed text-sm">Last</button>
                {% endif %}
              </div>
            </div>
          {% endif %}
          
        {% else %}
          <div class="no-schedules animate__animated animate__fadeIn">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-red-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 class="text-xl font-bold mb-2">No Valid Schedules Found</h2>
            <p class="text-gray-600">
              No valid schedules were found with your current selection criteria. 
              Try removing some filters or selecting different courses.
            </p>
            <a href="{{ url_for('index') }}" class="mt-4 inline-block bg-red-600 hover:bg-red-700 text-white font-medium py-2 px-4 rounded transition-all">
              Return to Form
            </a>
          </div>
        {% endif %}
      </div>
      
      <div class="p-6 text-center border-t border-gray-200">
        <a href="{{ url_for('index') }}" class="back-button text-white font-bold py-2 px-6 rounded inline-flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" />
          </svg>
          Back to Form
        </a>
      </div>
    </div>
  </div>
  
  <script>
    // Add event listeners to make calendar events interactive
    document.addEventListener('DOMContentLoaded', function() {
      // Make calendar events expandable on click
      const calendarEvents = document.querySelectorAll('[class*="bg-"][class*="-100"].p-2.rounded');
      calendarEvents.forEach(event => {
        event.style.cursor = 'pointer';
        event.addEventListener('click', function() {
          this.classList.toggle('shadow-md');
          
          // Animate the expansion
          if (this.style.maxHeight) {
            this.style.maxHeight = null;
          } else {
            this.style.maxHeight = this.scrollHeight + "px";
          }
        });
      });
      
      // Animate schedule patterns on scroll
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('animate__fadeInUp');
            entry.target.style.opacity = 1;
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1 });
      
      document.querySelectorAll('.schedule-pattern').forEach(pattern => {
        pattern.style.opacity = 0;
        observer.observe(pattern);
      });
    });
  </script>
</body>
</html>
"""

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if isinstance(value, str):
        return value
    return datetime.utcfromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S UTC")

@app.route("/", methods=["GET", "POST"])
def index():
    courses = fetch_courses_from_supabase()
    last_updated = None
    distinct_courses = sorted({ (course[0], course[1]) for course in courses })
    selected = session.get("selected_courses", [])
    if selected:
        all_profs = { course[8].strip() for course in courses if course[0] in selected and course[8].strip() }
    else:
        all_profs = { course[8].strip() for course in courses if course[8].strip() }
    time_ranges = [
        "08:00AM-09:00AM", "09:00AM-10:00AM", "10:00AM-11:00AM", "11:00AM-12:00PM",
        "12:00PM-01:00PM", "01:00PM-02:00PM", "02:00PM-03:00PM", "03:00PM-04:00PM",
        "04:00PM-05:00PM", "05:00PM-06:00PM", "06:00PM-07:00PM", "07:00PM-08:00PM",
        "08:00PM-09:00PM", "09:00PM-10:00PM", "10:00PM-11:00PM"
    ]
    exclude_professors = session.get("exclude_professors", [])
    exclude_times = session.get("exclude_times", [])
    exclude_days = session.get("exclude_days", [])
    exclude_custom = session.get("exclude_custom", [])
    return render_template_string(form_template, semester=CURRENT_SEMESTER, courses=distinct_courses,
                                  selected_courses=selected, professors=sorted(all_profs),
                                  time_ranges=time_ranges, exclude_professors=exclude_professors,
                                  exclude_times=exclude_times, exclude_days=exclude_days,
                                  exclude_custom=exclude_custom, last_updated=last_updated)

@app.route("/generate", methods=["GET", "POST"])
def generate():
    print("Session data:", dict(session))
    if request.method == "POST":
        # Process form data
        selected_courses = request.form.getlist("courses")
        session["selected_courses"] = selected_courses
        exclude_professors = request.form.getlist("exclude_professors")
        session["exclude_professors"] = exclude_professors
        exclude_times = request.form.getlist("exclude_times")
        session["exclude_times"] = exclude_times
        exclude_days = request.form.getlist("exclude_days")
        session["exclude_days"] = exclude_days
        custom_days = request.form.getlist("exclude_custom_day[]")
        custom_starts = request.form.getlist("exclude_custom_start[]")
        custom_ends = request.form.getlist("exclude_custom_end[]")
        exclude_custom = []
        for day, start, end in zip(custom_days, custom_starts, custom_ends):
            if day and start and end:
                exclude_custom.append((day.strip(), start.strip(), end.strip()))
        session["exclude_custom"] = exclude_custom
        
        # Store the cache key in the session
        cache_data = {
            "selected_courses": selected_courses,
            "exclude_professors": exclude_professors,
            "exclude_times": exclude_times,
            "exclude_days": exclude_days,
            "exclude_custom": exclude_custom,
        }
        cache_key = "schedule:" + hashlib.md5(json.dumps(cache_data, sort_keys=True).encode('utf-8')).hexdigest()
        session["cache_key"] = cache_key
    else:
        # For GET requests (pagination), try to get the key from URL first, then session
        url_cache_key = request.args.get("key")
        session_cache_key = session.get("cache_key")
        
        cache_key = url_cache_key or session_cache_key
        
        if not cache_key:
            print("No cache key found in URL or session for pagination!")
            return redirect(url_for('index'))
        
        # Store it back in session in case it came from URL
        if url_cache_key:
            session["cache_key"] = url_cache_key
        
        # Retrieve filter settings from session
        selected_courses = session.get("selected_courses", [])
        exclude_professors = session.get("exclude_professors", [])
        exclude_times = session.get("exclude_times", [])
        exclude_days = session.get("exclude_days", [])
        exclude_custom = session.get("exclude_custom", [])

    # Fetch course data
    courses = fetch_courses_from_supabase()
    if not courses:
        return "No course data available."
    
    # Check Redis for cached data using the cache_key
    # Update the Redis cached data retrieval section:

    # Check Redis for cached data using the cache_key
    cached = redis_client.get(cache_key)
    if cached:
        try:
            print(f"Cache hit for key: {cache_key}")
            # Redis returns binary data - decode it first
            if isinstance(cached, bytes):
                cached = cached.decode('utf-8')
            cached_data = json.loads(cached)
            
            # Convert the group_items correctly from serializable format
            group_items_serializable = cached_data["group_items"]
            group_items = []
            for sig_list, calendars in group_items_serializable:
                tuple_sig = tuple(tuple(item) if isinstance(item, list) else item for item in sig_list)
                group_items.append((tuple_sig, calendars))
            
            total_valid = cached_data["total_valid"]
            total_unique = cached_data["total_unique"]
            online_sections = cached_data.get("online_sections", {})
            
            print(f"Retrieved from cache: {len(group_items)} groups")
        except Exception as e:
            print(f"Error processing cached data: {e}")
            # Fall through to regenerate the data
            cached = None
            
    if not cached:
        print(f"Cache miss for key: {cache_key}")
        # Process course data to identify online sections and in-person courses
        online_sections = {}
        inperson_courses_by_code = {}
        for course in courses:
            code = course[0]
            time_field = course[6].strip().lower()
            comment_field = course[10].strip().lower()
            if code in selected_courses:
                if course[9] == "Seats Available" and (time_field in ["", "na"]) and (
                    "online-no meet times" in comment_field or 
                    "no-meet times" in comment_field or 
                    "online no meet times" in comment_field):
                    if not course[4].strip():
                        course[4] = "Online"
                    online_sections.setdefault(code, []).append(course)
                elif course[9] == "Seats Available" and time_field not in ["", "na"]:
                    inperson_courses_by_code.setdefault(code, {}).setdefault(course[4], []).append(course)
        
        # Check if all selected courses have available sections
        for code in selected_courses:
            if code not in inperson_courses_by_code and code not in online_sections:
                return render_template_string(result_template,
                    groups={},
                    total_count=0,
                    total_valid=0,
                    total_unique=0,
                    online_sections=online_sections,
                    current_page=1,
                    total_pages=1)
        
        # Identify required section types for each course
        required_types_by_code = {}
        for code in inperson_courses_by_code:
            for sec in sum(inperson_courses_by_code.get(code, {}).values(), []):
                required_types_by_code.setdefault(code, set()).add(sec[4])
        
        # Filter to only include courses with available sections
        courses_for_combinations = {code: secs for code, secs in inperson_courses_by_code.items() if secs}
        
        # Check if there are any in-person courses
        if not courses_for_combinations:
            return render_template_string(result_template, 
                                         groups={}, 
                                         total_count=0,
                                         total_valid=0,
                                         total_unique=0, 
                                         online_sections=online_sections,
                                         current_page=1, 
                                         total_pages=1)
        
        # Check if all required section types are available
        for code in courses_for_combinations:
            required = required_types_by_code.get(code, set())
            available = set(courses_for_combinations.get(code, {}).keys())
            if not required.issubset(available):
                return render_template_string(result_template,
                    groups={},
                    total_count=0,
                    total_valid=0,
                    total_unique=0,
                    online_sections=online_sections,
                    current_page=1,
                    total_pages=1)
        
        # Generate combinations of sections for each course
        course_combinations = {}
        for code in courses_for_combinations:
            types = sorted(required_types_by_code.get(code, []))
            sections_lists = [courses_for_combinations[code][t] for t in types]
            course_combinations[code] = list(itertools.product(*sections_lists))
        
        # Generate all possible schedule combinations
        overall_combinations = list(itertools.product(*[course_combinations[code] for code in courses_for_combinations]))
        
        # Find valid combinations (no time conflicts)
        valid_combinations = []
        for overall in overall_combinations:
            schedule_sections = []
            for sections_tuple in overall:
                schedule_sections.extend(sections_tuple)
            conflict = False
            n = len(schedule_sections)
            for i in range(n):
                for j in range(i+1, n):
                    sec1 = schedule_sections[i]
                    sec2 = schedule_sections[j]
                    sec1_time = sec1[6].strip().lower()
                    sec2_time = sec2[6].strip().lower()
                    if ("na" in sec1_time or sec1_time == "" or
                        "na" in sec2_time or sec2_time == ""):
                        continue
                    if time_test.are_time_windows_in_conflict(sec1[5], sec1[6], sec2[5], sec2[6]):
                        conflict = True
                        break
                if conflict:
                    break
            if not conflict:
                valid_combinations.append(schedule_sections)
        
        # Apply user filters
        filtered_combinations = []
        for comb in valid_combinations:
            skip = False
            for sec in comb:
                prof = sec[8].strip()
                if prof in exclude_professors:
                    skip = True
                    break
                for ex_time in exclude_times:
                    if event_overlaps_exclude_range(sec[6], ex_time):
                        skip = True
                        break
                if skip:
                    break
                event_days = sec[5].split()
                if any(day in event_days for day in exclude_days):
                    skip = True
                    break
                for custom in exclude_custom:
                    custom_day, cust_start, cust_end = custom
                    if custom_day in sec[5].split() and event_overlaps_custom(sec[6], cust_start, cust_end):
                        skip = True
                        break
                if skip:
                    break
            if not skip:
                filtered_combinations.append(comb)
        
        # Track total number of valid combinations
        total_valid = len(filtered_combinations)
        
        # Deduplicate combinations
        unique_combinations = []
        seen = set()
        for comb in filtered_combinations:
            # Create a canonical representation
            rep = tuple(sorted((sec[0], sec[3], sec[5].strip(), sec[6].strip()) for sec in comb))
            if rep not in seen:
                seen.add(rep)
                unique_combinations.append(comb)
        
        total_unique = len(unique_combinations)
        
        # Group schedules by their days and times
        groups = {}
        for comb in unique_combinations:
            sig = schedule_signature(comb)
            cal = format_combination_as_calendar(comb)
            groups.setdefault(sig, []).append(cal)
        
        # Deduplicate calendars within each group
        for sig in groups:
            groups[sig] = list(dict.fromkeys(groups[sig]))
        
        # Sort groups by signature
        group_items = sorted(groups.items(), key=lambda x: x[0])
        
        # Convert to serializable format for caching
        group_items_serializable = [(list(sig), calendars) for sig, calendars in group_items]
        cache_value = {
            "group_items": group_items_serializable,
            "total_valid": total_valid,
            "total_unique": total_unique,
            "online_sections": online_sections
        }
        redis_client.set(cache_key, json.dumps(cache_value), ex=3600)

    # Pagination
    page_size = 20
    page = int(request.args.get("page", 1))
    total_pages = math.ceil(len(group_items) / page_size) if group_items else 1
    
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    
    # Create a dictionary from the sliced group_items
    paginated_groups = dict(group_items[start_index:end_index])
    
    print(f"Rendering page {page} of {total_pages} with {len(paginated_groups)} groups")
    
    return render_template_string(result_template, groups=paginated_groups, total_count=total_unique,
                                 total_valid=total_valid, total_unique=total_unique,
                                 online_sections=online_sections, current_page=page, 
                                 total_pages=total_pages, cache_key=cache_key)

from http.server import BaseHTTPRequestHandler
from io import BytesIO
from urllib.parse import urlparse

class WSGIAdapter(BaseHTTPRequestHandler):
    def do_GET(self):
        self.wsgi_handle()
    def do_POST(self):
        self.wsgi_handle()
    def wsgi_handle(self):
        environ = {}
        environ['REQUEST_METHOD'] = self.command
        parsed_url = urlparse(self.path)
        environ['PATH_INFO'] = parsed_url.path
        environ['QUERY_STRING'] = parsed_url.query
        environ['SERVER_NAME'] = self.server.server_address[0]
        environ['SERVER_PORT'] = str(self.server.server_address[1])
        environ['wsgi.input'] = self.rfile
        environ['wsgi.errors'] = sys.stderr
        environ['wsgi.version'] = (1, 0)
        environ['wsgi.multithread'] = False
        environ['wsgi.multiprocess'] = False
        environ['wsgi.run_once'] = False
        environ['wsgi.url_scheme'] = 'http'
        length = self.headers.get('Content-Length')
        if length:
            environ['CONTENT_LENGTH'] = length
        environ['CONTENT_TYPE'] = self.headers.get('Content-Type', '')
        response_status = None
        response_headers = None
        def start_response(status, headers, exc_info=None):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = headers
            return lambda x: None
        result = app(environ, start_response)
        response_body = b"".join(result)
        self.send_response(int(response_status.split()[0]))
        for header, value in response_headers:
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

handler = WSGIAdapter

if __name__ == "__main__":
    app.run(debug=True)
